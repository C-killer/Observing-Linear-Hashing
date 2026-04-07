# PARI 线程安全问题分析

> 本文档记录在实现 MuSig2-H 并行签名协调器时遇到的 SageMath/PARI 线程安全问题，
> 包括问题复现、根因分析和解决方案。

---

## 1. 问题背景

MuSig2-H 协议中有三个阶段可以并行执行（每个签名者独立，无数据依赖）：

```
① KeyGen × n        ← 可并行：每人独立生成密钥
③ PreSign × n       ← 可并行：每人独立生成 nonce
⑤ Sign × n          ← 可并行：每人独立算部分签名
```

我们最初使用 Python 的 `ThreadPoolExecutor` 将这些步骤提交给线程池并发执行。

---

## 2. 错误现象

运行测试时，所有 9 个测试用例 **100% 崩溃**，报错均为：

```
cysignals.signals.SignalError: Segmentation fault
```

崩溃位置固定在 `sage/libs/pari/convert_gmp.pyx:52`。

---

## 3. 崩溃调用链

从用户代码到崩溃点的完整路径：

```
Signer.__init__()
  → musig2h.keygen()
    → lhf.F_key(sk)                         # F(sk, 0) = sk·G
      → curve.scalar_mult(sk, G)            # SageMath 标量乘法
        → Integer(k) * P                    # Sage 调用椭圆曲线点乘
          → ell_point._acted_upon_()
            → pari.ellmul(E, self, k)       # 委托给 PARI 库
              → cypari2.objtogen()          # Sage 对象 → PARI GEN 类型
                → convert_gmp.new_gen_from_integer()
                  💥 Segmentation fault     # GMP 大整数 → PARI 大整数时崩溃
```

---

## 4. 根本原因：PARI 全局栈不是线程安全的

### 4.1 PARI 的内存模型

PARI/GP 是一个数论计算库，SageMath 通过 `cypari2` 包装调用它。PARI 内部使用一个 **全局栈（PARI stack）** 管理所有临时对象的内存分配：

```
PARI 全局栈（进程唯一，所有线程共享）
┌────────────────────────────────────┐
│  栈指针 avma（指向当前栈顶）         │
│  ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄ │
│  临时对象 A（线程 1 分配）           │
│  临时对象 B（线程 2 分配）  ← 冲突！ │
│  临时对象 C（线程 1 分配）           │
└────────────────────────────────────┘
```

这个全局栈 **没有任何锁保护**。当两个线程同时执行 PARI 运算时：

1. 线程 1 调用 `new_gen_from_integer()`，移动栈指针，开始写入大整数
2. 线程 2 **同时**调用 `new_gen_from_integer()`，也移动同一个栈指针，开始写入
3. 两次写入互相覆盖，栈指针错乱
4. 后续读取到的是半写入的无效数据 → **段错误**

### 4.2 为什么 Python GIL 没有保护它

Python 的 GIL（全局解释器锁）只保护 Python 字节码的执行。但 `cypari2` 在调用 PARI 的 C 函数前会 **释放 GIL**（这是 C 扩展的标准做法，避免阻塞其他 Python 线程）：

```
线程 1: [持有 GIL] → 进入 cypari2 → [释放 GIL] → PARI C 代码 → 操作全局栈
线程 2: [获得 GIL] → 进入 cypari2 → [释放 GIL] → PARI C 代码 → 操作同一全局栈
                                                                 💥 并发写入冲突
```

GIL 释放后，两个线程的 C 代码在多核 CPU 上真正并行执行，PARI 全局栈的并发访问没有任何同步机制。

### 4.3 为什么不是偶发而是 100% 崩溃

椭圆曲线标量乘法（`ellmul`）是计算密集型操作，涉及大量 PARI 栈分配。即使只有 2 个线程、1 次调用，执行窗口也足够长，几乎必然发生并发写入。这就是为什么 9 个测试全部 segfault——不是概率性的竞争条件，而是确定性的并发冲突。

---

## 5. 为什么 ProcessPoolExecutor 也不可行

多进程方案可以避免共享内存问题（每个进程有独立的 PARI 栈），但存在另一个障碍：

**SageMath 对象无法跨进程传输。**

`ProcessPoolExecutor` 依赖 `pickle` 序列化在进程间传递参数和返回值。SageMath 的椭圆曲线点对象包含对内部环结构（`EllipticCurve_finite_field`、`FiniteField`）的复杂引用，这些引用：

- 序列化/反序列化开销极大（需要重建整个代数结构）
- 部分内部状态不支持 pickle（如缓存的 PARI 对象）

即使能序列化成功，传输开销也可能远超计算本身（一个曲线点序列化后可能有数百字节，但标量乘法本身只需毫秒级）。

---

## 6. 解决方案

### 6.1 当前方案：顺序执行 + 结构标注

保持顺序执行，但在代码中清楚标注哪些步骤在协议层面可并行：

```python
# ① KeyGen × n ← 可并行：每人独立生成密钥，互不依赖
signers = [Signer(seed=seed + i) for i in range(n_signers)]

# ④ PreAgg ← 顺序：同步点 1，聚合 nonce
app = preagg(pp_list)
```

这符合课堂要求——老师板书中"processus parallèles"指的是协议设计层面的并行性（节省通信轮次），而非要求多线程实现。

### 6.2 如需真正并行执行

| 方案 | 可行性 | 说明 |
|------|--------|------|
| C++ 多线程 + RELIC 库 | 推荐 | RELIC 是线程安全的椭圆曲线库，可扩展 Part 1 的 C++ 多线程框架 |
| 多进程 + 手动序列化 | 可行但复杂 | 将曲线点转为 (x, y) 整数对传输，接收端重建 Sage 对象 |
| 单线程 + asyncio | 无意义 | 椭圆曲线运算是 CPU 密集型，异步 I/O 无法加速 |

---

## 7. 参考

- [PARI/GP 官方文档：线程安全说明](https://pari.math.u-bordeaux.fr/dochtml/html-stable/GP_reference.html) — PARI 的 `libpari` 默认非线程安全，需编译时启用 `--enable-tls` 并使用 `pari_thread_*` API
- [cypari2 源码](https://github.com/sagemath/cypari2) — `sig_on()`/`sig_off()` 包裹 PARI 调用，释放 GIL
- [SageMath Trac #25094](https://trac.sagemath.org/ticket/25094) — SageMath 多线程安全性的已知问题讨论
