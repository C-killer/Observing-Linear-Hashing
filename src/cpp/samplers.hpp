#pragma once
#include <cstdint>
#include <random>
#include <vector>
#include <string>
#include <stdexcept>

struct DistSpec {
    std::string name; // "uniform" / "bernoulli" / ...
    // 以后可加入参数，比如 p/k/p0/p1
};

// fill x_blocks with u-bit random vector
inline void sample_uniform_blocks(std::mt19937_64& rng,
                                 std::vector<uint64_t>& x_blocks,
                                 int u) {
    const int B = int(x_blocks.size());
    for (int b = 0; b < B; ++b) x_blocks[b] = rng();
    // mask last block
    const int excess_bits = B * 64 - u;
    if (excess_bits > 0) {
        uint64_t mask = (~0ULL) >> excess_bits;
        x_blocks[B - 1] &= mask;
    }
}

inline void sample_blocks(std::mt19937_64& rng,
                          std::vector<uint64_t>& x_blocks,
                          int u,
                          const DistSpec& dist) {
    if (dist.name == "uniform") {
        sample_uniform_blocks(rng, x_blocks, u);
        return;
    }
    throw std::invalid_argument("unsupported dist: " + dist.name);
}

// TODO : sample_bernoulli, sample_Hamming_weight, sample_Markov