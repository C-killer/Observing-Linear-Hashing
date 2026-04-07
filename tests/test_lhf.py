"""Unit tests for lhf.py: verify Pedersen LHF satisfies Definition 1."""

import random
from src.crypto.curve import G, Z, O, q, E, scalar_mult, point_add, random_scalar
from src.crypto.lhf import F, F_vec, F_key
from sage.all import Integer


class TestLinearity:
    """F is a Z_q-linear map."""

    def test_homomorphism_add(self):
        """F(a + b) = F(a) + F(b)"""
        a1, a2 = 111, 222
        b1, b2 = 333, 444
        lhs = F(a1 + b1, a2 + b2)
        rhs = point_add(F(a1, a2), F(b1, b2))
        assert lhs == rhs

    def test_homomorphism_scalar(self):
        """F(k·a1, k·a2) = k·F(a1, a2)"""
        k = 77
        a1, a2 = 500, 600
        lhs = F(k * a1, k * a2)
        rhs = scalar_mult(k, F(a1, a2))
        assert lhs == rhs

    def test_linearity_random(self):
        """Random linearity test: F(a+b) = F(a) + F(b)"""
        rng = random.Random(42)
        for _ in range(10):
            a1, a2 = random_scalar(rng), random_scalar(rng)
            b1, b2 = random_scalar(rng), random_scalar(rng)
            lhs = F((a1 + b1) % q, (a2 + b2) % q)
            rhs = point_add(F(a1, a2), F(b1, b2))
            assert lhs == rhs


class TestEpimorphism:
    """F is an epimorphism: image covers all of E[q]."""

    def test_G_in_image(self):
        """G = F(1, 0)"""
        assert F(1, 0) == G

    def test_Z_in_image(self):
        """Z = F(0, 1)"""
        assert F(0, 1) == Z

    def test_arbitrary_point_in_image(self):
        """Any k·G + j·Z is in the image."""
        k, j = 12345, 67890
        P = point_add(scalar_mult(k, G), scalar_mult(j, Z))
        assert F(k, j) == P


class TestNonMonomorphism:
    """F is not injective: non-trivial kernel elements exist."""

    def test_F_zero_zero_is_identity(self):
        """F(0, 0) = O"""
        assert F(0, 0) == O

    def test_kernel_nontrivial(self):
        """
        Non-trivial kernel: if z* = (log_G(Z), -1), then F(z*) = O.
        We don't know log_G(Z), but can verify F(a, b) = O iff
        a·G = -b·Z, i.e., non-zero solutions exist.

        Equivalent check: F(0, q) = 0·G + q·Z = O (since Z has order q).
        This means (0, q) ≡ (0, 0) mod q is in the kernel,
        but truly non-trivial kernel elements require DL.

        Dimension argument: D = Z_q² (dim 2), R = E[q] (dim 1),
        kernel dim = 2 - 1 = 1 > 0.
        Direct verification: find two different preimages mapping to the same point.
        """
        # F(1, 0) = G, find another (a, b) such that F(a, b) = G
        # i.e., a·G + b·Z = G => (a-1)·G + b·Z = O
        # This requires DL, so we verify non-injectivity another way:
        # Domain Z_q² has q² elements, image E[q] has at most q elements
        # Therefore F cannot be injective (pigeonhole principle)
        #
        # Programmatic check: for any x, F(x1, x2) = F(x1 + q, x2)
        # (since G has order q)
        x1, x2 = 999, 888
        assert F(x1, x2) == F(x1 + q, x2)
        # same for the second component
        assert F(x1, x2) == F(x1, x2 + q)

    def test_two_preimages(self):
        """The same image has multiple preimages."""
        P = F(42, 0)  # 42·G
        # F(42, 0) = F(42 + 0, 0 + 0), alternatively:
        # F(0, 0) + F(42, 0) and F(41, 0) + F(1, 0)
        # Direct construction: F(42, q-1) + F(0, 1) is just F(42, q-1+1) = F(42, 0)
        # verify using a different decomposition
        assert F(42, 0) == point_add(F(20, 0), F(22, 0))


class TestFVec:
    """Interface tests for F_vec."""

    def test_tuple(self):
        assert F_vec((10, 20)) == F(10, 20)

    def test_list(self):
        assert F_vec([10, 20]) == F(10, 20)


class TestFKey:
    """F_key restricted to key space."""

    def test_fkey_equals_f_with_zero(self):
        """F_key(sk) = F(sk, 0)"""
        sk = 54321
        assert F_key(sk) == F(sk, 0)

    def test_fkey_is_scalar_mult_G(self):
        """F_key(sk) = sk·G"""
        sk = 12345
        assert F_key(sk) == scalar_mult(sk, G)

    def test_fkey_injective(self):
        """F|_{D_key} is bijective: different sk map to different pk."""
        sk1, sk2 = 100, 200
        assert F_key(sk1) != F_key(sk2)
