# tests/test_sampling.py

# Unit tests for sampling functions in src/hashing/sampling.py
# This test is created by chatGPT based on the code provided.

import random
import pytest

from src.hashing.sampling import (
    sample_uniform,
    sample_bernoulli,
    sample_Hamming_weight,
    sample_Markov,
    get_sample_x,
)

def popcount(x: int) -> int:
    # Python 3.8+ has int.bit_count(); keep compatibility if needed
    return x.bit_count() if hasattr(int, "bit_count") else bin(x).count("1")


# ---------------------------
#   Input validation tests
# ---------------------------

@pytest.mark.parametrize("bad_u", [0, -1, -10, 1.5, "8", None])
def test_sample_uniform_invalid_u(bad_u):
    rng = random.Random(0)
    with pytest.raises((ValueError, TypeError)):
        sample_uniform(bad_u, rng)  # type: ignore[arg-type]

@pytest.mark.parametrize("bad_u", [0, -2, 2.3, "u"])
def test_sample_bernoulli_invalid_u(bad_u):
    rng = random.Random(0)
    with pytest.raises((ValueError, TypeError)):
        sample_bernoulli(bad_u, 0.5, rng)  # type: ignore[arg-type]

@pytest.mark.parametrize("bad_p", [-0.1, 1.1, 2.0, "0.3", None])
def test_sample_bernoulli_invalid_p(bad_p):
    rng = random.Random(0)
    with pytest.raises((ValueError, TypeError)):
        sample_bernoulli(8, bad_p, rng)  # type: ignore[arg-type]

@pytest.mark.parametrize(
    "u,k",
    [
        (8, -1),
        (8, 9),
        (0, 0),      # u invalid
        (-3, 1),     # u invalid
        (8, "3"),    # type invalid
    ],
)
def test_sample_hamming_weight_invalid_params(u, k):
    rng = random.Random(0)
    with pytest.raises((ValueError, TypeError)):
        sample_Hamming_weight(u, k, rng)  # type: ignore[arg-type]

@pytest.mark.parametrize("bad_p", [-0.1, 1.1, 2.0, "0.3", None])
def test_sample_markov_invalid_p0(bad_p):
    rng = random.Random(0)
    with pytest.raises((ValueError, TypeError)):
        sample_Markov(8, bad_p, 0.5, rng)  # type: ignore[arg-type]

@pytest.mark.parametrize("bad_p", [-0.1, 1.1, 2.0, "0.3", None])
def test_sample_markov_invalid_p1(bad_p):
    rng = random.Random(0)
    with pytest.raises((ValueError, TypeError)):
        sample_Markov(8, 0.5, bad_p, rng)  # type: ignore[arg-type]

@pytest.mark.parametrize("bad_u", [0, -1, -10, 1.5, "8", None])
def test_sample_markov_invalid_u(bad_u):
    rng = random.Random(0)
    with pytest.raises(ValueError):
        sample_Markov(bad_u, 0.5, 0.5, rng)  # type: ignore[arg-type]

# ---------------------------
#   Output range tests
# ---------------------------

@pytest.mark.parametrize("u", [1, 2, 8, 31, 64, 127])
def test_sample_uniform_within_u_bits(u):
    rng = random.Random(123)
    x = sample_uniform(u, rng)
    assert 0 <= x < (1 << u)

@pytest.mark.parametrize("u,p", [(1, 0.2), (8, 0.5), (32, 0.9)])
def test_sample_bernoulli_within_u_bits(u, p):
    rng = random.Random(123)
    x = sample_bernoulli(u, p, rng)
    assert 0 <= x < (1 << u)

@pytest.mark.parametrize("u,k", [(1, 0), (1, 1), (8, 3), (16, 0), (16, 16)])
def test_sample_hamming_weight_within_u_bits(u, k):
    rng = random.Random(123)
    x = sample_Hamming_weight(u, k, rng)
    assert 0 <= x < (1 << u)

@pytest.mark.parametrize("u,p0,p1", [(1, 0.2, 0.8), (8, 0.5, 0.5), (64, 0.9, 0.1)])
def test_sample_markov_within_u_bits(u, p0, p1):
    rng = random.Random(123)
    x = sample_Markov(u, p0, p1, rng)
    assert 0 <= x < (1 << u)

# ---------------------------
#   Distribution property tests
# ---------------------------

@pytest.mark.parametrize("u,k", [(8, 0), (8, 1), (8, 3), (8, 8), (64, 5), (64, 32)])
def test_sample_hamming_weight_exact_popcount(u, k):
    rng = random.Random(0)
    x = sample_Hamming_weight(u, k, rng)
    assert popcount(x) == k

def test_sample_hamming_weight_edge_cases():
    rng = random.Random(0)
    assert sample_Hamming_weight(10, 0, rng) == 0
    assert sample_Hamming_weight(10, 10, rng) == (1 << 10) - 1

@pytest.mark.parametrize("u", [1, 8, 32, 64])
def test_sample_bernoulli_p_zero_returns_zero(u):
    rng = random.Random(0)
    x = sample_bernoulli(u, 0.0, rng)
    assert x == 0

@pytest.mark.parametrize("u", [1, 8, 32, 64])
def test_sample_bernoulli_p_one_returns_all_ones(u):
    rng = random.Random(0)
    x = sample_bernoulli(u, 1.0, rng)
    assert x == (1 << u) - 1

def test_sample_markov_all_zeros_when_p0_p1_zero_and_first_bit_forced_zero(monkeypatch):
    u = 32
    rng = random.Random(0)
    orig_random = rng.random
    first = True
    def random_once():
        nonlocal first
        if first:
            first = False
            return 0.9  # >= 0.5 => bit0 = 0
        return orig_random()
    monkeypatch.setattr(rng, "random", random_once)
    x = sample_Markov(u, 0.0, 0.0, rng)
    assert x == 0


def test_sample_markov_all_ones_when_p0_p1_one_and_first_bit_forced_one(monkeypatch):
    u = 32
    rng = random.Random(0)
    orig_random = rng.random
    first = True
    def random_once():
        nonlocal first
        if first:
            first = False
            return 0.1  # < 0.5 => bit0 = 1
        return orig_random()
    monkeypatch.setattr(rng, "random", random_once)
    x = sample_Markov(u, 1.0, 1.0, rng)
    assert x == (1 << u) - 1

def test_sample_markov_first_bit_only_depends_on_initial_coinflip():
    # when u=1, p0/p1 should not affect the result (only the first bit).
    rng1 = random.Random(42)
    rng2 = random.Random(42)
    x1 = sample_Markov(1, 0.0, 0.0, rng1)
    x2 = sample_Markov(1, 1.0, 1.0, rng2)
    assert x1 == x2
    assert x1 in (0, 1)

# ---------------------------
#   Dispatcher tests
# ---------------------------

def test_get_sample_x_uniform_dispatch():
    rng = random.Random(0)
    x1 = get_sample_x(u=16, rng=rng, dist="uniform")
    assert 0 <= x1 < (1 << 16)

def test_get_sample_x_bernoulli_dispatch_and_params():
    rng = random.Random(0)
    x = get_sample_x(u=16, rng=rng, dist="bernoulli", p=0.3)
    assert 0 <= x < (1 << 16)

def test_get_sample_x_hamming_weight_dispatch_and_params():
    rng = random.Random(0)
    x = get_sample_x(u=16, rng=rng, dist="Hamming_weight", k=5)
    assert popcount(x) == 5

def test_get_sample_x_unknown_dist_raises_keyerror():
    rng = random.Random(0)
    with pytest.raises((ValueError, TypeError, KeyError)):
        get_sample_x(u=8, rng=rng, dist="unknown")

def test_get_sample_x_missing_required_param_raises_typeerror():
    rng = random.Random(0)
    # bernoulli requires p
    with pytest.raises((ValueError, TypeError)):
        get_sample_x(u=8, rng=rng, dist="bernoulli")

def test_get_sample_x_unexpected_param_raises_typeerror():
    rng = random.Random(0)
    # uniform does not accept extra params
    with pytest.raises((ValueError, TypeError)):
        get_sample_x(u=8, rng=rng, dist="uniform", p=0.5)

def test_get_sample_x_markov_dispatch():
    rng = random.Random(0)
    x = get_sample_x(u=16, rng=rng, dist="Markov", p0=0.7, p1=0.2)
    assert 0 <= x < (1 << 16)

def test_get_sample_x_markov_missing_params_raises_typeerror():
    rng = random.Random(0)
    with pytest.raises(TypeError):
        get_sample_x(u=16, rng=rng, dist="Markov", p0=0.7)  # missing p1
