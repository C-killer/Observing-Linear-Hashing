"""
MuSig2-H 多签方案（TZ23 Fig. 4, ν=4）。

LHF = (PGen, F)，其中 F 为 Pedersen 线性哈希函数。
实现 8 个算法：Setup, KeyGen, KeyAgg, PreSign, PreAgg, Sign, SignAgg, Ver。

哈希函数域分离：
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

NU = 4  # nonce 数量，固定


# ═══════════════════════════════════════════
#  序列化工具（用于哈希输入）
# ═══════════════════════════════════════════

def _int_to_bytes(n):
    """将整数序列化为 32 字节（大端）。"""
    return int(n).to_bytes(32, "big")


def _point_to_bytes(P):
    """将曲线点序列化为 x||y 各 32 字节。"""
    if P == O:
        return b"\x00" * 64
    return _int_to_bytes(P[0]) + _int_to_bytes(P[1])


def _hash(domain_tag: int, *parts: bytes) -> int:
    """
    域分离哈希 H(tag, data) → Z_q。
    tag: 1=agg, 2=non, 3=sig
    """
    h = sha256()
    h.update(domain_tag.to_bytes(1, "big"))
    for part in parts:
        h.update(part)
    # 截断到 Z_q
    return Integer(int.from_bytes(h.digest(), "big") % int(q))


# ═══════════════════════════════════════════
#  三个哈希函数
# ═══════════════════════════════════════════

def _serialize_pk_list(L):
    """将公钥列表序列化（排序以保证确定性）。"""
    # 按 (x, y) 字典序排序
    sorted_L = sorted(L, key=lambda P: (ZZ(P[0]), ZZ(P[1])))
    return b"".join(_point_to_bytes(pk) for pk in sorted_L)


def H_agg(L, pk):
    """H_agg(L, pk_i) → Z_q，用于 KeyAgg。"""
    return _hash(1, _serialize_pk_list(L), _point_to_bytes(pk))


def H_non(apk, nonce_points, m):
    """
    H_non(apk, (R_1,...,R_4), m) → Z_q，用于 Sign。
    nonce_points: 长度为 4 的曲线点列表
    m: bytes
    """
    data = _point_to_bytes(apk)
    for R_j in nonce_points:
        data += _point_to_bytes(R_j)
    data += m
    return _hash(2, data)


def H_sig(apk, R, m):
    """H_sig(apk, R, m) → Z_q，用于 Sign/Ver。"""
    return _hash(3, _point_to_bytes(apk), _point_to_bytes(R), m)


# ═══════════════════════════════════════════
#  八个算法
# ═══════════════════════════════════════════

def setup():
    """
    Setup(1^κ) → par
    返回公共参数（本实现中 par 隐式为 curve.py 中的全局常量）。
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
    L: 公钥列表（曲线点）
    apk = Σ H_agg(L, pk_i) · pk_i
    """
    apk = O
    for pk_i in L:
        a_i = H_agg(L, pk_i)
        apk = point_add(apk, scalar_mult(a_i, pk_i))
    return apk


def presign(rng=None):
    """
    PreSign() → (pp, st)
    pp = (R_1, ..., R_4)    公开的 nonce 承诺（曲线点）
    st = (r_1, ..., r_4)    保密的 nonce 对（每个 r_j ∈ Z_q²）
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
    pp_list: 每个签名者的 pp = (R_1, ..., R_4)
    app = (Σ_i R_{i,1}, ..., Σ_i R_{i,4})
    """
    app = [O] * NU
    for pp_i in pp_list:
        for j in range(NU):
            app[j] = point_add(app[j], pp_i[j])
    return tuple(app)


def sign(st, app, sk, pk, m, L):
    """
    Sign(st, app, sk, pk, m, L) → out = (R, s)

    st:  保密 nonce 对 (r_1, ..., r_4)，每个 r_j = (r_j0, r_j1) ∈ Z_q²
    app: 聚合 nonce (R_1, ..., R_4)，曲线点
    sk:  签名私钥 ∈ Z_q
    pk:  签名公钥（曲线点）
    m:   消息 (bytes)
    L:   其他签名者的公钥列表（不含自己的 pk）
    """
    # L ← L ∪ {pk}
    L_full = list(L) + [pk]

    # apk ← KeyAgg(L)
    apk = key_agg(L_full)

    # a ← H_agg(L, pk)
    a = H_agg(L_full, pk)

    # (R_1, ..., R_4) ← app
    # b ← H_non(apk, (R_1,...,R_4), m)
    b = H_non(apk, app, m)

    # R ← Σ_{j∈[4]} b^{j-1} · R_j
    R = O
    for j in range(NU):
        bj = pow(int(b), j, int(q))  # b^{j-1} 用 j 因为 j 从 0 开始
        R = point_add(R, scalar_mult(bj, app[j]))

    # c ← H_sig(apk, R, m)
    c = H_sig(apk, R, m)

    # s ← Σ_{j∈[4]} b^{j-1} · r_j + c·a·sk
    # 其中 sk 作为 D_key 元素为 (sk, 0)
    # s[0] = Σ b^{j-1}·r_j[0] + c·a·sk
    # s[1] = Σ b^{j-1}·r_j[1]
    s0 = Integer(0)
    s1 = Integer(0)
    for j in range(NU):
        bj = Integer(pow(int(b), j, int(q)))
        s0 = (s0 + bj * st[j][0]) % q
        s1 = (s1 + bj * st[j][1]) % q
    s0 = (s0 + c * a * sk) % q
    # s1 不变（c·a·0 = 0）

    return (R, (int(s0), int(s1)))


def sign_agg(out_list):
    """
    SignAgg({out_1, ..., out_n}) → σ = (R, s) 或 None（失败）

    out_list: 每个签名者的 (R_i, s_i)
    验证所有 R_i 相等，然后 s = Σ s_i（Z_q² 上分量加法）
    """
    R, s = out_list[0]
    s0, s1 = s[0], s[1]

    for i in range(1, len(out_list)):
        R_i, s_i = out_list[i]
        if R_i != R:
            return None  # R 不一致，协议失败
        s0 = (s0 + s_i[0]) % int(q)
        s1 = (s1 + s_i[1]) % int(q)

    return (R, (int(s0), int(s1)))


def ver(apk, m, sigma):
    """
    Ver(apk, m, σ) → bool

    σ = (R, s)，其中 s = (s0, s1) ∈ Z_q²
    验证：F(s) == R + c·apk
    即：s0·G + s1·Z == R + H_sig(apk, R, m)·apk
    """
    R, s = sigma
    c = H_sig(apk, R, m)
    lhs = F(s[0], s[1])
    rhs = point_add(R, scalar_mult(c, apk))
    return lhs == rhs
