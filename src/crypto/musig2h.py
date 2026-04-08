"""
MuSig2-H multi-signature scheme (TZ23 Fig. 4, ν=4).

LHF = (PGen, F), where F is the Pedersen linear hash function.
Implements 8 algorithms: Setup, KeyGen, KeyAgg, PreSign, PreAgg, Sign, SignAgg, Ver.

Domain-separated hash functions:
  H_agg(·) := H(1, ·)
  H_non(·) := H(2, ·)
  H_sig(·) := H(3, ·)
"""

from hashlib import sha256
from sage.all import Integer, ZZ

from src.crypto.curve import (
    E, G, Z, O, q, Fp,
    scalar_mult, point_add, random_scalar,
)
from src.crypto.lhf import F, F_vec, F_key

NU = 4  # number of nonces, fixed


# ═══════════════════════════════════════════
#  Serialization utilities (for hash inputs)
# ═══════════════════════════════════════════

def _int_to_bytes(n):
    """Serialize an integer to 32 bytes (big-endian)."""
    return int(n).to_bytes(32, "big")


def _point_to_bytes(P):
    """Serialize a curve point as x||y, each 32 bytes."""
    if P == O:
        return b"\x00" * 64
    return _int_to_bytes(P[0]) + _int_to_bytes(P[1])


def _hash(domain_tag: int, *parts: bytes) -> int:
    """
    Domain-separated hash H(tag, data) → Z_q.
    tag: 1=agg, 2=non, 3=sig
    """
    h = sha256()
    h.update(domain_tag.to_bytes(1, "big"))
    for part in parts:
        h.update(part)
    # truncate to Z_q
    return Integer(int.from_bytes(h.digest(), "big") % int(q))


# ═══════════════════════════════════════════
#  Three hash functions
# ═══════════════════════════════════════════

def _serialize_pk_list(L):
    """Serialize public key list (sorted for determinism)."""
    # sort by (x, y) lexicographic order
    sorted_L = sorted(L, key=lambda P: (ZZ(P[0]), ZZ(P[1])))
    return b"".join(_point_to_bytes(pk) for pk in sorted_L)


def H_agg(L, pk, _L_bytes=None):
    """H_agg(L, pk_i) → Z_q, used in KeyAgg."""
    L_bytes = _L_bytes if _L_bytes is not None else _serialize_pk_list(L)
    return _hash(1, L_bytes, _point_to_bytes(pk))


def H_non(apk, nonce_points, m):
    """
    H_non(apk, (R_1,...,R_4), m) → Z_q, used in Sign.
    nonce_points: list of 4 curve points
    m: bytes
    """
    data = _point_to_bytes(apk)
    for R_j in nonce_points:
        data += _point_to_bytes(R_j)
    data += m
    return _hash(2, data)


def H_sig(apk, R, m):
    """H_sig(apk, R, m) → Z_q, used in Sign/Ver."""
    return _hash(3, _point_to_bytes(apk), _point_to_bytes(R), m)


# ═══════════════════════════════════════════
#  Eight algorithms
# ═══════════════════════════════════════════

def setup():
    """
    Setup(1^κ) → par
    Returns public parameters (in this implementation, par is implicitly the global constants in curve.py).
    """
    return {"p": int(E.base_ring().characteristic()), "G": G, "Z": Z, "q": q}


def keygen(rng=None):
    """
    KeyGen() → (sk, pk)
    sk ←$ Z_q, pk = F(sk, 0) = sk·G
    """
    sk = random_scalar(rng)
    pk = F_key(sk)
    return (sk, pk)


def key_agg(L):
    """
    KeyAgg(L) → apk
    L: list of public keys (curve points)
    apk = Σ H_agg(L, pk_i) · pk_i
    """
    apk, _ = key_agg_ex(L)
    return apk


def key_agg_ex(L):
    """
    KeyAgg(L) → (apk, coeffs)
    Extended version: also returns per-signer aggregation coefficients.
    coeffs: dict mapping pk → a_i (Z_q scalar)
    """
    L_bytes = _serialize_pk_list(L)
    apk = O
    coeffs = {}
    for pk_i in L:
        a_i = H_agg(L, pk_i, _L_bytes=L_bytes)
        coeffs[pk_i] = a_i
        apk = point_add(apk, scalar_mult(a_i, pk_i))
    return apk, coeffs


def presign(rng=None):
    """
    PreSign() → (pp, st)
    pp = (R_1, ..., R_4)    public nonce commitments (curve points)
    st = (r_1, ..., r_4)    secret nonce pairs (each r_j ∈ Z_q²)
    """
    st = []
    pp = []
    for _ in range(NU):
        r_j = (random_scalar(rng), random_scalar(rng))
        R_j = F(r_j[0], r_j[1])
        st.append(r_j)
        pp.append(R_j)
    return (tuple(pp), tuple(st))


def preagg(pp_list):
    """
    PreAgg({pp_1, ..., pp_n}) → app
    pp_list: each signer's pp = (R_1, ..., R_4)
    app = (Σ_i R_{i,1}, ..., Σ_i R_{i,4})
    """
    app = [O] * NU
    for pp_i in pp_list:
        for j in range(NU):
            app[j] = point_add(app[j], pp_i[j])
    return tuple(app)


def sign(st, app, sk, pk, m, L, apk=None, a=None):
    """
    Sign(st, app, sk, pk, m, L, [apk, a]) → out = (R, s)

    st:  secret nonce pairs (r_1, ..., r_4), each r_j = (r_j0, r_j1) ∈ Z_q²
    app: aggregated nonces (R_1, ..., R_4), curve points
    sk:  signing secret key ∈ Z_q
    pk:  signing public key (curve point)
    m:   message (bytes)
    L:   list of other signers' public keys (excluding own pk)
    apk: (optional) precomputed aggregated public key, skips KeyAgg recomputation
    a:   (optional) precomputed H_agg(L∪{pk}, pk), skips H_agg recomputation
    """
    # L ← L ∪ {pk}
    L_full = list(L) + [pk]

    # apk ← KeyAgg(L)  [use precomputed if available]
    if apk is None:
        apk = key_agg(L_full)

    # a ← H_agg(L, pk)  [use precomputed if available]
    if a is None:
        a = H_agg(L_full, pk)

    # (R_1, ..., R_4) ← app
    # b ← H_non(apk, (R_1,...,R_4), m)
    b = H_non(apk, app, m)

    # R ← Σ_{j∈[4]} b^{j-1} · R_j
    R = O
    for j in range(NU):
        bj = pow(int(b), j, int(q))  # b^{j-1} using j since j starts from 0
        R = point_add(R, scalar_mult(bj, app[j]))

    # c ← H_sig(apk, R, m)
    c = H_sig(apk, R, m)

    # s ← Σ_{j∈[4]} b^{j-1} · r_j + c·a·sk
    # where sk as a D_key element is (sk, 0)
    # s[0] = Σ b^{j-1}·r_j[0] + c·a·sk
    # s[1] = Σ b^{j-1}·r_j[1]
    s0 = Integer(0)
    s1 = Integer(0)
    for j in range(NU):
        bj = Integer(pow(int(b), j, int(q)))
        s0 = (s0 + bj * st[j][0]) % q
        s1 = (s1 + bj * st[j][1]) % q
    s0 = (s0 + c * a * sk) % q
    # s1 unchanged (c·a·0 = 0)

    return (R, (int(s0), int(s1)))


def sign_agg(out_list):
    """
    SignAgg({out_1, ..., out_n}) → σ = (R, s) or None (failure)

    out_list: each signer's (R_i, s_i)
    Verifies all R_i are equal, then s = Σ s_i (component-wise addition over Z_q²)
    """
    R, s = out_list[0]
    s0, s1 = s[0], s[1]

    for i in range(1, len(out_list)):
        R_i, s_i = out_list[i]
        if R_i != R:
            return None  # R mismatch, protocol failure
        s0 = (s0 + s_i[0]) % int(q)
        s1 = (s1 + s_i[1]) % int(q)

    return (R, (int(s0), int(s1)))


def ver(apk, m, sigma):
    """
    Ver(apk, m, σ) → bool

    σ = (R, s), where s = (s0, s1) ∈ Z_q²
    Verifies: F(s) == R + c·apk
    i.e.: s0·G + s1·Z == R + H_sig(apk, R, m)·apk
    """
    R, s = sigma
    c = H_sig(apk, R, m)
    lhs = F(s[0], s[1])
    rhs = point_add(R, scalar_mult(c, apk))
    return lhs == rhs
