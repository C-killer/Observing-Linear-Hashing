"""
MuSig2-H 并行签名协调器。

演示协议的两阶段并行结构，内部使用 Signer 对象封装各参与方，
计时展示各阶段耗时。

注：SageMath 的 PARI 底层库非线程安全，并发调用会 segfault，
因此可并行的阶段在此以顺序执行模拟，但代码结构和注释清楚标注了
哪些步骤在真实部署中可以并行（每个签名者独立执行，无数据依赖）。
如需真正并行，可通过 C++ (RELIC) 多线程或多进程+序列化实现。
"""

import time

from src.crypto.signer import Signer
from src.crypto.musig2h import key_agg, preagg, sign_agg, ver


def run_protocol(n_signers, message, seed=42):
    """
    运行 n 人 MuSig2-H 签名协议。

    n_signers:   签名者数量
    message:     待签消息 (bytes)
    seed:        随机种子（int），保证可复现

    返回字典：
      sigma    — 最终签名 (R, (s0, s1))
      apk      — 聚合公钥
      verified — 验证结果 (bool)
      n_signers— 签名者数量
      timing   — 各阶段耗时 (秒)

    内部流程：
      ① KeyGen × n        ← 可并行：每人独立生成密钥
      ② KeyAgg            ← 顺序：收集所有公钥后聚合
      ③ PreSign × n       ← 可并行：每人独立生成 nonce
      ④ PreAgg            ← 顺序：同步点 1，聚合 nonce
      ⑤ Sign × n          ← 可并行：每人独立算部分签名
      ⑥ SignAgg           ← 顺序：同步点 2，聚合签名
      ⑦ Ver               ← 顺序：验证
    """
    timing = {}

    # ① KeyGen × n ← 可并行：每人独立生成密钥，互不依赖
    t0 = time.perf_counter()
    signers = [Signer(seed=seed + i) for i in range(n_signers)]
    timing["keygen"] = time.perf_counter() - t0

    # ② KeyAgg ← 顺序：收集所有公钥后聚合
    t0 = time.perf_counter()
    all_pks = [s.pk for s in signers]
    apk = key_agg(all_pks)
    for s in signers:
        s.set_peers([pk for pk in all_pks if pk != s.pk])
    timing["keyagg"] = time.perf_counter() - t0

    # ③ PreSign × n ← 可并行：每人独立生成 nonce，互不依赖
    t0 = time.perf_counter()
    pp_list = [s.presign() for s in signers]
    timing["presign"] = time.perf_counter() - t0

    # ④ PreAgg ← 顺序：同步点 1，聚合 nonce
    t0 = time.perf_counter()
    app = preagg(pp_list)
    for s in signers:
        s.receive_agg_nonce(app)
    timing["preagg"] = time.perf_counter() - t0

    # ⑤ Sign × n ← 可并行：每人独立算部分签名，互不依赖
    t0 = time.perf_counter()
    outs = [s.sign(message) for s in signers]
    timing["sign"] = time.perf_counter() - t0

    # ⑥ SignAgg ← 顺序：同步点 2，聚合签名
    t0 = time.perf_counter()
    sigma = sign_agg(outs)
    timing["signagg"] = time.perf_counter() - t0

    # ⑦ Ver ← 顺序：验证
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
        description="MuSig2-H 并行签名协议模拟",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例：\n"
               "  sage -python -m src.crypto.parallel_signing -n 5\n"
               "  sage -python -m src.crypto.parallel_signing -n 3 -m 'vote yes'\n"
               "  sage -python -m src.crypto.parallel_signing -n 10 -s 0\n",
    )
    parser.add_argument("-n", "--n-signers", type=int, default=3,
                        help="签名者数量（默认 3）")
    parser.add_argument("-m", "--message", type=str, default="Hello MuSig2-H",
                        help="待签消息（默认 'Hello MuSig2-H'）")
    parser.add_argument("-s", "--seed", type=int, default=42,
                        help="随机种子（默认 42）")

    args = parser.parse_args()
    n = args.n_signers
    msg = args.message.encode()

    print(f"=== MuSig2-H 并行签名模拟 ===")
    print(f"签名者数量：{n}")
    print(f"消息：{msg}")
    print(f"随机种子：{args.seed}")
    print()

    result = run_protocol(n, msg, seed=args.seed)

    labels = {
        "keygen":  f"{n} 人（可并行）",
        "keyagg":  "聚合公钥",
        "presign": f"{n} 人（可并行）",
        "preagg":  "聚合 nonce",
        "sign":    f"{n} 人（可并行）",
        "signagg": "聚合签名",
        "verify":  "验证",
    }
    for step, label in labels.items():
        t = result["timing"][step]
        print(f"[{step:8s}]  {label:14s} ... {t:.3f}s")

    print()
    status = "通过" if result["verified"] else "失败"
    print(f"验证结果：{status}")
    print(f"总耗时：{result['timing']['total']:.3f}s")
    print()
    print("提示：make run-part2 ARGS=\"-h\" 查看所有参数")
    print("示例：make run-part2 ARGS=\"-n 5 -m 'vote yes' -s 0\"")


if __name__ == "__main__":
    main()
