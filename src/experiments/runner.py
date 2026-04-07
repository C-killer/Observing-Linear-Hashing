import math
import random
import time
from src.hashing import sampling
from src.hashing.linear_f2 import hash_f2
from src.experiments.maxload import Maxload
import matplotlib.pyplot as plt

import fasthash

#r * logn/loglogn
def threshold(l: int, r: float) -> int:
    n = 1 << l
    return math.ceil(r * math.log(n) / math.log(math.log(n)))


def make_S(m: int, u: int, rng: random.Random, dist: str, **params) -> list[int]:
    # m -> number of s
    return [sampling.get_sample_x(u=u, rng=rng, dist=dist, **params) for _ in range(m)]

def make_S_iter(m: int, u: int, seed: int, dist: str, **params):
    rng = random.Random(seed)
    for _ in range(m):
        yield sampling.get_sample_x(u=u, rng=rng, dist=dist, **params)


# for trails h, calculate the number of probability exceed threshold.
def estimate_prob_fixed_S(S: list[int], u: int, l: int, r: float, trials: int, seed: int = 0) -> float:
    rng = random.Random(seed)
    T = threshold(l, r)
    exceed = 0.0

    for _ in range(trials):
        h = hash_f2(l=l, u=u, seed=rng.randrange(1 << 30))
        # ml = Maxload(u=u, l=l, h=h).max_load(S)
        # ml, _ = Maxload(u=u, l=l, h=h).max_load(S, k=50_000)
        ml, _ = Maxload(u=u, l=l, h=h).max_load(S, k=50_000, chunk_size=16384)



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

def run_experiment_grid_not_fixed_S(
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

    rng = random.Random(seed)
    results = {}

    for u in u_values:
        for l in l_values:
            n = 1 << l
            m = int(m_factor * n)

            print(f"\n=== u={u}, l={l}, m={m}, dist={dist} ===")

            # 初始化统计
            exceed = {r: 0.0 for r in r_values}
            thresholds = {r: threshold(l, r) for r in r_values}

            for t in range(trials):

                # --- 每个 trial 新的 seed ---
                seed_S = rng.randrange(1 << 30)
                seed_h = rng.randrange(1 << 30)

                # 生成新的 S（generator）
                S_iter = make_S_iter(
                    m=m,
                    u=u,
                    seed=seed_S,
                    dist=dist,
                    **dist_params,
                )

                # 新 hash
                h = hash_f2(l=l, u=u, seed=seed_h)

                # 只算一次 max-load
                ml, _ = Maxload(u=u, l=l, h=h).max_load(
                    S_iter,
                    k=50_000,
                    chunk_size=65536,  # 4096/8192/16384/32768/65536
                )

                # 对所有 r 判阈值
                for r in r_values:
                    if ml >= thresholds[r]:
                        exceed[r] += 1.0

            # 计算概率
            curve = {}
            for r in r_values:
                p_hat = exceed[r] / trials
                curve[r] = p_hat
                print(f"  r={r:4.2f}  p_hat={p_hat:.8e}")
                print(f"  exceed={exceed[r]:.4e}")

            results[(u, l)] = curve

    return results

def run_experiment_grid_Cpp(
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
    rng = random.Random(seed)
    results = {}

    for u in u_values:
        for l in l_values:
            n = 1 << l
            m = int(m_factor * n)

            print(f"\n=== u={u}, l={l}, m={m}, dist={dist} ===")

            thresholds = {r: threshold(l, r) for r in r_values}

            seeds_S = [rng.randrange(1<<30) for _ in range(trials)]
            seeds_h = [rng.randrange(1<<30) for _ in range(trials)]

            start = time.time()
            mls = fasthash.run_trials_maxload(u, l, m, dist, seeds_S, seeds_h, k=50_000, num_threads=10)
            elapsed = time.time() - start
            print(f"time: {elapsed:.2f}s, per_trial: {elapsed/trials*1000:.2f}ms")

            curve = {}
            for r in r_values:
                T = thresholds[r]
                exceed = sum(ml >= T for ml in mls)
                p_hat = exceed / trials
                curve[r] = p_hat
                print(f"  r={r:4.2f}  T={T}  exceed={exceed}  p_hat={p_hat:.8e}")

            results[(u, l)] = curve

    return results


def parse_args():
    import argparse
    parser = argparse.ArgumentParser(description="Run linear hashing max-load experiments")
    parser.add_argument("-u", "--u-values", type=int, nargs="+", default=[3000],
                        help="u values (default: 3000)")
    parser.add_argument("-l", "--l-values", type=int, nargs="+", default=[30],
                        help="l values (default: 30)")
    parser.add_argument("-r", "--r-values", type=float, nargs="+",
                        default=[2.0, 2.3, 2.6, 2.9, 3.2, 3.5, 4.0],
                        help="r values (default: 2.0 2.3 2.6 2.9 3.2 3.5 4.0)")
    parser.add_argument("-t", "--trials", type=int, default=5000,
                        help="number of trials (default: 5000)")
    parser.add_argument("-m", "--m-factor", type=float, default=1.5,
                        help="m = m_factor * 2^l (default: 1.5)")
    parser.add_argument("-s", "--seed", type=int, default=123,
                        help="random seed (default: 123)")
    parser.add_argument("-d", "--dist", type=str, default="uniform",
                        help="distribution for S (default: uniform)")
    parser.add_argument("--threads", type=int, default=10,
                        help="number of threads for C++ backend (default: 10)")
    parser.add_argument("--backend", choices=["cpp", "py", "py-fixed"],
                        default="cpp",
                        help="backend: cpp / py (not fixed S) / py-fixed (default: cpp)")
    parser.add_argument("--no-plot", action="store_true",
                        help="disable plotting")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    u_values = args.u_values
    l_values = args.l_values
    r_values = args.r_values
    trials = args.trials
    m_factor = args.m_factor
    seed = args.seed
    dist = args.dist
    dist_params = {}

    common = dict(
        u_values=u_values,
        l_values=l_values,
        r_values=r_values,
        m_factor=m_factor,
        trials=trials,
        dist=dist,
        dist_params=dist_params,
        seed=seed,
    )

    if args.backend == "cpp":
        results = run_experiment_grid_Cpp(**common)
    elif args.backend == "py":
        results = run_experiment_grid_not_fixed_S(**common)
    else:
        results = run_experiment_grid(**common)

    if not args.no_plot:
        results_by_l = {
            l: [results[(u_values[0], l)][r] for r in r_values]
            for l in l_values
        }
        plot_profile_over_l(results_by_l, r_values)

    print()
    print("提示：make run-part1 ARGS=\"-h\" 查看所有参数")
    print("示例：make run-part1 ARGS=\"-u 3000 5000 -l 20 30 -t 10000\"")
