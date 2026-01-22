import sys
from pathlib import Path
import random

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from src.hashing.linear_f2 import hash_f2
from src.hashing import sampling


def bits(x: int, width: int) -> str:
    """Fixed-width binary without 0b prefix (math-friendly)."""
    return format(x, f"0{width}b")


def print_M(M: list[int], u: int) -> None:
    print("M = [")
    for row in M:
        print(f"  {bits(row, u)},")
    print("]")


def print_samples(h: hash_f2, xs: list[int], u: int, l: int) -> None:
    print("Samples (x -> h(x)):")
    for x in xs:
        y = h.h(x)
        print(f"  x    = {bits(x, u)}")
        print(f"  h(x) = {bits(y, l)}")
        print("-" * 40)


def demo_with_fixed_M(h: hash_f2, dist: str, u: int, l: int, seed_x: int, **params) -> None:
    print("=" * 60)
    print(f"dist = {dist}, params = {params}, seed_x={seed_x}")

    rng = random.Random(seed_x)
    xs = [sampling.get_sample_x(u, rng, dist, **params) for _ in range(5)]
    print_samples(h, xs, u, l)


def main() -> None:
    l = 5
    u = 8

    seed_M = 42
    seed_x_base = 2026

    h = hash_f2(l=l, u=u, seed=seed_M)

    print("=" * 60)
    print(f"Fixed hash function (single M) with seed_M={seed_M}, l={l}, u={u}")
    print_M(h.M, u)

    demo_with_fixed_M(h, "uniform", u, l, seed_x=seed_x_base + 1)
    demo_with_fixed_M(h, "bernoulli", u, l, seed_x=seed_x_base + 2, p=0.8)
    demo_with_fixed_M(h, "Hamming_weight", u, l, seed_x=seed_x_base + 3, k=3)


if __name__ == "__main__":
    main()
