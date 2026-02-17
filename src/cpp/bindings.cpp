#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <Python.h>  // PyLong_AsUnsignedLongLongMask, etc.

#include "linear_hash.hpp"

namespace py = pybind11;

static std::vector<uint64_t> pylong_to_u64_blocks(py::handle x, int u) {
    // little-endian 64-bit blocks, length = ceil(u/64)
    int n = (u + 63) / 64;
    std::vector<uint64_t> blocks;
    blocks.reserve(n);

    PyObject* obj = x.ptr();
    if (!PyLong_Check(obj)) {
        throw py::type_error("x must be int");
    }

    // Use _PyLong_AsByteArray to extract little-endian bytes efficiently
    int nbytes = n * 8;
    std::string buf;
    buf.resize(nbytes, '\0');

    // signed=0, little_endian=1
    if (_PyLong_AsByteArray((PyLongObject*)obj,
                            (unsigned char*)buf.data(),
                            nbytes,
                            /*little_endian=*/1,
                            /*is_signed=*/0,
                              0) < 0) {
        throw py::error_already_set();
    }

    for (int i = 0; i < n; i++) {
        uint64_t w = 0;
        // copy 8 bytes into uint64
        std::memcpy(&w, buf.data() + i * 8, 8);
        blocks.push_back(w);
    }
    return blocks;
}

static py::int_ u64_blocks_to_pylong(const std::vector<uint64_t>& blocks) {
    // Convert little-endian 64-bit blocks to Python int via bytes
    std::string buf;
    buf.resize(blocks.size() * 8, '\0');
    for (size_t i = 0; i < blocks.size(); i++) {
        std::memcpy(buf.data() + i * 8, &blocks[i], 8);
    }
    PyObject* out = _PyLong_FromByteArray((const unsigned char*)buf.data(),
                                          buf.size(),
                                          /*little_endian=*/1,
                                          /*is_signed=*/0);
    if (!out) throw py::error_already_set();
    return py::reinterpret_steal<py::int_>(out);
}

PYBIND11_MODULE(fasthash, m) {
    m.doc() = "High-performance linear hash over F2";

    py::class_<LinearHash>(m, "LinearHash")
        .def(py::init<int, int, uint64_t>(), py::arg("l"), py::arg("u"), py::arg("seed"))

        // Keep your old API if you want
        .def("hash", &LinearHash::hash, py::arg("x_blocks"),
             "Compute h(x) given x as little-endian uint64 blocks")

        // New API: take Python int, return Python int
        .def("hash_int",
             [](LinearHash& self, py::int_ x) -> py::int_ {
                 auto blocks = pylong_to_u64_blocks(x, self.get_u());   // 需要你有 u() getter；没有就存 u 到 wrapper 里
                 auto y_blocks = self.hash(blocks);
                 return u64_blocks_to_pylong(y_blocks);
             },
             py::arg("x"),
             "Compute h(x) given x as a Python int, return Python int");
}
