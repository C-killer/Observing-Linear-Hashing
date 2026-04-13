/**
 * MuSig2-H 8 algorithms — C++ translation of src/crypto/musig2h.py.
 *
 * All functions are stateless. State management is in signer.hpp/cpp.
 * Cache-friendly: key_agg_ex returns coefficients for all signers at once,
 * sign() accepts optional precomputed apk/a to avoid redundant recomputation.
 */

#include "musig2h.hpp"

// ═══════════════════════════════════════════
//  KeyGen
// ═══════════════════════════════════════════

KeyPair musig_keygen(uint64_t& rng) {
    KeyPair kp;
    kp.sk = Scalar::random(rng);
    // pk = F_key(sk) = sk·G  (D_key element: (sk, 0))
    kp.pk = scalar_mult(kp.sk, get_G());
    return kp;
}

// ═══════════════════════════════════════════
//  KeyAgg / KeyAgg_ex
// ═══════════════════════════════════════════

KeyAggResult musig_key_agg_ex(const std::vector<Point>& L) {
    KeyAggResult result;
    // Pre-serialize pk list once (cache for H_agg calls)
    auto L_bytes = serialize_pk_list(L);

    Point apk = point_identity();
    result.coeffs.reserve(L.size());

    for (const auto& pk_i : L) {
        Scalar a_i = H_agg(L, pk_i, &L_bytes);
        result.coeffs.push_back(a_i);
        // apk += a_i · pk_i
        apk = point_add(apk, scalar_mult(a_i, pk_i));
    }
    result.apk = apk;
    return result;
}

Point musig_key_agg(const std::vector<Point>& L) {
    return musig_key_agg_ex(L).apk;
}

// ═══════════════════════════════════════════
//  PreSign
// ═══════════════════════════════════════════

PreSignResult musig_presign(uint64_t& rng) {
    PreSignResult result;
    for (int j = 0; j < NU; j++) {
        Scalar r0 = Scalar::random(rng);
        Scalar r1 = Scalar::random(rng);
        // R_j = F(r0, r1) = r0·G + r1·Z
        Point R_j = point_add(scalar_mult(r0, get_G()), scalar_mult(r1, get_Z()));
        result.st[j] = {r0, r1};
        result.pp[j] = R_j;
    }
    return result;
}

// ═══════════════════════════════════════════
//  PreAgg
// ═══════════════════════════════════════════

std::array<Point, NU> musig_preagg(const std::vector<std::array<Point, NU>>& pp_list) {
    std::array<Point, NU> app;
    for (int j = 0; j < NU; j++) {
        app[j] = point_identity();
    }
    for (const auto& pp_i : pp_list) {
        for (int j = 0; j < NU; j++) {
            app[j] = point_add(app[j], pp_i[j]);
        }
    }
    return app;
}

// ═══════════════════════════════════════════
//  Sign
// ═══════════════════════════════════════════

SignOutput musig_sign(
    const std::array<std::pair<Scalar, Scalar>, NU>& st,
    const std::array<Point, NU>& app,
    const Scalar& sk,
    const Point& pk,
    const std::vector<uint8_t>& m,
    const std::vector<Point>& L,
    const Point* cached_apk,
    const Scalar* cached_a
) {
    // L_full = L ∪ {pk}
    std::vector<Point> L_full(L.begin(), L.end());
    L_full.push_back(pk);

    // apk ← KeyAgg(L_full) or use cached
    Point apk;
    Scalar a;
    if (cached_apk && cached_a) {
        apk = *cached_apk;
        a = *cached_a;
    } else {
        auto agg = musig_key_agg_ex(L_full);
        apk = agg.apk;
        // Find own coefficient: pk is the last element we pushed
        a = agg.coeffs.back();
    }

    // b ← H_non(apk, (R_1,...,R_4), m)
    Scalar b = H_non(apk, app, m);

    // R ← Σ_{j∈[NU]} b^{j} · R_j  (j starts from 0, so b^0, b^1, b^2, b^3)
    Point R = point_identity();
    for (int j = 0; j < NU; j++) {
        Scalar bj = b.pow_mod(static_cast<uint64_t>(j));
        R = point_add(R, scalar_mult(bj, app[j]));
    }

    // c ← H_sig(apk, R, m)
    Scalar c = H_sig(apk, R, m);

    // s = Σ_{j∈[NU]} b^{j} · r_j + c·a·(sk, 0)
    // s0 = Σ b^j · r_j[0] + c·a·sk
    // s1 = Σ b^j · r_j[1]           (c·a·0 = 0)
    Scalar s0(0);
    Scalar s1(0);
    for (int j = 0; j < NU; j++) {
        Scalar bj = b.pow_mod(static_cast<uint64_t>(j));
        s0 = s0 + bj * st[j].first;
        s1 = s1 + bj * st[j].second;
    }
    s0 = s0 + c * a * sk;

    return {R, s0, s1};
}

// ═══════════════════════════════════════════
//  SignAgg
// ═══════════════════════════════════════════

std::optional<SignOutput> musig_sign_agg(const std::vector<SignOutput>& outs) {
    if (outs.empty()) return std::nullopt;

    SignOutput result;
    result.R = outs[0].R;
    result.s0 = outs[0].s0;
    result.s1 = outs[0].s1;

    for (size_t i = 1; i < outs.size(); i++) {
        if (!(outs[i].R == result.R)) {
            return std::nullopt;  // R mismatch
        }
        result.s0 = result.s0 + outs[i].s0;
        result.s1 = result.s1 + outs[i].s1;
    }
    return result;
}

// ═══════════════════════════════════════════
//  Ver
// ═══════════════════════════════════════════

bool musig_ver(const Point& apk, const std::vector<uint8_t>& m, const SignOutput& sigma) {
    // c = H_sig(apk, R, m)
    Scalar c = H_sig(apk, sigma.R, m);
    // lhs = F(s0, s1) = s0·G + s1·Z
    Point lhs = point_add(scalar_mult(sigma.s0, get_G()), scalar_mult(sigma.s1, get_Z()));
    // rhs = R + c·apk
    Point rhs = point_add(sigma.R, scalar_mult(c, apk));
    return lhs == rhs;
}
