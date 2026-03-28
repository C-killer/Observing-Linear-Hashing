"""
Curve25519 椭圆曲线封装（Montgomery 形式），基于 SageMath。

提供：
- 有限域 F_p, p = 2^255 - 19
- 曲线 E: y² = x³ + 486662x² + x over F_p
- 基点 G (x=9)
- 独立生成元 Z（透明 hash-to-curve）
- 群的阶 q（素数阶子群）
"""

from sage.all import GF, EllipticCurve, Integer, ZZ

# ── 有限域 ──
p = Integer(2**255 - 19)
Fp = GF(p)

# ── Curve25519 (Montgomery: y² = x³ + Ax² + x) ──
A = Integer(486662)
E = EllipticCurve(Fp, [0, A, 0, 1, 0])

# 群阶 = 8 * q，q 为大素数
_order = E.order()
q = _order // 8  # cofactor = 8

# ── 基点 G ──
# Curve25519 标准基点 x=9，取 y 为正值
_G_candidates = E.lift_x(Fp(9), all=True)
G = min(_G_candidates, key=lambda P: ZZ(P[1]))  # 取较小的 y


def _hash_to_curve(tag: str):
    """
    透明 hash-to-curve：将标签字符串映射到 E 上的点。
    反复 hash 直到找到合法的 x 坐标，然后 lift 到曲线上。
    """
    from hashlib import sha256 as _sha256
    for counter in range(256):
        h = _sha256(f"{tag}:{counter}".encode()).digest()
        x = Fp(Integer(int.from_bytes(h, "little")) % p)
        try:
            pts = E.lift_x(x, all=True)
            # 取较小的 y，确保确定性
            return min(pts, key=lambda P: ZZ(P[1]))
        except ValueError:
            continue
    raise RuntimeError(f"hash_to_curve failed for tag={tag!r}")


# ── 独立生成元 Z ──
Z = _hash_to_curve("Curve25519-Pedersen-Z")

# ── 确保 G, Z 都在素数阶子群中（乘以 cofactor 8）──
G = 8 * G
Z = 8 * Z
assert G != E(0), "G must not be the identity"
assert Z != E(0), "Z must not be the identity"
assert q * G == E(0), "G must have order q"
assert q * Z == E(0), "Z must have order q"


def scalar_mult(k, P):
    """标量乘法 k·P，k 为整数，P 为曲线点。"""
    return Integer(k) * P


def point_add(P, Q):
    """曲线点加法 P + Q。"""
    return P + Q


def random_scalar(rng=None):
    """随机生成 Z_q 中的标量（1 <= s < q）。"""
    if rng is None:
        from sage.all import randint
        return Integer(randint(1, int(q) - 1))
    return Integer(rng.randint(1, int(q) - 1))


# ── 单位元 ──
O = E(0)
