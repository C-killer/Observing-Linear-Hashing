#ifndef LINEAR_HASH_HPP
#define LINEAR_HASH_HPP

#include <vector>
#include <cstdint>
#include <random>

class LinearHash {
public:
    LinearHash(int l, int u, uint64_t seed);

    // Compute h(x) where x is given as little-endian uint64 blocks
    // Return output also as little-endian uint64 blocks
    std::vector<uint64_t> hash(const std::vector<uint64_t>& x_blocks) const;
    int get_u() {return u;}

private:
    int l;                 // output bits
    int u;                 // input bits
    int num_in_blocks;     // ceil(u / 64)
    int num_out_blocks;    // ceil(l / 64)

    // rows[i][b] = b-th 64-bit block of i-th row
    std::vector<std::vector<uint64_t>> rows;
};

#endif