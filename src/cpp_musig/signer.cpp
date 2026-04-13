/**
 * Signer state machine — C++ translation of src/crypto/signer.py.
 *
 * Enforces protocol lifecycle and destroys nonce secrets after signing
 * to prevent nonce reuse (which would leak the secret key).
 */

#include "signer.hpp"

Signer::Signer(uint64_t seed) : rng_(seed) {
    auto kp = musig_keygen(rng_);
    sk_ = kp.sk;
    pk_ = kp.pk;
}

void Signer::set_peers(const std::vector<Point>& peer_pks) {
    peers_ = peer_pks;
    peers_set_ = true;
}

void Signer::set_agg_key(const Point& apk, const Scalar& a) {
    cached_apk_ = apk;
    cached_a_ = a;
}

std::array<Point, NU> Signer::presign() {
    auto ps = musig_presign(rng_);
    auto pp = ps.pp;
    presign_state_ = std::move(ps);
    app_ = std::nullopt;  // new nonce round, invalidate old aggregated commitments
    return pp;
}

void Signer::receive_agg_nonce(const std::array<Point, NU>& app) {
    if (!presign_state_) {
        throw std::runtime_error("must call presign() first");
    }
    app_ = app;
}

SignOutput Signer::sign(const std::vector<uint8_t>& message) {
    if (!peers_set_) {
        throw std::runtime_error("must call set_peers() first");
    }
    if (!presign_state_) {
        throw std::runtime_error("must call presign() first");
    }
    if (!app_) {
        throw std::runtime_error("must call receive_agg_nonce() first");
    }

    const Point* apk_ptr = cached_apk_ ? &(*cached_apk_) : nullptr;
    const Scalar* a_ptr = cached_a_ ? &(*cached_a_) : nullptr;

    SignOutput out = musig_sign(
        presign_state_->st,
        *app_,
        sk_, pk_,
        message,
        peers_,
        apk_ptr, a_ptr
    );

    // Destroy nonce after use — prevent reuse
    presign_state_ = std::nullopt;
    app_ = std::nullopt;

    return out;
}
