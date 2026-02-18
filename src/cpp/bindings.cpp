#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <Python.h>  // PyLong_AsUnsignedLongLongMask, etc.

#include "linear_hash.hpp"
#include "parallel_trials.hpp"

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

        // old API
        .def("hash", &LinearHash::hash, py::arg("x_blocks"),
             "Compute h(x) given x as little-endian uint64 blocks")

        // single int API: take Python int, return Python int
        .def("hash_int",
             [](LinearHash& self, py::int_ x) -> py::int_ {
                 auto blocks = pylong_to_u64_blocks(x, self.get_u());
                 auto y_blocks = self.hash(blocks);
                 return u64_blocks_to_pylong(y_blocks);
             },
             py::arg("x"),
             "Compute h(x) given x as a Python int, return Python int")

        // batch int API (ONE boundary crossing)
        .def("hash_many_int",
             [](LinearHash& self, py::sequence xs) -> py::list {
                 py::list out;
                 // 逐个元素处理，但只跨边界一次；核心收益在这里
                 for (py::handle item : xs) {
                     py::int_ x = py::reinterpret_borrow<py::int_>(item);
                     auto blocks = pylong_to_u64_blocks(x, self.get_u());
                     auto y_blocks = self.hash(blocks);
                     out.append(u64_blocks_to_pylong(y_blocks));
                 }
                 return out;
             },
             py::arg("xs"),
             "Batch compute: xs(list[int]) -> list[int]");
    
    m.def("run_trials_maxload",
          [](int u, int l, int64_t m_count,
             const std::string& dist,
             const std::vector<uint64_t>& seeds_S,
             const std::vector<uint64_t>& seeds_h,
             int k,
             int num_threads) {
              // 释放 GIL：C++ 多线程计算期间不占用 Python GIL
              py::gil_scoped_release release;
              return run_trials_parallel(u, l, m_count, dist, seeds_S, seeds_h, k, num_threads);
          },
          py::arg("u"), py::arg("l"), py::arg("m"),
          py::arg("dist"),
          py::arg("seeds_S"), py::arg("seeds_h"),
          py::arg("k") = 50000,
          py::arg("num_threads") = 0
    );
}
