#!/usr/bin/env sage -python
"""
profile_musig2h.py — MuSig2-H 性能分析与 PARI 线程安全 Profiling

四个实验：
  A. 线程崩溃复现（ThreadPoolExecutor → segfault）
  B. 顺序执行基准测试（签名者数量扩展性）
  C. 阶段耗时分解（可并行 vs 顺序占比）
  D. Amdahl's Law 理论加速比分析

用法：从项目根目录运行
  sage -python scripts/profile_musig2h.py [--skip-crash] [--repeats N] [--warmup N]
"""
from __future__ import annotations

import argparse
import os
import statistics
import subprocess
import sys
import time

# 确保从项目根目录导入 src 包
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.crypto.parallel_signing import run_protocol

# ─── 常量 ───────────────────────────────────────────────────────────────────

PARALLEL_PHASES = ["keygen", "presign", "sign"]
SEQUENTIAL_PHASES = ["keyagg", "preagg", "signagg", "verify"]
ALL_PHASES = ["keygen", "keyagg", "presign", "preagg", "sign", "signagg", "verify"]

PROFILING_DIR = os.path.join(os.path.dirname(__file__), "..", "profiling", "part2")


# ═══════════════════════════════════════════════════════════════════════════
# 实验 A：线程崩溃复现
# ═══════════════════════════════════════════════════════════════════════════

def thread_crash_demo(repeats=5):
    """通过 subprocess 调用 worker，统计 ThreadPoolExecutor 崩溃率。"""
    print("=" * 65)
    print("实验 A：PARI 线程安全崩溃复现")
    print("=" * 65)
    print("方法：subprocess 隔离调用 ThreadPoolExecutor 并发构造 Signer")
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
    print("cysignals 捕获 SIGSEGV 后抛出 SignalError，进程以 exit code 1 终止。")
    print("根因：PARI 全局栈 (avma) 无锁保护，多线程并发写入导致内存损坏。")
    print()
    return results


# ═══════════════════════════════════════════════════════════════════════════
# 实验 B：顺序执行基准测试
# ═══════════════════════════════════════════════════════════════════════════

def bench_scalability(n_list, warmup=2, repeats=5):
    """测量不同签名者数量下各阶段的中位数耗时。"""
    print("=" * 65)
    print("实验 B：顺序执行基准测试（签名者数量扩展性）")
    print("=" * 65)
    print(f"参数：warmup={warmup}, repeats={repeats}, seed=42")
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

    # 打印表格
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
    print("单位：毫秒（ms），取 5 次运行的中位数")
    print()
    return all_data


# ═══════════════════════════════════════════════════════════════════════════
# 实验 C：阶段耗时分解
# ═══════════════════════════════════════════════════════════════════════════

def phase_breakdown(all_data):
    """从扩展性数据中分析可并行 vs 顺序阶段的占比。"""
    print("=" * 65)
    print("实验 C：阶段耗时分解（可并行 vs 顺序）")
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
# 实验 D：Amdahl's Law 理论加速比
# ═══════════════════════════════════════════════════════════════════════════

def amdahl_analysis(breakdown_data):
    """
    计算理论并行加速比 vs 实际（始终 1x）。

    理论依据：Amdahl's Law
      S(n) = 1 / ((1-f) + f/n)
    参考：G. M. Amdahl, "Validity of the Single Processor Approach to
    Achieving Large Scale Computing Capabilities", AFIPS 1967, pp. 483-485.
    """
    print("=" * 65)
    print("实验 D：Amdahl's Law 理论加速比分析")
    print("=" * 65)
    print()

    # 用最大 n 的数据来计算并行比例（最稳定）
    n_ref, t_par, t_seq, t_total, f_pct = breakdown_data[-1]
    f = t_par / t_total if t_total > 0 else 0

    print(f"参考数据点：n={n_ref}")
    print(f"可并行比例 f = {f:.4f} ({f_pct:.1f}%)")
    print(f"顺序比例 1-f = {1 - f:.4f} ({100 - f_pct:.1f}%)")
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
    print("Actual 始终为 1.00x：PARI 全局栈非线程安全，无法并行。")
    print()
    return f, amdahl_data


# ═══════════════════════════════════════════════════════════════════════════
# 图表生成
# ═══════════════════════════════════════════════════════════════════════════

def generate_charts(all_data, f, amdahl_data):
    """用 matplotlib 生成 PNG 图表到 profiling/part2/。"""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("[WARN] matplotlib 不可用，跳过图表生成")
        return

    os.makedirs(PROFILING_DIR, exist_ok=True)

    # ── 图 1：扩展性（签名者数量 vs 各阶段耗时）──────────────────────
    fig, ax = plt.subplots(figsize=(10, 6))

    ns = [d[0] for d in all_data]

    # 可并行阶段用实线，顺序阶段用虚线
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
    print(f"[Chart] 扩展性图表已保存：{path1}")

    # ── 图 2：Amdahl's Law ────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(8, 5))

    workers = [d[0] for d in amdahl_data]
    theoretical = [d[1] for d in amdahl_data]
    actual = [d[2] for d in amdahl_data]

    ax.plot(workers, theoretical, "o-", label=f"Theoretical (f={f:.1%})", linewidth=2, color="tab:blue")
    ax.plot(workers, actual, "s--", label="Actual (PARI limitation)", linewidth=2, color="tab:red")

    # 填充"损失"区域
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
    print(f"[Chart] Amdahl 图表已保存：{path2}")


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(description="MuSig2-H profiling & PARI thread safety analysis")
    ap.add_argument("--skip-crash", action="store_true", help="跳过线程崩溃实验（加快调试）")
    ap.add_argument("--warmup", type=int, default=2, help="预热轮数（默认 2）")
    ap.add_argument("--repeats", type=int, default=5, help="测量轮数（默认 5）")
    ap.add_argument("--no-chart", action="store_true", help="跳过图表生成")
    args = ap.parse_args()

    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║     MuSig2-H 性能分析 & PARI 线程安全 Profiling            ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()

    # 实验 A
    if not args.skip_crash:
        thread_crash_demo(repeats=5)
    else:
        print("[SKIP] 线程崩溃实验（--skip-crash）\n")

    # 实验 B
    n_list = [1, 2, 3, 5, 8, 10, 15, 20]
    all_data = bench_scalability(n_list, warmup=args.warmup, repeats=args.repeats)

    # 实验 C
    breakdown_data = phase_breakdown(all_data)

    # 实验 D
    f, amdahl_data = amdahl_analysis(breakdown_data)

    # 图表
    if not args.no_chart:
        print("=" * 65)
        print("图表生成")
        print("=" * 65)
        generate_charts(all_data, f, amdahl_data)

    print()
    print("Done.")


if __name__ == "__main__":
    main()
