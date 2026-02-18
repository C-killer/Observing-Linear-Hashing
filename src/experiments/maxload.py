# from collections import defaultdict
# from typing import Dict, Iterable, Tuple

# class Maxload:
#     """
#     M(S,h) = max_y |{x in S : h(x)=y}|
#     - u : nombre de bits des clés x
#     - l : nombre de bits des sorties (nombre de bacs = 2^l)
#     - h : un objet ayant une méthode h(x:int)->int
#     - S : itérable de clés x (int u-bits)
#     """

#     def __init__(self, u: int, l: int, h) -> None:
#         self.u = u
#         self.l = l
#         self.h = h

#     def compute_counts(self, S: Iterable[int]) -> Dict[int, int]:
#         """
#         Calcule les charges par bac: counts[y] = #{x in S : h(x)=y}.
#         """
#         counts = defaultdict(int)
#         for x in S:
#             y = self.h.h(x)
#             counts[y] += 1
#         return dict(counts)
#     #返回最大桶
#     def max_load(self, S):
#         counts = self.compute_counts(S)
#         return max(counts.values(), default=0)

from __future__ import annotations

from typing import Dict, Iterable, Iterator, Tuple, Any, List
import heapq


def _chunked(iterable: Iterable[int], chunk_size: int) -> Iterator[List[int]]:
    """Yield lists of at most chunk_size items from an iterable."""
    buf: List[int] = []
    for x in iterable:
        buf.append(x)
        if len(buf) >= chunk_size:
            yield buf
            buf = []
    if buf:
        yield buf

"""
 把 “精确统计 2^l 个桶的计数” 换成 “只追踪最可能成为最大桶的少数候选桶”，用的是经典的 Space-Saving / Frequent algorithm(重频项近似) 

 思路：当 l 很大（桶数 2^l 爆炸）时，我们不再维护完整的 counts, 而是维护一个大小为 k 的候选表 table,并用最小堆在满员时“踢掉”当前估计最小的桶。
    这非常契合项目里“l 很大导致运算/内存不可承受”的痛点：项目要求是评估 max-load(最大桶负载) 的行为, 而不是必须输出每个桶的精确计数分布。
    该方案就是把 max-load 的估计做成 流式(single pass)、内存 O(k)
"""
class Maxload:
    """
    M(S,h) = max_y |{x in S : h(x)=y}|
    - h : objet avec une méthode h(x:int)->int;
        optionally method h_many(xs:list[int])->list[int] for batch hashing
    """

    def __init__(self, u: int, l: int, h: Any) -> None:
        self.u = u
        self.l = l
        self.h = h

    def max_load(
        self, S: Iterable[int], k: int = 50_000, *, chunk_size: int = 16_384,
    ) -> Tuple[int, Dict[int, Tuple[int, int]]]:
        """
        Space-Saving + min-heap (tas min) avec suppression paresseuse (lazy deletion).
        chunk_size = 8192 / 16384 / 32768 ...
            固定 u/l/k, 跑 4096/8192/16384/32768/65536, 看 wall time, 选最小的那个

        On maintient:
          - table[y] = (c, e) : c = compteur, e = erreur
          - heap contient des tuples (c, y) et peut contenir des entrées obsolètes.
            Une entrée (c,y) est valide ssi y est encore dans table ET table[y].c == c.

        Complexité (amortie): O(N log k).

        Retour:
          - ub_tracked: max des c parmi les y suivis (borne sup parmi candidats)
          - snapshot: {y: (c, e)}
        """
        if k <= 0:
            return 0, {}

        table: Dict[int, Tuple[int, int]] = {}   # y -> (c, e)
        heap: List[Tuple[int, int]] = []         # (c, y) (lazy)

        def push_state(y: int) -> None:
            """Empile l'état courant de y."""
            c, _e = table[y]
            heapq.heappush(heap, (c, y))

        def pop_min_valid() -> Tuple[int, int]:
            """
            Extrait le minimum courant (c_min, y_min) en supprimant les entrées obsolètes.
            Suppose table non vide.
            """
            while True:
                c_min, y_min = heapq.heappop(heap)
                cur = table.get(y_min)
                if cur is not None and cur[0] == c_min:
                    return c_min, y_min

        def process_y(y: int) -> None :
            # Cas 1 : y déjà suivi
            if y in table:
                c, e = table[y]
                table[y] = (c + 1, e)
                push_state(y)
                return

            # Cas 2 : place disponible
            if len(table) < k:
                table[y] = (1, 0)
                push_state(y)
                return

            # Cas 3 : table pleine -> remplacer l'entrée minimale
            c_min, y_min = pop_min_valid()

            # Supprimer y_min de la table (y_min sort de la structure)
            del table[y_min]

            # Insérer y en héritant de c_min comme "erreur"
            table[y] = (c_min + 1, c_min)
            push_state(y)

        # --- hash stream generation (single vs batch) ---
        h_many = getattr(self.h, "h_many", None)
        use_batch = callable(h_many)

        if use_batch:
            # Batch path: iterate S in chunks, call h_many once per chunk
            for xs_chunk in _chunked(S, chunk_size):
                ys_chunk = h_many(xs_chunk)  # type: ignore[misc]
                for y in ys_chunk:
                    process_y(int(y))
        else:
            # Single path
            for x in S:
                y = self.h.h(x)
                process_y(int(y))

        ub_tracked = 0
        for c, _e in table.values():
            if c > ub_tracked:
                ub_tracked = c

        return ub_tracked, table
