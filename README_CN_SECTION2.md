# Part 2：基于线性哈希函数的多签方案 MuSig2-H

## 概述

基于 Tessaro & Zhu (EUROCRYPT 2023) 论文，使用 Pedersen 线性哈希函数实例化 MuSig2-H 多签方案。

## 环境依赖

- **SageMath 10.8**（`brew install --cask sage`）
- Part 2 所有代码通过 `sage -python` 运行

## MuSig2-H 方案总览（TZ23 Fig. 4, ν=4）

### 八个算法

| # | 算法 | 执行者 | 功能 |
|---|------|--------|------|
| 1 | **Setup** | 系统 | 生成公共参数 `(p, E, G, Z)`，所有人共享 |
| 2 | **KeyGen** | 每个签名者 | 生成密钥对：`sk ← Z_q`，`pk = sk·G` |
| 3 | **KeyAgg** | 任何人 | 输入公钥列表 `L`，输出聚合公钥 `apk = Σ H_agg(L, pk_i)·pk_i` |
| 4 | **PreSign** | 每个签名者 | 生成 4 个随机 nonce 对 `r_j ∈ Z_q²`，计算 `R_j = F(r_j)`，公开 `(R_1..R_4)`，保密 `(r_1..r_4)` |
| 5 | **PreAgg** | 任何人 | 聚合所有签名者的 nonce：`R_j = Σ_i R_{i,j}`，得到 `(R_1..R_4)` |
| 6 | **Sign** | 每个签名者 | 用 `sk`、保密的 `r_j`、聚合 nonce、消息 `m`，计算部分签名 `(R, s_i)` |
| 7 | **SignAgg** | 任何人 | 聚合部分签名：`s = Σ s_i`，输出最终签名 `σ = (R, s)` |
| 8 | **Ver** | 任何人 | 验证 `F(s) == R + H_sig(apk, R, m)·apk` |

### 执行流程

```
KeyGen × n 人  →  KeyAgg  →  PreSign × n 人  →  PreAgg
                                                    ↓
                              收到消息 m  →  Sign × n 人  →  SignAgg  →  Ver
```

### 三个哈希函数（域分离）

| 哈希 | 输入 | 用途 |
|------|------|------|
| `H_agg(L, pk)` | 公钥列表 + 单个公钥 | KeyAgg 中计算聚合系数，防止 rogue-key 攻击 |
| `H_non(apk, R_1..R_4, m)` | 聚合公钥 + 4 个 nonce 点 + 消息 | Sign 中将 4 个 nonce 合并为 1 个 |
| `H_sig(apk, R, m)` | 聚合公钥 + 聚合 nonce + 消息 | Sign/Ver 中的 Schnorr 挑战值 |

---

## 实现进度

### 1. 椭圆曲线封装 — `src/crypto/curve.py`

Curve25519（Montgomery 形式）封装，基于 SageMath。

**提供：**

- 有限域 `Fp = GF(p)`，`p = 2²⁵⁵ − 19`
- 曲线 `E: y² = x³ + 486662x² + x` over `Fp`
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
F : Z_q² → E(F_p)
F(x₁, x₂) = x₁·G + x₂·Z
```

**提供：**

- `F(x1, x2)` — 核心函数，返回曲线点
- `F_vec((x1, x2))` — 向量形式接口
- `F_key(sk)` — 密钥空间限制 `F(sk, 0) = sk·G`，此时 F 为双射

**验证 Definition 1 的三个条件：**

1. **S-模满同态**：G = F(1,0)，Z = F(0,1)，任意群元素可由 G、Z 线性组合生成
2. **非单射**：定义域 Z_q² 有 q² 个元素，像 E[q] 最多 q 个元素（鸽巢原理）；且 F(x₁, x₂) = F(x₁+q, x₂)
3. **规模条件**：|S| = |Z_q| = q ≈ 2²⁵²，|D| = q²，|R| = q，均 ≥ 2^κ

**测试：**

```bash
sage -python -m pytest tests/test_lhf.py -v
```

覆盖：线性性（加法同态、标量同态、随机测试）、满同态性、非单射性、F_vec/F_key 接口、D_key 上的双射性。

### 3. MuSig2-H 方案 — `src/crypto/musig2h.py`

实现 TZ23 Fig. 4 的全部 8 个算法（ν=4）。

**算法实现：**

| 函数 | 对应算法 | 说明 |
|------|---------|------|
| `setup()` | Setup | 返回公共参数 `(p, G, Z, q)` |
| `keygen(rng)` | KeyGen | `sk ← Z_q`, `pk = sk·G` |
| `key_agg(L)` | KeyAgg | `apk = Σ H_agg(L, pk_i)·pk_i` |
| `presign(rng)` | PreSign | 生成 4 个 nonce 对 `r_j ∈ Z_q²` 和承诺 `R_j = F(r_j)` |
| `preagg(pp_list)` | PreAgg | 按分量聚合 nonce：`R_j = Σ_i R_{i,j}` |
| `sign(st, app, sk, pk, m, L)` | Sign | 计算部分签名 `(R, s)` |
| `sign_agg(out_list)` | SignAgg | 聚合部分签名，验证 R 一致性 |
| `ver(apk, m, sigma)` | Ver | 验证 `F(s) == R + c·apk` |

**三个域分离哈希函数：**

- `H_agg(L, pk)` — `SHA-256(0x01 || L_sorted || pk) mod q`
- `H_non(apk, nonces, m)` — `SHA-256(0x02 || apk || R_1..R_4 || m) mod q`
- `H_sig(apk, R, m)` — `SHA-256(0x03 || apk || R || m) mod q`

公钥列表在哈希前按坐标排序，确保确定性。

**Sign 中的关键计算：**

```
b = H_non(apk, (R_1,...,R_4), m)
R = Σ_{j=1}^{4} b^{j-1} · R_j          （曲线点运算）
c = H_sig(apk, R, m)
s = Σ_{j=1}^{4} b^{j-1} · r_j + c·a·(sk, 0)   （Z_q² 上运算）
```

其中 `s = (s0, s1)` 是 Z_q² 中的标量对，`(sk, 0)` 是 D_key 中的元素。

**测试：**

```bash
sage -python -m pytest tests/test_musig2h.py -v
```

覆盖：Setup/KeyGen 基本性质、KeyAgg 确定性、PreSign 一致性、PreAgg 正确性、哈希函数域分离、1/2/3/5 人完整协议验证、错误消息/公钥/签名篡改检测、R 不一致拒绝。
