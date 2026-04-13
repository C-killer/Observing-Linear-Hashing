/**
 * Parallel MuSig2-H protocol implementation.
 *
 * RelicThreadPool + run_protocol_parallel.
 * See docs/cpp_relic_parallel_design.md Section 9.
 */

#include "parallel_protocol.hpp"
#include "curve25519.hpp"

#include <algorithm>
#include <chrono>
#include <optional>
#include <stdexcept>

// ═══════════════════════════════════════════
//  RelicThreadPool
// ═══════════════════════════════════════════

RelicThreadPool::RelicThreadPool(int n_threads) {
    workers_.reserve(n_threads);
    for (int i = 0; i < n_threads; i++) {
        workers_.emplace_back([this] {
            curve_init_thread();   // RELIC per-thread init (once)

            uint64_t my_phase = 0;
            while (true) {
                // Wait for next phase or shutdown
                {
                    std::unique_lock lk(phase_mtx_);
                    phase_start_cv_.wait(lk, [&] {
                        return stop_ || phase_id_ > my_phase;
                    });
                    if (stop_) break;
                    my_phase = phase_id_;
                }

                // Grab tasks via atomic counter
                while (true) {
                    size_t i = task_idx_.fetch_add(1);
                    if (i >= task_count_) break;
                    task_fn_(i);
                }

                // Signal this worker is done
                if (workers_done_.fetch_add(1) + 1 ==
                    static_cast<int>(workers_.size())) {
                    std::lock_guard lk(phase_mtx_);
                    phase_done_cv_.notify_one();
                }
            }

            curve_clean_thread();  // RELIC per-thread cleanup (once)
        });
    }
}

void RelicThreadPool::run_phase(size_t n_tasks,
                                std::function<void(size_t)> fn) {
    // Setup phase
    {
        std::lock_guard lk(phase_mtx_);
        task_fn_ = std::move(fn);
        task_count_ = n_tasks;
        task_idx_.store(0);
        workers_done_.store(0);
        phase_id_++;
    }
    phase_start_cv_.notify_all();

    // Wait for all workers to finish
    std::unique_lock lk(phase_mtx_);
    phase_done_cv_.wait(lk, [&] {
        return workers_done_.load() ==
               static_cast<int>(workers_.size());
    });
}

RelicThreadPool::~RelicThreadPool() {
    {
        std::lock_guard lk(phase_mtx_);
        stop_ = true;
    }
    phase_start_cv_.notify_all();
    for (auto& w : workers_) w.join();
}

// ═══════════════════════════════════════════
//  run_protocol_parallel
// ═══════════════════════════════════════════

ProtocolResult run_protocol_parallel(
    int n_signers,
    const std::vector<uint8_t>& message,
    uint64_t seed,
    int num_threads)
{
    curve_init();  // idempotent, ensures main thread has RELIC context

    if (num_threads <= 0)
        num_threads = static_cast<int>(std::thread::hardware_concurrency());
    if (num_threads <= 0) num_threads = 1;
    num_threads = std::min(num_threads, n_signers);

    ProtocolResult result;
    result.n_signers = n_signers;
    result.num_threads = num_threads;
    auto& timing = result.timing;

    using clock = std::chrono::high_resolution_clock;
    auto elapsed = [](auto t0) {
        return std::chrono::duration<double>(clock::now() - t0).count();
    };

    // Signer storage: optional because Signer has no default constructor.
    // Declared BEFORE pool so pool destructor (join) runs first.
    std::vector<std::optional<Signer>> signers(n_signers);

    RelicThreadPool pool(num_threads);

    // ═══ Phase 1: KeyGen × n [PARALLEL] ═══
    auto t0 = clock::now();
    pool.run_phase(n_signers, [&](size_t i) {
        signers[i].emplace(seed + static_cast<uint64_t>(i));
    });
    timing["keygen"] = elapsed(t0);

    // ═══ Phase 2: KeyAgg [SEQUENTIAL] ═══
    t0 = clock::now();
    std::vector<Point> all_pks;
    all_pks.reserve(n_signers);
    for (int i = 0; i < n_signers; i++) {
        all_pks.push_back(signers[i]->pk());
    }
    auto agg = musig_key_agg_ex(all_pks);

    for (int i = 0; i < n_signers; i++) {
        std::vector<Point> peers;
        peers.reserve(n_signers - 1);
        for (int j = 0; j < n_signers; j++) {
            if (j != i) peers.push_back(all_pks[j]);
        }
        signers[i]->set_peers(peers);
        signers[i]->set_agg_key(agg.apk, agg.coeffs[i]);
    }
    timing["keyagg"] = elapsed(t0);

    // ═══ Phase 3: PreSign × n [PARALLEL] ═══
    t0 = clock::now();
    std::vector<std::array<Point, NU>> pp_list(n_signers);
    pool.run_phase(n_signers, [&](size_t i) {
        pp_list[i] = signers[i]->presign();
    });
    timing["presign"] = elapsed(t0);

    // ═══ Phase 4: PreAgg [SEQUENTIAL] ═══
    t0 = clock::now();
    auto app = musig_preagg(pp_list);
    for (int i = 0; i < n_signers; i++) {
        signers[i]->receive_agg_nonce(app);
    }
    timing["preagg"] = elapsed(t0);

    // ═══ Phase 5: Sign × n [PARALLEL] ═══
    t0 = clock::now();
    std::vector<SignOutput> outs(n_signers);
    pool.run_phase(n_signers, [&](size_t i) {
        outs[i] = signers[i]->sign(message);
    });
    timing["sign"] = elapsed(t0);

    // ═══ Phase 6: SignAgg [SEQUENTIAL] ═══
    t0 = clock::now();
    auto sigma_opt = musig_sign_agg(outs);
    if (!sigma_opt) {
        throw std::runtime_error("SignAgg failed: R mismatch");
    }
    result.sigma = *sigma_opt;
    timing["signagg"] = elapsed(t0);

    // ═══ Phase 7: Ver [SEQUENTIAL] ═══
    t0 = clock::now();
    result.verified = musig_ver(agg.apk, message, result.sigma);
    timing["verify"] = elapsed(t0);

    result.apk = agg.apk;

    // Total = sum of all phases
    timing["total"] = timing["keygen"] + timing["keyagg"] +
                      timing["presign"] + timing["preagg"] +
                      timing["sign"] + timing["signagg"] + timing["verify"];

    return result;
}
