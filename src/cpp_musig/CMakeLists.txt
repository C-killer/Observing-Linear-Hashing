cmake_minimum_required(VERSION 3.16)
project(fastmusig LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# ── RELIC via FetchContent ──
include(FetchContent)
FetchContent_Declare(relic
    GIT_REPOSITORY https://github.com/relic-toolkit/relic.git
    GIT_TAG main
)
# RELIC configuration for custom curve (we set Weierstrass params manually)
set(ALLOC "AUTO" CACHE STRING "" FORCE)
set(WSIZE 64 CACHE STRING "" FORCE)
set(RAND "UDEV" CACHE STRING "" FORCE)
set(SHLIB OFF CACHE BOOL "" FORCE)
set(STLIB ON CACHE BOOL "" FORCE)
set(MULTI "PTHREAD" CACHE STRING "" FORCE)
set(FP_PRIME 255 CACHE STRING "" FORCE)
set(EP_PLAIN ON CACHE BOOL "" FORCE)
set(EP_SUPER OFF CACHE BOOL "" FORCE)
FetchContent_MakeAvailable(relic)

# ── Python 3.13 (与 Part 1 保持一致，使用 .venv313) ──
set(Python_ROOT_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../../.venv313")
set(Python_FIND_STRATEGY LOCATION)
find_package(Python 3.13 EXACT COMPONENTS Interpreter Development.Module)

# ── pybind11 ──
find_package(pybind11 CONFIG REQUIRED)

# ── OpenSSL (SHA256) ──
set(OPENSSL_ROOT_DIR "/opt/homebrew/opt/openssl@3")
find_package(OpenSSL REQUIRED)

# ── fastmusig module ──
pybind11_add_module(fastmusig
    bindings.cpp
    curve25519.cpp
    hash_utils.cpp
    musig2h.cpp
    signer.cpp
)

target_link_libraries(fastmusig PRIVATE relic_s OpenSSL::Crypto)
target_include_directories(fastmusig PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}
    ${relic_BINARY_DIR}/include
    ${relic_SOURCE_DIR}/include
)

set_target_properties(fastmusig PROPERTIES
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/../.."
)
