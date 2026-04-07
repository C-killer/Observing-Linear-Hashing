#!/usr/bin/env sage -python
"""
profile_cpu_runner.py — cProfile CPU profiling

Generates .prof file + terminal top 20 hotspot function list.
Can be converted to SVG flame graph with flameprof.

Usage:
  sage -python scripts/profile_cpu_runner.py
  flameprof profiling/part2/profile_musig2h.prof > profiling/part2/profile_musig2h.svg
"""

import cProfile
import os
import pstats
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

PROF_DIR = os.path.join(os.path.dirname(__file__), "..", "profiling", "part2")
PROF_FILE = os.path.join(PROF_DIR, "profile_musig2h.prof")


def main():
    os.makedirs(PROF_DIR, exist_ok=True)

    # import outside profiler to avoid sage initialization overhead polluting results
    from src.crypto.parallel_signing import run_protocol

    # warmup (outside profiler)
    print("[cProfile] warmup ...")
    run_protocol(5, b"warmup", seed=0)

    # profiling
    print("[cProfile] profiling ... (n=10, repeats=5)")
    profiler = cProfile.Profile()
    profiler.enable()
    for i in range(5):
        run_protocol(10, b"cpu-profiling", seed=42 + i)
    profiler.disable()

    # save binary .prof file (can be visualized with flameprof / snakeviz)
    profiler.dump_stats(PROF_FILE)
    print(f"[cProfile] saved: {PROF_FILE}")

    # terminal output top 20 hotspot functions
    print()
    print("=" * 70)
    print("Top 20 hotspot functions (sorted by cumulative time)")
    print("=" * 70)
    stats = pstats.Stats(profiler)
    stats.sort_stats("cumulative")
    stats.print_stats(20)

    print("=" * 70)
    print("Top 20 hotspot functions (sorted by self time)")
    print("=" * 70)
    stats.sort_stats("tottime")
    stats.print_stats(20)

    # try to generate SVG flame graph
    try:
        import flameprof
        svg_path = os.path.join(PROF_DIR, "profile_musig2h.svg")
        os.system(f"flameprof {PROF_FILE} > {svg_path}")
        print(f"\n[Done] Flame graph saved: {svg_path}")
    except ImportError:
        print("\n[Info] Install flameprof to generate SVG flame graph:")
        print(f"  pip install flameprof")
        print(f"  flameprof {PROF_FILE} > profiling/part2/profile_musig2h.svg")


if __name__ == "__main__":
    main()
