
# Observing-Linear-Hashing

UE Projet STL (PSTL) - MU4IN508

## Structure du projet

```
Observing-Linear-Hashing/
├── Makefile                         # Point d'entrée unifié : make help pour la liste
├── src/
│   ├── hashing/                     # Part 1 : hachage linéaire sur F2
│   │   ├── linear_f2.py            #   Implémentation Python et C++
│   │   └── sampling.py             #   Générateurs de vecteurs aléatoires
│   ├── experiments/                 # Part 1 : expériences max-load
│   │   ├── runner.py               #   Point d'entrée principal des expériences
│   │   ├── maxload.py              #   Algorithme Space-Saving (Python)
│   │   └── mlShower.py             #   Affichage de la distribution du max-load
│   ├── crypto/                      # Part 2 : schéma multi-signatures MuSig2-H
│   │   ├── curve.py                #   Courbe elliptique Curve25519
│   │   ├── lhf.py                  #   Fonction de hachage linéaire Pedersen
│   │   ├── musig2h.py              #   8 algorithmes MuSig2-H + 3 hachages
│   │   ├── signer.py               #   Classe Signer (état d'un participant)
│   │   └── parallel_signing.py     #   Coordinateur de protocole (7 étapes)
│   └── cpp/                         # Part 1 : backend C++ (pybind11)
│       ├── linear_hash.hpp/cpp     #   Hachage linéaire F2 en C++
│       ├── trial_maxload.hpp/cpp   #   Un trial avec Space-Saving C++
│       ├── space_saving.hpp        #   Algorithme Space-Saving C++
│       ├── parallel_trials.hpp     #   Parallélisation via std::thread
│       ├── samplers.hpp            #   Génération de vecteurs aléatoires C++
│       ├── bindings.cpp            #   Bindings pybind11
│       └── CMakeLists.txt          #   Configuration CMake
├── tests/                           # Tests (Part 1 : 90, Part 2 : 82)
│   ├── conftest.py
│   ├── test_sampling.py            #   Distributions d'échantillonnage
│   ├── test_py.py                  #   Hachage Python
│   ├── test_cpp.py                 #   Module C++ fasthash
│   ├── test_curve.py               #   Courbe elliptique (21 tests)
│   ├── test_lhf.py                 #   Fonction de hachage linéaire (15 tests)
│   ├── test_musig2h.py             #   Schéma de signature (18 tests)
│   ├── test_signer.py              #   Classe Signer (14 tests)
│   ├── test_parallel.py            #   Coordinateur de protocole (9 tests)
│   └── example.py
├── docs/                            # Documentation
│   ├── part2_background.md         #   Contexte de recherche Part 2
│   └── pari_thread_safety.md       #   Analyse sécurité threads PARI
├── papers/                          # Références bibliographiques (PDF)
├── profiling/                       # Résultats de profilage (CPU/mémoire)
├── scripts/
│   └── compare.py                  # Benchmark Python vs C++
├── data/                            # Résultats d'expériences
└── .gitignore
```

## Conventions de développement

### Principes généraux

Les conventions de ce projet sont les suivantes : la branche `main` est protégée, sans CI, sans validation obligatoire, avec une préférence pour le rebase. Les règles principales sont :

1. Il est interdit de pousser directement sur la branche `main` (protection de branche activée) ;
2. Toutes les modifications de code doivent être effectuées sur une branche personnelle ou de fonctionnalité, puis intégrées à `main` via une Pull Request (PR) ;
3. La méthode de fusion doit être uniformément**Rebase (Rebase and merge)** .

### Règles de branchement

* `main` : branche stable, réservée à l'intégration — aucun développement direct ni push autorisé.
* Branches de développement : chaque membre travaille sur sa propre branche.
* Aucun commit direct sur `main` n'est autorisé ; les commits locaux faits par erreur ne doivent pas être poussés en contournant les règles.

### Initialisation (à faire une seule fois par membre)

```bash
# Cloner le dépôt
git clone https://github.com/C-killer/Observing-Linear-Hashing.git
cd Observing-Linear-Hashing

# Créer sa branche personnelle et la pousser sur le dépôt distant
git checkout -b dev-<nom>
git push -u origin dev-<nom>
```

### Avant chaque session de travail : synchroniser `main`, puis mettre à jour sa branche (obligatoire)

Cette synchronisation est requise avant chaque début de développement afin d'éviter les conflits lors des PR.

```bash
# Synchroniser le main distant en local
git checkout main
git pull origin main

# Revenir sur sa branche et la rebaser sur le main à jour
git checkout dev-<nom>
git rebase main
```

### Développement et commits (sur la branche personnelle)

```bash
# Commiter pendant le développement
git add .
git commit -m "xxx"  # Décrire clairement le travail effectué

# Pousser sur la branche personnelle distante (peut être fait plusieurs fois)
git push origin dev-<nom>
```

### Finaliser : fusionner dans `main` via PR (seule méthode autorisée)

#### 1. Préparation avant la PR (obligatoire)

```bash
# S'assurer que la branche personnelle est synchronisée avec le dernier main :
git checkout main
git pull origin main
git checkout dev-<nom>
git rebase main

# Pousser la branche personnelle :
git push origin dev-<nom>

# Si un rebase vient d'être effectué, un push forcé peut être nécessaire
# (autorisé uniquement sur les branches personnelles) :
git push --force-with-lease origin dev-<nom>
```

#### 2. Créer une Pull Request sur GitHub

* **Base :** `main`
* **Compare :** `dev-xxx`
* La description de la PR doit inclure :
  * Le contenu des modifications (ce qui a été fait)
  * La méthode de test / les résultats (le cas échéant)

#### 3. Méthode de fusion (uniformisée)

Lors de la fusion d'une PR, sélectionner :**Rebase and merge**

### Référence rapide (flux le plus courant)

```bash
# Démarrer une session
git checkout main
git pull origin main
git checkout dev-<nom>
git rebase main

# Commiter et pousser
git add .
git commit -m "xxx"
git push origin dev-<nom>

# Ouvrir une PR et fusionner dans main
# GitHub : créer une PR (branche dev → main)
# Fusion : Rebase and merge
```

---

## Commandes (Makefile)

Le projet utilise un `Makefile` comme point d'entrée unifié. Lancer `make help` pour la liste complète :

```bash
make help           # Afficher toutes les commandes disponibles
make build-cpp      # Compiler le backend C++ (pybind11, Python 3.13)
make test-part1     # Tests Part 1 (compile C++ automatiquement)
make test-part2     # Tests Part 2 (nécessite SageMath)
make test-all       # Tous les tests
make run-part1      # Lancer les expériences Part 1
make demo           # Simulation du protocole MuSig2-H
make clean          # Nettoyer les artefacts de compilation
```

### Exemple d'exécution

Le fichier **`tests/example.py` affiche des exemples de résultats** `x, M, h(x)` avec cet algorithme.

```bash
python3 tests/example.py
```

---

## Algorithme d'estimation du max-load : Space-Saving

### Description

Le problème central des expériences est d'estimer le max-load, c'est-à-dire le nombre de balles dans le bac le plus chargé après avoir distribué **`m` balles dans** `2^l` bacs :

```
M(S, h) = max_y |{x ∈ S : h(x) = y}|
```

Lorsque **`l` est grand (par exemple** **`l=20`, soit un million de bacs), maintenir un comptage exact de chaque bac nécessite une mémoire** **`O(2^l)`, ce qui devient prohibitif. Le projet utilise donc l'algorithme** **Space-Saving** , qui estime le max-load en mémoire `O(k)`.

### Principe

On maintient une table de **`k` candidats** **`table[y] = (c, e)`, où** **`c` est l'estimation du compteur et** **`e` la borne d'erreur, avec un** ****tas min paresseux** pour retrouver le candidat de compteur minimal. Pour chaque identifiant de bac** `y` traité :

* Si **`y` est déjà dans la table : on incrémente son compteur** `c` ;
* Si la table n'est pas pleine : on insère **`y` avec** `(c=1, e=0)` ;
* Si la table est pleine : on extrait le candidat de compteur minimal **`y_min`, on le remplace par** **`y` en héritant de** **`c_min`comme erreur, et on pose le nouveau compteur à** `c_min + 1`.

La méthode `max_count()` retourne le maximum des compteurs de la table, utilisé comme borne supérieure du max-load.

### Complexité

* Temps : **`O(N log k)` amorti, où** `N` est la longueur du flux d'entrée ;
* Espace :`O(k)`.

### Cas d'utilisation

Pour **`l` petit (par exemple** **`l ≤ 10`, soit ≤ 1024 bacs), un comptage exact est plus rapide et sans erreur d'approximation. Space-Saving est utile principalement quand** **`l` est grand et que le nombre de bacs dépasse la mémoire disponible** , au prix d'une légère imprécision.

### Implémentation

* Version Python : **`src/experiments/maxload.py` (classe** `Maxload`, supporte le hachage unitaire et par batch)
* Version C++ : **`src/cpp/space_saving.hpp` (classe** **`SpaceSaving`, compresse la sortie de hachage de longueur arbitraire en clé** **`uint64` via fingerprint)

---

## Méthodes de profilage des performances

### Profilage CPU

> **Note :** Cette section nécessite **Python 3.13** .

```bash
source .venv313/bin/activate

# Génération d'un flamegraph CPU
sudo py-spy record -o profiling/profile.svg -- python -m src.experiments.runner
open profiling/profile.svg
```

### Profilage mémoire

```bash
# Étape 1 : collecter les données mémoire
python -m memray run -o profiling/memray.bin -m src.experiments.runner

# Étape 2 : générer le rapport flamegraph HTML
python -m memray flamegraph profiling/memray.bin -o profiling/memray-flamegraph.html

# Étape 3 : ouvrir le rapport dans le navigateur
open profiling/memray-flamegraph.html
```
