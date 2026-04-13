#!/usr/bin/env sage -python
"""
bench_musig2h.py — MuSig2-H performance benchmark: Python vs C++ (sequential & parallel)

Four experiments:
  A. Python sequential execution benchmark
  B. C++ sequential execution benchmark (num_threads=1)
  C. C++ parallel execution benchmark (thread count sweep)
  D. Amdahl's Law: theoretical vs actual speedup

Usage: run from project root
  sage -python scripts/bench_musig2h.py [--fast] [--no-python] [--no-chart]
"""
from __future__ import annotations

import argparse
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ─── Constants ────────────────────────────────────────────────────────────────

PARALLEL_PHASES = ["keygen", "presign", "sign"]
SEQUENTIAL_PHASES = ["keyagg", "preagg", "signagg", "verify"]
ALL_PHASES = ["keygen", "keyagg", "presign", "preagg", "sign", "signagg", "verify"]

SIGNER_COUNTS = [1, 2, 5, 10, 20, 50, 100]
SIGNER_COUNTS_FAST = [1, 2, 5, 10, 20]

THREAD_COUNTS = [1, 2, 4, 8, 12]

MESSAGE = b"benchmark"
PROFILING_DIR = os.path.join(os.path.dirname(__file__), "..", "profiling", "part2")


# ═══════════════════════════════════════════════════════════════════════════
# Experiment A: Python sequential benchmark
# ═══════════════════════════════════════════════════════════════════════════

def bench_python_sequential(n_list, warmup, repeats):
    """Benchmark Python (SageMath) sequential protocol."""
    from src.crypto.parallel_signing import run_protocol

    print("=" * 70)
    print("Experiment A: Python sequential execution benchmark")
    print("=" * 70)
    print(f"Parameters: warmup={warmup}, repeats={repeats}, message={MESSAGE!r}")
    print()

    all_data = []

    for n in n_list:
        phase_times = {p: [] for p in ALL_PHASES}
        total_times = []

        for _ in range(warmup):
            run_protocol(n, MESSAGE, seed=42)

        for r in range(repeats):
            result = run_protocol(n, MESSAGE, seed=42 + r)
            for p in ALL_PHASES:
                phase_times[p].append(result["timing"][p] * 1000)
            total_times.append(result["timing"]["total"] * 1000)

        medians = {p: statistics.median(phase_times[p]) for p in ALL_PHASES}
        medians["total"] = statistics.median(total_times)
        all_data.append((n, medians))

    _print_phase_table("Python seq", all_data, repeats)
    return all_data


# ═══════════════════════════════════════════════════════════════════════════
# Experiment B: C++ sequential benchmark (num_threads=1)
# ═══════════════════════════════════════════════════════════════════════════

def bench_cpp_sequential(n_list, warmup, repeats):
    """Benchmark C++ protocol with num_threads=1 (functionally sequential)."""
    import fastmusig

    print("=" * 70)
    print("Experiment B: C++ sequential execution benchmark (num_threads=1)")
    print("=" * 70)
    print(f"Parameters: warmup={warmup}, repeats={repeats}, message={MESSAGE!r}")
    print()

    all_data = []

    for n in n_list:
        phase_times = {p: [] for p in ALL_PHASES}
        total_times = []

        for _ in range(warmup):
            fastmusig.run_protocol_parallel(n, MESSAGE, 42, 1)

        for r in range(repeats):
            result = fastmusig.run_protocol_parallel(n, MESSAGE, 42 + r, 1)
            timing = result["timing"]
            for p in ALL_PHASES:
                phase_times[p].append(timing[p] * 1000)
            total_times.append(timing["total"] * 1000)

        medians = {p: statistics.median(phase_times[p]) for p in ALL_PHASES}
        medians["total"] = statistics.median(total_times)
        all_data.append((n, medians))

    _print_phase_table("C++ seq", all_data, repeats)
    return all_data


# ═══════════════════════════════════════════════════════════════════════════
# Experiment C: C++ parallel benchmark (thread sweep)
# ═══════════════════════════════════════════════════════════════════════════

def bench_cpp_parallel(n_list, thread_list, warmup, repeats):
    """Benchmark C++ parallel protocol across signer counts and thread counts."""
    import fastmusig

    print("=" * 70)
    print("Experiment C: C++ parallel execution benchmark (thread count sweep)")
    print("=" * 70)
    print(f"Parameters: warmup={warmup}, repeats={repeats}, threads={thread_list}")
    print()

    # result: {(n, t): {phase: median_ms}}
    par_data = {}

    for n in n_list:
        for t in thread_list:
            effective_t = min(t, n)
            if effective_t != t and (n, effective_t) in par_data:
                par_data[(n, t)] = par_data[(n, effective_t)]
                continue

            total_times = []
            phase_times = {p: [] for p in ALL_PHASES}

            for _ in range(warmup):
                fastmusig.run_protocol_parallel(n, MESSAGE, 42, t)

            for r in range(repeats):
                result = fastmusig.run_protocol_parallel(n, MESSAGE, 42 + r, t)
                timing = result["timing"]
                for p in ALL_PHASES:
                    phase_times[p].append(timing[p] * 1000)
                total_times.append(timing["total"] * 1000)

            medians = {p: statistics.median(phase_times[p]) for p in ALL_PHASES}
            medians["total"] = statistics.median(total_times)
            par_data[(n, t)] = medians

    # Print matrix: rows = n, columns = thread counts
    header = f"{'n':>6s}"
    for t in thread_list:
        header += f"  {'t=' + str(t):>10s}"
    print(header)
    print("-" * len(header))

    for n in n_list:
        row = f"{n:>6d}"
        for t in thread_list:
            ms = par_data[(n, t)]["total"]
            row += f"  {ms:>9.2f}ms" if ms >= 0.1 else f"  {ms:>9.3f}ms"
        print(row)

    # Print speedup matrix (relative to t=1)
    print()
    print("Speedup (relative to C++ num_threads=1):")
    header2 = f"{'n':>6s}"
    for t in thread_list:
        header2 += f"  {'t=' + str(t):>10s}"
    print(header2)
    print("-" * len(header2))

    for n in n_list:
        row = f"{n:>6d}"
        base = par_data[(n, 1)]["total"]
        for t in thread_list:
            speedup = base / par_data[(n, t)]["total"] if par_data[(n, t)]["total"] > 0 else 0
            row += f"  {speedup:>9.2f}x"
        print(row)

    print()
    return par_data


# ═══════════════════════════════════════════════════════════════════════════
# Experiment D: Amdahl's Law analysis
# ═══════════════════════════════════════════════════════════════════════════

def amdahl_analysis(cpp_seq_data, par_data, thread_list):
    """Compare theoretical Amdahl speedup with actual C++ parallel speedup."""
    print("=" * 70)
    print("Experiment D: Amdahl's Law — theoretical vs actual speedup")
    print("=" * 70)
    print()

    # Use largest n for reference
    n_ref, medians_ref = cpp_seq_data[-1]
    t_par = sum(medians_ref[p] for p in PARALLEL_PHASES)
    t_total = medians_ref["total"]
    f = t_par / t_total if t_total > 0 else 0

    print(f"Reference: n={n_ref}, parallelizable fraction f = {f:.4f} ({f * 100:.1f}%)")
    print()

    header = f"{'threads':>8s}  {'theoretical':>12s}  {'actual':>12s}  {'efficiency':>11s}"
    print(header)
    print("-" * len(header))

    amdahl_data = []
    base_total = par_data[(n_ref, 1)]["total"]

    for t in thread_list:
        s_theory = 1.0 / ((1 - f) + f / t)
        actual_total = par_data[(n_ref, t)]["total"]
        s_actual = base_total / actual_total if actual_total > 0 else 0
        eff = s_actual / s_theory * 100 if s_theory > 0 else 0
        print(f"{t:>8d}  {s_theory:>11.2f}x  {s_actual:>11.2f}x  {eff:>10.1f}%")
        amdahl_data.append((t, s_theory, s_actual))

    print()
    return n_ref, f, amdahl_data


# ═══════════════════════════════════════════════════════════════════════════
# Speedup summary (Python vs C++)
# ═══════════════════════════════════════════════════════════════════════════

def print_speedup_summary(py_data, cpp_seq_data, par_data, thread_list):
    """Print Python vs C++ speedup summary."""
    print("=" * 70)
    print("Speedup summary: Python seq vs C++ seq vs C++ parallel (best)")
    print("=" * 70)
    print()

    best_t = max(thread_list)

    header = f"{'n':>6s}  {'Python':>10s}  {'C++ seq':>10s}  {'C++ par':>10s}  {'Py/C++seq':>10s}  {'Py/C++par':>10s}"
    print(header)
    print("-" * len(header))

    for (n_py, m_py), (n_cpp, m_cpp) in zip(py_data, cpp_seq_data):
        assert n_py == n_cpp
        n = n_py
        py_ms = m_py["total"]
        cpp_ms = m_cpp["total"]

        # find best parallel time for this n
        best_par_ms = min(par_data[(n, t)]["total"] for t in thread_list if (n, t) in par_data)

        sp_seq = py_ms / cpp_ms if cpp_ms > 0 else 0
        sp_par = py_ms / best_par_ms if best_par_ms > 0 else 0

        print(f"{n:>6d}  {py_ms:>9.1f}ms  {cpp_ms:>9.2f}ms  {best_par_ms:>9.2f}ms  {sp_seq:>9.1f}x  {sp_par:>9.1f}x")

    print()


# ═══════════════════════════════════════════════════════════════════════════
# Chart generation
# ═══════════════════════════════════════════════════════════════════════════

def generate_charts(py_data, cpp_seq_data, par_data, thread_list, n_ref, f, amdahl_data):
    """Generate 3 benchmark charts to profiling/part2/."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("[WARN] matplotlib not available, skipping chart generation")
        return

    os.makedirs(PROFILING_DIR, exist_ok=True)
    n_list = [d[0] for d in cpp_seq_data]

    # ── Chart 1: C++ parallel (per thread count) vs Python — time vs n ────
    fig, ax = plt.subplots(figsize=(10, 6))

    if py_data:
        ns_py = [d[0] for d in py_data]
        ys_py = [d[1]["total"] for d in py_data]
        ax.plot(ns_py, ys_py, "D-", label="Python (sequential)",
                linewidth=2.5, color="black", markersize=7)

    for t in thread_list:
        ys = [par_data[(n, t)]["total"] for n in n_list]
        ax.plot(n_list, ys, "o-", label=f"C++ {t} thread{'s' if t > 1 else ''}",
                linewidth=2, markersize=5)

    ax.set_xlabel("Number of signers (n)", fontsize=12)
    ax.set_ylabel("Total time (ms)", fontsize=12)
    ax.set_title("MuSig2-H: C++ Parallel vs Python", fontsize=13)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

    path1 = os.path.join(PROFILING_DIR, "bench_cpp_vs_python.png")
    fig.tight_layout()
    fig.savefig(path1, dpi=150)
    plt.close(fig)
    print(f"[Chart] {path1}")

    # ── Chart 2: C++ actual speedup vs Amdahl theoretical — per n ─────────
    fig, ax = plt.subplots(figsize=(10, 6))

    # theoretical Amdahl for largest n
    ts_amdahl = [d[0] for d in amdahl_data]
    theoretical = [d[1] for d in amdahl_data]
    ax.plot(ts_amdahl, theoretical, "k--", label=f"Amdahl theoretical (f={f:.1%})",
            linewidth=2.5, markersize=7)

    # actual speedup lines for several n values
    plot_ns = [n for n in n_list if n >= 5]
    for n in plot_ns:
        base = par_data[(n, 1)]["total"]
        ts = [t for t in thread_list if (n, t) in par_data]
        speedups = [base / par_data[(n, t)]["total"] if par_data[(n, t)]["total"] > 0 else 0 for t in ts]
        ax.plot(ts, speedups, "o-", label=f"Actual n={n}", linewidth=2, markersize=5)

    ax.set_xlabel("Thread count", fontsize=12)
    ax.set_ylabel("Speedup (vs 1 thread)", fontsize=12)
    ax.set_title(f"C++ Parallel Speedup: Actual vs Amdahl's Law", fontsize=13)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    ax.set_xticks(thread_list)

    path2 = os.path.join(PROFILING_DIR, "bench_speedup_vs_amdahl.png")
    fig.tight_layout()
    fig.savefig(path2, dpi=150)
    plt.close(fig)
    print(f"[Chart] {path2}")

    # ── Chart 3: C++ time vs n_signers (one line per thread count) ────────
    fig, ax = plt.subplots(figsize=(10, 6))

    for t in thread_list:
        ys = [par_data[(n, t)]["total"] for n in n_list]
        ax.plot(n_list, ys, "o-", label=f"{t} thread{'s' if t > 1 else ''}",
                linewidth=2, markersize=5)

    ax.set_xlabel("Number of signers (n)", fontsize=12)
    ax.set_ylabel("Total time (ms)", fontsize=12)
    ax.set_title("C++ MuSig2-H: Total Time vs Number of Signers", fontsize=13)
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3)

    path3 = os.path.join(PROFILING_DIR, "bench_cpp_time_vs_signers.png")
    fig.tight_layout()
    fig.savefig(path3, dpi=150)
    plt.close(fig)
    print(f"[Chart] {path3}")


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _print_phase_table(label, all_data, repeats):
    """Print a formatted table of per-phase median timings."""
    header = f"{'n':>4s}"
    for p in ALL_PHASES:
        header += f"  {p:>8s}"
    header += f"  {'total':>8s}"
    print(header)
    print("-" * len(header))

    for n, medians in all_data:
        row = f"{n:>4d}"
        for p in ALL_PHASES:
            v = medians[p]
            row += f"  {v:>7.1f}ms" if v >= 0.1 else f"  {v:>7.3f}ms"
        v = medians["total"]
        row += f"  {v:>7.1f}ms" if v >= 0.1 else f"  {v:>7.3f}ms"
        print(row)

    print()
    print(f"[{label}] Unit: milliseconds, median of {repeats} runs")
    print()


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(description="MuSig2-H benchmark: Python vs C++ (sequential & parallel)")
    ap.add_argument("--warmup", type=int, default=2, help="warmup rounds (default: 2)")
    ap.add_argument("--repeats", type=int, default=5, help="measurement rounds (default: 5)")
    ap.add_argument("--no-chart", action="store_true", help="skip chart generation")
    ap.add_argument("--no-python", action="store_true", help="skip Python benchmarks")
    ap.add_argument("--fast", action="store_true", help="fast mode: reduced sweep, repeats=3")
    args = ap.parse_args()

    if args.fast:
        n_list = SIGNER_COUNTS_FAST
        args.repeats = min(args.repeats, 3)
        args.warmup = min(args.warmup, 1)
    else:
        n_list = SIGNER_COUNTS

    thread_list = THREAD_COUNTS

    print()
    print("+" + "=" * 68 + "+")
    print("|     MuSig2-H Performance Benchmark: Python vs C++                 |")
    print("+" + "=" * 68 + "+")
    print(f"  Signer counts: {n_list}")
    print(f"  Thread counts: {thread_list}")
    print(f"  Warmup: {args.warmup}, Repeats: {args.repeats}")
    print()

    # Init C++
    import fastmusig
    fastmusig.init()

    # Experiment A: Python sequential
    py_data = []
    if not args.no_python:
        py_data = bench_python_sequential(n_list, args.warmup, args.repeats)
    else:
        print("[SKIP] Python sequential benchmark (--no-python)\n")

    # Experiment B: C++ sequential
    cpp_seq_data = bench_cpp_sequential(n_list, args.warmup, args.repeats)

    # Experiment C: C++ parallel
    par_data = bench_cpp_parallel(n_list, thread_list, args.warmup, args.repeats)

    # Experiment D: Amdahl analysis
    n_ref, f, amdahl_data = amdahl_analysis(cpp_seq_data, par_data, thread_list)

    # Speedup summary
    if py_data:
        print_speedup_summary(py_data, cpp_seq_data, par_data, thread_list)

    # Charts
    if not args.no_chart:
        print("=" * 70)
        print("Chart generation")
        print("=" * 70)
        generate_charts(py_data, cpp_seq_data, par_data, thread_list, n_ref, f, amdahl_data)

    print()
    print("Done.")


if __name__ == "__main__":
    main()
