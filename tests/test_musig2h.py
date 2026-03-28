"""musig2h.py 的单元测试：验证 MuSig2-H 方案正确性。"""

import random
from src.crypto.curve import G, Z, O, q, scalar_mult, point_add
from src.crypto.lhf import F, F_key
from src.crypto.musig2h import (
    setup, keygen, key_agg, presign, preagg,
    sign, sign_agg, ver,
    H_agg, H_non, H_sig, NU,
)


# ═══════════════════════════════════════════
#  辅助函数
# ═══════════════════════════════════════════

def _full_protocol(n_signers, msg, seed=42):
    """运行完整的 n 人签名协议，返回 (apk, msg, sigma, all_pks)。"""
    rng = random.Random(seed)

    # KeyGen
    keys = [keygen(rng) for _ in range(n_signers)]
    sks = [k[0] for k in keys]
    pks = [k[1] for k in keys]

    # KeyAgg
    apk = key_agg(pks)

    # PreSign
    presign_results = [presign(rng) for _ in range(n_signers)]
    pps = [r[0] for r in presign_results]
    sts = [r[1] for r in presign_results]

    # PreAgg
    app = preagg(pps)

    # Sign
    outs = []
    for i in range(n_signers):
        others = [pk for j, pk in enumerate(pks) if j != i]
        out_i = sign(sts[i], app, sks[i], pks[i], msg, others)
        outs.append(out_i)

    # SignAgg
    sigma = sign_agg(outs)

    return apk, msg, sigma, pks


# ═══════════════════════════════════════════
#  Setup / KeyGen
# ═══════════════════════════════════════════

class TestSetup:

    def test_setup_returns_params(self):
        par = setup()
        assert par["G"] == G
        assert par["Z"] == Z
        assert par["q"] == q


class TestKeyGen:

    def test_keygen_pk_on_curve(self):
        sk, pk = keygen(random.Random(1))
        assert pk in pk.parent()

    def test_keygen_pk_equals_F_key(self):
        rng = random.Random(99)
        sk, pk = keygen(rng)
        assert pk == F_key(sk)

    def test_keygen_deterministic(self):
        sk1, pk1 = keygen(random.Random(42))
        sk2, pk2 = keygen(random.Random(42))
        assert sk1 == sk2
        assert pk1 == pk2

    def test_keygen_different_seeds(self):
        _, pk1 = keygen(random.Random(1))
        _, pk2 = keygen(random.Random(2))
        assert pk1 != pk2


# ═══════════════════════════════════════════
#  KeyAgg
# ═══════════════════════════════════════════

class TestKeyAgg:

    def test_single_key(self):
        """单人 KeyAgg：apk = H_agg([pk], pk) · pk。"""
        _, pk = keygen(random.Random(10))
        apk = key_agg([pk])
        a = H_agg([pk], pk)
        assert apk == scalar_mult(a, pk)

    def test_deterministic(self):
        rng1 = random.Random(5)
        pks1 = [keygen(rng1)[1] for _ in range(3)]
        rng2 = random.Random(5)
        pks2 = [keygen(rng2)[1] for _ in range(3)]
        assert key_agg(pks1) == key_agg(pks2)


# ═══════════════════════════════════════════
#  PreSign / PreAgg
# ═══════════════════════════════════════════

class TestPreSign:

    def test_presign_shapes(self):
        pp, st = presign(random.Random(7))
        assert len(pp) == NU
        assert len(st) == NU
        for R_j in pp:
            assert R_j in R_j.parent()
        for r_j in st:
            assert len(r_j) == 2

    def test_presign_consistency(self):
        """R_j == F(r_j)"""
        pp, st = presign(random.Random(7))
        for j in range(NU):
            assert pp[j] == F(st[j][0], st[j][1])


class TestPreAgg:

    def test_preagg_single_signer(self):
        """单人 PreAgg 等于自己的 pp。"""
        pp, _ = presign(random.Random(3))
        app = preagg([pp])
        for j in range(NU):
            assert app[j] == pp[j]

    def test_preagg_two_signers(self):
        """两人 PreAgg：R_j = R_{1,j} + R_{2,j}。"""
        pp1, _ = presign(random.Random(1))
        pp2, _ = presign(random.Random(2))
        app = preagg([pp1, pp2])
        for j in range(NU):
            assert app[j] == point_add(pp1[j], pp2[j])


# ═══════════════════════════════════════════
#  哈希函数
# ═══════════════════════════════════════════

class TestHashFunctions:

    def test_H_agg_deterministic(self):
        _, pk = keygen(random.Random(1))
        L = [pk]
        assert H_agg(L, pk) == H_agg(L, pk)

    def test_H_agg_domain_separation(self):
        """H_agg 和 H_sig 对相同输入应产生不同输出。"""
        _, pk = keygen(random.Random(1))
        h_agg = H_agg([pk], pk)
        h_sig = H_sig(pk, pk, b"test")
        assert h_agg != h_sig

    def test_H_non_changes_with_message(self):
        _, pk = keygen(random.Random(1))
        pp, _ = presign(random.Random(2))
        h1 = H_non(pk, pp, b"msg1")
        h2 = H_non(pk, pp, b"msg2")
        assert h1 != h2

    def test_hash_in_range(self):
        """哈希输出在 [0, q) 中。"""
        _, pk = keygen(random.Random(1))
        h = H_agg([pk], pk)
        assert 0 <= h < q


# ═══════════════════════════════════════════
#  完整协议：Sign + SignAgg + Ver
# ═══════════════════════════════════════════

class TestFullProtocol:

    def test_single_signer(self):
        """单人签名验证。"""
        apk, msg, sigma, pks = _full_protocol(1, b"hello")
        assert sigma is not None
        assert ver(apk, msg, sigma)

    def test_two_signers(self):
        """两人签名验证。"""
        apk, msg, sigma, pks = _full_protocol(2, b"hello two")
        assert sigma is not None
        assert ver(apk, msg, sigma)

    def test_three_signers(self):
        """三人签名验证。"""
        apk, msg, sigma, pks = _full_protocol(3, b"hello three")
        assert sigma is not None
        assert ver(apk, msg, sigma)

    def test_five_signers(self):
        """五人签名验证。"""
        apk, msg, sigma, pks = _full_protocol(5, b"hello five", seed=99)
        assert sigma is not None
        assert ver(apk, msg, sigma)

    def test_wrong_message_fails(self):
        """错误消息验证失败。"""
        apk, _, sigma, _ = _full_protocol(2, b"correct msg")
        assert not ver(apk, b"wrong msg", sigma)

    def test_wrong_apk_fails(self):
        """错误聚合公钥验证失败。"""
        apk, msg, sigma, _ = _full_protocol(2, b"test")
        fake_apk = scalar_mult(999, G)
        assert not ver(fake_apk, msg, sigma)

    def test_tampered_signature_fails(self):
        """篡改签名验证失败。"""
        apk, msg, sigma, _ = _full_protocol(2, b"test")
        R, s = sigma
        tampered = (R, ((s[0] + 1) % int(q), s[1]))
        assert not ver(apk, msg, tampered)

    def test_different_messages_different_signatures(self):
        """不同消息产生不同签名。"""
        apk1, _, sigma1, _ = _full_protocol(2, b"msg A", seed=10)
        apk2, _, sigma2, _ = _full_protocol(2, b"msg B", seed=10)
        assert sigma1[0] != sigma2[0] or sigma1[1] != sigma2[1]


class TestSignAggFailure:

    def test_mismatched_R_returns_none(self):
        """R 不一致时 SignAgg 返回 None。"""
        rng = random.Random(50)
        sk1, pk1 = keygen(rng)
        sk2, pk2 = keygen(rng)

        pp1, st1 = presign(rng)
        pp2, st2 = presign(rng)
        app = preagg([pp1, pp2])

        msg = b"test"
        out1 = sign(st1, app, sk1, pk1, msg, [pk2])
        out2 = sign(st2, app, sk2, pk2, msg, [pk1])

        # 篡改 out2 的 R
        fake_R = scalar_mult(12345, G)
        out2_tampered = (fake_R, out2[1])

        result = sign_agg([out1, out2_tampered])
        assert result is None
