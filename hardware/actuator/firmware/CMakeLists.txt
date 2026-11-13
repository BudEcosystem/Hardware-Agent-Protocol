cmake_minimum_required(VERSION 3.16)
project(bhms_arm_firmware C)

# BHMS Arm controller firmware: the portable core (arm logic, STS3215 codec, limits, E-stop
# supervisor, tool handling, BHMS device table) plus host tests and the host simulator.
# The RP2040 port lives in hal/rp2040 and is built with pico-sdk (see hal/rp2040/CMakeLists.txt).
set(CMAKE_C_STANDARD 99)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

option(ARM_SANITIZE "Build host targets with ASan+UBSan" ON)

set(REPO "${CMAKE_CURRENT_SOURCE_DIR}/../../..")
set(SDK_C "${REPO}/sdk/c")
set(FRAME_DIR "${REPO}/protocol/serial")

# The endpoint library is used as is; BHMS_* bounds are the defaults.
add_library(bhms STATIC
  ${SDK_C}/src/bhms_codec.c ${SDK_C}/src/bhms_tx.c ${SDK_C}/src/bhms_endpoint.c
  ${FRAME_DIR}/frame.c)
target_include_directories(bhms PUBLIC ${SDK_C}/include ${FRAME_DIR})
target_compile_options(bhms PRIVATE -Wall -Wextra -Wpedantic -Wshadow -Wconversion -Werror)

add_library(arm_core STATIC
  core/arm_params.c core/arm_limits.c core/sts.c core/power.c core/tool_id.c
  core/epoch_flash.c core/arm.c core/arm_device.c)
target_include_directories(arm_core PUBLIC core)
target_link_libraries(arm_core PUBLIC bhms m)
target_compile_options(arm_core PRIVATE -Wall -Wextra -Wpedantic -Wshadow -Wconversion -Werror)

if(ARM_SANITIZE)
  foreach(t bhms arm_core)
    target_compile_options(${t} PUBLIC -fsanitize=address,undefined -fno-omit-frame-pointer
                                       -fno-sanitize-recover=undefined)
    target_link_options(${t} PUBLIC -fsanitize=address,undefined)
  endforeach()
endif()

add_library(arm_sim STATIC sim/sim_rig.c)
target_include_directories(arm_sim PUBLIC sim)
target_link_libraries(arm_sim PUBLIC arm_core)

# Host simulator: the whole firmware core (endpoint + arm logic) on a pty against the
# simulated rig, driven by tests/test_e2e.py exactly like the Task 9a harness.
add_executable(sim_arm sim/sim_arm.c ${SDK_C}/hal/host/bhms_hal_posix.c)
target_include_directories(sim_arm PRIVATE ${SDK_C}/hal/host)
target_link_libraries(sim_arm PRIVATE arm_sim)

add_executable(dump_tables tests/dump_tables.c)
target_link_libraries(dump_tables PRIVATE arm_core)

enable_testing()
find_package(Python3 COMPONENTS Interpreter)
foreach(t test_sts test_limits test_power test_tool_id test_epoch test_arm test_device)
  add_executable(${t} tests/${t}.c)
  target_link_libraries(${t} PRIVATE arm_sim ${CMAKE_THREAD_LIBS_INIT})
  target_include_directories(${t} PRIVATE tests ${SDK_C}/tests ${SDK_C}/hal/host)
  target_compile_options(${t} PRIVATE -Wall -Wextra)
  add_test(NAME ${t} COMMAND ${t})
endforeach()
target_sources(test_device PRIVATE ${SDK_C}/hal/host/bhms_hal_host.c)

if(Python3_FOUND)
  add_test(NAME sidecar_up_to_date
           COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_CURRENT_SOURCE_DIR}/tools/gen_sidecar.py --check)
  add_test(NAME tables_match_params_and_sidecar
           COMMAND ${CMAKE_COMMAND} -E env BHMS_DUMP_TABLES=$<TARGET_FILE:dump_tables>
                   ${Python3_EXECUTABLE} -B ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_tables.py)
  add_test(NAME e2e_arm_pty
           COMMAND ${CMAKE_COMMAND} -E env BHMS_SIM_ARM=$<TARGET_FILE:sim_arm>
                   ${Python3_EXECUTABLE} -B ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_e2e.py)
endif()
