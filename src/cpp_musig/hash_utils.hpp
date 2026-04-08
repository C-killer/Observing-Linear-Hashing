#pragma once
/**
 * Domain-separated SHA256 hash functions for MuSig2-H.
 *
 * H(tag, data) → SHA256(tag_byte || data) → big-endian int → mod q
 *
 * Tags: H_agg = 1, H_non = 2, H_sig = 3
 *
 * Point serialization: Montgomery x||y, 32+32 bytes, big-endian
 * Scalar serialization: 32 bytes, big-endian
 */

#include "curve25519.hpp"
#include <vector>
#include <array>

// ═══════════════════════════════════════════
//  Serialization helpers
// ═══════════════════════════════════════════

/// Serialize curve point as Montgomery x||y (64 bytes, big-endian)
std::array<uint8_t, 64> point_to_bytes(const Point& P);

/// Serialize integer to 32 bytes (big-endian)
std::array<uint8_t, 32> int_to_bytes(const Scalar& n);

/// Serialize public key list (sorted by Montgomery x,y lexicographic order)
std::vector<uint8_t> serialize_pk_list(const std::vector<Point>& L);

// ═══════════════════════════════════════════
//  Domain-separated hash functions
// ═══════════════════════════════════════════

/// Core hash: SHA256(tag_byte || data) → big-endian → mod q → Scalar
Scalar hash_domain(uint8_t tag, const uint8_t* data, size_t len);
Scalar hash_domain(uint8_t tag, const std::vector<uint8_t>& data);

/// H_agg(L, pk_i) → Z_q, tag=1
/// cached_L_bytes: optional pre-serialized pk list to avoid re-sorting
Scalar H_agg(const std::vector<Point>& L, const Point& pk,
             const std::vector<uint8_t>* cached_L_bytes = nullptr);

/// H_non(apk, (R_1,...,R_4), m) → Z_q, tag=2
Scalar H_non(const Point& apk, const std::array<Point, 4>& nonce_points,
             const std::vector<uint8_t>& m);

/// H_sig(apk, R, m) → Z_q, tag=3
Scalar H_sig(const Point& apk, const Point& R,
             const std::vector<uint8_t>& m);
