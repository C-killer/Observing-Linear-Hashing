#pragma once
/**
 * Signer: wraps state and workflow of a single MuSig2-H signing participant.
 *
 * C++ translation of src/crypto/signer.py.
 * Lifecycle: construct (KeyGen) → set_peers → presign → receive_agg_nonce → sign
 *
 * Thread-safety: each Signer has its own RNG (uint64_t seed), safe for
 * per-thread use in Phase 3 parallel protocol.
 */

#include "musig2h.hpp"

#include <optional>
#include <stdexcept>
#include <vector>

class Signer {
    Scalar sk_;
    Point pk_;
    uint64_t rng_;

    std::vector<Point> peers_;
    bool peers_set_ = false;

    std::optional<PreSignResult> presign_state_;
    std::optional<std::array<Point, NU>> app_;

    // Cached aggregation values (from key_agg_ex, avoids recomputation in sign)
    std::optional<Point> cached_apk_;
    std::optional<Scalar> cached_a_;

public:
    /// Construct a signer, automatically executes KeyGen.
    explicit Signer(uint64_t seed);

    const Point& pk() const { return pk_; }
    const Scalar& sk() const { return sk_; }

    /// Set other signers' public keys (excluding self).
    void set_peers(const std::vector<Point>& peer_pks);

    /// Cache precomputed aggregated public key and own coefficient.
    void set_agg_key(const Point& apk, const Scalar& a);

    /// Offline pre-signing: generate NU nonce groups, return public commitments.
    std::array<Point, NU> presign();

    /// Receive aggregated nonce commitments from PreAgg.
    void receive_agg_nonce(const std::array<Point, NU>& app);

    /// Online signing: compute partial signature. Destroys nonce state after use.
    SignOutput sign(const std::vector<uint8_t>& message);
};
