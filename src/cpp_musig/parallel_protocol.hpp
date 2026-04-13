#pragma once
/**
 * Parallel MuSig2-H protocol coordinator.
 *
 * RelicThreadPool: persistent thread pool with per-thread RELIC init/clean.
 * run_protocol_parallel: 7-step protocol with parallel KeyGen/PreSign/Sign.
 *
 * Design: docs/cpp_relic_parallel_design.md Section 9.
 */

#include "musig2h.hpp"
#include "signer.hpp"

#include <atomic>
#include <condition_variable>
#include <functional>
#include <map>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

// ═══════════════════════════════════════════
//  RelicThreadPool
// ═══════════════════════════════════════════

class RelicThreadPool {
    std::vector<std::thread> workers_;

    // Phase task dispatch
    std::function<void(size_t)> task_fn_;
    std::atomic<size_t> task_idx_{0};
    size_t task_count_ = 0;

    // Phase synchronization
    std::atomic<int> workers_done_{0};
    std::mutex phase_mtx_;
    std::condition_variable phase_start_cv_;
    std::condition_variable phase_done_cv_;
    uint64_t phase_id_ = 0;
    bool stop_ = false;

public:
    explicit RelicThreadPool(int n_threads);

    /// Dispatch n_tasks to workers, block until all complete (barrier).
    void run_phase(size_t n_tasks, std::function<void(size_t)> fn);

    ~RelicThreadPool();

    // Non-copyable, non-movable
    RelicThreadPool(const RelicThreadPool&) = delete;
    RelicThreadPool& operator=(const RelicThreadPool&) = delete;
};

// ═══════════════════════════════════════════
//  Protocol result
// ═══════════════════════════════════════════

struct ProtocolResult {
    SignOutput sigma;
    Point apk;
    bool verified;
    int n_signers;
    int num_threads;
    std::map<std::string, double> timing;
    // keys: keygen, keyagg, presign, preagg, sign, signagg, verify, total
};

// ═══════════════════════════════════════════
//  Parallel protocol entry point
// ═══════════════════════════════════════════

ProtocolResult run_protocol_parallel(
    int n_signers,
    const std::vector<uint8_t>& message,
    uint64_t seed = 42,
    int num_threads = 0   // 0 = std::thread::hardware_concurrency()
);
