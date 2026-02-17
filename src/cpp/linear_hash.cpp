#include "linear_hash.hpp"

#include <stdexcept>

// Constructor
LinearHash::LinearHash(int l_, int u_, uint64_t seed)
    : l(l_), u(u_)
{
    if (l <= 0 || u <= 0)
        throw std::invalid_argument("l and u must be positive");

    num_in_blocks  = (u + 63) / 64;
    num_out_blocks = (l + 63) / 64;

    std::mt19937_64 rng(seed);

    rows.resize(l);
    for (int i = 0; i < l; ++i) {
        rows[i].resize(num_in_blocks);
        for (int b = 0; b < num_in_blocks; ++b) {
            rows[i][b] = rng();  // uniform 64-bit
        }

        // Mask off unused bits in last block if u not multiple of 64
        int excess_bits = num_in_blocks * 64 - u;
        if (excess_bits > 0) {
            uint64_t mask = (~0ULL) >> excess_bits;
            rows[i][num_in_blocks - 1] &= mask;
        }
    }
}


// Compute h(x)
std::vector<uint64_t>
LinearHash::hash(const std::vector<uint64_t>& x_blocks) const
{
    if ((int)x_blocks.size() != num_in_blocks) {
        throw std::invalid_argument("x_blocks size mismatch");
    }

    std::vector<uint64_t> y(num_out_blocks, 0ULL);

    for (int i = 0; i < l; ++i) {

        uint64_t parity = 0ULL;

        for (int b = 0; b < num_in_blocks; ++b) {
            uint64_t v = rows[i][b] & x_blocks[b];
            parity ^= (__builtin_popcountll(v) & 1ULL);
        }

        if (parity & 1ULL) {
            int block_id = i / 64;
            int bit_id   = i % 64;
            y[block_id] |= (1ULL << bit_id);
        }
    }

    return y;
}