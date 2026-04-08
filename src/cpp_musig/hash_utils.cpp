/**
 * Domain-separated SHA256 hash functions for MuSig2-H.
 *
 * Matches Python implementation in musig2h.py:
 *   H(tag, data) = int.from_bytes(SHA256(tag_byte || data).digest(), "big") % q
 */

#include "hash_utils.hpp"
#include <openssl/evp.h>
#include <algorithm>
#include <cstring>

// ═══════════════════════════════════════════
//  Serialization helpers
// ═══════════════════════════════════════════

std::array<uint8_t, 64> point_to_bytes(const Point& P) {
    return P.to_montgomery_bytes();
}

std::array<uint8_t, 32> int_to_bytes(const Scalar& n) {
    return n.to_bytes_be();
}

std::vector<uint8_t> serialize_pk_list(const std::vector<Point>& L) {
    // Sort by Montgomery (x, y) lexicographic order (big-endian byte comparison)
    std::vector<std::array<uint8_t, 64>> serialized;
    serialized.reserve(L.size());
    for (const auto& pk : L) {
        serialized.push_back(point_to_bytes(pk));
    }

    // Sort by byte representation (same as Python's (ZZ(P[0]), ZZ(P[1])) sort)
    std::vector<size_t> indices(L.size());
    for (size_t i = 0; i < L.size(); i++) indices[i] = i;
    std::sort(indices.begin(), indices.end(), [&](size_t a, size_t b) {
        return serialized[a] < serialized[b];
    });

    std::vector<uint8_t> result;
    result.reserve(L.size() * 64);
    for (size_t idx : indices) {
        result.insert(result.end(), serialized[idx].begin(), serialized[idx].end());
    }
    return result;
}

// ═══════════════════════════════════════════
//  Core hash function
// ═══════════════════════════════════════════

Scalar hash_domain(uint8_t tag, const uint8_t* data, size_t len) {
    uint8_t digest[32];

    EVP_MD_CTX* ctx = EVP_MD_CTX_new();
    EVP_DigestInit_ex(ctx, EVP_sha256(), nullptr);
    EVP_DigestUpdate(ctx, &tag, 1);
    EVP_DigestUpdate(ctx, data, len);
    unsigned int md_len;
    EVP_DigestFinal_ex(ctx, digest, &md_len);
    EVP_MD_CTX_free(ctx);

    // big-endian interpretation, then mod q
    return Scalar::from_bytes_be(digest, 32);
}

Scalar hash_domain(uint8_t tag, const std::vector<uint8_t>& data) {
    return hash_domain(tag, data.data(), data.size());
}

// ═══════════════════════════════════════════
//  Three domain-separated hash functions
// ═══════════════════════════════════════════

Scalar H_agg(const std::vector<Point>& L, const Point& pk,
             const std::vector<uint8_t>* cached_L_bytes) {
    // H_agg(L, pk) = H(1, serialize_pk_list(L) || point_to_bytes(pk))
    std::vector<uint8_t> data;
    if (cached_L_bytes) {
        data = *cached_L_bytes;
    } else {
        data = serialize_pk_list(L);
    }
    auto pk_bytes = point_to_bytes(pk);
    data.insert(data.end(), pk_bytes.begin(), pk_bytes.end());
    return hash_domain(1, data);
}

Scalar H_non(const Point& apk, const std::array<Point, 4>& nonce_points,
             const std::vector<uint8_t>& m) {
    // H_non(apk, (R_1,...,R_4), m) = H(2, point_to_bytes(apk) || R_1..R_4 || m)
    std::vector<uint8_t> data;
    data.reserve(64 + 4 * 64 + m.size());

    auto apk_bytes = point_to_bytes(apk);
    data.insert(data.end(), apk_bytes.begin(), apk_bytes.end());

    for (const auto& R_j : nonce_points) {
        auto rj_bytes = point_to_bytes(R_j);
        data.insert(data.end(), rj_bytes.begin(), rj_bytes.end());
    }

    data.insert(data.end(), m.begin(), m.end());
    return hash_domain(2, data);
}

Scalar H_sig(const Point& apk, const Point& R,
             const std::vector<uint8_t>& m) {
    // H_sig(apk, R, m) = H(3, point_to_bytes(apk) || point_to_bytes(R) || m)
    std::vector<uint8_t> data;
    data.reserve(64 + 64 + m.size());

    auto apk_bytes = point_to_bytes(apk);
    data.insert(data.end(), apk_bytes.begin(), apk_bytes.end());

    auto r_bytes = point_to_bytes(R);
    data.insert(data.end(), r_bytes.begin(), r_bytes.end());

    data.insert(data.end(), m.begin(), m.end());
    return hash_domain(3, data);
}
