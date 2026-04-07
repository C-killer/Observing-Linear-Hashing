#!/usr/bin/env sage -python
"""
thread_crash_worker.py — 线程安全崩溃复现脚本

被 profile_musig2h.py 通过 subprocess 调用。
在 ThreadPoolExecutor 中并发构造 Signer 对象，
预期触发 PARI 全局栈并发写入 → Segmentation fault。

用法：sage -python scripts/thread_crash_worker.py <n_signers> <n_threads>
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from concurrent.futures import ThreadPoolExecutor, as_completed

from src.crypto.signer import Signer


def create_signer(seed):
    """在线程中构造 Signer（触发 PARI ellmul）。"""
    return Signer(seed=seed)


def main():
    n_signers = int(sys.argv[1])
    n_threads = int(sys.argv[2])

    with ThreadPoolExecutor(max_workers=n_threads) as pool:
        futures = [pool.submit(create_signer, i) for i in range(n_signers)]
        for f in as_completed(futures):
            f.result()

    # 如果到这里说明没崩溃（极不可能）
    print("NO_CRASH")
    sys.exit(0)


if __name__ == "__main__":
    main()
