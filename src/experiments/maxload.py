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

from typing import Dict, Iterable, Tuple, Any, List
import heapq


class Maxload:
    """
    M(S,h) = max_y |{x in S : h(x)=y}|
    - h : objet avec une méthode h(x:int)->int
    """

    def __init__(self, u: int, l: int, h: Any) -> None:
        self.u = u
        self.l = l
        self.h = h

    def max_load(
        self, S: Iterable[int], k: int = 5_000
    ) -> Tuple[int, Dict[int, Tuple[int, int]]]:
        """
        Space-Saving + min-heap (tas min) avec suppression paresseuse (lazy deletion).

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
                # sinon, entrée obsolète -> on continue

        for x in S:
            y = self.h.h(x)

            # Cas 1 : y déjà suivi
            if y in table:
                c, e = table[y]
                table[y] = (c + 1, e)
                push_state(y)
                continue

            # Cas 2 : place disponible
            if len(table) < k:
                table[y] = (1, 0)
                push_state(y)
                continue

            # Cas 3 : table pleine -> remplacer l'entrée minimale
            c_min, y_min = pop_min_valid()

            # Supprimer y_min de la table (y_min sort de la structure)
            del table[y_min]

            # Insérer y en héritant de c_min comme "erreur"
            table[y] = (c_min + 1, c_min)
            push_state(y)

        ub_tracked = 0
        for c, _e in table.values():
            if c > ub_tracked:
                ub_tracked = c

        return ub_tracked, table
