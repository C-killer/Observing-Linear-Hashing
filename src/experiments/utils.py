# src/experiments/utils.py

import math
import random
from typing import List

from src.hashing.sampling import get_sample_x
from src.hashing.linear_f2 import hash_f2
from src.experiments.maxload import Maxload   # 如果你的 Maxload 在别的地方，改这里


# ============================================================
# Threshold: r * log n / log log n
# ============================================================

def threshold(l: int, r: float) -> int:
    """
    Threshold T = ceil(r * log n / log log n),
    where n = 2^l.
    """
    n = 1 << l
    return math.ceil(r * math.log(n) / math.log(math.log(n)))


# ============================================================
# Generate S ⊆ F_2^u, |S| = m
# ============================================================

def make_S(
    *,
    m: int,
    u: int,
    rng: random.Random,
    dist: str,
    **params,
) -> List[int]:
    """
    Generate a fixed set S of size m, where each element is a u-bit integer.

    dist:
      - "uniform"
      - "Markov"
      - others supported by sampling.get_sample_x
    """
    return [
        get_sample_x(u=u, rng=rng, dist=dist, **params)
        for _ in range(m)
    ]


# ============================================================
# Monte-Carlo estimation for fixed S
# ============================================================

def estimate_prob_fixed_S(
    *,
    S: List[int],
    u: int,
    l: int,
    r: float,
    trials: int,
    seed: int = 0,
) -> float:
    """
    Estimate:
        P_h [ max_load(h(S)) >= r * log n / log log n ]
    for a fixed set S and random linear hash h.
    """
    rng = random.Random(seed)
    T = threshold(l, r)
    exceed = 0

    for _ in range(trials):
        h = hash_f2(l=l, u=u, seed=rng.randrange(1 << 30))
        ml = Maxload(u=u, l=l, h=h).max_load(S)
        if ml >= T:
            exceed += 1

    return exceed / trials
