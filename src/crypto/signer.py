"""
Signer: wraps the state and workflow of a single MuSig2-H signing participant.

Thin wrapper that internally calls stateless functions from musig2h.py,
managing keys, nonces, and protocol phases to prevent misuse and nonce reuse.
"""

import random

from src.crypto.musig2h import keygen, presign, sign


class Signer:
    """
    A single MuSig2-H signing participant.

    Lifecycle:
        construct (KeyGen) → set_peers → presign → receive_agg_nonce → sign
        To sign again, must redo presign → receive_agg_nonce → sign
    """

    def __init__(self, seed=None):
        """
        Create a signer, automatically executes KeyGen.

        seed: random seed (int or None), for reproducible testing.
        """
        self.rng = random.Random(seed)
        self.sk, self.pk = keygen(self.rng)

        self._peers = None   # list of other signers' public keys
        self._pp = None      # own nonce commitments (public)
        self._st = None      # own nonce secrets (private)
        self._app = None     # aggregated nonce commitments

    def set_peers(self, peer_pks):
        """
        Set the list of other signers' public keys (excluding self).

        peer_pks: list of curve points
        """
        self._peers = list(peer_pks)

    def presign(self):
        """
        Offline pre-signing: generate 4 nonce groups, return public commitments.

        Returns: pp = (R_1, R_2, R_3, R_4), tuple of curve points
        """
        self._pp, self._st = presign(self.rng)
        self._app = None  # new nonce round, old aggregated commitments invalidated
        return self._pp

    def receive_agg_nonce(self, app):
        """
        Receive aggregated nonce commitments.

        app: (R_1, R_2, R_3, R_4), produced by preagg()
        """
        if self._st is None:
            raise RuntimeError("must call presign() first")
        self._app = app

    def sign(self, message):
        """
        Online signing: compute partial signature after receiving the message.

        message: bytes, the message to sign
        Returns: (R, (s0, s1))

        Nonce secrets are automatically destroyed after signing; must presign again to sign again.
        """
        if self._peers is None:
            raise RuntimeError("must call set_peers() first")
        if self._st is None:
            raise RuntimeError("must call presign() first")
        if self._app is None:
            raise RuntimeError("must call receive_agg_nonce() first")

        out = sign(self._st, self._app, self.sk, self.pk, message, self._peers)

        # destroy nonce after use, prevent reuse which could leak secret key
        self._st = None
        self._pp = None
        self._app = None

        return out
