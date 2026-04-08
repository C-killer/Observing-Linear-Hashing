/**
 * pybind11 bindings for fastmusig module.
 *
 * Phase 1: Exports curve constants (G, Z, q) and hash functions
 * for cross-validation with Python/SageMath implementation.
 */

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "curve25519.hpp"
#include "hash_utils.hpp"

namespace py = pybind11;

PYBIND11_MODULE(fastmusig, m) {
    m.doc() = "Parallel MuSig2-H via RELIC + C++17 threads";

    // ── Initialization ──
    m.def("init", []() {
        curve_init();
    }, "Initialize curve parameters (call once before use)");

    // ── Curve constants (Montgomery bytes) ──
    m.def("get_G_bytes", []() {
        curve_init();
        auto bytes = get_G().to_montgomery_bytes();
        return py::bytes(reinterpret_cast<const char*>(bytes.data()), 64);
    }, "Get base point G as Montgomery x||y (64 bytes)");

    m.def("get_Z_bytes", []() {
        curve_init();
        auto bytes = get_Z().to_montgomery_bytes();
        return py::bytes(reinterpret_cast<const char*>(bytes.data()), 64);
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

    // ── Hash functions (for cross-validation) ──
    m.def("H_agg_bytes", [](py::list pk_list_bytes, py::bytes pk_bytes) {
        curve_init();
        // Parse pk list from list of 64-byte items
        std::vector<Point> L;
        for (auto item : pk_list_bytes) {
            auto s = item.cast<std::string>();
            if (s.size() != 64) throw std::runtime_error("pk must be 64 bytes");
            L.push_back(Point::from_montgomery_bytes(
                reinterpret_cast<const uint8_t*>(s.data())));
        }
        // Parse target pk
        auto pk_str = pk_bytes.cast<std::string>();
        if (pk_str.size() != 64) throw std::runtime_error("pk must be 64 bytes");
        Point pk = Point::from_montgomery_bytes(
            reinterpret_cast<const uint8_t*>(pk_str.data()));

        Scalar result = H_agg(L, pk);
        auto out = result.to_bytes_be();
        return py::bytes(reinterpret_cast<const char*>(out.data()), 32);
    }, py::arg("pk_list_bytes"), py::arg("pk_bytes"),
    "H_agg(L, pk) → 32 bytes (big-endian scalar)");

    m.def("H_sig_bytes", [](py::bytes apk_bytes, py::bytes R_bytes, py::bytes msg) {
        curve_init();
        auto apk_str = apk_bytes.cast<std::string>();
        auto r_str = R_bytes.cast<std::string>();
        auto m_str = msg.cast<std::string>();

        Point apk = Point::from_montgomery_bytes(
            reinterpret_cast<const uint8_t*>(apk_str.data()));
        Point R = Point::from_montgomery_bytes(
            reinterpret_cast<const uint8_t*>(r_str.data()));
        std::vector<uint8_t> m_vec(m_str.begin(), m_str.end());

        Scalar result = H_sig(apk, R, m_vec);
        auto out = result.to_bytes_be();
        return py::bytes(reinterpret_cast<const char*>(out.data()), 32);
    }, py::arg("apk_bytes"), py::arg("R_bytes"), py::arg("msg"),
    "H_sig(apk, R, m) → 32 bytes (big-endian scalar)");

    m.def("H_non_bytes", [](py::bytes apk_bytes, py::list nonce_bytes_list,
                            py::bytes msg) {
        curve_init();
        auto apk_str = apk_bytes.cast<std::string>();
        Point apk = Point::from_montgomery_bytes(
            reinterpret_cast<const uint8_t*>(apk_str.data()));

        std::array<Point, 4> nonces;
        if (py::len(nonce_bytes_list) != 4)
            throw std::runtime_error("need exactly 4 nonce points");
        for (int i = 0; i < 4; i++) {
            auto s = nonce_bytes_list[i].cast<std::string>();
            if (s.size() != 64) throw std::runtime_error("nonce must be 64 bytes");
            nonces[i] = Point::from_montgomery_bytes(
                reinterpret_cast<const uint8_t*>(s.data()));
        }

        auto m_str = msg.cast<std::string>();
        std::vector<uint8_t> m_vec(m_str.begin(), m_str.end());

        Scalar result = H_non(apk, nonces, m_vec);
        auto out = result.to_bytes_be();
        return py::bytes(reinterpret_cast<const char*>(out.data()), 32);
    }, py::arg("apk_bytes"), py::arg("nonce_bytes_list"), py::arg("msg"),
    "H_non(apk, nonces, m) → 32 bytes (big-endian scalar)");
}
