cmake_minimum_required(VERSION 3.16)
project(bhms_compact C)

set(CMAKE_C_STANDARD 99)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

option(BHMS_SANITIZE "Build host targets with ASan+UBSan" ON)
option(BHMS_BUILD_TESTS "Build native tests" ON)

# The framing parser is reused unchanged from protocol/serial (not copied).
set(BHMS_FRAME_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../../protocol/serial")

add_library(bhms STATIC
  src/bhms_codec.c src/bhms_tx.c src/bhms_endpoint.c
  ${BHMS_FRAME_DIR}/frame.c)
target_include_directories(bhms PUBLIC include ${BHMS_FRAME_DIR})
target_compile_options(bhms PRIVATE -Wall -Wextra -Wpedantic -Wshadow -Wconversion -Werror)
if(BHMS_SANITIZE)
  target_compile_options(bhms PUBLIC -fsanitize=address,undefined -fno-omit-frame-pointer
                                     -fno-sanitize-recover=undefined)
  target_link_options(bhms PUBLIC -fsanitize=address,undefined)
endif()

add_library(bhms_hal_host STATIC hal/host/bhms_hal_host.c)
target_link_libraries(bhms_hal_host PUBLIC bhms)
target_include_directories(bhms_hal_host PUBLIC hal/host)

if(BHMS_BUILD_TESTS)
  enable_testing()
  foreach(t test_codec test_endpoint)
    if(EXISTS ${CMAKE_CURRENT_SOURCE_DIR}/tests/${t}.c)
      add_executable(${t} tests/${t}.c)
      target_link_libraries(${t} PRIVATE bhms_hal_host)
      target_include_directories(${t} PRIVATE tests)
      target_compile_options(${t} PRIVATE -Wall -Wextra)
      add_test(NAME ${t} COMMAND ${t})
    endif()
  endforeach()
endif()

# Host device simulator (native twin of examples/LedAnalog) and its pty tests.
add_library(bhms_hal_posix STATIC hal/host/bhms_hal_posix.c)
target_link_libraries(bhms_hal_posix PUBLIC bhms)
target_include_directories(bhms_hal_posix PUBLIC hal/host)
add_executable(sim_device tests/host/sim_device.c)
target_link_libraries(sim_device PRIVATE bhms_hal_posix)
target_include_directories(sim_device PRIVATE arduino/BHMS/examples/LedAnalog)
# A richer native endpoint (async, cancel, stop, fences, faults) for the Python gateway bridge tests.
add_executable(sim_bench tests/host/sim_bench.c)
target_link_libraries(sim_bench PRIVATE bhms_hal_posix)
target_include_directories(sim_bench PRIVATE tests/host)
if(BHMS_BUILD_TESTS)
  find_package(Python3 COMPONENTS Interpreter)
  if(Python3_FOUND)
    add_test(NAME e2e_native_pty
             COMMAND ${CMAKE_COMMAND} -E env BHMS_SIM_DEVICE=$<TARGET_FILE:sim_device>
                     ${Python3_EXECUTABLE} -B ${CMAKE_CURRENT_SOURCE_DIR}/tests/host/test_e2e.py)
    add_test(NAME description_mirror
             COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_CURRENT_SOURCE_DIR}/tests/host/test_description_mirror.py)
  endif()
  add_test(NAME arduino_library_in_sync
           COMMAND ${CMAKE_CURRENT_SOURCE_DIR}/scripts/sync_arduino.sh --check)
endif()
