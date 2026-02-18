cmake_minimum_required(VERSION 3.16)
project(fasthash LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(PYBIND11_FINDPYTHON ON)
find_package(pybind11 CONFIG REQUIRED)

pybind11_add_module(fasthash
  bindings.cpp
  linear_hash.cpp
  trial_maxload.cpp
)

# 放在这里：target 已经存在了
set_target_properties(fasthash PROPERTIES
  LIBRARY_OUTPUT_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/../.."
)

target_include_directories(fasthash PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})
