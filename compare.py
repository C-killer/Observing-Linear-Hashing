#!/usr/bin/env python3
# compare.py
from __future__ import annotations

import argparse
import random
import statistics
import time
from typing import Callable, List, Tuple

from src.hashing.linear_f2 import HashF2Python, HashF2Cpp


def bench(name: str, fn: Callable[[int], int], xs: List[int], warmup: int, repeats: int) -> Tuple[float, List[float]]:
    """
    Return (median_ns_per_op, times_sec_list)
    """
    # warmup (not timed)
    for _ in range(warmup):
        for x in xs:
            fn(x)

    times = []
    n = len(xs)
    for _ in range(repeats):
        t0 = time.perf_counter_ns()
        for x in xs:
            fn(x)
        t1 = time.perf_counter_ns()
        times.append((t1 - t0) / 1e9)

    ns_per_op = [(t * 1e9) / n for t in times]
    return statistics.median(ns_per_op), times

def bench_batch(name: str, fn_many: Callable[[List[int]], List[int]], xs: List[int], warmup: int, repeats: int) -> Tuple[float, List[float]]:
    """
    fn_many takes the whole list once and returns list once.
    Return (median_ns_per_op, times_sec_list)
    """
    for _ in range(warmup):
        fn_many(xs)

    times = []
    n = len(xs)
    for _ in range(repeats):
        t0 = time.perf_counter_ns()
        fn_many(xs)
        t1 = time.perf_counter_ns()
        times.append((t1 - t0) / 1e9)

    ns_per_op = [(t * 1e9) / n for t in times]
    return statistics.median(ns_per_op), times


def format_times(times: List[float]) -> str:
    return ", ".join(f"{t:.6f}s" for t in times)


def main():
    ap = argparse.ArgumentParser(description="Compare HashF2 Python vs C++ (pybind) throughput.")
    ap.add_argument("--u", type=int, default=100, help="input bit-width u")
    ap.add_argument("--l", type=int, default=10, help="output bit-width l")
    ap.add_argument("--n", type=int, default=200_000, help="number of hash calls per run")
    ap.add_argument("--seed", type=int, default=12345, help="seed for input generation and hash init")
    ap.add_argument("--warmup", type=int, default=1, help="warmup runs (not timed)")
    ap.add_argument("--repeats", type=int, default=5, help="timed repeats")
    ap.add_argument("--no-cpp", action="store_true", help="skip C++ benchmark")
    args = ap.parse_args()

    u, l, n = args.u, args.l, args.n
    if u <= 0 or l <= 0 or n <= 0:
        raise SystemExit("u, l, n must be positive integers")

    rng = random.Random(args.seed)
    xs = [rng.getrandbits(u) for _ in range(n)]

    # Build hashers
    py_hasher = HashF2Python(l=l, u=u, seed=args.seed)
    py_fn = py_hasher.h

    print(f"=== Benchmark: u={u}, l={l}, n={n}, seed={args.seed} ===")
    py_median_ns, py_times = bench("py", py_fn, xs, args.warmup, args.repeats)
    py_mops = 1e3 / py_median_ns  # (1e9 ns/s) / ns/op / 1e6 = 1e3/ns
    print(f"[PY ] times: {format_times(py_times)}")
    print(f"[PY ] median: {py_median_ns:.1f} ns/op  =>  {py_mops:.3f} M ops/s")

    if args.no_cpp:
        return

    # C++ backend (requires import fasthash)
    try:
        cpp_hasher = HashF2Cpp(l=l, u=u, seed=args.seed)
    except ModuleNotFoundError as e:
        print("\n[C++] ERROR: cannot import 'fasthash'.")
        print("      Fix by making fasthash visible to Python, e.g.:")
        print("        export PYTHONPATH=\"$(pwd)/src/cpp/build:${PYTHONPATH}\"")
        print("      or output the .so to project root and rebuild.")
        raise

    cpp_fn = cpp_hasher.h
    cpp_median_ns, cpp_times = bench("cpp", cpp_fn, xs, args.warmup, args.repeats)
    cpp_mops = 1e3 / cpp_median_ns
    speedup = py_median_ns / cpp_median_ns if cpp_median_ns > 0 else float("inf")
    print(f"\n[C++ Single] times: {format_times(cpp_times)}")
    print(f"[C++Single] median: {cpp_median_ns:.1f} ns/op  =>  {cpp_mops:.3f} M ops/s")
    print(f"\nSpeedup (C++ Single over PY): {speedup:.2f}x")

    try:
        cpp_hasher = HashF2Cpp(l=l, u=u, seed=args.seed)
    except ModuleNotFoundError as e:
        print("\n[C++] ERROR: cannot import 'fasthash'.")
        print("      Fix by making fasthash visible to Python, e.g.:")
        print("        export PYTHONPATH=\"$(pwd)/src/cpp/build:${PYTHONPATH}\"")
        print("      or output the .so to project root and rebuild.")
        raise

    cpp_fn = cpp_hasher.h
    cpp_median_ns, cpp_times = bench_batch("cpp", cpp_hasher.h_many, xs, args.warmup, args.repeats)
    cpp_mops = 1e3 / cpp_median_ns
    speedup = py_median_ns / cpp_median_ns if cpp_median_ns > 0 else float("inf")
    print(f"\n[C++ Batch] times: {format_times(cpp_times)}")
    print(f"[C++ Batch] median: {cpp_median_ns:.1f} ns/op  =>  {cpp_mops:.3f} M ops/s")
    print(f"\nSpeedup (C++ Batch over PY): {speedup:.2f}x")


if __name__ == "__main__":
    main()
