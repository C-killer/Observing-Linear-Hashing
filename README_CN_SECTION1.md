
# Observing-Linear-Hashing

UE Projet STL (PSTL) - MU4IN508

## 项目结构

```
Observing-Linear-Hashing/
├── Makefile                         # 统一入口：make help 查看所有命令
├── src/
│   ├── hashing/                     # Part 1：F2 上线性哈希
│   │   ├── linear_f2.py            #   Python 与 C++ 两个后端
│   │   └── sampling.py             #   随机向量生成器
│   ├── experiments/                 # Part 1：max-load 实验
│   │   ├── runner.py               #   实验主入口
│   │   ├── maxload.py              #   Space-Saving 算法（Python）
│   │   └── mlShower.py             #   max-load 分布打印
│   ├── crypto/                      # Part 2：MuSig2-H 多签方案
│   │   ├── curve.py                #   椭圆曲线封装（Curve25519）
│   │   ├── lhf.py                  #   Pedersen 线性哈希函数
│   │   ├── musig2h.py              #   MuSig2-H 8 个算法 + 3 个哈希
│   │   ├── signer.py               #   Signer 类（参与方状态封装）
│   │   └── parallel_signing.py     #   协议协调器（7 步流程）
│   └── cpp/                         # Part 1：C++ 后端（pybind11）
│       ├── linear_hash.hpp/cpp     #   C++ 线性哈希 F2
│       ├── trial_maxload.hpp/cpp   #   单次 trial + Space-Saving
│       ├── space_saving.hpp        #   C++ Space-Saving 算法
│       ├── parallel_trials.hpp     #   std::thread 并行化
│       ├── samplers.hpp            #   C++ 随机向量生成
│       ├── bindings.cpp            #   pybind11 绑定
│       └── CMakeLists.txt          #   CMake 配置
├── tests/                           # 测试（Part 1：90 个，Part 2：82 个）
│   ├── conftest.py
│   ├── test_sampling.py            #   采样分布测试
│   ├── test_py.py                  #   Python 哈希测试
│   ├── test_cpp.py                 #   C++ fasthash 测试
│   ├── test_curve.py               #   椭圆曲线性质（21 tests）
│   ├── test_lhf.py                 #   线性哈希函数（15 tests）
│   ├── test_musig2h.py             #   签名方案正确性（18 tests）
│   ├── test_signer.py              #   Signer 封装（14 tests）
│   ├── test_parallel.py            #   协议协调器（9 tests）
│   └── example.py
├── docs/                            # 文档
│   ├── part2_background.md         #   Part 2 研究背景
│   └── pari_thread_safety.md       #   PARI 线程安全问题分析
├── papers/                          # 参考文献（PDF）
├── profiling/                       # 性能分析结果（CPU/内存）
├── scripts/
│   └── compare.py                  # Python vs C++ 基准测试
├── data/                            # 实验数据
└── .gitignore
```

## 开发规范

### 总原则

本项目的规范大致遵循：仓库 `main` 受保护、无 CI、无审批、合并方式倾向 rebase。主要遵循以下几点：

1. 禁止直接向 `main` 分支 push（已启用分支保护）；
2. 所有代码修改必须在个人分支/功能分支完成，并通过 Pull Request（PR）合并到 `main`；
3. 合并方式统一使用 **Rebase（Rebase and merge）** 。

### 分支规则

* `main`：稳定分支，仅用于集成，禁止直接开发与 push。
* 开发分支：每位成员在自己的分支上工作。
* 不允许在 `main` 上直接 commit；本地误提交也不得通过绕过规则推送。

### 首次使用（每位成员仅需做一次）

```bash
# 克隆仓库
git clone https://github.com/C-killer/Observing-Linear-Hashing.git
cd Observing-Linear-Hashing

# 创建个人分支并推送到远程
git checkout -b dev-<name>
git push -u origin dev-<name>
```

### 每次开始工作：先同步 main，再更新个人分支（必须执行）

要求每次开始写代码前必须做一次同步，避免后期 PR 冲突集中爆发。

```bash
# 同步远程 main 到本地
git checkout main
git pull origin main

# 切回个人分支并 rebase 到最新 main
git checkout dev-<name>
git rebase main
```

### 开发与提交（在个人分支完成）

```bash
# 开发过程中提交
git add .
git commit -m "xxx"  # 尽量写清楚你完成的工作

# 推送到远程个人分支（可多次）
git push origin dev-<name>
```

### 完成工作：通过 PR 合并到 main（唯一允许进入 main 的方式）

#### 1. 提 PR 前准备（必须）

```bash
# 确保个人分支已同步最新 main：
git checkout main
git pull origin main
git checkout dev-<name>
git rebase main

# 推送个人分支：
git push origin dev-<name>

# 如果你刚执行了 rebase，可能需要强推（仅对个人分支允许）：
git push --force-with-lease origin dev-<name>
```

#### 2. 在 GitHub 创建 Pull Request

* **Base：** `main`
* **Compare：** `dev-xxx`
* PR 描述需包含：
  * 变更内容（做了什么）
  * 自测方式/结果（如果有）

#### 3. 合并方式（必须统一）

合并 PR 时选择：**Rebase and merge**

### 快速流程速查（最常用）

```bash
# 开工
git checkout main
git pull origin main
git checkout dev-<name>
git rebase main

# 提交与推送
git add .
git commit -m "xxx"
git push origin dev-<name>

# 提 PR 并 rebase 合并到 main
# GitHub：开 PR（dev 分支 → main）
# 合并：Rebase and merge
```

---

## 命令（Makefile）

项目使用 `Makefile` 作为统一入口。运行 `make help` 查看所有命令：

```bash
make help           # 显示所有可用命令
make build-cpp      # 构建 C++ 后端（pybind11, Python 3.13）
make test-part1     # Part 1 测试（自动编译 C++）
make test-part2     # Part 2 测试（需要 SageMath）
make test-all       # 全部测试
make run-part1      # 运行 Part 1 实验
make demo           # MuSig2-H 协议模拟
make clean          # 清理构建产物
```

### 运行示例

在 **`tests/example.py` 中，打印了在该算法下** `x, M, h(x)` 结果的示例。

```bash
python3 tests/example.py
```

---

## Max-load 估计算法：Space-Saving

### 算法说明

实验的核心问题是估计 max-load，即将 **`m` 个球投入** `2^l` 个桶后，最重桶的球数：

```
M(S, h) = max_y |{x ∈ S : h(x) = y}|
```

当 **`l` 较大时（例如** **`l=20`，桶数达 100 万），用完整哈希表精确统计每个桶的计数会导致内存不可承受（`O(2^l)`）。为此项目采用** **Space-Saving 算法** ，在 `O(k)` 内存下近似估计 max-load。

### 核心思路

维护一张大小为** **`k` 的候选表** **`table[y] = (c, e)`，其中** **`c` 为计数估计，`e` 为误差上界，并用一个**惰性最小堆**追踪当前计数最小的候选桶。每次处理一个新的桶标识** `y` 时：

* 若 **`y` 已在候选表中：直接将其计数** `c` 加一；
* 若候选表未满：以 `(c=1, e=0)` 插入；
* 若候选表已满：从堆中弹出当前计数最小的候选 **`y_min`，将其替换为新的** **`y`，并继承** **`c_min` 作为误差，新计数为** `c_min + 1`。

最终通过 `max_count()` 返回候选表中计数的最大值，作为 max-load 的上界估计。

### 复杂度

* 时间复杂度：`O(N log k)`（均摊），`N` 为输入流长度；
* 空间复杂度：`O(k)`。

### 适用场景

`l` 较小时（如 **`l ≤ 10`，桶数 ≤ 1024），直接精确计数更快且无近似误差。Space-Saving 主要用于** **`l` 较大、桶数远超可用内存**的场景，以牺牲少量精度换取可行的内存占用。

### 实现位置

* Python 版：`src/experiments/maxload.py`（`Maxload` 类，支持单次/批量哈希）
* C++ 版：`src/cpp/space_saving.hpp`（`SpaceSaving` 类，通过 fingerprint 将任意长度的哈希输出压缩为 `uint64` 键）

---

## 性能检测方法

### CPU 监测

> **注意：** 本节需要使用 **Python 3.13** 。

```bash
source .venv313/bin/activate

# CPU 火焰图
sudo py-spy record -o profiling/part1/profile.svg -- python -m src.experiments.runner
open profiling/part1/profile.svg
```

### 内存监测

```bash
# 第一步：采集内存数据
python -m memray run -o profiling/part1/memray.bin -m src.experiments.runner

# 第二步：生成 HTML 火焰图报告
python -m memray flamegraph profiling/part1/memray.bin -o profiling/part1/memray-flamegraph.html

# 第三步：在浏览器中打开报告
open profiling/part1/memray-flamegraph.html
```
