#!/usr/bin/env sage -python
"""
profile_musig2h.py — MuSig2-H performance analysis & PARI thread safety profiling

Four experiments:
  A. Thread crash reproduction (ThreadPoolExecutor → segfault)
  B. Sequential execution benchmark (signer count scalability)
  C. Phase timing breakdown (parallelizable vs sequential ratio)
  D. Amdahl's Law theoretical speedup analysis

Usage: run from project root
  sage -python scripts/profile_musig2h.py [--skip-crash] [--repeats N] [--warmup N]
"""
from __future__ import annotations

import argparse
import os
import statistics
import subprocess
import sys
import time

# ensure src package is importable from project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.crypto.parallel_signing import run_protocol

# ─── Constants ────────────────────────────────────────────────────────────────

PARALLEL_PHASES = ["keygen", "presign", "sign"]
SEQUENTIAL_PHASES = ["keyagg", "preagg", "signagg", "verify"]
ALL_PHASES = ["keygen", "keyagg", "presign", "preagg", "sign", "signagg", "verify"]

PROFILING_DIR = os.path.join(os.path.dirname(__file__), "..", "profiling", "part2")


# ═══════════════════════════════════════════════════════════════════════════
# Experiment A: Thread crash reproduction
# ═══════════════════════════════════════════════════════════════════════════

def thread_crash_demo(repeats=5):
    """Call worker via subprocess, count ThreadPoolExecutor crash rate."""
    print("=" * 65)
    print("Experiment A: PARI thread safety crash reproduction")
    print("=" * 65)
    print("Method: subprocess isolation calling ThreadPoolExecutor to concurrently construct Signer")
    print()

    worker = os.path.join(os.path.dirname(__file__), "thread_crash_worker.py")
    configs = [(2, 2), (4, 4), (8, 8)]

    print(f"{'signers':>8s}  {'threads':>8s}  {'repeats':>8s}  {'crashed':>8s}  {'rate':>6s}  {'exit codes'}")
    print("-" * 65)

    results = []
    for n_signers, n_threads in configs:
        crashes = 0
        has_segfault = 0
        codes = []
        for _ in range(repeats):
            r = subprocess.run(
                ["sage", "-python", worker, str(n_signers), str(n_threads)],
                capture_output=True, timeout=30,
            )
            codes.append(r.returncode)
            if r.returncode != 0:
                crashes += 1
            stderr = r.stderr.decode(errors="replace")
            if "SignalError" in stderr or "Segmentation fault" in stderr:
                has_segfault += 1

        rate = crashes / repeats * 100
        code_str = ", ".join(str(c) for c in codes)
        print(f"{n_signers:>8d}  {n_threads:>8d}  {repeats:>8d}  {crashes:>8d}  {rate:>5.0f}%  [{code_str}]")
        results.append((n_signers, n_threads, crashes, repeats, codes))

    print()
    print("cysignals catches SIGSEGV and raises SignalError, process terminates with exit code 1.")
    print("Root cause: PARI global stack (avma) has no lock protection, concurrent multi-thread writes cause memory corruption.")
    print()
    return results


# ═══════════════════════════════════════════════════════════════════════════
# Experiment B: Sequential execution benchmark
# ═══════════════════════════════════════════════════════════════════════════

def bench_scalability(n_list, warmup=2, repeats=5):
    """Measure median timing for each phase across different signer counts."""
    print("=" * 65)
    print("Experiment B: Sequential execution benchmark (signer count scalability)")
    print("=" * 65)
    print(f"Parameters: warmup={warmup}, repeats={repeats}, seed=42")
    print()

    all_data = []  # [(n, {phase: median_ms})]

    for n in n_list:
        phase_times = {p: [] for p in ALL_PHASES}
        total_times = []

        # warmup
        for _ in range(warmup):
            run_protocol(n, b"warmup", seed=42)

        # timed runs
        for r in range(repeats):
            result = run_protocol(n, b"benchmark", seed=42 + r)
            for p in ALL_PHASES:
                phase_times[p].append(result["timing"][p] * 1000)  # → ms
            total_times.append(result["timing"]["total"] * 1000)

        medians = {p: statistics.median(phase_times[p]) for p in ALL_PHASES}
        medians["total"] = statistics.median(total_times)
        all_data.append((n, medians))

    # print table
    header = f"{'n':>4s}"
    for p in ALL_PHASES:
        header += f"  {p:>8s}"
    header += f"  {'total':>8s}"
    print(header)
    print("-" * len(header))

    for n, medians in all_data:
        row = f"{n:>4d}"
        for p in ALL_PHASES:
            row += f"  {medians[p]:>7.1f}ms" if medians[p] >= 0.1 else f"  {medians[p]:>7.2f}ms"
        row += f"  {medians['total']:>7.1f}ms"
        print(row)

    print()
    print("Unit: milliseconds (ms), median of 5 runs")
    print()
    return all_data


# ═══════════════════════════════════════════════════════════════════════════
# Experiment C: Phase timing breakdown
# ═══════════════════════════════════════════════════════════════════════════

def phase_breakdown(all_data):
    """Analyze parallelizable vs sequential phase ratio from scalability data."""
    print("=" * 65)
    print("Experiment C: Phase timing breakdown (parallelizable vs sequential)")
    print("=" * 65)
    print()

    print(f"{'n':>4s}  {'T_parallel':>11s}  {'T_sequential':>13s}  {'T_total':>8s}  {'parallel%':>10s}")
    print("-" * 55)

    breakdown_data = []
    for n, medians in all_data:
        t_par = sum(medians[p] for p in PARALLEL_PHASES)
        t_seq = sum(medians[p] for p in SEQUENTIAL_PHASES)
        t_total = medians["total"]
        pct = t_par / t_total * 100 if t_total > 0 else 0
        print(f"{n:>4d}  {t_par:>10.1f}ms  {t_seq:>12.1f}ms  {t_total:>7.1f}ms  {pct:>9.1f}%")
        breakdown_data.append((n, t_par, t_seq, t_total, pct))

    print()
    return breakdown_data


# ═══════════════════════════════════════════════════════════════════════════
# Experiment D: Amdahl's Law theoretical speedup
# ═══════════════════════════════════════════════════════════════════════════

def amdahl_analysis(breakdown_data):
    """
    Compute theoretical parallel speedup vs actual (always 1x).

    Based on Amdahl's Law:
      S(n) = 1 / ((1-f) + f/n)
    Reference: G. M. Amdahl, "Validity of the Single Processor Approach to
    Achieving Large Scale Computing Capabilities", AFIPS 1967, pp. 483-485.
    """
    print("=" * 65)
    print("Experiment D: Amdahl's Law theoretical speedup analysis")
    print("=" * 65)
    print()

    # use data from max n to compute parallel ratio (most stable)
    n_ref, t_par, t_seq, t_total, f_pct = breakdown_data[-1]
    f = t_par / t_total if t_total > 0 else 0

    print(f"Reference data point: n={n_ref}")
    print(f"Parallelizable fraction f = {f:.4f} ({f_pct:.1f}%)")
    print(f"Sequential fraction 1-f = {1 - f:.4f} ({100 - f_pct:.1f}%)")
    print()

    workers_list = [1, 2, 4, 8, 10, 16, 32]
    print(f"{'workers':>8s}  {'theoretical':>12s}  {'actual(seq)':>12s}  {'lost speedup':>13s}")
    print("-" * 50)

    amdahl_data = []
    for w in workers_list:
        s_theory = 1.0 / ((1 - f) + f / w)
        s_actual = 1.0
        lost = s_theory - s_actual
        print(f"{w:>8d}  {s_theory:>11.2f}x  {s_actual:>11.2f}x  {lost:>12.2f}x")
        amdahl_data.append((w, s_theory, s_actual))

    print()
    print("Actual is always 1.00x: PARI global stack is not thread-safe, cannot parallelize.")
    print()
    return f, amdahl_data


# ═══════════════════════════════════════════════════════════════════════════
# Chart generation
# ═══════════════════════════════════════════════════════════════════════════

def generate_charts(all_data, f, amdahl_data):
    """Generate PNG charts to profiling/part2/ using matplotlib."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("[WARN] matplotlib not available, skipping chart generation")
        return

    os.makedirs(PROFILING_DIR, exist_ok=True)

    # ── Chart 1: Scalability (signer count vs phase timing) ──────────────────
    fig, ax = plt.subplots(figsize=(10, 6))

    ns = [d[0] for d in all_data]

    # parallelizable phases with solid lines, sequential with dashed
    for phase in PARALLEL_PHASES:
        ys = [d[1][phase] for d in all_data]
        ax.plot(ns, ys, "o-", label=f"{phase} (parallelizable)", linewidth=2)

    for phase in SEQUENTIAL_PHASES:
        ys = [d[1][phase] for d in all_data]
        ax.plot(ns, ys, "s--", label=f"{phase} (sequential)", linewidth=1.5, alpha=0.7)

    # total
    ys_total = [d[1]["total"] for d in all_data]
    ax.plot(ns, ys_total, "D-", label="total", linewidth=2.5, color="black")

    ax.set_xlabel("Number of signers (n)", fontsize=12)
    ax.set_ylabel("Time (ms, median of 5 runs)", fontsize=12)
    ax.set_title("MuSig2-H Sequential Execution: Phase Timing vs Number of Signers", fontsize=13)
    ax.legend(fontsize=9, loc="upper left")
    ax.grid(True, alpha=0.3)
    ax.set_xticks(ns)

    path1 = os.path.join(PROFILING_DIR, "scalability.png")
    fig.tight_layout()
    fig.savefig(path1, dpi=150)
    plt.close(fig)
    print(f"[Chart] Scalability chart saved: {path1}")

    # ── Chart 2: Amdahl's Law ────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(8, 5))

    workers = [d[0] for d in amdahl_data]
    theoretical = [d[1] for d in amdahl_data]
    actual = [d[2] for d in amdahl_data]

    ax.plot(workers, theoretical, "o-", label=f"Theoretical (f={f:.1%})", linewidth=2, color="tab:blue")
    ax.plot(workers, actual, "s--", label="Actual (PARI limitation)", linewidth=2, color="tab:red")

    # fill "lost speedup" area
    ax.fill_between(workers, actual, theoretical, alpha=0.15, color="tab:red",
                     label="Lost speedup (PARI unsafe)")

    ax.set_xlabel("Number of parallel workers", fontsize=12)
    ax.set_ylabel("Speedup", fontsize=12)
    ax.set_title("Amdahl's Law: Theoretical vs Actual Speedup\n(PARI global stack prevents parallelism)",
                  fontsize=12)
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3)
    ax.set_xticks(workers)

    path2 = os.path.join(PROFILING_DIR, "amdahl.png")
    fig.tight_layout()
    fig.savefig(path2, dpi=150)
    plt.close(fig)
    print(f"[Chart] Amdahl chart saved: {path2}")


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(description="MuSig2-H profiling & PARI thread safety analysis")
    ap.add_argument("--skip-crash", action="store_true", help="skip thread crash experiment (faster debugging)")
    ap.add_argument("--warmup", type=int, default=2, help="warmup rounds (default: 2)")
    ap.add_argument("--repeats", type=int, default=5, help="measurement rounds (default: 5)")
    ap.add_argument("--no-chart", action="store_true", help="skip chart generation")
    args = ap.parse_args()

    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║     MuSig2-H Profiling & PARI Thread Safety Analysis       ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()

    # Experiment A
    if not args.skip_crash:
        thread_crash_demo(repeats=5)
    else:
        print("[SKIP] Thread crash experiment (--skip-crash)\n")

    # Experiment B
    n_list = [1, 2, 3, 5, 8, 10, 15, 20]
    all_data = bench_scalability(n_list, warmup=args.warmup, repeats=args.repeats)

    # Experiment C
    breakdown_data = phase_breakdown(all_data)

    # Experiment D
    f, amdahl_data = amdahl_analysis(breakdown_data)

    # Charts
    if not args.no_chart:
        print("=" * 65)
        print("Chart generation")
        print("=" * 65)
        generate_charts(all_data, f, amdahl_data)

    print()
    print("Done.")


if __name__ == "__main__":
    main()
