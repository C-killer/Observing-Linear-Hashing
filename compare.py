#!/usr/bin/env python3
# compare.py
from __future__ import annotations

import argparse
import random
import statistics
import time
from typing import Callable, List, Tuple, Optional

from src.hashing.linear_f2 import HashF2Python, HashF2Cpp


def bench_single(fn: Callable[[int], int], xs: List[int], warmup: int, repeats: int) -> Tuple[float, List[float]]:
    """
    Measure per-element hashing via per-call function fn(x).
    Return (median_ns_per_op, times_sec_list).
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


def bench_batch(fn_many: Callable[[List[int]], List[int]], xs: List[int], warmup: int, repeats: int) -> Tuple[float, List[float]]:
    """
    Measure hashing via batch function fn_many(xs)->list.
    Return (median_ns_per_op, times_sec_list).
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


def mops_from_ns_per_op(ns_per_op: float) -> float:
    # (1e9 ns/s) / (ns/op) / 1e6 = 1e3/ns
    return 1e3 / ns_per_op


def safe_speedup(base_ns: float, new_ns: float) -> float:
    if new_ns <= 0:
        return float("inf")
    return base_ns / new_ns


def ensure_h_many(obj) -> Callable[[List[int]], List[int]]:
    """
    Return a batch callable. Prefer obj.h_many if present; otherwise fallback to python loop over obj.h.
    """
    if hasattr(obj, "h_many") and callable(getattr(obj, "h_many")):
        return obj.h_many  # type: ignore[return-value]
    # fallback: wrap single-call h
    h = obj.h
    return lambda xs: [h(x) for x in xs]


def print_block(title: str, times: List[float], median_ns: float) -> None:
    mops = mops_from_ns_per_op(median_ns)
    print(f"{title} times: {format_times(times)}")
    print(f"{title} median: {median_ns:.1f} ns/op  =>  {mops:.3f} M ops/s")


def main():
    ap = argparse.ArgumentParser(description="Compare HashF2 Python vs C++ (pybind) throughput.")
    ap.add_argument("--u", type=int, default=100, help="input bit-width u")
    ap.add_argument("--l", type=int, default=10, help="output bit-width l")
    ap.add_argument("--n", type=int, default=200_000, help="number of inputs per run")
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

    print(f"=== Benchmark: u={u}, l={l}, n={n}, seed={args.seed} ===")

    # Python hasher
    py_hasher = HashF2Python(l=l, u=u, seed=args.seed)
    py_single = py_hasher.h
    py_batch = getattr(py_hasher, "h_many", None)
    if not callable(py_batch):
        py_batch = lambda xs_: [py_single(x) for x in xs_]  # type: ignore[assignment]

    py_single_ns, py_single_times = bench_single(py_single, xs, args.warmup, args.repeats)
    print_block("[PY  single]", py_single_times, py_single_ns)

    py_batch_ns, py_batch_times = bench_batch(py_batch, xs, args.warmup, args.repeats)  # type: ignore[arg-type]
    print_block("[PY  batch ]", py_batch_times, py_batch_ns)

    if args.no_cpp:
        return

    # C++ hasher
    try:
        cpp_hasher = HashF2Cpp(l=l, u=u, seed=args.seed)
    except ModuleNotFoundError:
        print("\n[C++] ERROR: cannot import 'fasthash'.")
        print("      Make sure you built the extension for THIS python and it's importable.")
        print("      Recommended: build into repo root, then run: python -m pytest / python compare.py")
        raise

    cpp_single = cpp_hasher.h
    cpp_batch = ensure_h_many(cpp_hasher)

    cpp_single_ns, cpp_single_times = bench_single(cpp_single, xs, args.warmup, args.repeats)
    print_block("[C++ single]", cpp_single_times, cpp_single_ns)

    cpp_batch_ns, cpp_batch_times = bench_batch(cpp_batch, xs, args.warmup, args.repeats)
    print_block("[C++ batch ]", cpp_batch_times, cpp_batch_ns)

    # speedups
    print("\n=== Speedups ===")
    print(f"C++ single over PY single: {safe_speedup(py_single_ns, cpp_single_ns):.2f}x")
    print(f"C++ batch  over PY single: {safe_speedup(py_single_ns, cpp_batch_ns):.2f}x")
    print(f"C++ single over PY batch : {safe_speedup(py_batch_ns, cpp_single_ns):.2f}x")
    print(f"C++ batch  over PY batch : {safe_speedup(py_batch_ns, cpp_batch_ns):.2f}x")


if __name__ == "__main__":
    main()
