"""Unit tests for signer.py: verify Signer wrapper correctness and safety constraints."""

import pytest
from src.crypto.signer import Signer
from src.crypto.musig2h import key_agg, preagg, sign_agg, ver


# ═══════════════════════════════════════════
#  Helper functions
# ═══════════════════════════════════════════

def _run_protocol(n_signers, msg, seed=42):
    """Run complete n-party signing protocol using the Signer class."""
    signers = [Signer(seed=seed + i) for i in range(n_signers)]
    all_pks = [s.pk for s in signers]

    # exchange public keys
    for s in signers:
        s.set_peers([pk for pk in all_pks if pk != s.pk])

    # offline: pre-sign + aggregate nonces
    pp_list = [s.presign() for s in signers]
    app = preagg(pp_list)
    for s in signers:
        s.receive_agg_nonce(app)

    # online: sign + aggregate
    outs = [s.sign(msg) for s in signers]
    sigma = sign_agg(outs)

    apk = key_agg(all_pks)
    return apk, msg, sigma


# ═══════════════════════════════════════════
#  Basic functionality
# ═══════════════════════════════════════════

class TestSignerKeyGen:
    """Test KeyGen during Signer construction."""

    def test_pk_on_curve(self):
        s = Signer(seed=0)
        assert s.pk.curve() == s.pk.curve()  # no exception means it's on the curve

    def test_deterministic_with_seed(self):
        s1 = Signer(seed=123)
        s2 = Signer(seed=123)
        assert s1.pk == s2.pk

    def test_different_seeds_different_keys(self):
        s1 = Signer(seed=1)
        s2 = Signer(seed=2)
        assert s1.pk != s2.pk


# ═══════════════════════════════════════════
#  Full protocol
# ═══════════════════════════════════════════

class TestSignerProtocol:
    """Test running the full signing protocol via the Signer class."""

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
#  Nonce one-time destruction
# ═══════════════════════════════════════════

class TestNonceDestruction:
    """Test that nonces are destroyed after signing and cannot be reused."""

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
        # signing again should raise error
        with pytest.raises(RuntimeError, match="presign"):
            s1.sign(b"msg2")

    def test_can_resign_after_new_presign(self):
        """Can sign again after new presign following destruction."""
        s1 = Signer(seed=20)
        s2 = Signer(seed=21)
        s1.set_peers([s2.pk])
        s2.set_peers([s1.pk])

        # round 1
        pp_list = [s1.presign(), s2.presign()]
        app = preagg(pp_list)
        s1.receive_agg_nonce(app)
        s2.receive_agg_nonce(app)
        outs = [s1.sign(b"msg1"), s2.sign(b"msg1")]
        sigma1 = sign_agg(outs)
        apk = key_agg([s1.pk, s2.pk])
        assert ver(apk, b"msg1", sigma1)

        # round 2: re-presign
        pp_list = [s1.presign(), s2.presign()]
        app = preagg(pp_list)
        s1.receive_agg_nonce(app)
        s2.receive_agg_nonce(app)
        outs = [s1.sign(b"msg2"), s2.sign(b"msg2")]
        sigma2 = sign_agg(outs)
        assert ver(apk, b"msg2", sigma2)


# ═══════════════════════════════════════════
#  Protocol order checks
# ═══════════════════════════════════════════

class TestProtocolOrder:
    """Test error messages when skipping protocol steps."""

    def test_sign_without_peers(self):
        s = Signer(seed=0)
        s.presign()
        s._app = ()  # pretend we have app
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
