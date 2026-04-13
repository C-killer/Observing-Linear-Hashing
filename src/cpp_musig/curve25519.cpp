/**
 * Curve25519 implementation using RELIC library.
 * Info : https://fr.wikipedia.org/wiki/Curve25519
 *
 * Montgomery curve: y² = x³ + 486662x² + x over F_p, p = 2^255 - 19
 * Internally converted to Short Weierstrass for RELIC operations.
 *
 * Coordinate conversion:
 *   x_w = x_m + A/3   (Montgomery → Weierstrass)
 *   x_m = x_w - A/3   (Weierstrass → Montgomery)
 *   y unchanged
 *
 * Base points:
 *   G: Montgomery x=9, lift_x, smaller y, ×8 cofactor
 *   Z: hash-to-curve("Curve25519-Pedersen-Z"), ×8 cofactor
 */

#include "curve25519.hpp"

#include <openssl/evp.h>
#include <cstring>
#include <stdexcept>
#include <algorithm>

// ═══════════════════════════════════════════
//  Constants
// ═══════════════════════════════════════════

// p = 2^255 - 19, le module du corps fini F_p de Curve25519
static const char* P_STR =
    "7fffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffed";

// A = 486662 (0x76D06), coefficient de la courbe Montgomery y² = x³ + Ax² + x
static const char* A_MONT = "76d06";

// q = ordre du sous-groupe premier de Curve25519 (cofacteur = 8, ordre total = 8q)
// q = 2^252 + 27742317777372353535851937790883648493
// Les points G et Z sont multipliés par 8 pour avoir l'ordre q
static const char* Q_STR =
    "1000000000000000000000000000000014def9dea2f79cd65812631a5cf5d3ed";

// A/3 mod p — constante pour la conversion Montgomery ↔ Weierstrass
// Conversion : x_w = x_m + A/3, x_m = x_w - A/3
// 486662/3 n'est pas entier, mais modulo p l'inverse de 3 existe :
// A/3 = 486662 × 3⁻¹ mod p (un grand nombre dans F_p)
static const char* A_DIV_3_STR =
    "2aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaad2451";

// Coefficients de la forme Short Weierstrass y² = x³ + a_w·x + b_w
// Déduits du paramètre Montgomery A pour que RELIC puisse opérer nativement
// a_w = (3 - A²) / 3 mod p
static const char* A_W_STR =
    "2aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa984914a144";
// b_w = (2A³ - 9A) / 27 mod p
static const char* B_W_STR =
    "7b425ed097b425ed097b425ed097b425ed097b425ed097b4260b5e9c7710c864";

// Global instances
static Point g_G;
static Point g_Z;
static bn_t g_q;
static fp_t g_A_div_3;  // A/3 mod p for coordinate conversion
static bool g_initialized = false;

// ═══════════════════════════════════════════
//  Helper: bn from hex
// ═══════════════════════════════════════════

static void bn_from_hex(bn_t n, const char* hex) {
    bn_read_str(n, hex, strlen(hex), 16);
}

static void fp_from_hex(fp_t f, const char* hex) {
    bn_t tmp;
    bn_null(tmp);
    bn_new(tmp);
    bn_read_str(tmp, hex, strlen(hex), 16);
    fp_prime_conv(f, tmp);
    bn_free(tmp);
}

// ═══════════════════════════════════════════
//  Scalar implementation
// ═══════════════════════════════════════════

Scalar::Scalar() {
    bn_null(s_);
    bn_new(s_);
    bn_zero(s_);
}

Scalar::Scalar(uint64_t v) {
    bn_null(s_);
    bn_new(s_);
    bn_set_dig(s_, v);
}

Scalar::Scalar(const Scalar& other) {
    bn_null(s_);
    bn_new(s_);
    bn_copy(s_, other.s_);
}

Scalar& Scalar::operator=(const Scalar& other) {
    if (this != &other) {
        bn_copy(s_, other.s_);
    }
    return *this;
}

Scalar::Scalar(Scalar&& other) noexcept {
    bn_null(s_);
    bn_new(s_);
    bn_copy(s_, other.s_);
    bn_zero(other.s_);
}

Scalar& Scalar::operator=(Scalar&& other) noexcept {
    if (this != &other) {
        bn_copy(s_, other.s_);
        bn_zero(other.s_);
    }
    return *this;
}

Scalar::~Scalar() {
    bn_free(s_);
}

Scalar Scalar::random(uint64_t& rng_state) {
    // Simple xorshift64 for reproducible RNG (same seed → same sequence)
    // Generate 32 bytes, interpret as big-endian, mod q, ensure [1, q-1]
    Scalar result;
    uint8_t buf[32];
    for (int i = 0; i < 4; i++) {
        rng_state ^= rng_state << 13;
        rng_state ^= rng_state >> 7;
        rng_state ^= rng_state << 17;
        uint64_t val = rng_state;
        for (int j = 0; j < 8; j++) {
            buf[i * 8 + j] = (uint8_t)(val >> (56 - j * 8));
        }
    }
    bn_read_bin(result.s_, buf, 32);
    bn_mod(result.s_, result.s_, g_q);
    // ensure non-zero
    if (bn_is_zero(result.s_)) {
        bn_set_dig(result.s_, 1);
    }
    return result;
}

Scalar Scalar::from_bytes_be(const uint8_t* data, size_t len) {
    Scalar result;
    bn_read_bin(result.s_, data, len);
    bn_mod(result.s_, result.s_, g_q);
    return result;
}

Scalar Scalar::from_int_str(const char* decimal_str) {
    Scalar result;
    bn_read_str(result.s_, decimal_str, strlen(decimal_str), 10);
    return result;
}

Scalar Scalar::operator+(const Scalar& other) const {
    Scalar result;
    bn_add(result.s_, s_, other.s_);
    bn_mod(result.s_, result.s_, g_q);
    return result;
}

Scalar Scalar::operator*(const Scalar& other) const {
    Scalar result;
    bn_mul(result.s_, s_, other.s_);
    bn_mod(result.s_, result.s_, g_q);
    return result;
}

Scalar Scalar::pow_mod(uint64_t exp) const {
    Scalar result(1);
    if (exp == 0) return result;

    bn_t e;
    bn_null(e);
    bn_new(e);
    bn_set_dig(e, exp);
    bn_mxp(result.s_, s_, e, g_q);
    bn_free(e);
    return result;
}

bool Scalar::operator==(const Scalar& other) const {
    return bn_cmp(s_, other.s_) == RLC_EQ;
}

void Scalar::to_bytes_be(uint8_t out[32]) const {
    memset(out, 0, 32);
    int len = bn_size_bin(s_);
    if (len > 32) len = 32;
    bn_write_bin(out + (32 - len), len, s_);
}

std::array<uint8_t, 32> Scalar::to_bytes_be() const {
    std::array<uint8_t, 32> out;
    to_bytes_be(out.data());
    return out;
}

bool Scalar::is_zero() const {
    return bn_is_zero(s_);
}

// ═══════════════════════════════════════════
//  Point implementation
// ═══════════════════════════════════════════

Point::Point() {
    ep_null(p_);
    ep_new(p_);
    ep_set_infty(p_);
}

Point::Point(const Point& other) {
    ep_null(p_);
    ep_new(p_);
    ep_copy(p_, other.p_);
}

Point& Point::operator=(const Point& other) {
    if (this != &other) {
        ep_copy(p_, other.p_);
    }
    return *this;
}

Point::Point(Point&& other) noexcept {
    ep_null(p_);
    ep_new(p_);
    ep_copy(p_, other.p_);
    ep_set_infty(other.p_);
}

Point& Point::operator=(Point&& other) noexcept {
    if (this != &other) {
        ep_copy(p_, other.p_);
        ep_set_infty(other.p_);
    }
    return *this;
}

Point::~Point() {
    ep_free(p_);
}

bool Point::is_identity() const {
    return ep_is_infty(p_);
}

bool Point::operator==(const Point& other) const {
    return ep_cmp(p_, other.p_) == RLC_EQ;
}

/// Convert Weierstrass x to Montgomery x: x_m = x_w - A/3 mod p
static void weierstrass_to_montgomery_x(fp_t x_m, const fp_t x_w) {
    fp_sub(x_m, x_w, g_A_div_3);
}

/// Convert Montgomery x to Weierstrass x: x_w = x_m + A/3 mod p
static void montgomery_to_weierstrass_x(fp_t x_w, const fp_t x_m) {
    fp_add(x_w, x_m, g_A_div_3);
}

/// Read fp_t to big-endian 32 bytes
static void fp_to_bytes_be(uint8_t out[32], const fp_t f) {
    bn_t tmp;
    bn_null(tmp);
    bn_new(tmp);
    fp_prime_back(tmp, f);
    memset(out, 0, 32);
    int len = bn_size_bin(tmp);
    if (len > 32) len = 32;
    bn_write_bin(out + (32 - len), len, tmp);
    bn_free(tmp);
}

/// Read big-endian 32 bytes to fp_t
static void fp_from_bytes_be(fp_t f, const uint8_t data[32]) {
    bn_t tmp;
    bn_null(tmp);
    bn_new(tmp);
    bn_read_bin(tmp, data, 32);
    fp_prime_conv(f, tmp);
    bn_free(tmp);
}

void Point::to_montgomery_bytes(uint8_t out[64]) const {
    if (is_identity()) {
        memset(out, 0, 64);
        return;
    }
    // Normalize to affine
    ep_t norm;
    ep_null(norm);
    ep_new(norm);
    ep_norm(norm, p_);

    // Convert Weierstrass x to Montgomery x
    fp_t x_m;
    fp_null(x_m);
    weierstrass_to_montgomery_x(x_m, norm->x);

    fp_to_bytes_be(out, x_m);
    fp_to_bytes_be(out + 32, norm->y);

    ep_free(norm);
}

std::array<uint8_t, 64> Point::to_montgomery_bytes() const {
    std::array<uint8_t, 64> out;
    to_montgomery_bytes(out.data());
    return out;
}

Point Point::from_montgomery_bytes(const uint8_t data[64]) {
    Point result;

    // Check for identity (all zeros)
    bool all_zero = true;
    for (int i = 0; i < 64; i++) {
        if (data[i] != 0) { all_zero = false; break; }
    }
    if (all_zero) return result;

    // Read Montgomery x, convert to Weierstrass x
    fp_t x_m, x_w;
    fp_null(x_m);
    fp_null(x_w);
    fp_from_bytes_be(x_m, data);
    montgomery_to_weierstrass_x(x_w, x_m);

    // Read y (unchanged between forms)
    fp_t y;
    fp_null(y);
    fp_from_bytes_be(y, data + 32);

    // Set point coordinates
    fp_copy(result.p_->x, x_w);
    fp_copy(result.p_->y, y);
    fp_set_dig(result.p_->z, 1);  // affine: z = 1
    result.p_->coord = BASIC;

    return result;
}

// ═══════════════════════════════════════════
//  Curve operations
// ═══════════════════════════════════════════

/// Lift x-coordinate on Montgomery curve, return both y candidates
/// Montgomery: y² = x³ + Ax² + x  (mod p)
static bool lift_x_montgomery(fp_t y_out, const fp_t x_m, bool pick_smaller) {
    fp_t rhs, x2, x3, ax2, tmp;

    // rhs = x³ + A*x² + x
    fp_sqr(x2, x_m);        // x²
    fp_mul(x3, x2, x_m);    // x³

    // A * x²
    fp_t a_fp;
    fp_from_hex(a_fp, A_MONT);
    fp_mul(ax2, a_fp, x2);

    fp_add(rhs, x3, ax2);   // x³ + Ax²
    fp_add(rhs, rhs, x_m);  // x³ + Ax² + x

    // Check if rhs is a QR and compute sqrt
    if (!fp_srt(y_out, rhs)) {
        return false;  // x is not on the curve
    }

    // Pick smaller y if requested
    // Compare y_out with p - y_out, pick the smaller one
    fp_t y_neg;
    fp_neg(y_neg, y_out);

    bn_t y_bn, y_neg_bn;
    bn_null(y_bn);
    bn_null(y_neg_bn);
    bn_new(y_bn);
    bn_new(y_neg_bn);
    fp_prime_back(y_bn, y_out);
    fp_prime_back(y_neg_bn, y_neg);

    int cmp = bn_cmp(y_bn, y_neg_bn);
    if (pick_smaller && cmp == RLC_GT) {
        fp_copy(y_out, y_neg);
    } else if (!pick_smaller && cmp == RLC_LT) {
        fp_copy(y_out, y_neg);
    }

    bn_free(y_bn);
    bn_free(y_neg_bn);

    return true;
}

/// Explicit Weierstrass point doubling using fp arithmetic only.
/// For curve y²=x³+ax+b: 2*(x1,y1) = (x3,y3)
///   λ = (3x1² + a) / (2y1)
///   x3 = λ² - 2x1
///   y3 = λ(x1 - x3) - y1
static void fp_point_double(fp_t x3, fp_t y3, const fp_t x1, const fp_t y1,
                            const fp_t a_w) {
    fp_t lam, num, den, tmp;

    // num = 3*x1² + a
    fp_sqr(tmp, x1);           // x1²
    fp_add(num, tmp, tmp);     // 2*x1²
    fp_add(num, num, tmp);     // 3*x1²
    fp_add(num, num, a_w);     // 3*x1² + a

    // den = 2*y1
    fp_add(den, y1, y1);

    // λ = num / den
    fp_inv(den, den);
    fp_mul(lam, num, den);

    // x3 = λ² - 2*x1
    fp_sqr(x3, lam);
    fp_sub(x3, x3, x1);
    fp_sub(x3, x3, x1);

    // y3 = λ*(x1 - x3) - y1
    fp_sub(tmp, x1, x3);
    fp_mul(y3, lam, tmp);
    fp_sub(y3, y3, y1);
}

/// Multiply by cofactor 8 = 2^3 using 3 doublings (fp arithmetic only, no ep dependency)
static void cofactor_mult(fp_t xr, fp_t yr, const fp_t x0, const fp_t y0,
                          const fp_t a_w) {
    fp_t xt, yt;
    fp_point_double(xt, yt, x0, y0, a_w);   // 2P
    fp_point_double(xr, yr, xt, yt, a_w);    // 4P
    fp_point_double(xt, yt, xr, yr, a_w);    // 8P
    fp_copy(xr, xt);
    fp_copy(yr, yt);
}

/// Compute G: Montgomery x=9, lift_x, smaller y, ×8
static void compute_G_coords(fp_t gx_w, fp_t gy_w, const fp_t a_w) {
    fp_t x_m;
    fp_set_dig(x_m, 9);

    fp_t y;
    if (!lift_x_montgomery(y, x_m, true)) {
        throw std::runtime_error("Cannot lift x=9 on Curve25519");
    }

    // Convert to Weierstrass
    fp_t x_w;
    montgomery_to_weierstrass_x(x_w, x_m);

    // Multiply by cofactor 8 using explicit doublings
    cofactor_mult(gx_w, gy_w, x_w, y, a_w);
}

/// Compute Z via hash-to-curve: replicating Python's _hash_to_curve("Curve25519-Pedersen-Z")
static void compute_Z_coords(fp_t zx_w, fp_t zy_w, const fp_t a_w) {
    bn_t p_bn;
    bn_null(p_bn);
    bn_new(p_bn);
    bn_from_hex(p_bn, P_STR);

    const char* tag = "Curve25519-Pedersen-Z";

    for (int counter = 0; counter < 256; counter++) {
        char input[64];
        snprintf(input, sizeof(input), "%s:%d", tag, counter);

        // SHA256
        uint8_t hash[32];
        EVP_MD_CTX* ctx = EVP_MD_CTX_new();
        EVP_DigestInit_ex(ctx, EVP_sha256(), nullptr);
        EVP_DigestUpdate(ctx, input, strlen(input));
        unsigned int md_len;
        EVP_DigestFinal_ex(ctx, hash, &md_len);
        EVP_MD_CTX_free(ctx);

        // int.from_bytes(h, "little") → reverse to big-endian for bn
        uint8_t hash_rev[32];
        for (int i = 0; i < 32; i++) {
            hash_rev[i] = hash[31 - i];
        }

        bn_t x_bn;
        bn_null(x_bn);
        bn_new(x_bn);
        bn_read_bin(x_bn, hash_rev, 32);
        bn_mod(x_bn, x_bn, p_bn);

        fp_t x_m;
        fp_prime_conv(x_m, x_bn);
        bn_free(x_bn);

        // Try lift_x on Montgomery curve
        fp_t y;
        if (!lift_x_montgomery(y, x_m, true)) {
            continue;
        }

        // Convert to Weierstrass
        fp_t x_w;
        montgomery_to_weierstrass_x(x_w, x_m);

        // Multiply by cofactor 8 using explicit doublings
        cofactor_mult(zx_w, zy_w, x_w, y, a_w);

        bn_free(p_bn);
        return;
    }

    bn_free(p_bn);
    throw std::runtime_error("hash_to_curve failed for Curve25519-Pedersen-Z");
}

void curve_init() {
    if (g_initialized) return;

    core_init();

    // Set up custom Weierstrass curve over F_p
    // y² = x³ + a_w·x + b_w
    bn_t p_bn;
    bn_null(p_bn);
    bn_new(p_bn);
    bn_from_hex(p_bn, P_STR);

    // Set prime field
    fp_prime_set_dense(p_bn);
    bn_free(p_bn);

    // Precompute A/3 for coordinate conversion
    fp_from_hex(g_A_div_3, A_DIV_3_STR);

    // Set subgroup order q
    bn_null(g_q);
    bn_new(g_q);
    bn_from_hex(g_q, Q_STR);

    // Configure curve parameters (a_w, b_w)
    fp_t a_w, b_w;
    fp_from_hex(a_w, A_W_STR);
    fp_from_hex(b_w, B_W_STR);

    // Compute G coordinates using explicit fp arithmetic (no ep dependency)
    fp_t gx_w, gy_w;
    compute_G_coords(gx_w, gy_w, a_w);

    // Build generator point for ep_curve_set_plain
    ep_t gen;
    ep_null(gen);
    ep_new(gen);
    fp_copy(gen->x, gx_w);
    fp_copy(gen->y, gy_w);
    fp_set_dig(gen->z, 1);
    gen->coord = BASIC;

    // Set the curve: ep_curve_set_plain(a, b, g, r, h, ctmap)
    bn_t cofactor;
    bn_null(cofactor);
    bn_new(cofactor);
    bn_set_dig(cofactor, 8);
    ep_curve_set_plain(a_w, b_w, gen, g_q, cofactor, 0);
    bn_free(cofactor);
    ep_free(gen);

    // Copy G into global
    fp_copy(g_G.p_->x, gx_w);
    fp_copy(g_G.p_->y, gy_w);
    fp_set_dig(g_G.p_->z, 1);
    g_G.p_->coord = BASIC;

    // Compute Z coordinates and set global
    fp_t zx_w, zy_w;
    compute_Z_coords(zx_w, zy_w, a_w);
    fp_copy(g_Z.p_->x, zx_w);
    fp_copy(g_Z.p_->y, zy_w);
    fp_set_dig(g_Z.p_->z, 1);
    g_Z.p_->coord = BASIC;

    // Verify: q * G == O, q * Z == O
    Point test;
    ep_mul(test.p_, g_G.p_, g_q);
    if (!test.is_identity()) {
        throw std::runtime_error("G does not have order q");
    }
    ep_mul(test.p_, g_Z.p_, g_q);
    if (!test.is_identity()) {
        throw std::runtime_error("Z does not have order q");
    }

    g_initialized = true;
}

/// Set up RELIC thread-local curve parameters (prime field + Weierstrass curve).
/// Must be called after core_init() on any thread that does RELIC operations.
static void setup_curve_params_for_thread() {
    // Set prime field (thread-local in RELIC)
    bn_t p_bn;
    bn_null(p_bn);
    bn_new(p_bn);
    bn_from_hex(p_bn, P_STR);
    fp_prime_set_dense(p_bn);
    bn_free(p_bn);

    // Set curve equation and generator (thread-local in RELIC)
    fp_t a_w, b_w;
    fp_from_hex(a_w, A_W_STR);
    fp_from_hex(b_w, B_W_STR);

    // Reconstruct generator from global G (already computed by curve_init)
    ep_t gen;
    ep_null(gen);
    ep_new(gen);
    fp_copy(gen->x, g_G.p_->x);
    fp_copy(gen->y, g_G.p_->y);
    fp_set_dig(gen->z, 1);
    gen->coord = BASIC;

    bn_t cofactor;
    bn_null(cofactor);
    bn_new(cofactor);
    bn_set_dig(cofactor, 8);
    ep_curve_set_plain(a_w, b_w, gen, g_q, cofactor, 0);
    bn_free(cofactor);
    ep_free(gen);
}

void curve_init_thread() {
    core_init();
    setup_curve_params_for_thread();
}

void curve_clean_thread() {
    core_clean();
}

const Point& get_G() { return g_G; }
const Point& get_Z() { return g_Z; }
const bn_t& get_q() { return g_q; }

Point scalar_mult(const Scalar& k, const Point& P) {
    Point result;
    if (P.is_identity() || k.is_zero()) {
        return result;  // identity
    }
    ep_mul(result.p_, P.p_, k.s_);
    return result;
}

Point point_add(const Point& P, const Point& Q) {
    Point result;
    ep_add(result.p_, P.p_, Q.p_);
    return result;
}

Point point_identity() {
    return Point();  // default constructor sets to infinity
}
