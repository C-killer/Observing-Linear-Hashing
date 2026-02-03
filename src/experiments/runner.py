import math
import random
from src.hashing import sampling
from src.hashing.linear_f2 import hash_f2
from src.experiments.maxload import Maxload
import matplotlib.pyplot as plt


#r * logn/loglogn
def threshold(l: int, r: float) -> int:
    n = 1 << l
    return math.ceil(r * math.log(n) / math.log(math.log(n)))


def make_S(m: int, u: int, rng: random.Random, dist: str, **params) -> list[int]:
    # m -> number of s
    return [sampling.get_sample_x(u=u, rng=rng, dist=dist, **params) for _ in range(m)]

# for trails h, calculate the number of probability exceed threshold.
def estimate_prob_fixed_S(S: list[int], u: int, l: int, r: float, trials: int, seed: int = 0) -> float:
    rng = random.Random(seed)
    T = threshold(l, r)
    exceed = 0.0

    for _ in range(trials):
        h = hash_f2(l=l, u=u, seed=rng.randrange(1 << 30))
        # ml = Maxload(u=u, l=l, h=h).max_load(S)
        ml, _ = Maxload(u=u, l=l, h=h).max_load(S, k=50_000)


        if ml >= T:
            exceed += 1.0

    return exceed / trials

def plot_profile_over_l(results, r_values):
    plt.figure(figsize=(7, 5))

    
    for l, probs in results.items():
        plt.plot(r_values, probs, marker="o", label=f"l={l}")

    
    theory = [1 / (r * r) for r in r_values]
    plt.plot(
        r_values,
        theory,
        linestyle="--",
        color="black",
        linewidth=2,
        label="theory: 1/r²"
    )

    plt.xlabel("r")
    plt.ylabel("P[max-load ≥ r · log n / log log n]")
    plt.yscale("log")   
    plt.grid(True, which="both", linestyle="--", alpha=0.5)
    plt.legend()
    plt.tight_layout()
    plt.show()




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

# main interface for use: 
def run_experiment_grid(
    *,
    u_values: list[int],
    l_values: list[int],
    r_values: list[float],
    m_factor: float,
    trials: int,
    dist: str,
    dist_params: dict,
    seed: int = 0,
):
    """
    - u_values: groupe of u
    - l_values: groupe of l
    - r_values: groupe of r
    - m = m_factor * 2^l == number of the blocks of the hashtable
    - dist / dist_params: the generation of the S
    - trials: 
    """

    rng = random.Random(seed)
    results = {}  
    # results[(u,l)][r] = p_hat

    for u in u_values:
        for l in l_values:
            n = 1 << l
            m = int(m_factor * n)

            print(f"\n=== u={u}, l={l}, m={m}, dist={dist} ===")
            #fix S, the same S for the whole round
            S = make_S(
                m=m,
                u=u,
                rng=rng,
                dist=dist,
                **dist_params,
            )

            curve = {}
            for r in r_values:
                p_hat = estimate_prob_fixed_S(
                    S=S,
                    u=u,
                    l=l,
                    r=r,
                    trials=trials,
                    seed=rng.randrange(1 << 30),
                )
                curve[r] = p_hat
                print(f"  r={r:4.2f}  p_hat={p_hat:.4e}")

            results[(u, l)] = curve

    return results

if __name__ == "__main__":
    u_values = [200]                 
    l_values = [20]         
    r_values = [6,7,8]

    trials = 1000
    m_factor = 1.4                  # m(initial) = 2^l
    seed = 123

    dist = "uniform"
    dist_params = {}                


    results = run_experiment_grid(
        u_values=u_values,
        l_values=l_values,
        r_values=r_values,
        m_factor=m_factor,
        trials=trials,
        dist=dist,
        dist_params=dist_params,
        seed=seed,
    )
    # results 的 key 是 (u, l)
    results_by_l = {
        l: [results[(u_values[0], l)][r] for r in r_values]
        for l in l_values
    }

    plot_profile_over_l(results_by_l, r_values)
