from typing import Callable, Dict, Optional, Any
import random
import math

# ---------------------------
# Sampling functions
# ---------------------------

def sample_uniform(u: int, rng: random.Random) -> int:
    TODO: sample_uniform
    return 0

def sample_bernoulli(u: int, p: float, rng: random.Random) -> int:
    TODO: sample_bernoulli
    return 0

def sample_Hamming_weight(u: int, k: int, rng: random.Random) -> int:
    TODO: sample_Hamming_weight
    return 0


# ---------------------------
# Dispatcher
# ---------------------------

Sampler = Callable[..., int]

_SAMPLERS: Dict[str, Sampler] = {
    "uniform": sample_uniform,
    "bernoulli": sample_bernoulli,
    "Hamming_weight": sample_Hamming_weight
}

def sample_x(u: int, rng: random.Random, dist: str, **params: Any) -> int:
    """
    Unified entry point.
    dist: one of {"uniform","bernoulli","Hamming_weight"}.
    params: distribution parameters (e.g., p=..., k=...).
    """
    return _SAMPLERS[dist](u=u, rng=rng, **params)