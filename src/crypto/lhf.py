"""
Pedersen Linear Hash Function (TZ23 Section 5.1, Lemma 8).

F : Z_q² → E(F_p)
F(x1, x2) = x1·G + x2·Z

Satisfies Definition 1:
- S-module epimorphism
- Non-monomorphism
- |S|, |D|, |R| ≥ 2^κ
"""

from sage.all import Integer

from src.crypto.curve import G, Z, O, q, E, scalar_mult, point_add


def F(x1, x2):
    """
    Pedersen linear hash function.
    F(x1, x2) = x1·G + x2·Z

    Args: x1, x2 ∈ Z_q
    Returns: a point on E(F_p)
    """
    return point_add(scalar_mult(x1, G), scalar_mult(x2, Z))


def F_vec(vec):
    """
    Vector form: F((x1, x2)) = x1·G + x2·Z

    Args: vec = (x1, x2), a tuple/list of length 2
    Returns: a point on E(F_p)
    """
    return F(vec[0], vec[1])


def F_key(sk):
    """
    F restricted to key space: F(sk, 0) = sk·G
    D_key = Z_q × {0}, where F|_{D_key} is bijective.

    Args: sk ∈ Z_q
    Returns: pk ∈ E(F_p)
    """
    return scalar_mult(sk, G)
