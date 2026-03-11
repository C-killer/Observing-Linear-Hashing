# Observing-Linear-Hashing
UE Projet STL (PSTL) - MU4IN508

## Structure du projet

```
Observing-Linear-Hashing/
├── src/
│   ├── hashing/
│   │   ├── linear_f2.py       # Implémentation du hachage linéaire sur F2 (Python et C++)
│   │   └── sampling.py        # Générateurs de vecteurs aléatoires (uniforme, Bernoulli,
│   │                          #   poids de Hamming, Markov)
│   ├── experiments/
│   │   ├── runner.py          # Point d'entrée principal des expériences ;
│   │   │                      #   grilles de paramètres (u, l, r, m), estimation de
│   │   │                      #   P[max-load ≥ T(r)] en Python pur ou via le module C++
│   │   ├── maxload.py         # Algorithme Space-Saving (Python) pour estimer le max-load
│   │   │                      #   en mémoire O(k) avec un tas min paresseux
│   │   └── mlShower.py        # Script rapide : lance des trials C++ et affiche la
│   │                          #   distribution du max-load
│   ├── viz/
│   │   └── plot.py            # Fonctions de visualisation (courbes empiriques vs théorie)
│   └── cpp/
│       ├── linear_hash.hpp/cpp      # Hachage linéaire F2 en C++ (arithmétique bit-à-bit,
│       │                            #   blocs uint64)
│       ├── trial_maxload.hpp/cpp    # Un trial : génère S, calcule h(x) pour chaque x,
│       │                            #   estime le max-load via Space-Saving C++
│       ├── space_saving.hpp         # Algorithme Space-Saving C++ (tas min paresseux,
│       │                            #   clé uint64 par fingerprint)
│       ├── parallel_trials.hpp      # Parallélisation des trials via std::thread
│       ├── samplers.hpp             # Génération de vecteurs aléatoires en C++
│       ├── bindings.cpp             # Bindings pybind11 : expose LinearHash et
│       │                            #   run_trials_maxload à Python
│       └── CMakeLists.txt           # Configuration de compilation du module fasthash
├── tests/
│   ├── conftest.py         # Fixtures partagées pytest
│   ├── test_sampling.py    # Tests unitaires pour les distributions d'échantillonnage
│   ├── test_py.py          # Tests du hachage Python
│   ├── test_cpp.py         # Tests du module C++ fasthash
│   └── example.py          # Exemple : affiche x, M, h(x)
├── compare.py                   # Benchmark Python vs C++ : débit (ns/op, M ops/s),
│                                #   speedup single/batch, trials multi-threadés
├── DD22.pdf                     # Référence bibliographique
├── JKZ25.pdf                    # Référence bibliographique
├── TZ23.pdf                     # Référence bibliographique
├── Observing_Linear_Hashing.pdf # Rapport du projet
└── .gitignore
```

## Conventions de développement

### Principes généraux

Les conventions de ce projet sont les suivantes : la branche `main` est protégée, sans CI, sans validation obligatoire, avec une préférence pour le rebase. Les règles principales sont :

1. Il est interdit de pousser directement sur la branche `main` (protection de branche activée) ;
2. Toutes les modifications de code doivent être effectuées sur une branche personnelle ou de fonctionnalité, puis intégrées à `main` via une Pull Request (PR) ;
3. La méthode de fusion doit être uniformément **Rebase (Rebase and merge)**.

### Règles de branchement

- `main` : branche stable, réservée à l'intégration — aucun développement direct ni push autorisé.
- Branches de développement : chaque membre travaille sur sa propre branche.
- Aucun commit direct sur `main` n'est autorisé ; les commits locaux faits par erreur ne doivent pas être poussés en contournant les règles.

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

- **Base :** `main`
- **Compare :** `dev-xxx`
- La description de la PR doit inclure :
  - Le contenu des modifications (ce qui a été fait)
  - La méthode de test / les résultats (le cas échéant)

#### 3. Méthode de fusion (uniformisée)

Lors de la fusion d'une PR, sélectionner : **Rebase and merge**

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

## Tests

### Prérequis

Python ≥ 3.10 et `pytest` installé.

### Lancer les tests

```bash
# Depuis la racine du projet
pytest

# Ou pour un fichier de test spécifique
pytest tests/test_sampling.py
```

### Exemple d'exécution

Le fichier `tests/example.py` affiche des exemples de résultats `x, M, h(x)` avec cet algorithme.

```bash
# Depuis la racine du projet
python3 tests/example.py
```

---

## Compilation du module C++

### Compilation

```bash
# Depuis la racine
cd Observing-Linear-Hashing/
cmake -S src/cpp -B src/cpp/build -DCMAKE_BUILD_TYPE=Release
cmake --build src/cpp/build -j

# Vérifier que la compilation a réussi
python3 -c "import fasthash; print(fasthash.__file__)"
# Exemple de sortie : Observing-Linear-Hashing/fasthash.cpython-313-darwin.so
```

---

## Expériences

Les expériences permettent d'évaluer le comportement des fonctions de hachage
linéaires dans le problème classique "balls into bins".

### Lancer une expérience

Depuis la racine du projet :

```bash
python -m src.experiments.runner
```

---

## Méthodes de profilage des performances

### Profilage CPU

> **Note :** Cette section nécessite **Python 3.13**.

```bash
python3 -m venv .venv313
source .venv313/bin/activate
python -V   # Vérifier que la version est bien 3.13.x
```

```bash
# Génération d'un flamegraph CPU
sudo py-spy record -o profile.svg -- python -m src.experiments.runner
open profile.svg
```

### Profilage mémoire

```bash
# Étape 1 : collecter les données mémoire
python -m memray run -o memray.bin -m src.experiments.runner

# Étape 2 : générer le rapport flamegraph HTML
python -m memray flamegraph memray.bin -o memray-flamegraph.html

# Étape 3 : ouvrir le rapport dans le navigateur
open memray-flamegraph.html
```
