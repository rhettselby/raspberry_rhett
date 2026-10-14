# Build file for the device program. CMake reads this file and generates
# Makefiles; `cmake --build` then runs make to compile everything.
#
# From the repo root:
#   cmake -S device -B device/build                  # configure: generate the Makefiles
#   cmake --build device/build                       # build: compile and link
#   ctest --test-dir device/build --output-on-failure  # run the tests

cmake_minimum_required(VERSION 3.25)
project(device LANGUAGES CXX)

# --- Language settings --------------------------------------------------------

# C++20 (for std::span), and fail rather than quietly fall back to an older standard.
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
# Plain ISO C++ (-std=c++20), not the GNU dialect (-std=gnu++20).
set(CMAKE_CXX_EXTENSIONS OFF)
# Write compile_commands.json so editors (clangd, VS Code) understand the code.
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# A Debug build (no optimization, full debug info) unless you ask for another,
# e.g. -DCMAKE_BUILD_TYPE=Release when building the real thing on the Pi.
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Debug)
endif()

# --- Sanitizers ---------------------------------------------------------------

# AddressSanitizer catches memory bugs (reading past the end of a buffer, using
# memory after it's freed). UndefinedBehaviorSanitizer catches things like
# signed integer overflow. Both stop the program with a report pointing at the
# bad line. On by default while learning; turn off with -DDEVICE_SANITIZE=OFF.
option(DEVICE_SANITIZE "Build with AddressSanitizer and UndefinedBehaviorSanitizer" ON)
if(DEVICE_SANITIZE)
  add_compile_options(-fsanitize=address,undefined -fno-omit-frame-pointer)
  add_link_options(-fsanitize=address,undefined)
endif()

# Warnings for our own code. -Wconversion is strict: it flags silent
# conversions such as double to float or int to int16_t, which matter in audio.
set(DEVICE_WARNINGS -Wall -Wextra -Wpedantic -Wconversion)

# --- Library ------------------------------------------------------------------

# Everything except main() goes in a library, so the tool and the tests can
# share it instead of each compiling the same files.
add_library(device_core
  src/noise.cpp
  src/wav_writer.cpp
)
# PUBLIC: anything that links device_core can also #include "noise.hpp".
target_include_directories(device_core PUBLIC src)
target_compile_options(device_core PRIVATE ${DEVICE_WARNINGS})

# --- Tools --------------------------------------------------------------------

# noise_gen: writes a few seconds of noise to a WAV file.
add_executable(noise_gen tools/noise_gen.cpp)
target_link_libraries(noise_gen PRIVATE device_core)
target_compile_options(noise_gen PRIVATE ${DEVICE_WARNINGS})

# --- Tests --------------------------------------------------------------------

# GoogleTest is downloaded the first time you configure (this needs internet
# once; afterwards it's cached in build/_deps). SYSTEM hides warnings that come
# from its headers, since it isn't our code.
include(FetchContent)
FetchContent_Declare(
  googletest
  URL https://github.com/google/googletest/archive/refs/tags/v1.17.0.tar.gz
  SYSTEM
)
FetchContent_MakeAvailable(googletest)

enable_testing()
add_executable(device_tests
  tests/noise_test.cpp
  tests/wav_writer_test.cpp
)
# gtest_main supplies main(), so the test files only contain TEST()s.
target_link_libraries(device_tests PRIVATE device_core GTest::gtest_main)
target_compile_options(device_tests PRIVATE ${DEVICE_WARNINGS})

# Register each TEST() with CTest, which runs every test in its own process:
# one crashing test can't hide the results of the others.
include(GoogleTest)
gtest_discover_tests(device_tests)
