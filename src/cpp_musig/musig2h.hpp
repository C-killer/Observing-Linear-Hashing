#pragma once
/**
 * MuSig2-H multi-signature scheme (TZ23 Fig. 4, ν=4).
 *
 * 8 stateless algorithms: setup, keygen, key_agg, key_agg_ex,
 * presign, preagg, sign, sign_agg, ver.
 *
 * Direct C++ translation of src/crypto/musig2h.py.
 */

#include "curve25519.hpp"
#include "hash_utils.hpp"

#include <array>
#include <optional>
#include <utility>
#include <vector>

constexpr int NU = 4;  // number of nonces per signer

// ═══════════════════════════════════════════
//  Data structures
// ═══════════════════════════════════════════

struct KeyPair {
    Scalar sk;
    Point pk;
};

struct PreSignResult {
    std::array<Point, NU> pp;                          // public nonce commitments
    std::array<std::pair<Scalar, Scalar>, NU> st;      // secret nonce pairs (r_j0, r_j1)
};

struct SignOutput {
    Point R;
    Scalar s0;
    Scalar s1;
};

struct KeyAggResult {
    Point apk;
    std::vector<Scalar> coeffs;  // coeffs[i] = H_agg(L, L[i]), same order as input L
};

// ═══════════════════════════════════════════
//  Eight algorithms
// ═══════════════════════════════════════════

/// KeyGen() → (sk, pk), sk ← random Z_q, pk = sk·G
KeyPair musig_keygen(uint64_t& rng);

/// KeyAgg(L) → apk
Point musig_key_agg(const std::vector<Point>& L);

/// KeyAgg(L) → (apk, coeffs), extended version with per-signer coefficients
KeyAggResult musig_key_agg_ex(const std::vector<Point>& L);

/// PreSign() → (pp, st)
PreSignResult musig_presign(uint64_t& rng);

/// PreAgg({pp_1, ..., pp_n}) → app
std::array<Point, NU> musig_preagg(const std::vector<std::array<Point, NU>>& pp_list);

/// Sign(st, app, sk, pk, m, L, [apk, a]) → (R, s0, s1)
/// apk/a: optional precomputed values (cache from key_agg_ex)
SignOutput musig_sign(
    const std::array<std::pair<Scalar, Scalar>, NU>& st,
    const std::array<Point, NU>& app,
    const Scalar& sk,
    const Point& pk,
    const std::vector<uint8_t>& m,
    const std::vector<Point>& L,
    const Point* apk = nullptr,
    const Scalar* a = nullptr
);

/// SignAgg({out_1, ..., out_n}) → σ or nullopt (R mismatch)
std::optional<SignOutput> musig_sign_agg(const std::vector<SignOutput>& outs);

/// Ver(apk, m, σ) → bool, verifies F(s) == R + c·apk
bool musig_ver(const Point& apk, const std::vector<uint8_t>& m, const SignOutput& sigma);
