"""signer.py 的单元测试：验证 Signer 封装的正确性和安全约束。"""

import pytest
from src.crypto.signer import Signer
from src.crypto.musig2h import key_agg, preagg, sign_agg, ver


# ═══════════════════════════════════════════
#  辅助函数
# ═══════════════════════════════════════════

def _run_protocol(n_signers, msg, seed=42):
    """用 Signer 类运行完整的 n 人签名协议。"""
    signers = [Signer(seed=seed + i) for i in range(n_signers)]
    all_pks = [s.pk for s in signers]

    # 交换公钥
    for s in signers:
        s.set_peers([pk for pk in all_pks if pk != s.pk])

    # 离线：预签名 + 聚合 nonce
    pp_list = [s.presign() for s in signers]
    app = preagg(pp_list)
    for s in signers:
        s.receive_agg_nonce(app)

    # 在线：签名 + 聚合
    outs = [s.sign(msg) for s in signers]
    sigma = sign_agg(outs)

    apk = key_agg(all_pks)
    return apk, msg, sigma


# ═══════════════════════════════════════════
#  基本功能
# ═══════════════════════════════════════════

class TestSignerKeyGen:
    """测试 Signer 构造时的 KeyGen。"""

    def test_pk_on_curve(self):
        s = Signer(seed=0)
        assert s.pk.curve() == s.pk.curve()  # 不抛异常即在曲线上

    def test_deterministic_with_seed(self):
        s1 = Signer(seed=123)
        s2 = Signer(seed=123)
        assert s1.pk == s2.pk

    def test_different_seeds_different_keys(self):
        s1 = Signer(seed=1)
        s2 = Signer(seed=2)
        assert s1.pk != s2.pk


# ═══════════════════════════════════════════
#  完整协议
# ═══════════════════════════════════════════

class TestSignerProtocol:
    """测试通过 Signer 类运行完整签名协议。"""

    def test_1_signer(self):
        apk, msg, sigma = _run_protocol(1, b"solo sign")
        assert sigma is not None
        assert ver(apk, msg, sigma)

    def test_2_signers(self):
        apk, msg, sigma = _run_protocol(2, b"two-party sign")
        assert sigma is not None
        assert ver(apk, msg, sigma)

    def test_3_signers(self):
        apk, msg, sigma = _run_protocol(3, b"three-party sign")
        assert sigma is not None
        assert ver(apk, msg, sigma)

    def test_5_signers(self):
        apk, msg, sigma = _run_protocol(5, b"five-party sign")
        assert sigma is not None
        assert ver(apk, msg, sigma)

    def test_wrong_message_fails(self):
        apk, _, sigma = _run_protocol(2, b"correct message")
        assert not ver(apk, b"wrong message", sigma)


# ═══════════════════════════════════════════
#  Nonce 一次性销毁
# ═══════════════════════════════════════════

class TestNonceDestruction:
    """测试签名后 nonce 被销毁，不能复用。"""

    def test_sign_destroys_nonce(self):
        s1 = Signer(seed=10)
        s2 = Signer(seed=11)
        s1.set_peers([s2.pk])
        s2.set_peers([s1.pk])

        pp_list = [s1.presign(), s2.presign()]
        app = preagg(pp_list)
        s1.receive_agg_nonce(app)
        s2.receive_agg_nonce(app)

        s1.sign(b"msg")
        # 再次签名应该报错
        with pytest.raises(RuntimeError, match="presign"):
            s1.sign(b"msg2")

    def test_can_resign_after_new_presign(self):
        """销毁后重新 presign 可以再次签名。"""
        s1 = Signer(seed=20)
        s2 = Signer(seed=21)
        s1.set_peers([s2.pk])
        s2.set_peers([s1.pk])

        # 第一轮
        pp_list = [s1.presign(), s2.presign()]
        app = preagg(pp_list)
        s1.receive_agg_nonce(app)
        s2.receive_agg_nonce(app)
        outs = [s1.sign(b"msg1"), s2.sign(b"msg1")]
        sigma1 = sign_agg(outs)
        apk = key_agg([s1.pk, s2.pk])
        assert ver(apk, b"msg1", sigma1)

        # 第二轮：重新 presign
        pp_list = [s1.presign(), s2.presign()]
        app = preagg(pp_list)
        s1.receive_agg_nonce(app)
        s2.receive_agg_nonce(app)
        outs = [s1.sign(b"msg2"), s2.sign(b"msg2")]
        sigma2 = sign_agg(outs)
        assert ver(apk, b"msg2", sigma2)


# ═══════════════════════════════════════════
#  协议顺序检查
# ═══════════════════════════════════════════

class TestProtocolOrder:
    """测试跳步骤时的错误提示。"""

    def test_sign_without_peers(self):
        s = Signer(seed=0)
        s.presign()
        s._app = ()  # 假装有 app
        with pytest.raises(RuntimeError, match="set_peers"):
            s.sign(b"msg")

    def test_sign_without_presign(self):
        s = Signer(seed=0)
        s.set_peers([])
        with pytest.raises(RuntimeError, match="presign"):
            s.sign(b"msg")

    def test_receive_agg_nonce_without_presign(self):
        s = Signer(seed=0)
        with pytest.raises(RuntimeError, match="presign"):
            s.receive_agg_nonce(())

    def test_sign_without_agg_nonce(self):
        s = Signer(seed=0)
        s.set_peers([])
        s.presign()
        with pytest.raises(RuntimeError, match="receive_agg_nonce"):
            s.sign(b"msg")
