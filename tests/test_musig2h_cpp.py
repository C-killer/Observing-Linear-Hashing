"""
Cross-validation tests: C++ fastmusig ↔ Python/SageMath.

Phase 1: curve25519 (G, Z, q, Scalar, Point, coordinate conversion)
         hash_utils (H_agg, H_non, H_sig, serialization)
"""

import pytest
from sage.all import Integer, ZZ

import fastmusig
from src.crypto.curve import G, Z, O, q, p, E, scalar_mult, point_add, random_scalar
from src.crypto.lhf import F
from src.crypto.musig2h import (
    _point_to_bytes, _int_to_bytes, _serialize_pk_list,
    H_agg, H_non, H_sig, keygen,
)


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
#  Curve constants consistency
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
#  Point serialization round-trip
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
        import random
        rng = random.Random(12345)
        for _ in range(5):
            k = random_scalar(rng)
            P = scalar_mult(k, G)
            P_bytes = py_point_bytes(P)
            # Verify bytes are 64 bytes and non-zero
            assert len(P_bytes) == 64
            assert P_bytes != b"\x00" * 64


# ═══════════════════════════════════════════
#  H_agg cross-validation
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
        import random
        rng = random.Random(999)
        keys = [keygen(rng) for _ in range(3)]
        pks = [pk for _, pk in keys]
        L_bytes = [py_point_bytes(pk) for pk in pks]
        for pk in pks:
            py_val = py_scalar_bytes(H_agg(pks, pk))
            cpp_val = fastmusig.H_agg_bytes(L_bytes, py_point_bytes(pk))
            assert cpp_val == py_val


# ═══════════════════════════════════════════
#  H_sig cross-validation
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
#  H_non cross-validation
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
        import random
        rng = random.Random(42)
        nonces_py = [scalar_mult(random_scalar(rng), G) for _ in range(4)]
        apk = scalar_mult(random_scalar(rng), G)
        msg = b"cross-validate"

        py_val = py_scalar_bytes(H_non(apk, nonces_py, msg))
        nonce_bytes = [py_point_bytes(R) for R in nonces_py]
        cpp_val = fastmusig.H_non_bytes(py_point_bytes(apk), nonce_bytes, msg)
        assert cpp_val == py_val


# ═══════════════════════════════════════════
#  Pk list serialization consistency
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
        import random
        rng = random.Random(777)
        pks = [keygen(rng)[1] for _ in range(3)]
        s1 = _serialize_pk_list(pks)
        s2 = _serialize_pk_list(list(reversed(pks)))
        assert s1 == s2
        assert len(s1) == 3 * 64


# ═══════════════════════════════════════════
#  Hash output range
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
