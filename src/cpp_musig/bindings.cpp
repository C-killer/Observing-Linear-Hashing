/**
 * pybind11 bindings for fastmusig module.
 *
 * Phase 1: Exports curve constants (G, Z, q) and hash functions.
 * Phase 2: Exports MuSig2-H algorithms, Signer, and sequential protocol runner.
 */

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "curve25519.hpp"
#include "hash_utils.hpp"
#include "musig2h.hpp"
#include "signer.hpp"

namespace py = pybind11;

// ═══════════════════════════════════════════
//  Helpers: bytes ↔ C++ types
// ═══════════════════════════════════════════

static Point bytes_to_point(const std::string& s) {
    if (s.size() != 64) throw std::runtime_error("point must be 64 bytes");
    return Point::from_montgomery_bytes(reinterpret_cast<const uint8_t*>(s.data()));
}

static py::bytes point_to_pybytes(const Point& P) {
    auto bytes = P.to_montgomery_bytes();
    return py::bytes(reinterpret_cast<const char*>(bytes.data()), 64);
}

static py::bytes scalar_to_pybytes(const Scalar& s) {
    auto bytes = s.to_bytes_be();
    return py::bytes(reinterpret_cast<const char*>(bytes.data()), 32);
}

static std::vector<Point> parse_pk_list(py::list pk_list_bytes) {
    std::vector<Point> L;
    for (auto item : pk_list_bytes) {
        L.push_back(bytes_to_point(item.cast<std::string>()));
    }
    return L;
}

PYBIND11_MODULE(fastmusig, m) {
    m.doc() = "Parallel MuSig2-H via RELIC + C++17 threads";

    // ══════════════════════════════════════
    //  Phase 1: Initialization & constants
    // ══════════════════════════════════════

    m.def("init", []() {
        curve_init();
    }, "Initialize curve parameters (call once before use)");

    m.def("get_G_bytes", []() {
        curve_init();
        return point_to_pybytes(get_G());
    }, "Get base point G as Montgomery x||y (64 bytes)");

    m.def("get_Z_bytes", []() {
        curve_init();
        return point_to_pybytes(get_Z());
    }, "Get independent generator Z as Montgomery x||y (64 bytes)");

    m.def("get_q_bytes", []() {
        curve_init();
        uint8_t buf[32];
        memset(buf, 0, 32);
        int len = bn_size_bin(get_q());
        if (len > 32) len = 32;
        bn_write_bin(buf + (32 - len), len, get_q());
        return py::bytes(reinterpret_cast<const char*>(buf), 32);
    }, "Get subgroup order q as big-endian 32 bytes");

    // ══════════════════════════════════════
    //  Phase 1: Hash functions
    // ══════════════════════════════════════

    m.def("H_agg_bytes", [](py::list pk_list_bytes, py::bytes pk_bytes) {
        curve_init();
        auto L = parse_pk_list(pk_list_bytes);
        Point pk = bytes_to_point(pk_bytes.cast<std::string>());
        return scalar_to_pybytes(H_agg(L, pk));
    }, py::arg("pk_list_bytes"), py::arg("pk_bytes"),
    "H_agg(L, pk) → 32 bytes (big-endian scalar)");

    m.def("H_sig_bytes", [](py::bytes apk_bytes, py::bytes R_bytes, py::bytes msg) {
        curve_init();
        Point apk = bytes_to_point(apk_bytes.cast<std::string>());
        Point R = bytes_to_point(R_bytes.cast<std::string>());
        auto m_str = msg.cast<std::string>();
        std::vector<uint8_t> m_vec(m_str.begin(), m_str.end());
        return scalar_to_pybytes(H_sig(apk, R, m_vec));
    }, py::arg("apk_bytes"), py::arg("R_bytes"), py::arg("msg"),
    "H_sig(apk, R, m) → 32 bytes (big-endian scalar)");

    m.def("H_non_bytes", [](py::bytes apk_bytes, py::list nonce_bytes_list,
                            py::bytes msg) {
        curve_init();
        Point apk = bytes_to_point(apk_bytes.cast<std::string>());

        std::array<Point, 4> nonces;
        if (py::len(nonce_bytes_list) != 4)
            throw std::runtime_error("need exactly 4 nonce points");
        for (int i = 0; i < 4; i++) {
            nonces[i] = bytes_to_point(nonce_bytes_list[i].cast<std::string>());
        }

        auto m_str = msg.cast<std::string>();
        std::vector<uint8_t> m_vec(m_str.begin(), m_str.end());
        return scalar_to_pybytes(H_non(apk, nonces, m_vec));
    }, py::arg("apk_bytes"), py::arg("nonce_bytes_list"), py::arg("msg"),
    "H_non(apk, nonces, m) → 32 bytes (big-endian scalar)");

    // ══════════════════════════════════════
    //  Phase 2: MuSig2-H algorithms
    // ══════════════════════════════════════

    m.def("keygen", [](uint64_t seed) {
        curve_init();
        auto kp = musig_keygen(seed);
        return py::make_tuple(scalar_to_pybytes(kp.sk), point_to_pybytes(kp.pk));
    }, py::arg("seed"),
    "KeyGen(seed) → (sk_bytes, pk_bytes)");

    m.def("key_agg", [](py::list pk_list_bytes) {
        curve_init();
        auto L = parse_pk_list(pk_list_bytes);
        Point apk = musig_key_agg(L);
        return point_to_pybytes(apk);
    }, py::arg("pk_list_bytes"),
    "KeyAgg(L) → apk_bytes (64 bytes)");

    m.def("key_agg_ex", [](py::list pk_list_bytes) {
        curve_init();
        auto L = parse_pk_list(pk_list_bytes);
        auto result = musig_key_agg_ex(L);
        py::list coeffs;
        for (const auto& c : result.coeffs) {
            coeffs.append(scalar_to_pybytes(c));
        }
        return py::make_tuple(point_to_pybytes(result.apk), coeffs);
    }, py::arg("pk_list_bytes"),
    "KeyAgg_ex(L) → (apk_bytes, [coeff_bytes...])");

    m.def("ver", [](py::bytes apk_bytes, py::bytes msg,
                    py::bytes R_bytes, py::bytes s0_bytes, py::bytes s1_bytes) {
        curve_init();
        Point apk = bytes_to_point(apk_bytes.cast<std::string>());
        auto m_str = msg.cast<std::string>();
        std::vector<uint8_t> m_vec(m_str.begin(), m_str.end());

        SignOutput sigma;
        sigma.R = bytes_to_point(R_bytes.cast<std::string>());
        auto s0_str = s0_bytes.cast<std::string>();
        auto s1_str = s1_bytes.cast<std::string>();
        sigma.s0 = Scalar::from_bytes_be(
            reinterpret_cast<const uint8_t*>(s0_str.data()), s0_str.size());
        sigma.s1 = Scalar::from_bytes_be(
            reinterpret_cast<const uint8_t*>(s1_str.data()), s1_str.size());

        return musig_ver(apk, m_vec, sigma);
    }, py::arg("apk_bytes"), py::arg("msg"),
       py::arg("R_bytes"), py::arg("s0_bytes"), py::arg("s1_bytes"),
    "Ver(apk, m, σ) → bool, verifies F(s) == R + c·apk");

    // ══════════════════════════════════════
    //  Phase 2: Sequential protocol runner
    // ══════════════════════════════════════

    m.def("run_protocol_sequential", [](int n_signers, py::bytes msg, uint64_t seed) {
        curve_init();
        auto m_str = msg.cast<std::string>();
        std::vector<uint8_t> message(m_str.begin(), m_str.end());

        // 1. KeyGen × n
        std::vector<Signer> signers;
        signers.reserve(n_signers);
        for (int i = 0; i < n_signers; i++) {
            signers.emplace_back(seed + static_cast<uint64_t>(i));
        }

        // 2. KeyAgg (with caching)
        std::vector<Point> all_pks;
        all_pks.reserve(n_signers);
        for (const auto& s : signers) {
            all_pks.push_back(s.pk());
        }
        auto agg = musig_key_agg_ex(all_pks);

        for (int i = 0; i < n_signers; i++) {
            std::vector<Point> peers;
            peers.reserve(n_signers - 1);
            for (int j = 0; j < n_signers; j++) {
                if (j != i) peers.push_back(all_pks[j]);
            }
            signers[i].set_peers(peers);
            signers[i].set_agg_key(agg.apk, agg.coeffs[i]);
        }

        // 3. PreSign × n
        std::vector<std::array<Point, NU>> pp_list;
        pp_list.reserve(n_signers);
        for (auto& s : signers) {
            pp_list.push_back(s.presign());
        }

        // 4. PreAgg
        auto app = musig_preagg(pp_list);
        for (auto& s : signers) {
            s.receive_agg_nonce(app);
        }

        // 5. Sign × n
        std::vector<SignOutput> outs;
        outs.reserve(n_signers);
        for (auto& s : signers) {
            outs.push_back(s.sign(message));
        }

        // 6. SignAgg
        auto sigma_opt = musig_sign_agg(outs);
        if (!sigma_opt) {
            throw std::runtime_error("SignAgg failed: R mismatch");
        }
        auto& sigma = *sigma_opt;

        // 7. Ver
        bool verified = musig_ver(agg.apk, message, sigma);

        // Return result as dict
        py::dict result;
        result["apk"] = point_to_pybytes(agg.apk);
        result["R"] = point_to_pybytes(sigma.R);
        result["s0"] = scalar_to_pybytes(sigma.s0);
        result["s1"] = scalar_to_pybytes(sigma.s1);
        result["verified"] = verified;
        result["n_signers"] = n_signers;
        return result;
    }, py::arg("n_signers"), py::arg("message"), py::arg("seed") = 42,
    "Run complete MuSig2-H protocol sequentially, return dict with signature and verification");
}
