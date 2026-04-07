#!/usr/bin/env sage -python
"""
profile_cpu_runner.py — cProfile CPU 性能采集

生成 .prof 文件 + 终端 top 20 热点函数列表。
配合 flameprof 可转为 SVG 火焰图。

用法：
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

    # import 在 profiler 外，避免 sage 初始化开销污染结果
    from src.crypto.parallel_signing import run_protocol

    # warmup（profiler 外）
    print("[cProfile] warmup ...")
    run_protocol(5, b"warmup", seed=0)

    # 正式采集
    print("[cProfile] 采集中 ... (n=10, repeats=5)")
    profiler = cProfile.Profile()
    profiler.enable()
    for i in range(5):
        run_protocol(10, b"cpu-profiling", seed=42 + i)
    profiler.disable()

    # 保存二进制 .prof 文件（可用 flameprof / snakeviz 可视化）
    profiler.dump_stats(PROF_FILE)
    print(f"[cProfile] 已保存：{PROF_FILE}")

    # 终端输出 top 20 热点函数
    print()
    print("=" * 70)
    print("Top 20 热点函数（按累计时间排序）")
    print("=" * 70)
    stats = pstats.Stats(profiler)
    stats.sort_stats("cumulative")
    stats.print_stats(20)

    print("=" * 70)
    print("Top 20 热点函数（按自身时间排序）")
    print("=" * 70)
    stats.sort_stats("tottime")
    stats.print_stats(20)

    # 尝试生成 SVG 火焰图
    try:
        import flameprof
        svg_path = os.path.join(PROF_DIR, "profile_musig2h.svg")
        os.system(f"flameprof {PROF_FILE} > {svg_path}")
        print(f"\n[Done] 火焰图已保存：{svg_path}")
    except ImportError:
        print("\n[Info] 安装 flameprof 可生成 SVG 火焰图：")
        print(f"  pip install flameprof")
        print(f"  flameprof {PROF_FILE} > profiling/part2/profile_musig2h.svg")


if __name__ == "__main__":
    main()
