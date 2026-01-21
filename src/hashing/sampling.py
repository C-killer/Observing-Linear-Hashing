from typing import Callable, Dict, Any
import random

# ---------------------------
#      Sampling functions
# ---------------------------

def _check_u(u: int) -> None:
    if not isinstance(u, int) or u <= 0:
        raise ValueError(f"u must be a positive integer, got {u}.")

def sample_uniform(u: int, rng: random.Random) -> int:
    """
    Uniform over F2^u.
    Returns x as an int bitmask with u bits.
    """
    _check_u(u)
    return rng.getrandbits(u)

def sample_bernoulli(u: int, p: float, rng: random.Random) -> int:
    """
    Independent bits: P(bit=1)=p, P(bit=0)=1-p
    Returns x as an int bitmask with u bits.
    """
    _check_u(u)
    if not (0.0 <= p <= 1.0):
        raise ValueError(f"p must be in [0,1], got {p}.")
    x = 0
    for i in range(u):
        if rng.random() < p:
            x |= (1 << i)
    return x

def sample_Hamming_weight(u: int, k: int, rng: random.Random) -> int:
    """
    Uniform over all vectors in F2^u with Hamming weight k, which means x has exactly k ones.
    In this case, the bits are not independent.
    Returns x as an int bitmask with u bits.
    """
    _check_u(u)
    if not (0 <= k <= u):
        raise ValueError(f"k must be in [0,u], got k={k}, u={u}.")
    if k == 0:
        return 0
    if k == u:
        return (1 << u) - 1
    
    # pick k distinct positions from [0,u-1] uniformly at random
    pos = rng.sample(range(u), k)
    x = 0
    for i in pos:
        x |= (1 << i)
    return x


# ---------------------------
#         Dispatcher
# ---------------------------

Sampler = Callable[..., int]

_SAMPLERS: Dict[str, Sampler] = {
    "uniform": sample_uniform,
    "bernoulli": sample_bernoulli,
    "Hamming_weight": sample_Hamming_weight
}

def get_sample_x(u: int, rng: random.Random, dist: str, **params: Any) -> int:
    """
    Unified entry point for sampling x according to different distributions.
    dist: one of {"uniform","bernoulli","Hamming_weight"}.
    params: distribution parameters (e.g., p=..., k=...).
    """
    return _SAMPLERS[dist](u=u, rng=rng, **params)
