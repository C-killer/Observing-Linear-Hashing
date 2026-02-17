# Observing-Linear-Hashing

 l'UE Projet STL (PSTL) - MU4IN508

## Rapport

 https://www.overleaf.com/8127484713dywzfygnjrkx#8a671a

## 开发规范

### 总原则

 本 Projet 的规范大致遵循：仓库 main 受保护、无 CI、无审批、合并方式倾向 rebase。主要遵循以下几点：

1. 禁止直接向 main 分支 push（已启用分支保护）；
2. 所有代码修改必须在个人分支/功能分支完成，并通过 Pull Request（PR） 合并到 main；
3. 合并方式统一使用 Rebase（Rebase and merge）。

### 分支规则

main：稳定分支，仅用于集成，禁止直接开发与 push。

开发分支：每位成员在自己的分支上工作

不允许在 main 上直接 commit；本地误提交也不得通过绕过规则推送。

### 首次使用（每位成员仅需做一次）

```
# 克隆仓库
git clone https://github.com/C-killer/Observing-Linear-Hashing.git
cd Observing-Linear-Hashing

# 创建个人分支并推送到远程
git checkout -b dev-<name>
git push -u origin dev-<name>
```

### 每次开始工作：先同步 main，再更新个人分支（必须执行）

要求每次开始写代码前必须做一次同步，避免后期 PR 冲突集中爆发。

```
# 同步远程 main 到本地
git checkout main
git pull origin main

# 切回个人分支并 rebase 到最新 main
git checkout dev-<name>
git rebase main
```

### 开发与提交（在个人分支完成）

```
# 开发过程中提交
git add .
git commit -m "xxx"  # 尽量写清楚你完成的工作

# 推送到远程个人分支（可多次）
git push origin dev-<name>
```

### 完成工作：通过 PR 合并到 main（唯一允许进入 main 的方式）

#### 1. 提 PR 前准备（必须）

```
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

Base：main

Compare：dev-xxx

PR 描述需包含：
    变更内容（做了什么）,自测方式/结果（如果有）

#### 3. 合并方式（必须统一）

合并 PR 时选择：Rebase and merge

### 快速流程速查（最常用）

```
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

## 测试

### 环境要求

Python ≥ 3.10 并且已经安装pytest

### 运行测试

```
# 在项目根目录执行
pytest

# 或只运行某个测试文件
pytest tests/test_sampling.py
```

### 运行示例

在 `tests/example.py` 中，打印了在该算法下 `x, M, h(x)` 结果的示例

```
# 在项目根目录运行
python3 tests/example.py
```

## 构建C++模块

### 编译

```
# 在根目录
cd Observing-Linear-Hashing/
cmake -S src/cpp -B src/cpp/build -DCMAKE_BUILD_TYPE=Release
cmake --build src/cpp/build -j

# 验证编译成功
python3 -c "import fasthash; print(fasthash.__file__)"
# 输出类似：Observing-Linear-Hashing/fasthash.cpython-313-darwin.so
```
