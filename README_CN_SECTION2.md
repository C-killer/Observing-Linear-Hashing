# Part 2：基于线性哈希函数的多签方案 MuSig2-H

## 概述

基于 Tessaro & Zhu (EUROCRYPT 2023) 论文，使用 Pedersen 线性哈希函数实例化 MuSig2-H 多签方案。

**相关文档：**

- [Part 2 背景手册](docs/part2_background.md) — 研究动机、Part 1 到 Part 2 的桥梁、MuSig2 vs MuSig2-H 对比
- [PARI 线程安全问题分析](docs/pari_thread_safety.md) — 并行化过程中遇到的 SageMath/PARI 底层问题及解决方案
- [课堂黑板笔记](blackboard_notes.md) — 老师板书转录

## 环境依赖

- **SageMath 10.8**（`brew install --cask sage`）
- Part 2 所有代码通过 `sage -python` 运行

## MuSig2-H 方案总览（TZ23 Fig. 4, v=4）

### 八个算法

| # | 算法              | 执行者     | 功能                                                                                                     |
| - | ----------------- | ---------- | -------------------------------------------------------------------------------------------------------- |
| 1 | **Setup**   | 系统       | 生成公共参数 `(p, E, G, Z)`，所有人共享                                                                |
| 2 | **KeyGen**  | 每个签名者 | 生成密钥对：`sk <- Z_q`，`pk = sk*G`                                                                 |
| 3 | **KeyAgg**  | 任何人     | 输入公钥列表 `L`，输出聚合公钥 `apk = Sum H_agg(L, pk_i)*pk_i`                                       |
| 4 | **PreSign** | 每个签名者 | 生成 4 个随机 nonce 对 `r_j in Z_q^2`，计算 `R_j = F(r_j)`，公开 `(R_1..R_4)`，保密 `(r_1..r_4)` |
| 5 | **PreAgg**  | 任何人     | 聚合所有签名者的 nonce：`R_j = Sum_i R_{i,j}`，得到 `(R_1..R_4)`                                     |
| 6 | **Sign**    | 每个签名者 | 用私钥 `sk`、保密的 `r_j`、聚合 nonce、消息 `m`，计算部分签名 `(R, s_i)`                         |
| 7 | **SignAgg** | 任何人     | 聚合部分签名：`s = Sum s_i`，输出最终签名 `sigma = (R, s)`                                           |
| 8 | **Ver**     | 任何人     | 验证 `F(s) == R + H_sig(apk, R, m)*apk`                                                                |

### 执行流程

```
      ① KeyGen × n        ← 可并行：每人独立生成密钥
      ② KeyAgg            ← 顺序：收集所有公钥后聚合
      ③ PreSign × n       ← 可并行：每人独立生成 nonce
      ④ PreAgg            ← 顺序：同步点 1，聚合 nonce
      ⑤ Sign × n          ← 可并行：每人独立算部分签名
      ⑥ SignAgg           ← 顺序：同步点 2，聚合签名
      ⑦ Ver               ← 顺序：验证
```

### 三个哈希函数（域分离）

| 哈希                        | 输入                            | 用途                                       |
| --------------------------- | ------------------------------- | ------------------------------------------ |
| `H_agg(L, pk)`            | 公钥列表 + 单个公钥             | KeyAgg 中计算聚合系数，防止 rogue-key 攻击 |
| `H_non(apk, R_1..R_4, m)` | 聚合公钥 + 4 个 nonce 点 + 消息 | Sign 中将 4 个 nonce 合并为 1 个           |
| `H_sig(apk, R, m)`        | 聚合公钥 + 聚合 nonce + 消息    | Sign/Ver 中的 Schnorr 挑战值               |

---

## 实现进度

### 1. 椭圆曲线封装 — `src/crypto/curve.py`

Curve25519（Montgomery 形式）封装，基于 SageMath。

**提供：**

- 有限域 `Fp = GF(p)`，`p = 2^255 - 19`
- 曲线 `E: y^2 = x^3 + 486662x^2 + x` over `Fp`
- 基点 `G`（标准基点 x=9，乘 cofactor 8 投影到素数阶子群）
- 独立生成元 `Z`（透明 hash-to-curve，标签 `"Curve25519-Pedersen-Z"`）
- 素数阶子群阶 `q`（`|E| = 8q`，`q` 为素数）
- 工具函数：`scalar_mult(k, P)`、`point_add(P, Q)`、`random_scalar(rng)`

**设计要点：**

- G 和 Z 均乘以 cofactor 8，确保在素数阶子群中（阶为 q）
- Z 通过 `SHA-256("Curve25519-Pedersen-Z:{counter}")` 生成，透明且确定性
- `random_scalar` 支持传入 `random.Random` 实例以保证可复现

**测试：**

```bash
sage -python -m pytest tests/test_curve.py -v
```

覆盖：素数性质、曲线阶、子群阶、G/Z 性质、点加交换律/结合律/分配律、逆元、单位元、随机标量范围与确定性。

### 2. Pedersen 线性哈希函数 — `src/crypto/lhf.py`

实现 TZ23 Section 5.1 的 DL 实例化。

**定义：**

```
F : Z_q^2 -> E(F_p)
F(x1, x2) = x1*G + x2*Z
```

**提供：**

- `F(x1, x2)` — 核心函数，返回曲线点
- `F_vec((x1, x2))` — 向量形式接口
- `F_key(sk)` — 密钥空间限制 `F(sk, 0) = sk*G`，此时 F 为双射

**验证 Definition 1 的三个条件：**

1. **S-模满同态**：G = F(1,0)，Z = F(0,1)，任意群元素可由 G、Z 线性组合生成
2. **非单射**：定义域 Z_q^2 有 q^2 个元素，像 E[q] 最多 q 个元素（鸽巢原理）
3. **规模条件**：|S| = |Z_q| = q 约 2^252，|D| = q^2，|R| = q，均 >= 2^kappa

**测试：**

```bash
sage -python -m pytest tests/test_lhf.py -v
```

覆盖：线性性（加法同态、标量同态、随机测试）、满同态性、非单射性、F_vec/F_key 接口、D_key 上的双射性。

### 3. MuSig2-H 方案 — `src/crypto/musig2h.py`

实现 TZ23 Fig. 4 的全部 8 个算法（v=4）。

**算法实现：**

| 函数                            | 对应算法 | 说明                                                        |
| ------------------------------- | -------- | ----------------------------------------------------------- |
| `setup()`                     | Setup    | 返回公共参数 `(p, G, Z, q)`                               |
| `keygen(rng)`                 | KeyGen   | `sk <- Z_q`, `pk = sk*G`                                |
| `key_agg(L)`                  | KeyAgg   | `apk = Sum H_agg(L, pk_i)*pk_i`                           |
| `presign(rng)`                | PreSign  | 生成 4 个 nonce 对 `r_j in Z_q^2` 和承诺 `R_j = F(r_j)` |
| `preagg(pp_list)`             | PreAgg   | 按分量聚合 nonce：`R_j = Sum_i R_{i,j}`                   |
| `sign(st, app, sk, pk, m, L)` | Sign     | 计算部分签名 `(R, s)`                                     |
| `sign_agg(out_list)`          | SignAgg  | 聚合部分签名，验证 R 一致性                                 |
| `ver(apk, m, sigma)`          | Ver      | 验证 `F(s) == R + c*apk`                                  |

**三个域分离哈希函数：**

- `H_agg(L, pk)` — `SHA-256(0x01 || L_sorted || pk) mod q`
- `H_non(apk, nonces, m)` — `SHA-256(0x02 || apk || R_1..R_4 || m) mod q`
- `H_sig(apk, R, m)` — `SHA-256(0x03 || apk || R || m) mod q`

公钥列表在哈希前按坐标排序，确保确定性。

**Sign 中的关键计算：**

```
b = H_non(apk, (R_1,...,R_4), m)
R = Sum_{j=1}^{4} b^{j-1} * R_j          （曲线点运算）
c = H_sig(apk, R, m)
s = Sum_{j=1}^{4} b^{j-1} * r_j + c*a*(sk, 0)   （Z_q^2 上运算）
```

其中 `s = (s0, s1)` 是 Z_q^2 中的标量对，`(sk, 0)` 是 D_key 中的元素。

**测试：**

```bash
sage -python -m pytest tests/test_musig2h.py -v
```

覆盖：Setup/KeyGen 基本性质、KeyAgg 确定性、PreSign 一致性、PreAgg 正确性、哈希函数域分离、1/2/3/5 人完整协议验证、错误消息/公钥/签名篡改检测、R 不一致拒绝。

### 4. 签名者封装 — `src/crypto/signer.py`

将单个 MuSig2-H 签名参与者的状态和流程封装为 `Signer` 类。

**设计原则：**

- **薄封装**：内部调用 `musig2h.py` 的无状态函数，不复制任何密码学计算逻辑
- **状态管理**：持有私钥、公钥、nonce 秘密、聚合承诺等状态
- **防误用**：跳步骤调用会抛出 `RuntimeError`，明确提示缺少哪一步
- **nonce 一次性**：签名后自动销毁 nonce 秘密（`self._st = None`），防止复用泄露私钥

**生命周期：**

```
Signer(seed)              # 构造时自动 KeyGen，持有私钥和公钥
  -> set_peers(other_pks) # 告知队友公钥
  -> presign()            # 生成 nonce，返回公开承诺
  -> receive_agg_nonce()  # 接收聚合承诺
  -> sign(message)        # 计算部分签名，nonce 自动销毁
（如需再次签名，从 presign 重新开始）
```

**内部状态：**

| 属性       | 类型         | 何时设置              | 说明                     |
| ---------- | ------------ | --------------------- | ------------------------ |
| `sk`     | 标量         | 构造时                | 私钥，永久保密           |
| `pk`     | 曲线点       | 构造时                | 公钥，公开               |
| `_peers` | 曲线点列表   | `set_peers`         | 其他签名者的公钥         |
| `_st`    | nonce 对元组 | `presign`           | 保密的随机数，签名后销毁 |
| `_pp`    | 曲线点元组   | `presign`           | 公开的 nonce 承诺        |
| `_app`   | 曲线点元组   | `receive_agg_nonce` | 聚合后的 nonce 承诺      |

**测试：**

```bash
sage -python -m pytest tests/test_signer.py -v
```

覆盖：KeyGen 确定性与区分性、1/2/3/5 人完整协议验证、nonce 销毁与重签、跳步骤报错（4 种错误路径）。

### 5. 协议协调器 — `src/crypto/parallel_signing.py`

编排 n 个 Signer 走完整个协议，展示两阶段并行结构并计时。

**核心函数 `run_protocol(n_signers, message, seed)`：**

```
① KeyGen x n        <- 可并行：每人独立生成密钥
② KeyAgg            <- 顺序：收集所有公钥后聚合
③ PreSign x n       <- 可并行：每人独立生成 nonce
④ PreAgg            <- 顺序：同步点 1，聚合 nonce
⑤ Sign x n          <- 可并行：每人独立算部分签名
⑥ SignAgg           <- 顺序：同步点 2，聚合签名
⑦ Ver               <- 顺序：验证
```

**返回字典包含：**

- `sigma` — 最终签名 `(R, (s0, s1))`
- `apk` — 聚合公钥
- `verified` — 验证结果
- `timing` — 各阶段耗时（keygen, keyagg, presign, preagg, sign, signagg, verify, total）

**可直接作为脚本运行：**

```bash
sage -python -m src.crypto.parallel_signing
```

输出示例：

```
=== MuSig2-H 并行签名模拟 ===
签名者数量：3
消息：b'Hello MuSig2-H'

[keygen  ]  3 人（可并行）   ... 0.002s
[keyagg  ]  聚合公钥         ... 0.002s
[presign ]  3 人（可并行）   ... 0.013s
[preagg  ]  聚合 nonce       ... 0.000s
[sign    ]  3 人（可并行）   ... 0.010s
[signagg ]  聚合签名         ... 0.000s
[verify  ]  验证             ... 0.002s

验证结果：通过
总耗时：0.027s
```

**测试：**

```bash
sage -python -m pytest tests/test_parallel.py -v
```

覆盖：1/2/3/5 人正确性、返回结构完整性、同种子可复现、错误消息验证失败。

---

## 并行化与 PARI 线程安全问题

### 协议层面的并行性

MuSig2-H 协议天然支持并行——步骤 ①③⑤ 中每个签名者独立执行，互不依赖，只需在步骤 ④（PreAgg）和 ⑥（SignAgg）进行同步。这是老师板书中强调的"processus paralleles"，目的是节省通信轮次（economiser comm.）。

### 实现层面遇到的问题

我们最初使用 Python 的 `ThreadPoolExecutor` 将步骤 ①③⑤ 提交给线程池并发执行，但 **100% 触发段错误（Segmentation fault）**。

根本原因：SageMath 的椭圆曲线运算底层依赖 **PARI/GP 库**，PARI 使用一个进程唯一的**全局栈**分配临时内存，且**没有任何锁保护**。当多个线程同时执行标量乘法时，并发写入全局栈导致内存损坏。

Python 的 GIL 无法防止此问题——`cypari2` 在调用 PARI 的 C 函数前会释放 GIL（标准做法，避免阻塞其他线程），释放后多个线程的 C 代码在多核 CPU 上真正并行执行，PARI 全局栈就被并发读写了。

`ProcessPoolExecutor`（多进程）理论上可避免共享内存问题，但 SageMath 的曲线点对象包含对内部环结构的复杂引用，无法通过 `pickle` 序列化跨进程传输。

**详细的崩溃调用链、原因分析和替代方案见 [docs/pari_thread_safety.md](docs/pari_thread_safety.md)。**

### 当前方案

可并行的步骤以**顺序执行模拟**，代码结构和注释清楚标注了并行性。这忠实反映了协议设计——每个签名者独立执行，两个同步点聚合结果。

如需真正并行执行，可通过 C++ (RELIC 库) 多线程实现，或用多进程 + 手动序列化（将曲线点转为整数坐标对传输）。

---

## 运行所有测试

```bash
# 通过 Makefile（推荐）
make test-part2     # 一次性运行全部 Part 2 测试（82 个）
make demo           # 运行 MuSig2-H 协议模拟

# 逐模块运行
sage -python -m pytest tests/test_curve.py -v
sage -python -m pytest tests/test_lhf.py -v
sage -python -m pytest tests/test_musig2h.py -v
sage -python -m pytest tests/test_signer.py -v
sage -python -m pytest tests/test_parallel.py -v
```

## 文件总览

### 源码

| 文件                               | 行数 | 职责                                              |
| ---------------------------------- | ---- | ------------------------------------------------- |
| `src/crypto/curve.py`            | 82   | Curve25519 封装：有限域、曲线、基点 G/Z、工具函数 |
| `src/crypto/lhf.py`              | 48   | Pedersen 线性哈希函数：`F(x1,x2) = x1*G + x2*Z` |
| `src/crypto/musig2h.py`          | 234  | MuSig2-H 8 个算法 + 3 个域分离哈希函数            |
| `src/crypto/signer.py`           | 88   | Signer 类：状态管理、协议顺序检查、nonce 销毁     |
| `src/crypto/parallel_signing.py` | 124  | 协议协调器：7 步流程编排 + 计时                   |

### 测试

| 文件                       | 测试数 | 覆盖内容                                 |
| -------------------------- | ------ | ---------------------------------------- |
| `tests/test_curve.py`    | 21     | 素数域、曲线阶、子群、算术性质、随机标量 |
| `tests/test_lhf.py`      | 15     | 线性性、满同态、非单射、接口兼容         |
| `tests/test_musig2h.py`  | 18     | 8 算法单元测试 + 1/2/3/5 人协议 + 安全性 |
| `tests/test_signer.py`   | 14     | Signer 生命周期、nonce 安全、跳步报错    |
| `tests/test_parallel.py` | 9      | 协调器正确性、返回结构、可复现、安全性   |

### 文档

| 文件                           | 说明                              |
| ------------------------------ | --------------------------------- |
| `README_CN_SECTION2.md`      | 本文件，Part 2 实现指南           |
| `docs/part2_background.md`   | 研究动机、Part 1 到 Part 2 的桥梁 |
| `docs/pari_thread_safety.md` | PARI 线程安全问题的完整分析       |
