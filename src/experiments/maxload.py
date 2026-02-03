from collections import defaultdict
from typing import Dict, Iterable, Tuple

class Maxload:
    """
    M(S,h) = max_y |{x in S : h(x)=y}|
    - u : nombre de bits des clés x
    - l : nombre de bits des sorties (nombre de bacs = 2^l)
    - h : un objet ayant une méthode h(x:int)->int
    - S : itérable de clés x (int u-bits)
    """

    def __init__(self, u: int, l: int, h) -> None:
        self.u = u
        self.l = l
        self.h = h

    def compute_counts(self, S: Iterable[int]) -> Dict[int, int]:
        """
        Calcule les charges par bac: counts[y] = #{x in S : h(x)=y}.
        """
        counts = defaultdict(int)
        for x in S:
            y = self.h.h(x)
            counts[y] += 1
        return dict(counts)
    #返回最大桶
    def max_load(self, S):
        counts = self.compute_counts(S)
        return max(counts.values(), default=0)
