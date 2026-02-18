#pragma once
#include "trial_maxload.hpp"

#include <thread>
#include <atomic>
#include <vector>
#include <stdexcept>

static std::vector<int> run_trials_parallel(
    int u, int l, int64_t m,
    const std::string& dist,
    const std::vector<uint64_t>& seeds_S,
    const std::vector<uint64_t>& seeds_h,
    int k,
    int num_threads
) {
    if (seeds_S.size() != seeds_h.size()) throw std::invalid_argument("seeds size mismatch");
    const size_t T = seeds_S.size();
    std::vector<int> out(T);

    if (num_threads <= 0) num_threads = int(std::thread::hardware_concurrency());
    if (num_threads <= 0) num_threads = 1;

    std::atomic<size_t> idx{0};

    auto worker = [&]() {
        while (true) {
            size_t i = idx.fetch_add(1);
            if (i >= T) break;
            TrialConfig cfg{u, l, m, seeds_S[i], seeds_h[i], k, dist};
            out[i] = run_trial_maxload(cfg);
        }
    };

    std::vector<std::thread> threads;
    threads.reserve(size_t(num_threads));
    for (int t = 0; t < num_threads; ++t) threads.emplace_back(worker);
    for (auto& th : threads) th.join();

    return out;
}
