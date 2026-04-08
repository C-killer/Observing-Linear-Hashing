# C++ RELIC 并行 MuSig2-H 技术设计文档

## 1. 背景与动机

### 问题

当前 MuSig2-H 基于 SageMath/Python 实现，椭圆曲线运算依赖 PARI/GP 库。PARI 全局栈（`avma`）非线程安全：

- **ThreadPoolExecutor**：cypari2 释放 GIL 后多线程并发写入全局栈 → 100% segfault
- **ProcessPoolExecutor**：SageMath 曲线点对象无法 pickle 序列化跨进程传输

详见 `docs/pari_thread_safety.md`。

### 目标

使用 C++ + RELIC 密码学库实现 MuSig2-H，通过 `std::thread` 实现真正的多线程并行，通过 pybind11 暴露给 Python。

### 预期收益

协议中 96.3%（n=20 签名者）的计算可并行化（KeyGen / PreSign / Sign），理论加速比约 15x（32 线程）。当前因 PARI 限制，加速比为 1.0x。

---

## 2. 架构总览

```
Python 层（调用方）
    │
    │  pybind11 (GIL released)
    ▼
fastmusig.cpython-313-darwin.so
    │
    ├── parallel_protocol  ── RelicThreadPool（std::thread）
    │       │
    │       ├── [并行] KeyGen × n
    │       ├── [顺序] KeyAgg
    │       ├── [并行] PreSign × n    ← 同步点 1
    │       ├── [顺序] PreAgg
    │       ├── [并行] Sign × n       ← 同步点 2
    │       ├── [顺序] SignAgg
    │       └── [顺序] Ver
    │
    ├── musig2h          ── 8 个无状态算法
    ├── signer           ── Signer 状态机
    ├── hash_utils       ── SHA256 域分离哈希
    └── curve25519       ── RELIC 曲线封装
                              │
                              └── librelic_s.a（静态链接）
```

---

## 3. 曲线表示与坐标转换

### Montgomery → Short Weierstrass

Curve25519 Montgomery 形式 `y² = x³ + 486662x² + x` 转换为 Short Weierstrass `y² = x³ + ax + b`：

```
A = 486662
x_w = x_m + A/3  (mod p)
a_w = (3 - A²) / 3  (mod p)
b_w = (2A³ - 9A) / 27  (mod p)
```

- **内部运算**：全部在 Weierstrass 形式下进行（RELIC 原生支持）
- **序列化**：转回 Montgomery 坐标（`x_m = x_w - A/3`），确保与 Python 实现哈希输出字节级一致

### 基点计算

| 点 | 计算方式 |
|----|---------|
| G | Montgomery x=9 → lift_x 取较小 y → 转 Weierstrass → ×8 cofactor |
| Z | 复刻 `_hash_to_curve("Curve25519-Pedersen-Z")`：SHA256 迭代 → little-endian 解释 → mod p → lift_x → 较小 y → ×8 |

### 字节序注意事项

| 场景 | 字节序 | 说明 |
|------|--------|------|
| `_hash_to_curve` SHA256 输出 | **little-endian** | `int.from_bytes(h, "little")` |
| H_agg/H_non/H_sig SHA256 输出 | **big-endian** | `int.from_bytes(h.digest(), "big") % q` |
| 点序列化（x \|\| y） | **big-endian** | `_int_to_bytes(n) = n.to_bytes(32, "big")` |

---

## 4. 文件结构

```
src/cpp_musig/
├── CMakeLists.txt                # CMake 构建（FetchContent 拉取 RELIC）
├── curve25519.hpp / .cpp         # Point/Scalar 类，G/Z 常量，坐标转换
├── hash_utils.hpp / .cpp         # SHA256 域分离哈希：H_agg, H_non, H_sig
├── musig2h.hpp / .cpp            # 8 个算法（无状态函数）
├── signer.hpp / .cpp             # Signer 状态机（nonce-destroy-after-use）
├── parallel_protocol.hpp / .cpp  # RelicThreadPool + run_protocol_parallel
└── bindings.cpp                  # pybind11 模块 "fastmusig"

构建输出：
    fastmusig.cpython-313-darwin.so  （repo 根目录）

测试：
    tests/test_musig2h_cpp.py        （交叉验证 C++ ↔ Python）
```

---

## 5. 核心类设计

### 5.1 Scalar（`curve25519.hpp`）

```cpp
class Scalar {
    bn_t s_;  // RELIC 大数，mod q
public:
    Scalar();
    Scalar(uint64_t v);
    ~Scalar();

    static Scalar random(std::mt19937_64& rng);    // [1, q-1]
    static Scalar from_bytes_be(const uint8_t* data, size_t len);
    static Scalar from_hash_bytes(const uint8_t* digest, size_t len); // big-endian % q

    Scalar operator+(const Scalar& other) const;    // mod q
    Scalar operator*(const Scalar& other) const;    // mod q
    Scalar pow_mod(uint64_t exp) const;             // mod q

    void to_bytes_be(uint8_t out[32]) const;
    bool operator==(const Scalar& other) const;
};
```

### 5.2 Point（`curve25519.hpp`）

```cpp
class Point {
    ep_t p_;  // RELIC 内部 Weierstrass 表示
public:
    Point();
    Point(const Point& other);
    Point& operator=(const Point& other);
    ~Point();

    bool is_identity() const;
    bool operator==(const Point& other) const;
    bool operator<(const Point& other) const;  // 排序 pk 列表用（Montgomery x,y 字典序）

    // 序列化：Montgomery (x||y), 32+32 bytes, big-endian
    void to_montgomery_bytes(uint8_t out[64]) const;
    static Point from_montgomery_bytes(const uint8_t data[64]);
};
```

### 5.3 曲线全局函数

```cpp
void curve_init();            // 主线程调用一次：设置曲线参数、计算 G/Z
void curve_init_thread();     // 每个工作线程调用 core_init()
void curve_clean_thread();    // 每个工作线程调用 core_clean()

const Point& get_G();
const Point& get_Z();
const Scalar& get_q();

Point scalar_mult(const Scalar& k, const Point& P);
Point point_add(const Point& P, const Point& Q);
```

---

## 6. 哈希函数（`hash_utils.hpp`）

使用 OpenSSL `EVP_MD` 实现 SHA256（Homebrew: `brew install openssl@3`，路径 `/opt/homebrew/opt/openssl@3`），确保与 Python `hashlib.sha256` 字节级一致。

```cpp
// 核心: SHA256(tag_byte || data...) → 32 bytes → big-endian int → mod q
Scalar hash_domain(uint8_t tag, const std::vector<uint8_t>& data);

// pk 列表序列化（按 Montgomery x,y 字典序排序）
std::vector<uint8_t> serialize_pk_list(const std::vector<Point>& L);

// 三个域分离哈希（tag = 0x01/0x02/0x03）
Scalar H_agg(const std::vector<Point>& L, const Point& pk,
             const std::vector<uint8_t>* cached_L_bytes = nullptr);
Scalar H_non(const Point& apk, const std::array<Point, 4>& nonce_points,
             const std::vector<uint8_t>& m);
Scalar H_sig(const Point& apk, const Point& R,
             const std::vector<uint8_t>& m);
```

---

## 7. MuSig2-H 8 个算法（`musig2h.hpp`）

直接翻译 `src/crypto/musig2h.py`，所有函数无状态：

```cpp
constexpr int NU = 4;  // nonce 组数

struct KeyPair { Scalar sk; Point pk; };
struct PreSignResult {
    std::array<Point, NU> pp;                          // 公开 nonce 承诺
    std::array<std::pair<Scalar, Scalar>, NU> st;      // 秘密 nonce 对
};
struct SignOutput { Point R; Scalar s0; Scalar s1; };

KeyPair keygen(std::mt19937_64& rng);
Point key_agg(const std::vector<Point>& L);
std::pair<Point, std::vector<Scalar>> key_agg_ex(const std::vector<Point>& L);
PreSignResult presign(std::mt19937_64& rng);
std::array<Point, NU> preagg(const std::vector<std::array<Point, NU>>& pp_list);
SignOutput sign(/* st, app, sk, pk, m, L, apk?, a? */);
std::optional<SignOutput> sign_agg(const std::vector<SignOutput>& outs);
bool ver(const Point& apk, const std::vector<uint8_t>& m, const SignOutput& sigma);
```

**验证方程**：`F(s0, s1) = s0·G + s1·Z == R + c·apk`

---

## 8. Signer 状态机（`signer.hpp`）

复刻 `src/crypto/signer.py` 的生命周期和安全约束：

```cpp
class Signer {
    Scalar sk_;
    Point pk_;
    std::vector<Point> peers_;
    std::optional<PreSignResult> presign_state_;
    std::optional<std::array<Point, NU>> app_;
    std::optional<Point> apk_;
    std::optional<Scalar> a_;
    std::mt19937_64 rng_;        // 线程安全：每个 Signer 独立 RNG

public:
    explicit Signer(uint64_t seed);
    const Point& pk() const;
    void set_peers(const std::vector<Point>& peer_pks);
    void set_agg_key(const Point& apk, const Scalar& a);
    std::array<Point, NU> presign();
    void receive_agg_nonce(const std::array<Point, NU>& app);
    SignOutput sign(const std::vector<uint8_t>& message);
    // sign() 执行后自动销毁 nonce（presign_state_ = std::nullopt）
};
```

---

## 9. 并行协调器（`parallel_protocol.hpp`）

### RelicThreadPool

```cpp
class RelicThreadPool {
    std::vector<std::thread> threads_;
    std::queue<std::function<void()>> tasks_;
    std::mutex mtx_;
    std::condition_variable cv_;
    bool stop_ = false;

    void worker_loop() {
        core_init();   // RELIC 要求每线程调用一次
        while (true) {
            std::function<void()> task;
            {
                std::unique_lock lock(mtx_);
                cv_.wait(lock, [&] { return stop_ || !tasks_.empty(); });
                if (stop_ && tasks_.empty()) break;
                task = std::move(tasks_.front());
                tasks_.pop();
            }
            task();
        }
        core_clean();
    }

public:
    explicit RelicThreadPool(int n_threads);
    void submit(std::function<void()> f);
    void wait_all();   // barrier 同步
    ~RelicThreadPool();
};
```

**关键**：线程池在 3 个并行阶段间复用，避免重复 `core_init()/core_clean()` 开销。

### 协议执行流程

```cpp
struct ProtocolResult {
    SignOutput sigma;
    Point apk;
    bool verified;
    int n_signers;
    std::map<std::string, double> timing;
};

ProtocolResult run_protocol_parallel(
    int n_signers,
    const std::vector<uint8_t>& message,
    uint64_t seed = 42,
    int num_threads = 0   // 0 = std::thread::hardware_concurrency()
);
```

执行时序：

```
Phase 1 [并行]  KeyGen × n     → 线程池分发，每个 Signer 独立生成密钥
Phase 2 [顺序]  KeyAgg         → 主线程聚合公钥
Phase 3 [并行]  PreSign × n    → 线程池分发，每人生成 4 组 nonce
        ────── 同步点 1 ──────
Phase 4 [顺序]  PreAgg         → 主线程聚合 nonce 承诺
Phase 5 [并行]  Sign × n       → 线程池分发，每人计算部分签名
        ────── 同步点 2 ──────
Phase 6 [顺序]  SignAgg        → 主线程聚合签名
Phase 7 [顺序]  Ver            → 主线程验证
```

---

## 10. pybind11 接口（`bindings.cpp`）

```cpp
PYBIND11_MODULE(fastmusig, m) {
    m.doc() = "Parallel MuSig2-H via RELIC + C++17 threads";

    // 主入口：完整并行协议
    m.def("run_protocol", [](int n, py::bytes msg, uint64_t seed, int threads) {
        py::gil_scoped_release release;
        auto result = run_protocol_parallel(n, to_vec(msg), seed, threads);
        py::gil_scoped_acquire acquire;
        return to_python_dict(result);
    }, py::arg("n_signers"), py::arg("message"),
       py::arg("seed") = 42, py::arg("num_threads") = 0);

    // 常量导出（交叉验证用）
    m.def("get_G_bytes", ...);    // Montgomery 64 bytes
    m.def("get_Z_bytes", ...);
    m.def("get_q_bytes", ...);

    // 单独算法导出（交叉验证用）
    m.def("H_agg_bytes", ...);
    m.def("H_sig_bytes", ...);
    m.def("ver", ...);            // C++ ver 可验证 Python 签名
}
```

数据类型在 Python/C++ 边界的约定：
- **曲线点**：`bytes`（64 字节，Montgomery x||y，big-endian）
- **标量**：`bytes`（32 字节，big-endian）或 Python `int`
- **协议结果**：Python `dict`

---

## 11. 构建系统

### CMakeLists.txt（`src/cpp_musig/CMakeLists.txt`）

```cmake
cmake_minimum_required(VERSION 3.16)
project(fastmusig LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# RELIC 通过 FetchContent 引入
include(FetchContent)
FetchContent_Declare(relic
    GIT_REPOSITORY https://github.com/relic-toolkit/relic.git
    GIT_TAG main
)
set(ALLOC "AUTO" CACHE STRING "")
set(WSIZE 64 CACHE STRING "")
set(RAND "UDEV" CACHE STRING "")
set(SHLIB OFF CACHE BOOL "")
set(STLIB ON CACHE BOOL "")
set(FP_PRIME 255 CACHE STRING "")
FetchContent_MakeAvailable(relic)

# pybind11
set(PYBIND11_FINDPYTHON ON)
find_package(pybind11 CONFIG REQUIRED)

# OpenSSL（SHA256）
find_package(OpenSSL REQUIRED)

pybind11_add_module(fastmusig
    bindings.cpp
    curve25519.cpp
    hash_utils.cpp
    musig2h.cpp
    signer.cpp
    parallel_protocol.cpp
)

target_link_libraries(fastmusig PRIVATE relic_s OpenSSL::Crypto)
target_include_directories(fastmusig PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})

set_target_properties(fastmusig PROPERTIES
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/../.."
)
```

### Makefile 新增目标

```makefile
build-musig:      ## 构建 C++ MuSig2-H 后端（RELIC + pybind11）
    cmake -S src/cpp_musig -B src/cpp_musig/build -DCMAKE_BUILD_TYPE=Release
    cmake --build src/cpp_musig/build -j

test-part2-cpp:   ## 运行 C++ 交叉验证测试
    sage -python -m pytest tests/test_musig2h_cpp.py -v

bench-part2:      ## Python vs C++ 性能对比
    sage -python scripts/bench_musig2h.py
```

---

## 12. 交叉验证策略

C++ 实现使用独立的 RNG（`std::mt19937_64`），与 Python `random.Random` 种子算法不同，因此**不要求中间值一致**，只要求：

### 必须字节级一致

| 项目 | 验证方式 |
|------|---------|
| G 坐标（Montgomery） | `fastmusig.get_G_bytes() == _point_to_bytes(G)` |
| Z 坐标（Montgomery） | `fastmusig.get_Z_bytes() == _point_to_bytes(Z)` |
| H_agg/H_non/H_sig 输出 | 固定输入 → 比较标量值 |
| 点序列化格式 | 64 字节 Montgomery x\|\|y big-endian |

### 交叉签名验证

| 测试 | 说明 |
|------|------|
| C++ 签名 → Python Ver | `musig2h.ver(apk, m, sigma_cpp) == True` |
| Python 签名 → C++ Ver | `fastmusig.ver(apk_bytes, m, sigma_py) == True` |
| C++ 并行 n=1,2,3,5,10,50 | `result["verified"] == True` |

### 测试文件

`tests/test_musig2h_cpp.py`：

```python
import fastmusig
from src.crypto.musig2h import ver, H_agg, H_sig
from src.crypto.curve import G, Z, q

def test_G_consistency():
    assert fastmusig.get_G_bytes() == _point_to_bytes(G)

def test_Z_consistency():
    assert fastmusig.get_Z_bytes() == _point_to_bytes(Z)

def test_hash_consistency():
    # 固定输入，比较 H_agg 输出
    ...

def test_cpp_sign_python_verify():
    result = fastmusig.run_protocol(3, b"test", seed=42)
    # 转换 result 为 SageMath 对象，调用 Python ver
    assert ver(apk, b"test", sigma)

def test_parallel_correctness():
    for n in [1, 2, 3, 5, 10, 50]:
        result = fastmusig.run_protocol(n, b"test", seed=42)
        assert result["verified"]

def test_parallel_speedup():
    t1 = benchmark(fastmusig.run_protocol, n=20, threads=1)
    tp = benchmark(fastmusig.run_protocol, n=20, threads=0)
    print(f"Speedup: {t1/tp:.2f}x")
```

---

## 13. 实现阶段

### Phase 1: 基础层（曲线 + 哈希）

1. 创建 `src/cpp_musig/CMakeLists.txt`，配置 RELIC FetchContent
2. 实现 `curve25519.cpp`：Scalar/Point 类，G/Z 计算，Montgomery ↔ Weierstrass 转换
3. 实现 `hash_utils.cpp`：SHA256 + H_agg/H_non/H_sig
4. 从 Python 导出测试向量（G/Z 坐标、哈希输出），验证 C++ 一致

### Phase 2: 算法层（顺序执行）

5. 实现 `musig2h.cpp`：8 个算法
6. 实现 `signer.cpp`：状态机
7. 写 `bindings.cpp`：暴露单个函数
8. 交叉验证：C++ `ver` 验证 Python 签名，反之亦然

### Phase 3: 并行层

9. 实现 `parallel_protocol.cpp`：RelicThreadPool + run_protocol_parallel
10. pybind11 暴露 `run_protocol`
11. 性能基准测试

### Phase 4: 集成

12. Makefile 新增目标
13. `tests/test_musig2h_cpp.py` 交叉验证测试
14. 更新文档

---

## 14. 风险与应对

| 风险 | 影响 | 应对方案 |
|------|------|---------|
| RELIC Curve25519 preset 不可用 | 无法使用内置曲线配置 | 用自定义 Weierstrass 参数手动调用 `ep_curve_set()` |
| Montgomery ↔ Weierstrass 转换 bug | 哈希不一致导致签名互验失败 | Phase 1 用 5+ 测试向量验证往返转换 |
| `_hash_to_curve` 字节序不一致 | Z 点不一致 | 逐字节对比 Python 和 C++ 中间值 |
| RELIC `core_init()` 线程问题 | 线程池生命周期错误 | 线程启动时 init、退出时 clean，不跨线程共享 |
| FetchContent 下载 RELIC 慢 | 构建时间长 | 可选 git submodule 方式引入 |
| OpenSSL 版本差异 | SHA256 API 不一致 | 使用 `EVP_MD` 新 API（兼容 OpenSSL 1.1+/3.x） |

---

## 15. 依赖

| 依赖 | 版本 | 用途 |
|------|------|------|
| RELIC | main (≥ 0.6.0) | 椭圆曲线运算（线程安全） |
| pybind11 | ≥ 2.11 | C++ → Python 绑定 |
| OpenSSL | 3.x（Homebrew `openssl@3`） | SHA256 哈希 |
| CMake | ≥ 3.16 | 构建系统 |
| C++17 | - | 语言标准（std::optional, std::thread） |
| Python | 3.13 | 目标运行环境（.venv313） |
