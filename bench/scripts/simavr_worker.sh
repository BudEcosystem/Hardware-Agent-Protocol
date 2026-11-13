#!/bin/bash
# Build the Arduino LedAnalog firmware and the simavr runner in the AVR image (docker image bhms9a-avr, built by
# sdk/c/scripts/run_avr_on_worker.sh) and run the compact scenario against it at 115200 baud.
# Usage (on the machine with docker, from the repo root): bench/scripts/simavr_worker.sh [N] > simavr.json
set -eu
N=${1:-1000}
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
nice -n 10 docker run --rm --cpus=2 --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$ROOT":/work bhms9a-avr bash -c "
  cd /work/sdk/c && scripts/avr_build.sh /tmp/avr >/tmp/avr.log 2>&1 &&
  gcc -O2 -I/usr/include/simavr tests/simavr/runner.c -o /tmp/runner -lsimavr -lelf -lm &&
  python3 -B /work/bench/scenarios/compact.py --label simavr --baud 115200 --n $N --timeout 10 \
    --cmd '/tmp/runner --mcu atmega328p --freq 16000000 --adc0-mv 1667 --led-pin 5 /tmp/avr/atmega328p/atmega328p.elf --eeprom {tmp}/e.bin'"
