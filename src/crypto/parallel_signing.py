"""
MuSig2-H parallel signing coordinator.

Demonstrates the two-phase parallel structure of the protocol, using Signer objects
to encapsulate each participant, with timing for each phase.

Note: SageMath's underlying PARI library is not thread-safe; concurrent calls will segfault.
Therefore, parallelizable phases are simulated sequentially here, but the code structure
and comments clearly mark which steps can be parallelized in a real deployment
(each signer executes independently, no data dependencies).
For true parallelism, use C++ (RELIC) multithreading or multiprocessing + serialization.
"""

import time

from src.crypto.signer import Signer
from src.crypto.musig2h import key_agg_ex, preagg, sign_agg, ver


def run_protocol(n_signers, message, seed=42):
    """
    Run n-party MuSig2-H signing protocol.

    n_signers:   number of signers
    message:     message to sign (bytes)
    seed:        random seed (int), for reproducibility

    Returns dict:
      sigma    — final signature (R, (s0, s1))
      apk      — aggregated public key
      verified — verification result (bool)
      n_signers— number of signers
      timing   — per-phase timing (seconds)

    Internal flow:
      1. KeyGen × n        ← parallelizable: each signer generates keys independently
      2. KeyAgg            ← sequential: aggregate after collecting all public keys
      3. PreSign × n       ← parallelizable: each signer generates nonces independently
      4. PreAgg            ← sequential: sync point 1, aggregate nonces
      5. Sign × n          ← parallelizable: each signer computes partial signature independently
      6. SignAgg           ← sequential: sync point 2, aggregate signatures
      7. Ver               ← sequential: verify
    """
    timing = {}

    # 1. KeyGen × n ← parallelizable: each signer generates keys independently
    t0 = time.perf_counter()
    signers = [Signer(seed=seed + i) for i in range(n_signers)]
    timing["keygen"] = time.perf_counter() - t0

    # 2. KeyAgg ← sequential: aggregate after collecting all public keys
    t0 = time.perf_counter()
    all_pks = [s.pk for s in signers]
    apk, coeffs = key_agg_ex(all_pks)
    for s in signers:
        s.set_peers([pk for pk in all_pks if pk != s.pk])
        s.set_agg_key(apk, coeffs[s.pk])
    timing["keyagg"] = time.perf_counter() - t0

    # 3. PreSign × n ← parallelizable: each signer generates nonces independently
    t0 = time.perf_counter()
    pp_list = [s.presign() for s in signers]
    timing["presign"] = time.perf_counter() - t0

    # 4. PreAgg ← sequential: sync point 1, aggregate nonces
    t0 = time.perf_counter()
    app = preagg(pp_list)
    for s in signers:
        s.receive_agg_nonce(app)
    timing["preagg"] = time.perf_counter() - t0

    # 5. Sign × n ← parallelizable: each signer computes partial signature independently
    t0 = time.perf_counter()
    outs = [s.sign(message) for s in signers]
    timing["sign"] = time.perf_counter() - t0

    # 6. SignAgg ← sequential: sync point 2, aggregate signatures
    t0 = time.perf_counter()
    sigma = sign_agg(outs)
    timing["signagg"] = time.perf_counter() - t0

    # 7. Ver ← sequential: verify
    t0 = time.perf_counter()
    verified = ver(apk, message, sigma)
    timing["verify"] = time.perf_counter() - t0

    timing["total"] = sum(timing.values())

    return {
        "sigma": sigma,
        "apk": apk,
        "verified": verified,
        "n_signers": n_signers,
        "timing": timing,
    }


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="MuSig2-H parallel signing protocol simulation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n"
               "  sage -python -m src.crypto.parallel_signing -n 5\n"
               "  sage -python -m src.crypto.parallel_signing -n 3 -m 'vote yes'\n"
               "  sage -python -m src.crypto.parallel_signing -n 10 -s 0\n",
    )
    parser.add_argument("-n", "--n-signers", type=int, default=3,
                        help="number of signers (default: 3)")
    parser.add_argument("-m", "--message", type=str, default="Hello MuSig2-H",
                        help="message to sign (default: 'Hello MuSig2-H')")
    parser.add_argument("-s", "--seed", type=int, default=42,
                        help="random seed (default: 42)")

    args = parser.parse_args()
    n = args.n_signers
    msg = args.message.encode()

    print(f"=== MuSig2-H Parallel Signing Simulation ===")
    print(f"Number of signers: {n}")
    print(f"Message: {msg}")
    print(f"Random seed: {args.seed}")
    print()

    result = run_protocol(n, msg, seed=args.seed)

    labels = {
        "keygen":  f"{n} signers (parallelizable)",
        "keyagg":  "aggregate pubkeys",
        "presign": f"{n} signers (parallelizable)",
        "preagg":  "aggregate nonces",
        "sign":    f"{n} signers (parallelizable)",
        "signagg": "aggregate signatures",
        "verify":  "verify",
    }
    for step, label in labels.items():
        t = result["timing"][step]
        print(f"[{step:8s}]  {label:14s} ... {t:.3f}s")

    print()
    status = "PASSED" if result["verified"] else "FAILED"
    print(f"Verification: {status}")
    print(f"Total time: {result['timing']['total']:.3f}s")
    print()
    print("Hint: make run-part2 ARGS=\"-h\" to see all parameters")
    print("Example: make run-part2 ARGS=\"-n 5 -m 'vote yes' -s 0\"")


if __name__ == "__main__":
    main()
