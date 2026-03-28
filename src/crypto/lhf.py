"""
Pedersen 线性哈希函数（TZ23 Section 5.1, Lemma 8）。

F : Z_q² → E(F_p)
F(x1, x2) = x1·G + x2·Z

满足 Definition 1：
- S-模满同态（epimorphism）
- 非单射（non-monomorphism）
- |S|, |D|, |R| ≥ 2^κ
"""

from sage.all import Integer

from src.crypto.curve import G, Z, O, q, E, scalar_mult, point_add


def F(x1, x2):
    """
    Pedersen 线性哈希函数。
    F(x1, x2) = x1·G + x2·Z

    参数：x1, x2 ∈ Z_q
    返回：E(F_p) 上的点
    """
    return point_add(scalar_mult(x1, G), scalar_mult(x2, Z))


def F_vec(vec):
    """
    向量形式：F((x1, x2)) = x1·G + x2·Z

    参数：vec = (x1, x2)，长度为 2 的元组/列表
    返回：E(F_p) 上的点
    """
    return F(vec[0], vec[1])


def F_key(sk):
    """
    密钥空间上的 F：F(sk, 0) = sk·G
    D_key = Z_q × {0}，此时 F|_{D_key} 为双射。

    参数：sk ∈ Z_q
    返回：pk ∈ E(F_p)
    """
    return scalar_mult(sk, G)
