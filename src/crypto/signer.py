"""
Signer：封装单个 MuSig2-H 签名参与者的状态和流程。

薄封装层，内部调用 musig2h.py 的无状态函数，
管理密钥、nonce、协议阶段，防止误用和 nonce 复用。
"""

import random

from src.crypto.musig2h import keygen, presign, sign


class Signer:
    """
    单个 MuSig2-H 签名参与者。

    生命周期：
        构造（KeyGen）→ set_peers → presign → receive_agg_nonce → sign
        如需再次签名，须重新 presign → receive_agg_nonce → sign
    """

    def __init__(self, seed=None):
        """
        创建签名者，自动执行 KeyGen。

        seed: 随机种子（int 或 None），用于可复现测试。
        """
        self.rng = random.Random(seed)
        self.sk, self.pk = keygen(self.rng)

        self._peers = None   # 其他签名者的公钥列表
        self._pp = None      # 自己的 nonce 承诺（公开）
        self._st = None      # 自己的 nonce 秘密（保密）
        self._app = None     # 聚合后的 nonce 承诺

    def set_peers(self, peer_pks):
        """
        设置其他签名者的公钥列表（不含自己）。

        peer_pks: 曲线点列表
        """
        self._peers = list(peer_pks)

    def presign(self):
        """
        离线预签名：生成 4 组 nonce，返回公开承诺。

        返回: pp = (R_1, R_2, R_3, R_4)，曲线点元组
        """
        self._pp, self._st = presign(self.rng)
        self._app = None  # 新一轮 nonce，旧的聚合承诺失效
        return self._pp

    def receive_agg_nonce(self, app):
        """
        接收聚合后的 nonce 承诺。

        app: (R_1, R_2, R_3, R_4)，由 preagg() 产出
        """
        if self._st is None:
            raise RuntimeError("必须先调用 presign()")
        self._app = app

    def sign(self, message):
        """
        在线签名：收到消息后计算部分签名。

        message: bytes，待签消息
        返回: (R, (s0, s1))

        签名后 nonce 秘密自动销毁，须重新 presign 才能再次签名。
        """
        if self._peers is None:
            raise RuntimeError("必须先调用 set_peers()")
        if self._st is None:
            raise RuntimeError("必须先调用 presign()")
        if self._app is None:
            raise RuntimeError("必须先调用 receive_agg_nonce()")

        out = sign(self._st, self._app, self.sk, self.pk, message, self._peers)

        # nonce 用完即毁，防止复用泄露私钥
        self._st = None
        self._pp = None
        self._app = None

        return out
