#pragma once
/**
 * Curve25519 elliptic curve wrapper using RELIC library.
 *
 * Internal representation: Short Weierstrass form (RELIC native).
 * Serialization: Montgomery form x||y (64 bytes, big-endian), for hash
 * compatibility with Python/SageMath implementation.
 *
 * Montgomery: y² = x³ + 486662x² + x  over F_p, p = 2^255 - 19
 * Weierstrass: y² = x³ + a_w·x + b_w  (converted)
 *
 * Conversion: x_w = x_m + A/3,  where A = 486662
 */

#include <array>
#include <cstdint>
#include <string>
#include <vector>

extern "C" {
#include <relic.h>
}

// ═══════════════════════════════════════════
//  Scalar (mod q, prime-order subgroup)
// ═══════════════════════════════════════════

class Scalar {
public:
    bn_t s_;

    Scalar();
    Scalar(uint64_t v);
    Scalar(const Scalar& other);
    Scalar& operator=(const Scalar& other);
    Scalar(Scalar&& other) noexcept;
    Scalar& operator=(Scalar&& other) noexcept;
    ~Scalar();

    static Scalar random(uint64_t& rng_state);
    static Scalar from_bytes_be(const uint8_t* data, size_t len);
    static Scalar from_int_str(const char* decimal_str);

    Scalar operator+(const Scalar& other) const;
    Scalar operator*(const Scalar& other) const;
    Scalar pow_mod(uint64_t exp) const;
    bool operator==(const Scalar& other) const;

    void to_bytes_be(uint8_t out[32]) const;
    std::array<uint8_t, 32> to_bytes_be() const;
    bool is_zero() const;
};

// ═══════════════════════════════════════════
//  Point (on Weierstrass curve, internally)
// ═══════════════════════════════════════════

class Point {
public:
    ep_t p_;

    Point();
    Point(const Point& other);
    Point& operator=(const Point& other);
    Point(Point&& other) noexcept;
    Point& operator=(Point&& other) noexcept;
    ~Point();

    bool is_identity() const;
    bool operator==(const Point& other) const;

    /// Serialize as Montgomery x||y, 64 bytes, big-endian
    void to_montgomery_bytes(uint8_t out[64]) const;
    std::array<uint8_t, 64> to_montgomery_bytes() const;

    /// Deserialize from Montgomery x||y, 64 bytes
    static Point from_montgomery_bytes(const uint8_t data[64]);
};

// ═══════════════════════════════════════════
//  Curve operations
// ═══════════════════════════════════════════

/// Initialize curve parameters (call once from main thread)
void curve_init();

/// Per-thread RELIC init (for worker threads)
void curve_init_thread();
void curve_clean_thread();

/// Global constants
const Point& get_G();
const Point& get_Z();
const bn_t& get_q();

/// Arithmetic
Point scalar_mult(const Scalar& k, const Point& P);
Point point_add(const Point& P, const Point& Q);
Point point_identity();
