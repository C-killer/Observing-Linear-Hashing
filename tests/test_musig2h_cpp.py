"""
Cross-validation tests: C++ fastmusig ↔ Python/SageMath.

Phase 1: curve25519 (G, Z, q, Scalar, Point, coordinate conversion)
         hash_utils (H_agg, H_non, H_sig, serialization)
Phase 2: musig2h algorithms (keygen, key_agg, ver, sign, full protocol)
         cross-signing (C++ sign → Python ver, Python sign → C++ ver)
Phase 3: parallel protocol (RelicThreadPool + run_protocol_parallel)
"""

import pytest
import random
from sage.all import Integer, ZZ

import fastmusig
from src.crypto.curve import G, Z, O, q, p, E, scalar_mult, point_add, random_scalar
from src.crypto.lhf import F
from src.crypto.musig2h import (
    _point_to_bytes, _int_to_bytes, _serialize_pk_list,
    H_agg, H_non, H_sig, keygen, key_agg, key_agg_ex,
    presign, preagg, sign, sign_agg, ver,
)
from src.crypto.signer import Signer


# ═══════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════

def py_point_bytes(P):
    """Python point → 64 bytes (Montgomery x||y, big-endian)."""
    return _point_to_bytes(P)


def py_scalar_bytes(s):
    """Python scalar → 32 bytes (big-endian)."""
    return int(s).to_bytes(32, "big")


@pytest.fixture(autouse=True)
def init_curve():
    fastmusig.init()


# ═══════════════════════════════════════════
#  Phase 1: Curve constants consistency
# ═══════════════════════════════════════════

class TestCurveConstants:
    """G, Z, q must be byte-level identical between C++ and Python."""

    def test_G_consistency(self):
        assert fastmusig.get_G_bytes() == py_point_bytes(G)

    def test_Z_consistency(self):
        assert fastmusig.get_Z_bytes() == py_point_bytes(Z)

    def test_q_consistency(self):
        assert fastmusig.get_q_bytes() == py_scalar_bytes(q)

    def test_G_not_identity(self):
        assert fastmusig.get_G_bytes() != b"\x00" * 64

    def test_Z_not_identity(self):
        assert fastmusig.get_Z_bytes() != b"\x00" * 64

    def test_G_Z_distinct(self):
        assert fastmusig.get_G_bytes() != fastmusig.get_Z_bytes()

    def test_G_length(self):
        assert len(fastmusig.get_G_bytes()) == 64

    def test_Z_length(self):
        assert len(fastmusig.get_Z_bytes()) == 64

    def test_q_length(self):
        assert len(fastmusig.get_q_bytes()) == 32


# ═══════════════════════════════════════════
#  Phase 1: Point serialization round-trip
# ═══════════════════════════════════════════

class TestPointSerialization:
    """Montgomery ↔ Weierstrass coordinate conversion via serialization."""

    def test_G_roundtrip_via_hash(self):
        """G bytes from C++ can be used as input to C++ hash, matches Python."""
        G_cpp = fastmusig.get_G_bytes()
        G_py = py_point_bytes(G)
        assert G_cpp == G_py

    def test_Z_roundtrip_via_hash(self):
        Z_cpp = fastmusig.get_Z_bytes()
        Z_py = py_point_bytes(Z)
        assert Z_cpp == Z_py

    def test_identity_is_64_zeros(self):
        """Identity point serializes as 64 zero bytes in Python."""
        assert py_point_bytes(O) == b"\x00" * 64

    def test_multiple_points_consistency(self):
        """Multiple derived points serialize consistently."""
        rng = random.Random(12345)
        for _ in range(5):
            k = random_scalar(rng)
            P = scalar_mult(k, G)
            P_bytes = py_point_bytes(P)
            # Verify bytes are 64 bytes and non-zero
            assert len(P_bytes) == 64
            assert P_bytes != b"\x00" * 64


# ═══════════════════════════════════════════
#  Phase 1: H_agg cross-validation
# ═══════════════════════════════════════════

class TestHAgg:
    """H_agg(L, pk) → Z_q, tag=1."""

    def test_single_key(self):
        """H_agg with single-element list."""
        L = [G]
        py_val = py_scalar_bytes(H_agg(L, G))
        cpp_val = fastmusig.H_agg_bytes([py_point_bytes(G)], py_point_bytes(G))
        assert cpp_val == py_val

    def test_two_keys(self):
        """H_agg with two keys."""
        L = [G, Z]
        py_val = py_scalar_bytes(H_agg(L, G))
        L_bytes = [py_point_bytes(pk) for pk in L]
        cpp_val = fastmusig.H_agg_bytes(L_bytes, py_point_bytes(G))
        assert cpp_val == py_val

    def test_two_keys_second(self):
        """H_agg for the second key in a two-key list."""
        L = [G, Z]
        py_val = py_scalar_bytes(H_agg(L, Z))
        L_bytes = [py_point_bytes(pk) for pk in L]
        cpp_val = fastmusig.H_agg_bytes(L_bytes, py_point_bytes(Z))
        assert cpp_val == py_val

    def test_sorting_invariance(self):
        """H_agg sorts internally, so list order shouldn't matter."""
        L1 = [G, Z]
        L2 = [Z, G]
        py1 = py_scalar_bytes(H_agg(L1, G))
        py2 = py_scalar_bytes(H_agg(L2, G))
        assert py1 == py2

        L1_bytes = [py_point_bytes(pk) for pk in L1]
        L2_bytes = [py_point_bytes(pk) for pk in L2]
        cpp1 = fastmusig.H_agg_bytes(L1_bytes, py_point_bytes(G))
        cpp2 = fastmusig.H_agg_bytes(L2_bytes, py_point_bytes(G))
        assert cpp1 == cpp2 == py1

    def test_domain_separation(self):
        """H_agg(L, G) ≠ H_sig(G, Z, ...)."""
        h_agg = fastmusig.H_agg_bytes([py_point_bytes(G)], py_point_bytes(G))
        h_sig = fastmusig.H_sig_bytes(py_point_bytes(G), py_point_bytes(Z), b"test")
        assert h_agg != h_sig

    def test_with_generated_keys(self):
        """H_agg with KeyGen-produced keys."""
        rng = random.Random(999)
        keys = [keygen(rng) for _ in range(3)]
        pks = [pk for _, pk in keys]
        L_bytes = [py_point_bytes(pk) for pk in pks]
        for pk in pks:
            py_val = py_scalar_bytes(H_agg(pks, pk))
            cpp_val = fastmusig.H_agg_bytes(L_bytes, py_point_bytes(pk))
            assert cpp_val == py_val


# ═══════════════════════════════════════════
#  Phase 1: H_sig cross-validation
# ═══════════════════════════════════════════

class TestHSig:
    """H_sig(apk, R, m) → Z_q, tag=3."""

    def test_basic(self):
        py_val = py_scalar_bytes(H_sig(G, Z, b"test"))
        cpp_val = fastmusig.H_sig_bytes(py_point_bytes(G), py_point_bytes(Z), b"test")
        assert cpp_val == py_val

    def test_empty_message(self):
        py_val = py_scalar_bytes(H_sig(G, Z, b""))
        cpp_val = fastmusig.H_sig_bytes(py_point_bytes(G), py_point_bytes(Z), b"")
        assert cpp_val == py_val

    def test_long_message(self):
        msg = b"A" * 1000
        py_val = py_scalar_bytes(H_sig(G, Z, msg))
        cpp_val = fastmusig.H_sig_bytes(py_point_bytes(G), py_point_bytes(Z), msg)
        assert cpp_val == py_val

    def test_different_messages(self):
        h1 = fastmusig.H_sig_bytes(py_point_bytes(G), py_point_bytes(Z), b"msg1")
        h2 = fastmusig.H_sig_bytes(py_point_bytes(G), py_point_bytes(Z), b"msg2")
        assert h1 != h2

    def test_different_apk(self):
        h1 = fastmusig.H_sig_bytes(py_point_bytes(G), py_point_bytes(Z), b"test")
        h2 = fastmusig.H_sig_bytes(py_point_bytes(Z), py_point_bytes(Z), b"test")
        assert h1 != h2


# ═══════════════════════════════════════════
#  Phase 1: H_non cross-validation
# ═══════════════════════════════════════════

class TestHNon:
    """H_non(apk, (R_1,...,R_4), m) → Z_q, tag=2."""

    def test_basic(self):
        nonces = [G, Z, G, Z]
        py_val = py_scalar_bytes(H_non(G, nonces, b"msg"))
        nonce_bytes = [py_point_bytes(R) for R in nonces]
        cpp_val = fastmusig.H_non_bytes(py_point_bytes(G), nonce_bytes, b"msg")
        assert cpp_val == py_val

    def test_all_same_nonces(self):
        nonces = [G, G, G, G]
        py_val = py_scalar_bytes(H_non(Z, nonces, b"hello"))
        nonce_bytes = [py_point_bytes(R) for R in nonces]
        cpp_val = fastmusig.H_non_bytes(py_point_bytes(Z), nonce_bytes, b"hello")
        assert cpp_val == py_val

    def test_different_messages(self):
        nonces = [G, Z, G, Z]
        nonce_bytes = [py_point_bytes(R) for R in nonces]
        h1 = fastmusig.H_non_bytes(py_point_bytes(G), nonce_bytes, b"a")
        h2 = fastmusig.H_non_bytes(py_point_bytes(G), nonce_bytes, b"b")
        assert h1 != h2

    def test_wrong_nonce_count_rejected(self):
        """Passing != 4 nonces should raise."""
        with pytest.raises(RuntimeError):
            fastmusig.H_non_bytes(py_point_bytes(G), [py_point_bytes(G)] * 3, b"msg")

    def test_with_derived_points(self):
        """H_non with points derived from scalar multiplication."""
        rng = random.Random(42)
        nonces_py = [scalar_mult(random_scalar(rng), G) for _ in range(4)]
        apk = scalar_mult(random_scalar(rng), G)
        msg = b"cross-validate"

        py_val = py_scalar_bytes(H_non(apk, nonces_py, msg))
        nonce_bytes = [py_point_bytes(R) for R in nonces_py]
        cpp_val = fastmusig.H_non_bytes(py_point_bytes(apk), nonce_bytes, msg)
        assert cpp_val == py_val


# ═══════════════════════════════════════════
#  Phase 1: Pk list serialization consistency
# ═══════════════════════════════════════════

class TestPkListSerialization:
    """Sorting and serialization of public key lists must match."""

    def test_two_keys_order_independent(self):
        """serialize_pk_list sorts, so [G,Z] == [Z,G]."""
        py1 = _serialize_pk_list([G, Z])
        py2 = _serialize_pk_list([Z, G])
        assert py1 == py2

    def test_three_generated_keys(self):
        """Serialization of 3 keygen'd public keys is deterministic."""
        rng = random.Random(777)
        pks = [keygen(rng)[1] for _ in range(3)]
        s1 = _serialize_pk_list(pks)
        s2 = _serialize_pk_list(list(reversed(pks)))
        assert s1 == s2
        assert len(s1) == 3 * 64


# ═══════════════════════════════════════════
#  Phase 1: Hash output range
# ═══════════════════════════════════════════

class TestHashRange:
    """Hash outputs must be in [0, q)."""

    def test_H_agg_in_range(self):
        val = int.from_bytes(
            fastmusig.H_agg_bytes([py_point_bytes(G)], py_point_bytes(G)), "big"
        )
        assert 0 <= val < int(q)

    def test_H_sig_in_range(self):
        val = int.from_bytes(
            fastmusig.H_sig_bytes(py_point_bytes(G), py_point_bytes(Z), b"x"), "big"
        )
        assert 0 <= val < int(q)

    def test_H_non_in_range(self):
        nonce_bytes = [py_point_bytes(G)] * 4
        val = int.from_bytes(
            fastmusig.H_non_bytes(py_point_bytes(G), nonce_bytes, b"y"), "big"
        )
        assert 0 <= val < int(q)


# ═══════════════════════════════════════════
#  Phase 2: KeyAgg cross-validation
# ═══════════════════════════════════════════

class TestKeyAgg:
    """KeyAgg must produce identical apk and coefficients."""

    def test_key_agg_two_points(self):
        """KeyAgg([G, Z]) must match between C++ and Python."""
        L = [G, Z]
        py_apk = key_agg(L)
        cpp_apk = fastmusig.key_agg([py_point_bytes(pk) for pk in L])
        assert cpp_apk == py_point_bytes(py_apk)

    def test_key_agg_ex_coefficients(self):
        """key_agg_ex coefficients must match for 3 generated keys."""
        rng = random.Random(123)
        keys = [keygen(rng) for _ in range(3)]
        pks = [pk for _, pk in keys]

        py_apk, py_coeffs = key_agg_ex(pks)
        L_bytes = [py_point_bytes(pk) for pk in pks]
        cpp_apk, cpp_coeffs = fastmusig.key_agg_ex(L_bytes)

        assert cpp_apk == py_point_bytes(py_apk)
        for i, pk in enumerate(pks):
            assert cpp_coeffs[i] == py_scalar_bytes(py_coeffs[pk])

    def test_key_agg_single_key(self):
        """KeyAgg with single key."""
        L = [G]
        py_apk = key_agg(L)
        cpp_apk = fastmusig.key_agg([py_point_bytes(G)])
        assert cpp_apk == py_point_bytes(py_apk)

    def test_key_agg_order_invariance(self):
        """KeyAgg result should not depend on input order (sorts internally)."""
        rng = random.Random(456)
        keys = [keygen(rng) for _ in range(4)]
        pks = [pk for _, pk in keys]

        L_bytes_1 = [py_point_bytes(pk) for pk in pks]
        L_bytes_2 = [py_point_bytes(pk) for pk in reversed(pks)]
        assert fastmusig.key_agg(L_bytes_1) == fastmusig.key_agg(L_bytes_2)


# ═══════════════════════════════════════════
#  Phase 2: Ver cross-validation
# ═══════════════════════════════════════════

class TestVer:
    """C++ ver must accept valid Python signatures and reject invalid ones."""

    def _run_python_protocol(self, n_signers, msg, seed=42):
        """Run full Python protocol, return (apk, sigma)."""
        rng_base = random.Random(seed)
        signers = [Signer(seed=seed + i) for i in range(n_signers)]
        all_pks = [s.pk for s in signers]
        apk, coeffs = key_agg_ex(all_pks)
        for s in signers:
            s.set_peers([pk for pk in all_pks if pk != s.pk])
            s.set_agg_key(apk, coeffs[s.pk])
        pp_list = [s.presign() for s in signers]
        app = preagg(pp_list)
        for s in signers:
            s.receive_agg_nonce(app)
        outs = [s.sign(msg) for s in signers]
        sigma = sign_agg(outs)
        return apk, sigma

    def test_python_sign_cpp_ver_2_signers(self):
        """Python 2-signer signature verified by C++ ver."""
        msg = b"hello from python"
        apk, sigma = self._run_python_protocol(2, msg)
        R, (s0, s1) = sigma
        assert fastmusig.ver(
            py_point_bytes(apk), msg,
            py_point_bytes(R), py_scalar_bytes(s0), py_scalar_bytes(s1)
        )

    def test_python_sign_cpp_ver_3_signers(self):
        """Python 3-signer signature verified by C++ ver."""
        msg = b"three signers"
        apk, sigma = self._run_python_protocol(3, msg, seed=100)
        R, (s0, s1) = sigma
        assert fastmusig.ver(
            py_point_bytes(apk), msg,
            py_point_bytes(R), py_scalar_bytes(s0), py_scalar_bytes(s1)
        )

    def test_python_sign_cpp_ver_5_signers(self):
        """Python 5-signer signature verified by C++ ver."""
        msg = b"five signers"
        apk, sigma = self._run_python_protocol(5, msg, seed=200)
        R, (s0, s1) = sigma
        assert fastmusig.ver(
            py_point_bytes(apk), msg,
            py_point_bytes(R), py_scalar_bytes(s0), py_scalar_bytes(s1)
        )

    def test_ver_rejects_wrong_message(self):
        """Verification fails if message is tampered."""
        msg = b"original"
        apk, sigma = self._run_python_protocol(2, msg)
        R, (s0, s1) = sigma
        assert not fastmusig.ver(
            py_point_bytes(apk), b"tampered",
            py_point_bytes(R), py_scalar_bytes(s0), py_scalar_bytes(s1)
        )

    def test_ver_rejects_wrong_s0(self):
        """Verification fails if s0 is tampered."""
        msg = b"test"
        apk, sigma = self._run_python_protocol(2, msg)
        R, (s0, s1) = sigma
        bad_s0 = (s0 + 1) % int(q)
        assert not fastmusig.ver(
            py_point_bytes(apk), msg,
            py_point_bytes(R), py_scalar_bytes(bad_s0), py_scalar_bytes(s1)
        )

    def test_ver_rejects_wrong_s1(self):
        """Verification fails if s1 is tampered."""
        msg = b"test"
        apk, sigma = self._run_python_protocol(2, msg)
        R, (s0, s1) = sigma
        bad_s1 = (s1 + 1) % int(q)
        assert not fastmusig.ver(
            py_point_bytes(apk), msg,
            py_point_bytes(R), py_scalar_bytes(s0), py_scalar_bytes(bad_s1)
        )


# ═══════════════════════════════════════════
#  Phase 2: C++ sequential protocol
# ═══════════════════════════════════════════

class TestSequentialProtocol:
    """C++ run_protocol_sequential must self-verify."""

    def test_1_signer(self):
        result = fastmusig.run_protocol_sequential(1, b"solo", seed=42)
        assert result["verified"] is True

    def test_2_signers(self):
        result = fastmusig.run_protocol_sequential(2, b"duo", seed=42)
        assert result["verified"] is True

    def test_3_signers(self):
        result = fastmusig.run_protocol_sequential(3, b"trio", seed=42)
        assert result["verified"] is True

    def test_5_signers(self):
        result = fastmusig.run_protocol_sequential(5, b"five", seed=42)
        assert result["verified"] is True

    def test_10_signers(self):
        result = fastmusig.run_protocol_sequential(10, b"ten", seed=42)
        assert result["verified"] is True

    def test_different_seeds(self):
        """Different seeds produce different signatures but all verify."""
        for seed in [0, 1, 42, 999, 2**32]:
            result = fastmusig.run_protocol_sequential(3, b"test", seed=seed)
            assert result["verified"] is True

    def test_different_messages(self):
        """Different messages produce different signatures."""
        r1 = fastmusig.run_protocol_sequential(3, b"msg1", seed=42)
        r2 = fastmusig.run_protocol_sequential(3, b"msg2", seed=42)
        assert r1["verified"] is True
        assert r2["verified"] is True
        assert r1["R"] != r2["R"] or r1["s0"] != r2["s0"]

    def test_empty_message(self):
        result = fastmusig.run_protocol_sequential(2, b"", seed=42)
        assert result["verified"] is True

    def test_long_message(self):
        result = fastmusig.run_protocol_sequential(2, b"A" * 10000, seed=42)
        assert result["verified"] is True

    def test_result_fields(self):
        """Result dict has all expected fields."""
        result = fastmusig.run_protocol_sequential(3, b"test", seed=42)
        assert "apk" in result
        assert "R" in result
        assert "s0" in result
        assert "s1" in result
        assert "verified" in result
        assert "n_signers" in result
        assert result["n_signers"] == 3
        assert len(result["apk"]) == 64
        assert len(result["R"]) == 64
        assert len(result["s0"]) == 32
        assert len(result["s1"]) == 32


# ═══════════════════════════════════════════
#  Phase 2: C++ sign → Python ver (cross-signing)
# ═══════════════════════════════════════════

class TestCppSignPythonVer:
    """Signatures produced by C++ must be verifiable by Python ver."""

    def _cpp_sigma_to_python(self, result):
        """Convert C++ result dict to Python (apk, sigma) for ver()."""
        from src.crypto.curve import E, Fp
        apk_bytes = result["apk"]
        R_bytes = result["R"]
        s0_bytes = result["s0"]
        s1_bytes = result["s1"]

        # Deserialize apk
        ax = Integer(int.from_bytes(apk_bytes[:32], "big"))
        ay = Integer(int.from_bytes(apk_bytes[32:], "big"))
        apk = E(Fp(ax), Fp(ay))

        # Deserialize R
        rx = Integer(int.from_bytes(R_bytes[:32], "big"))
        ry = Integer(int.from_bytes(R_bytes[32:], "big"))
        R = E(Fp(rx), Fp(ry))

        s0 = int.from_bytes(s0_bytes, "big")
        s1 = int.from_bytes(s1_bytes, "big")

        return apk, (R, (s0, s1))

    def test_cpp_sign_python_ver_2(self):
        result = fastmusig.run_protocol_sequential(2, b"cross test", seed=42)
        apk, sigma = self._cpp_sigma_to_python(result)
        assert ver(apk, b"cross test", sigma)

    def test_cpp_sign_python_ver_3(self):
        result = fastmusig.run_protocol_sequential(3, b"three", seed=100)
        apk, sigma = self._cpp_sigma_to_python(result)
        assert ver(apk, b"three", sigma)

    def test_cpp_sign_python_ver_5(self):
        result = fastmusig.run_protocol_sequential(5, b"five signers", seed=200)
        apk, sigma = self._cpp_sigma_to_python(result)
        assert ver(apk, b"five signers", sigma)

    def test_cpp_sign_python_ver_10(self):
        result = fastmusig.run_protocol_sequential(10, b"ten signers", seed=300)
        apk, sigma = self._cpp_sigma_to_python(result)
        assert ver(apk, b"ten signers", sigma)


# ═══════════════════════════════════════════
#  Phase 3: Parallel protocol (RelicThreadPool)
# ═══════════════════════════════════════════

TIMING_KEYS = {"keygen", "keyagg", "presign", "preagg", "sign", "signagg", "verify", "total"}


class TestParallelProtocol:
    """C++ run_protocol_parallel: correctness across signer counts."""

    def test_1_signer(self):
        result = fastmusig.run_protocol_parallel(1, b"solo", seed=42)
        assert result["verified"] is True

    def test_2_signers(self):
        result = fastmusig.run_protocol_parallel(2, b"duo", seed=42)
        assert result["verified"] is True

    def test_3_signers(self):
        result = fastmusig.run_protocol_parallel(3, b"trio", seed=42)
        assert result["verified"] is True

    def test_5_signers(self):
        result = fastmusig.run_protocol_parallel(5, b"five", seed=42)
        assert result["verified"] is True

    def test_10_signers(self):
        result = fastmusig.run_protocol_parallel(10, b"ten", seed=42)
        assert result["verified"] is True

    def test_50_signers(self):
        result = fastmusig.run_protocol_parallel(50, b"fifty", seed=42)
        assert result["verified"] is True


class TestParallelDeterminism:
    """Parallel protocol determinism and consistency with sequential."""

    def test_same_seed_same_result(self):
        """Same seed must produce identical signatures."""
        r1 = fastmusig.run_protocol_parallel(3, b"det", seed=777)
        r2 = fastmusig.run_protocol_parallel(3, b"det", seed=777)
        assert r1["apk"] == r2["apk"]
        assert r1["R"] == r2["R"]
        assert r1["s0"] == r2["s0"]
        assert r1["s1"] == r2["s1"]

    def test_different_seeds_different_signatures(self):
        """Different seeds must produce different signatures."""
        r1 = fastmusig.run_protocol_parallel(3, b"test", seed=42)
        r2 = fastmusig.run_protocol_parallel(3, b"test", seed=99)
        assert r1["R"] != r2["R"] or r1["s0"] != r2["s0"]

    def test_parallel_matches_sequential(self):
        """Same seed → parallel and sequential produce identical signature."""
        seq = fastmusig.run_protocol_sequential(3, b"match", seed=42)
        par = fastmusig.run_protocol_parallel(3, b"match", seed=42)
        assert seq["apk"] == par["apk"]
        assert seq["R"] == par["R"]
        assert seq["s0"] == par["s0"]
        assert seq["s1"] == par["s1"]


class TestParallelCrossValidation:
    """C++ parallel signatures verified by Python ver."""

    def _cpp_result_to_python(self, result):
        """Convert C++ parallel result dict to Python (apk, sigma)."""
        from src.crypto.curve import E, Fp
        ax = Integer(int.from_bytes(result["apk"][:32], "big"))
        ay = Integer(int.from_bytes(result["apk"][32:], "big"))
        apk = E(Fp(ax), Fp(ay))
        rx = Integer(int.from_bytes(result["R"][:32], "big"))
        ry = Integer(int.from_bytes(result["R"][32:], "big"))
        R = E(Fp(rx), Fp(ry))
        s0 = int.from_bytes(result["s0"], "big")
        s1 = int.from_bytes(result["s1"], "big")
        return apk, (R, (s0, s1))

    def test_parallel_sign_python_ver_3(self):
        result = fastmusig.run_protocol_parallel(3, b"cross3", seed=42)
        apk, sigma = self._cpp_result_to_python(result)
        assert ver(apk, b"cross3", sigma)

    def test_parallel_sign_python_ver_5(self):
        result = fastmusig.run_protocol_parallel(5, b"cross5", seed=200)
        apk, sigma = self._cpp_result_to_python(result)
        assert ver(apk, b"cross5", sigma)

    def test_parallel_sign_python_ver_10(self):
        result = fastmusig.run_protocol_parallel(10, b"cross10", seed=300)
        apk, sigma = self._cpp_result_to_python(result)
        assert ver(apk, b"cross10", sigma)


class TestParallelEdgeCases:
    """Thread count variations and edge cases."""

    def test_single_thread(self):
        result = fastmusig.run_protocol_parallel(5, b"1thread", seed=42, num_threads=1)
        assert result["verified"] is True

    def test_more_threads_than_signers(self):
        """num_threads > n_signers: should cap to n_signers."""
        result = fastmusig.run_protocol_parallel(2, b"excess", seed=42, num_threads=16)
        assert result["verified"] is True
        assert result["num_threads"] == 2

    def test_empty_message(self):
        result = fastmusig.run_protocol_parallel(3, b"", seed=42)
        assert result["verified"] is True

    def test_long_message(self):
        result = fastmusig.run_protocol_parallel(3, b"A" * 10000, seed=42)
        assert result["verified"] is True

    def test_timing_keys(self):
        """Timing dict must contain all 8 phase keys."""
        result = fastmusig.run_protocol_parallel(3, b"timing", seed=42)
        assert set(result["timing"].keys()) == TIMING_KEYS
        for key in TIMING_KEYS:
            assert result["timing"][key] >= 0

    def test_result_fields(self):
        """Result dict has all expected fields with correct sizes."""
        result = fastmusig.run_protocol_parallel(3, b"fields", seed=42)
        assert "apk" in result and len(result["apk"]) == 64
        assert "R" in result and len(result["R"]) == 64
        assert "s0" in result and len(result["s0"]) == 32
        assert "s1" in result and len(result["s1"]) == 32
        assert result["verified"] is True
        assert result["n_signers"] == 3
        assert "num_threads" in result
        assert "timing" in result
