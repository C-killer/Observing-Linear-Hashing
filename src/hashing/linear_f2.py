from typing import Optional
from src.hashing import sampling
import random

class HashF2Python :
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

class HashF2Cpp:

    def __init__(self, l: int, u: int, seed: int):
        import fasthash
        self._core = fasthash.LinearHash(l, u, int(seed))

    # single
    def h(self, x: int) -> int:
        return int(self._core.hash_int(x))
    
    # batch
    def h_many(self, xs: list[int]) -> list[int]:
        ys = self._core.hash_many_int(xs)
        return [int(y) for y in ys]
    
def blocks_to_int(blocks):
    x = 0
    shift = 0
    for b in blocks:
        x |= (b << shift)
        shift += 64
    return x

def pack_int_to_u64_blocks(x: int, u: int) -> list[int]:
    """Pack python int into little-endian uint64 blocks."""
    num_blocks = (u + 63) // 64
    blocks: list[int] = []
    mask64 = (1 << 64) - 1
    for _ in range(num_blocks):
        blocks.append(x & mask64)
        x >>= 64
    return blocks

def hash_f2(l: int, u: int, seed: int, has_cpp: bool = True):
    """
    Return an object with method h(x:int)->int
    Prefer C++ backend if available and supported, else fall back to Python version.
    """
    if has_cpp:
        print("cpp")
        return HashF2Cpp(l=l, u=u, seed=seed)
    print("py")
    return HashF2Python(l=l, u=u, seed=seed)