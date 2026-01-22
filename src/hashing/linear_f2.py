from typing import Optional
from src.hashing import sampling
import random

class hash_f2 :
    l : int
    u : int
    M : list[int]  # M with l int, each int has u bits

    def __init__(self, l: int, u: int, seed: Optional[int] = None) -> None:
        self.l = l
        self.u = u
        rng = random.Random(seed)
        self.M = [sampling.get_sample_x(u, rng, "uniform") for _ in range(l)]

    def h(self, x: int) -> int :
        """ h(x) = M x over F2 """
        # check if x has u bits
        if not (0 <= x < (1 << self.u)):
            raise ValueError(f"x must be an int with {self.u} bits, got {x.bit_length()}.")
        
        # M · x
        res = 0
        for i in range(self.l):
            M_i = self.M[i]
            prod = (M_i & x).bit_count() & 1  # dot product over F2
            res |= (prod << i)
        return res