# Analyse de la sécurité des threads PARI

> Ce document décrit les problèmes de sécurité des threads SageMath/PARI rencontrés
> lors de l'implémentation du coordinateur de signature parallèle MuSig2-H,
> incluant la reproduction du problème, l'analyse des causes profondes et les solutions.

---

## 1. Contexte du problème

Dans le protocole MuSig2-H, trois phases peuvent être exécutées en parallèle (chaque signataire est indépendant, sans dépendance de données) :

```
① KeyGen × n        ← parallélisable : chaque signataire génère sa clé indépendamment
③ PreSign × n       ← parallélisable : chaque signataire génère son nonce indépendamment
⑤ Sign × n          ← parallélisable : chaque signataire calcule sa signature partielle indépendamment
```

Nous avons initialement utilisé le `ThreadPoolExecutor` de Python pour soumettre ces étapes à un pool de threads pour une exécution concurrente.

---

## 2. Symptômes de l'erreur

Lors de l'exécution des tests, les 9 cas de test **plantent à 100%**, tous avec la même erreur :

```
cysignals.signals.SignalError: Segmentation fault
```

Le point de plantage est systématiquement situé dans `sage/libs/pari/convert_gmp.pyx:52`.

---

## 3. Chaîne d'appels menant au plantage

Le chemin complet du code utilisateur jusqu'au point de plantage :

```
Signer.__init__()
  → musig2h.keygen()
    → lhf.F_key(sk)                         # F(sk, 0) = sk·G
      → curve.scalar_mult(sk, G)            # Multiplication scalaire SageMath
        → Integer(k) * P                    # Sage appelle la multiplication de point EC
          → ell_point._acted_upon_()
            → pari.ellmul(E, self, k)       # Délégué à la bibliothèque PARI
              → cypari2.objtogen()          # Objet Sage → type GEN PARI
                → convert_gmp.new_gen_from_integer()
                  💥 Segmentation fault     # Plantage lors de la conversion GMP → PARI
```

---

## 4. Cause profonde : la pile globale PARI n'est pas thread-safe

### 4.1 Modèle mémoire de PARI

PARI/GP est une bibliothèque de calcul en théorie des nombres. SageMath l'appelle via le wrapper `cypari2`. En interne, PARI utilise une **pile globale (PARI stack)** pour gérer l'allocation mémoire de tous les objets temporaires :

```
Pile globale PARI (unique par processus, partagée par tous les threads)
┌──────────────────────────────────────────────┐
│  Pointeur de pile avma (pointe vers le sommet)│
│  ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄ │
│  Objet temporaire A (alloué par le thread 1)  │
│  Objet temporaire B (alloué par le thread 2)  │  ← conflit !
│  Objet temporaire C (alloué par le thread 1)  │
└──────────────────────────────────────────────┘
```

Cette pile globale **n'est protégée par aucun verrou**. Lorsque deux threads exécutent simultanément des opérations PARI :

1. Le thread 1 appelle `new_gen_from_integer()`, déplace le pointeur de pile et commence à écrire un grand entier
2. Le thread 2 appelle **simultanément** `new_gen_from_integer()`, déplace aussi le même pointeur et commence à écrire
3. Les deux écritures se chevauchent, le pointeur de pile est corrompu
4. Les lectures suivantes accèdent à des données partiellement écrites et invalides → **segmentation fault**

### 4.2 Pourquoi le GIL de Python ne protège pas

Le GIL (Global Interpreter Lock) de Python ne protège que l'exécution du bytecode Python. Or, `cypari2` **libère le GIL** avant d'appeler les fonctions C de PARI (c'est la pratique standard pour les extensions C, afin de ne pas bloquer les autres threads Python) :

```
Thread 1: [détient le GIL] → entre dans cypari2 → [libère le GIL] → code C PARI → opère sur la pile globale
Thread 2: [obtient le GIL]  → entre dans cypari2 → [libère le GIL] → code C PARI → opère sur la même pile
                                                                     💥 conflit d'écriture concurrente
```

Une fois le GIL libéré, le code C des deux threads s'exécute véritablement en parallèle sur les processeurs multicœurs, et l'accès concurrent à la pile globale PARI n'a aucun mécanisme de synchronisation.

### 4.3 Pourquoi le plantage est systématique et non intermittent

La multiplication scalaire sur courbe elliptique (`ellmul`) est une opération intensive en calcul, impliquant de nombreuses allocations sur la pile PARI. Même avec seulement 2 threads et 1 appel, la fenêtre d'exécution est suffisamment longue pour qu'une écriture concurrente se produise presque certainement. C'est pourquoi les 9 tests provoquent tous un segfault — il ne s'agit pas d'une condition de course probabiliste, mais d'un conflit de concurrence déterministe.

---

## 5. Pourquoi ProcessPoolExecutor n'est pas viable non plus

La solution multiprocessus permet d'éviter le problème de mémoire partagée (chaque processus possède sa propre pile PARI), mais se heurte à un autre obstacle :

**Les objets SageMath ne peuvent pas être transmis entre processus.**

`ProcessPoolExecutor` repose sur `pickle` pour sérialiser les paramètres et valeurs de retour entre processus. Les objets de points de courbe elliptique de SageMath contiennent des références complexes aux structures algébriques internes (`EllipticCurve_finite_field`, `FiniteField`), qui :

- Ont un coût de sérialisation/désérialisation extrêmement élevé (nécessitent la reconstruction de toute la structure algébrique)
- Contiennent des états internes partiellement incompatibles avec pickle (comme les objets PARI mis en cache)

Même si la sérialisation réussissait, le coût de transfert dépasserait probablement le calcul lui-même (un point de courbe sérialisé peut faire plusieurs centaines d'octets, alors que la multiplication scalaire ne prend que quelques millisecondes).

---

## 6. Solutions

### 6.1 Solution actuelle : exécution séquentielle + annotations structurelles

Nous conservons une exécution séquentielle, tout en annotant clairement dans le code les étapes parallélisables au niveau du protocole :

```python
# ① KeyGen × n ← parallélisable : chaque signataire génère sa clé indépendamment
signers = [Signer(seed=seed + i) for i in range(n_signers)]

# ④ PreAgg ← séquentiel : point de synchronisation 1, agrégation des nonces
app = preagg(pp_list)
```

Cela correspond aux exigences du cours — le terme « processus parallèles » écrit au tableau par l'enseignant désigne le parallélisme au niveau de la conception du protocole (réduction des tours de communication), et non une exigence d'implémentation multithreadée.

### 6.2 Pour une exécution véritablement parallèle

| Solution                                 | Faisabilité           | Description                                                                                                                 |
| ---------------------------------------- | ---------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| C++ multithreadé + bibliothèque RELIC  | Recommandé            | RELIC est une bibliothèque de courbes elliptiques thread-safe, extensible depuis le framework C++ multithread de la Part 1 |
| Multiprocessus + sérialisation manuelle | Faisable mais complexe | Convertir les points de courbe en paires d'entiers (x, y) pour le transfert, reconstruire les objets Sage côté réception |
| Monothread + asyncio                     | Sans intérêt         | Les opérations sur courbes elliptiques sont CPU-intensives, l'I/O asynchrone ne peut pas les accélérer                   |
