# BHMS Arm controller firmware for the RP2040 (pico-sdk 2.x, arm-none-eabi-gcc).
#   export PICO_SDK_PATH=/path/to/pico-sdk   (with lib/tinyusb)
#   cmake -S hardware/actuator/firmware/hal/rp2040 -B build-rp2040 -G Ninja
#   cmake --build build-rp2040           -> bhms_arm.elf / .uf2 / .bin
cmake_minimum_required(VERSION 3.16)

set(PICO_BOARD pico CACHE STRING "Generic RP2040 boot2 (W25Q-class flash)")
set(PICO_PLATFORM rp2040)
include($ENV{PICO_SDK_PATH}/external/pico_sdk_import.cmake)

project(bhms_arm C CXX ASM)
set(CMAKE_C_STANDARD 11)

# The controller carries a W25Q128JV (16 MiB); the epoch region is its last two sectors.
add_compile_definitions(PICO_FLASH_SIZE_BYTES=16777216)
pico_sdk_init()

set(FW ${CMAKE_CURRENT_SOURCE_DIR}/../..)
set(REPO ${FW}/../../..)
set(SDK_C ${REPO}/sdk/c)
set(FRAME ${REPO}/protocol/serial)

add_executable(bhms_arm
  main.c hw_rp2040.c flash_rp2040.c
  ${FW}/core/arm_params.c ${FW}/core/arm_limits.c ${FW}/core/sts.c ${FW}/core/power.c
  ${FW}/core/tool_id.c ${FW}/core/epoch_flash.c ${FW}/core/arm.c ${FW}/core/arm_device.c
  ${SDK_C}/src/bhms_codec.c ${SDK_C}/src/bhms_tx.c ${SDK_C}/src/bhms_endpoint.c
  ${FRAME}/frame.c)
target_include_directories(bhms_arm PRIVATE ${CMAKE_CURRENT_SOURCE_DIR} ${FW}/core
  ${SDK_C}/include ${FRAME})
target_compile_options(bhms_arm PRIVATE -Wall -Wextra -Werror -Os)
# The portable core is held to the strict host-build warning set.
set_source_files_properties(${FW}/core/arm_params.c ${FW}/core/arm_limits.c ${FW}/core/sts.c
  ${FW}/core/power.c ${FW}/core/tool_id.c ${FW}/core/epoch_flash.c ${FW}/core/arm.c
  ${FW}/core/arm_device.c PROPERTIES COMPILE_OPTIONS "-Wshadow;-Wconversion")
target_compile_definitions(bhms_arm PRIVATE
  PICO_STDIO_USB_STDOUT_TIMEOUT_US=20000   # a stalled host must not freeze the control loop
  PICO_STDIO_USB_CONNECT_WAIT_TIMEOUT_MS=0)
target_link_libraries(bhms_arm pico_stdlib pico_stdio_usb pico_flash hardware_uart hardware_i2c
  hardware_adc hardware_gpio hardware_irq hardware_flash hardware_sync m)
pico_enable_stdio_usb(bhms_arm 1)
pico_enable_stdio_uart(bhms_arm 0)
pico_add_extra_outputs(bhms_arm)
