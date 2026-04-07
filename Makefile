# Python 3.13 虚拟环境（C++ pybind11 模块编译目标版本）
VENV := .venv313/bin/python

.PHONY: test-part1 test-part2 test-all build-cpp run-part1 demo clean help

help:  ## 显示帮助信息
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

# === Part 1 ===
test-part1: build-cpp  ## 运行 Part 1 测试（Python 3.13 + C++）
	$(VENV) -m pytest tests/test_sampling.py tests/test_py.py tests/test_cpp.py -v

build-cpp:  ## 构建 C++ 后端（pybind11, Python 3.13）
	cmake -S src/cpp -B src/cpp/build -DCMAKE_BUILD_TYPE=Release
	cmake --build src/cpp/build -j

run-part1:  ## 运行 Part 1 实验
	$(VENV) -m src.experiments.runner

# === Part 2 ===
test-part2:  ## 运行 Part 2 测试（需要 SageMath）
	sage -python -m pytest tests/test_curve.py tests/test_lhf.py \
		tests/test_musig2h.py tests/test_signer.py tests/test_parallel.py -v

demo:  ## 运行 MuSig2-H 协议模拟
	sage -python -m src.crypto.parallel_signing

# === 全部 ===
test-all: test-part1 test-part2  ## 运行全部测试

clean:  ## 清理构建产物
	rm -rf src/cpp/build
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
