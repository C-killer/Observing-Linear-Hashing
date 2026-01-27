import math
import random
from src.hashing import sampling
from src.hashing.linear_f2 import hash_f2
from src.experiments.maxload import Maxload
import matplotlib.pyplot as plt

def threshold(l: int, r: float) -> int:
    n = 1 << l
    return math.ceil(r * math.log(n) / math.log(math.log(n)))


def make_S(m: int, u: int, rng: random.Random, dist: str, **params) -> list[int]:
    return [sampling.get_sample_x(u=u, rng=rng, dist=dist, **params) for _ in range(m)]

def estimate_prob_fixed_S(S: list[int], u: int, l: int, r: float, trials: int, seed: int = 0) -> float:
    rng = random.Random(seed)
    T = threshold(l, r)
    exceed = 0

    for _ in range(trials):
        h = hash_f2(l=l, u=u, seed=rng.randrange(1 << 30))
        ml = Maxload(u=u, l=l, h=h).max_load(S)
        if ml >= T:
            exceed += 1

    return exceed / trials



def plot_tail_probability(r_values, probs):
    theory = [1 / (r * r) for r in r_values]

    plt.figure()
    plt.plot(r_values, probs, marker='o', label="empirical")
    plt.plot(r_values, theory, linestyle='--', label="1 / r^2 (theory)")

    plt.yscale("log")
    plt.xlabel("r")
    plt.ylabel("P[max-load ≥ T(r)]")
    plt.title("Tail probability of the max-load")
    plt.legend()
    plt.grid(True, which="both")
    plt.show()

if __name__ == "__main__":
    u = 32
    l = 16
    m = 1 << l
    trials = 100
    r = 6.0

    # rng = random.Random(123)
    # S = make_S(m=m, u=u, rng=rng, dist="Markov", p0=0.9, p1=0.1)  # 也可以 uniform/bernoulli

    # p_hat = estimate_prob_fixed_S(S, u=u, l=l, r=r, trials=trials, seed=999)
    # print("p_hat =", p_hat, "  bound 1/r^2 =", 1/(r*r))
    rng = random.Random(123)
    S = make_S(m=m, u=u, rng=rng, dist="Markov", p0=0.9, p1=0.1)

    
    r_values = [1.5, 2, 3, 4, 5, 6, 8, 10]

    probs = []
    for r in r_values:
        p_hat = estimate_prob_fixed_S(S, u=u, l=l, r=r, trials=trials, seed=999)
        probs.append(p_hat)
        print(f"r={r:4}  p_hat={p_hat:.4e}  1/r^2={1/(r*r):.4e}")

    plot_tail_probability(r_values, probs)