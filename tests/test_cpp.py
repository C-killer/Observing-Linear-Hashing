import random
import unittest

import fasthash

from src.hashing.linear_f2 import (
    HashF2Python,
    pack_int_to_u64_blocks,
    blocks_to_int,
)


class TestLinearHashCpp(unittest.TestCase):

    def test_basic_construction(self):
        l = 100
        u = 200
        seed = 42

        h = fasthash.LinearHash(l, u, seed)
        self.assertIsNotNone(h)

    def test_output_bit_length(self):
        l = 100
        u = 200
        seed = 123

        h = fasthash.LinearHash(l, u, seed)

        for _ in range(50):
            x = random.getrandbits(u)
            blocks = pack_int_to_u64_blocks(x, u)
            y_blocks = h.hash(blocks)
            y = blocks_to_int(y_blocks)

            # Ensure output fits in l bits
            self.assertLessEqual(y.bit_length(), l)

    def test_different_inputs_give_different_outputs(self):
        l = 64
        u = 128
        seed = 999

        h = fasthash.LinearHash(l, u, seed)

        x1 = 123456789
        x2 = 987654321

        y1 = blocks_to_int(h.hash(pack_int_to_u64_blocks(x1, u)))
        y2 = blocks_to_int(h.hash(pack_int_to_u64_blocks(x2, u)))

        self.assertNotEqual(y1, y2)

    def test_multiple_calls_consistency(self):
        l = 80
        u = 160
        seed = 777

        h = fasthash.LinearHash(l, u, seed)

        x = random.getrandbits(u)
        blocks = pack_int_to_u64_blocks(x, u)

        y1 = blocks_to_int(h.hash(blocks))
        y2 = blocks_to_int(h.hash(blocks))

        self.assertEqual(y1, y2)


if __name__ == "__main__":
    unittest.main()