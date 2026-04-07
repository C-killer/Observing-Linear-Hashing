#!/usr/bin/env sage -python
"""
thread_crash_worker.py — Thread safety crash reproduction script

Called by profile_musig2h.py via subprocess.
Constructs Signer objects concurrently in ThreadPoolExecutor,
expected to trigger PARI global stack concurrent writes → Segmentation fault.

Usage: sage -python scripts/thread_crash_worker.py <n_signers> <n_threads>
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from concurrent.futures import ThreadPoolExecutor, as_completed

from src.crypto.signer import Signer


def create_signer(seed):
    """Construct Signer in a thread (triggers PARI ellmul)."""
    return Signer(seed=seed)


def main():
    n_signers = int(sys.argv[1])
    n_threads = int(sys.argv[2])

    with ThreadPoolExecutor(max_workers=n_threads) as pool:
        futures = [pool.submit(create_signer, i) for i in range(n_signers)]
        for f in as_completed(futures):
            f.result()

    # if we reach here it means no crash (extremely unlikely)
    print("NO_CRASH")
    sys.exit(0)


if __name__ == "__main__":
    main()
