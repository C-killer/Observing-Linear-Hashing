"""parallel_signing.py 的单元测试：验证并行协议的正确性和可复现性。"""

from src.crypto.parallel_signing import run_protocol


TIMING_KEYS = ["keygen", "keyagg", "presign", "preagg", "sign", "signagg", "verify", "total"]


# ═══════════════════════════════════════════
#  正确性
# ═══════════════════════════════════════════

class TestParallelCorrectness:
    """并行协议在不同签名者数量下都能验证通过。"""

    def test_1_signer(self):
        r = run_protocol(1, b"1-signer", seed=100)
        assert r["verified"]

    def test_2_signers(self):
        r = run_protocol(2, b"2-signers", seed=200)
        assert r["verified"]

    def test_3_signers(self):
        r = run_protocol(3, b"3-signers", seed=300)
        assert r["verified"]

    def test_5_signers(self):
        r = run_protocol(5, b"5-signers", seed=500)
        assert r["verified"]


# ═══════════════════════════════════════════
#  返回结构
# ═══════════════════════════════════════════

class TestReturnStructure:
    """返回字典包含所有预期字段。"""

    def test_timing_keys(self):
        r = run_protocol(2, b"check-timing", seed=42)
        for key in TIMING_KEYS:
            assert key in r["timing"], f"timing 缺少 {key}"

    def test_all_timings_positive(self):
        r = run_protocol(2, b"check-positive", seed=42)
        for key in TIMING_KEYS:
            assert r["timing"][key] >= 0

    def test_result_fields(self):
        r = run_protocol(2, b"check-fields", seed=42)
        assert "sigma" in r
        assert "apk" in r
        assert "verified" in r
        assert "n_signers" in r
        assert r["n_signers"] == 2


# ═══════════════════════════════════════════
#  可复现性
# ═══════════════════════════════════════════

class TestReproducibility:
    """同种子同结果。"""

    def test_same_seed_same_signature(self):
        r1 = run_protocol(3, b"reproducible", seed=777)
        r2 = run_protocol(3, b"reproducible", seed=777)
        assert r1["sigma"] == r2["sigma"]
        assert r1["apk"] == r2["apk"]


# ═══════════════════════════════════════════
#  安全性
# ═══════════════════════════════════════════

class TestParallelSecurity:
    """并行签名结果对错误消息验证失败。"""

    def test_wrong_message_fails(self):
        r = run_protocol(3, b"correct message", seed=42)
        from src.crypto.musig2h import ver
        assert not ver(r["apk"], b"wrong message", r["sigma"])
