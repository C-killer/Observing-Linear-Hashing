#pragma once
#include <cstdint>
#include <string>

struct TrialConfig {
    int u;
    int l;
    int64_t m;
    uint64_t seed_S;
    uint64_t seed_h;
    int k;
    std::string dist; // "uniform"
};

int run_trial_maxload(const TrialConfig& cfg);
