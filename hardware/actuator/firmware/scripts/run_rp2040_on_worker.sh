#!/bin/bash
# Ship the firmware sources to the AMD lab worker and build them in Docker (nice -n 10,
# <= 4 CPUs, only under ~/hms-lab): host tests under ASan/UBSan, then the RP2040 image with
# pico-sdk, then arm-none-eabi-size. Needs ~/hms-lab/bhms13b/pico-sdk (git clone --depth 1
# --branch 2.1.1, plus lib/tinyusb) and the bhms13b-rp2040 image (scripts/docker/Dockerfile.rp2040).
# Usage: run_rp2040_on_worker.sh [worker-host]     (default: bmh-worker)
set -eu
HOST=${1:-bmh-worker}
ROOT=$(cd "$(dirname "$0")/../../../.." && pwd)
LAB='~/hms-lab/bhms13b'
cd "$ROOT"
ssh "$HOST" "mkdir -p $LAB/src && rm -rf $LAB/src/* $LAB/out && mkdir -p $LAB/out"
tar --exclude='build*' -cf - hardware/actuator/firmware hardware/actuator/cad/params.py sdk/c/include sdk/c/src \
    sdk/c/hal sdk/c/tests sdk/c/tools protocol/serial | ssh "$HOST" "tar -xf - -C $LAB/src"
ssh "$HOST" "cd $LAB && nice -n 10 docker run --rm --cpus=4 --user \$(id -u):\$(id -g) -e HOME=/tmp \
  -e PICO_SDK_PATH=/pico-sdk -v $LAB/src:/work -v $LAB/pico-sdk:/pico-sdk:ro -v $LAB/out:/out \
  bhms13b-rp2040 bash -c '
    set -e
    cmake -S /work/hardware/actuator/firmware/hal/rp2040 -B /out/rp2040 -G Ninja -DCMAKE_BUILD_TYPE=Release -DPICO_NO_PICOTOOL=1 >/out/configure.log 2>&1 || { tail -30 /out/configure.log; exit 1; }
    cmake --build /out/rp2040 -j4 2>&1 | tail -40
    arm-none-eabi-size /out/rp2040/bhms_arm.elf | tee /out/size.txt
    ls -l /out/rp2040/bhms_arm.uf2 /out/rp2040/bhms_arm.bin
  '"
