"""
Curve25519 elliptic curve wrapper (Montgomery form), based on SageMath.

Provides:
- Finite field F_p, p = 2^255 - 19
- Curve E: y² = x³ + 486662x² + x over F_p
- Base point G (x=9)
- Independent generator Z (transparent hash-to-curve)
- Group order q (prime-order subgroup)
"""

from sage.all import GF, EllipticCurve, Integer, ZZ

# ── Finite field ──
p = Integer(2**255 - 19)
Fp = GF(p)

# ── Curve25519 (Montgomery: y² = x³ + Ax² + x) ──
A = Integer(486662)
E = EllipticCurve(Fp, [0, A, 0, 1, 0])

# Group order = 8 * q, where q is a large prime
_order = E.order()
q = _order // 8  # cofactor = 8

# ── Base point G ──
# Curve25519 standard base point x=9, pick the smaller y
_G_candidates = E.lift_x(Fp(9), all=True)
G = min(_G_candidates, key=lambda P: ZZ(P[1]))  # pick the smaller y


def _hash_to_curve(tag: str):
    """
    Transparent hash-to-curve: maps a tag string to a point on E.
    Repeatedly hashes until a valid x-coordinate is found, then lifts onto the curve.
    """
    from hashlib import sha256 as _sha256
    for counter in range(256):
        h = _sha256(f"{tag}:{counter}".encode()).digest()
        x = Fp(Integer(int.from_bytes(h, "little")) % p)
        try:
            pts = E.lift_x(x, all=True)
            # pick the smaller y for determinism
            return min(pts, key=lambda P: ZZ(P[1]))
        except ValueError:
            continue
    raise RuntimeError(f"hash_to_curve failed for tag={tag!r}")


# ── Independent generator Z ──
Z = _hash_to_curve("Curve25519-Pedersen-Z")

# ── Ensure G, Z are in the prime-order subgroup (multiply by cofactor 8) ──
G = 8 * G
Z = 8 * Z
assert G != E(0), "G must not be the identity"
assert Z != E(0), "Z must not be the identity"
assert q * G == E(0), "G must have order q"
assert q * Z == E(0), "Z must have order q"


def scalar_mult(k, P):
    """Scalar multiplication k·P, where k is an integer and P is a curve point."""
    return Integer(k) * P


def point_add(P, Q):
    """Point addition P + Q on the curve."""
    return P + Q


def random_scalar(rng=None):
    """Generate a random scalar in Z_q (1 <= s < q)."""
    if rng is None:
        from sage.all import randint
        return Integer(randint(1, int(q) - 1))
    return Integer(rng.randint(1, int(q) - 1))


# ── Identity element ──
O = E(0)
