# Python 3.13 virtual environment (target version for C++ pybind11 module)
VENV := .venv313/bin/python

.PHONY: test-part1 test-part2 test-all build-cpp run-part1 run-part2 clean help \
       benchmark-part1 profile-part2 profile-part2-fast profile-part2-cpu

help:  ## Show help information
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

# === Part 1 ===
test-part1: build-cpp  ## Run Part 1 tests (Python 3.13 + C++)
	$(VENV) -m pytest tests/test_sampling.py tests/test_py.py tests/test_cpp.py -v

build-cpp:  ## Build C++ backend (pybind11, Python 3.13)
	cmake -S src/cpp -B src/cpp/build -DCMAKE_BUILD_TYPE=Release
	cmake --build src/cpp/build -j

run-part1:  ## Run Part 1 experiment (supports ARGS)
	$(VENV) -m src.experiments.runner $(ARGS)

benchmark-part1: build-cpp  ## Part 1 benchmark: Python vs C++ performance
	$(VENV) scripts/compare.py $(ARGS)

# === Part 2 ===
test-part2:  ## Run Part 2 tests (requires SageMath)
	sage -python -m pytest tests/test_curve.py tests/test_lhf.py \
		tests/test_musig2h.py tests/test_signer.py tests/test_parallel.py -v

run-part2:  ## Run Part 2 experiment (supports ARGS, e.g. make run-part2 ARGS="-n 5 -m 'test'")
	sage -python -m src.crypto.parallel_signing $(ARGS)

profile-part2:  ## Part 2 profiling (benchmark + thread crash experiment)
	sage -python scripts/profile_musig2h.py

profile-part2-fast:  ## Part 2 profiling (skip crash experiment, fast)
	sage -python scripts/profile_musig2h.py --skip-crash --warmup 1 --repeats 3

profile-part2-cpu:  ## Part 2 CPU profiling (cProfile + call graph)
	sage -python scripts/profile_cpu_runner.py
	gprof2dot -f pstats profiling/part2/profile_musig2h.prof | dot -Tpng -o profiling/part2/profile_musig2h.png
	@echo "[Done] Call graph: profiling/part2/profile_musig2h.png"

# === All ===
test-all: test-part1 test-part2  ## Run all tests

clean:  ## Clean build artifacts
	rm -rf src/cpp/build
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
