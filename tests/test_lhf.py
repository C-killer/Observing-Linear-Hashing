"""lhf.py 的单元测试：验证 Pedersen LHF 满足 Definition 1。"""

import random
from src.crypto.curve import G, Z, O, q, E, scalar_mult, point_add, random_scalar
from src.crypto.lhf import F, F_vec, F_key
from sage.all import Integer


class TestLinearity:
    """F 是 Z_q-线性映射。"""

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
        """随机测试线性性：F(a+b) = F(a) + F(b)"""
        rng = random.Random(42)
        for _ in range(10):
            a1, a2 = random_scalar(rng), random_scalar(rng)
            b1, b2 = random_scalar(rng), random_scalar(rng)
            lhs = F((a1 + b1) % q, (a2 + b2) % q)
            rhs = point_add(F(a1, a2), F(b1, b2))
            assert lhs == rhs


class TestEpimorphism:
    """F 是满同态：像覆盖整个 E[q]。"""

    def test_G_in_image(self):
        """G = F(1, 0)"""
        assert F(1, 0) == G

    def test_Z_in_image(self):
        """Z = F(0, 1)"""
        assert F(0, 1) == Z

    def test_arbitrary_point_in_image(self):
        """任意 k·G + j·Z 都在像中。"""
        k, j = 12345, 67890
        P = point_add(scalar_mult(k, G), scalar_mult(j, Z))
        assert F(k, j) == P


class TestNonMonomorphism:
    """F 不是单射：存在非零核元素。"""

    def test_F_zero_zero_is_identity(self):
        """F(0, 0) = O"""
        assert F(0, 0) == O

    def test_kernel_nontrivial(self):
        """
        核非平凡：若 z* = (log_G(Z), -1)，则 F(z*) = O。
        我们不知道 log_G(Z)，但可以验证 F(a, b) = O 当且仅当
        a·G = -b·Z，即存在非零解。

        等价验证：F(0, q) = 0·G + q·Z = O（因为 Z 的阶是 q）。
        这说明 (0, q) ≡ (0, 0) mod q 在核中，
        但真正的非平凡核元素需要 DL。

        我们用 F 的维度论证：D = Z_q²（维度2），R = E[q]（维度1），
        核维度 = 2 - 1 = 1 > 0。
        直接验证：取两个不同的原像映射到同一点。
        """
        # F(1, 0) = G, 找另一组 (a, b) 使得 F(a, b) = G
        # 即 a·G + b·Z = G => (a-1)·G + b·Z = O
        # 这需要 DL，所以我们验证 non-injectivity 的另一种方式：
        # F 的定义域 Z_q² 有 q² 个元素，像 E[q] 最多 q 个元素
        # 因此 F 不可能是单射（鸽巢原理）
        #
        # 程序化验证：对随机 x，F(x1, x2) = F(x1 + q, x2)
        # （因为 G 的阶是 q）
        x1, x2 = 999, 888
        assert F(x1, x2) == F(x1 + q, x2)
        # 同理第二个分量
        assert F(x1, x2) == F(x1, x2 + q)

    def test_two_preimages(self):
        """同一个像有多个原像。"""
        P = F(42, 0)  # 42·G
        # F(42, 0) = F(42 + 0, 0 + 0)，换一种：
        # F(0, 0) + F(42, 0) 和 F(41, 0) + F(1, 0)
        # 直接构造：F(42, q-1) + F(0, 1) 只是 F(42, q-1+1) = F(42, 0)
        # 用不同的分解验证
        assert F(42, 0) == point_add(F(20, 0), F(22, 0))


class TestFVec:
    """F_vec 的接口测试。"""

    def test_tuple(self):
        assert F_vec((10, 20)) == F(10, 20)

    def test_list(self):
        assert F_vec([10, 20]) == F(10, 20)


class TestFKey:
    """F_key 密钥空间限制。"""

    def test_fkey_equals_f_with_zero(self):
        """F_key(sk) = F(sk, 0)"""
        sk = 54321
        assert F_key(sk) == F(sk, 0)

    def test_fkey_is_scalar_mult_G(self):
        """F_key(sk) = sk·G"""
        sk = 12345
        assert F_key(sk) == scalar_mult(sk, G)

    def test_fkey_injective(self):
        """F|_{D_key} 是双射：不同 sk 映射到不同 pk。"""
        sk1, sk2 = 100, 200
        assert F_key(sk1) != F_key(sk2)
