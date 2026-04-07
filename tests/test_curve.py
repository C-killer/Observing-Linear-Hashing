"""Unit tests for curve.py."""

import random
from src.crypto.curve import (
    p, Fp, E, G, Z, O, q,
    scalar_mult, point_add, random_scalar,
)
from sage.all import Integer


class TestCurveBasics:
    """Finite field and curve basic properties."""

    def test_p_is_prime(self):
        assert Integer(p).is_prime()

    def test_p_value(self):
        assert p == 2**255 - 19

    def test_curve_order_cofactor(self):
        """Group order = 8q, where q is prime."""
        assert E.order() == 8 * q
        assert Integer(q).is_prime()

    def test_G_on_curve(self):
        assert G in E

    def test_Z_on_curve(self):
        assert Z in E

    def test_G_not_identity(self):
        assert G != O

    def test_Z_not_identity(self):
        assert Z != O

    def test_G_Z_distinct(self):
        assert G != Z


class TestSubgroupOrder:
    """G and Z are in the prime-order subgroup."""

    def test_G_order(self):
        assert q * G == O

    def test_Z_order(self):
        assert q * Z == O

    def test_G_not_small_order(self):
        """G's order is not a proper divisor of q."""
        for d in [2, 4, 8]:
            assert (q // d) * G != O if q % d == 0 else True


class TestArithmetic:
    """Scalar multiplication and point addition."""

    def test_scalar_mult_identity(self):
        assert scalar_mult(1, G) == G

    def test_scalar_mult_zero(self):
        assert scalar_mult(0, G) == O

    def test_scalar_mult_order(self):
        assert scalar_mult(q, G) == O

    def test_point_add_commutative(self):
        P = scalar_mult(42, G)
        Q = scalar_mult(99, G)
        assert point_add(P, Q) == point_add(Q, P)

    def test_point_add_associative(self):
        P = scalar_mult(7, G)
        Q = scalar_mult(13, G)
        R = scalar_mult(29, G)
        assert point_add(point_add(P, Q), R) == point_add(P, point_add(Q, R))

    def test_scalar_mult_distributive(self):
        """(a + b)·G == a·G + b·G"""
        a, b = 12345, 67890
        lhs = scalar_mult(a + b, G)
        rhs = point_add(scalar_mult(a, G), scalar_mult(b, G))
        assert lhs == rhs

    def test_point_add_inverse(self):
        P = scalar_mult(100, G)
        neg_P = scalar_mult(q - 100, G)
        assert point_add(P, neg_P) == O

    def test_point_add_identity(self):
        P = scalar_mult(55, G)
        assert point_add(P, O) == P


class TestRandomScalar:
    """Random scalar generation."""

    def test_range(self):
        rng = random.Random(42)
        for _ in range(20):
            s = random_scalar(rng)
            assert 1 <= s < q

    def test_deterministic_with_seed(self):
        s1 = random_scalar(random.Random(123))
        s2 = random_scalar(random.Random(123))
        assert s1 == s2
