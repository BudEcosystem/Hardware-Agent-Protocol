#!/bin/bash
# Inside the AVR image: build the firmware (avr_build.sh), build the simavr runner
# and run the pty end-to-end harness against the ATmega328P (and ATmega2560) image.
# Usage: avr_sim_test.sh [outdir]
set -eu
SDK=$(cd "$(dirname "$0")/.." && pwd)
OUT=${1:-"$SDK/build-avr"}
"$SDK/scripts/avr_build.sh" "$OUT" > "$OUT.log" 2>&1 || { cat "$OUT.log"; exit 1; }
cat "$OUT/sizes.txt"
gcc -O2 -Wall -I/usr/include/simavr "$SDK/tests/simavr/runner.c" -o "$OUT/runner" \
    -lsimavr -lelf -lm
status=0
# ADC: 1667 mV on a 5000 mV reference reads as 341 (0x155) on a 10-bit converter.
run() { # name mcu led_pin
    echo "== simavr e2e: $1 =="
    BHMS_TARGET=simavr BHMS_ANALOG=341 BHMS_TIMEOUT=10 \
    BHMS_SIMAVR_CMD="$OUT/runner --mcu $2 --freq 16000000 --adc0-mv 1667 --led-pin $3 $OUT/$1/$1.elf" \
        python3 -B "$SDK/tests/host/test_e2e.py" -v || status=1
}
run atmega328p atmega328p 5
run atmega2560 atmega2560 7
exit $status
