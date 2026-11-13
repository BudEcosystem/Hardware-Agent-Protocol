#!/bin/bash
# Build the Arduino LedAnalog example for ATmega328P (Uno) and ATmega2560 (Mega)
# with avr-gcc and the Debian/Ubuntu arduino-core-avr core, and report sizes.
# Run inside the AVR image (scripts/docker/Dockerfile.avr); output in $1.
#
#   Flash = text + data   (what the chip stores)      RAM = data + bss (static)
set -eu
SDK=$(cd "$(dirname "$0")/.." && pwd)
OUT=${1:-"$SDK/build-avr"}
CORE=/usr/share/arduino/hardware/arduino/avr
LIB="$SDK/arduino/BHMS/src"
SKETCH="$SDK/arduino/BHMS/examples/LedAnalog/LedAnalog.ino"
mkdir -p "$OUT"
: > "$OUT/sizes.txt"

COMMON="-Os -ffunction-sections -fdata-sections -flto -fno-fat-lto-objects -DF_CPU=16000000L -DARDUINO=10806 -DARDUINO_ARCH_AVR"

build() { # name mcu variant board_define
    name=$1; mcu=$2; variant=$3; board=$4
    d="$OUT/$name"; mkdir -p "$d/core" "$d/lib"
    inc="-I$CORE/cores/arduino -I$CORE/variants/$variant -I$CORE/libraries/EEPROM/src -I$LIB"
    flags="-mmcu=$mcu $COMMON -D$board $inc"
    for f in "$CORE"/cores/arduino/*.c; do
        avr-gcc -c -w -std=gnu11 $flags "$f" -o "$d/core/$(basename "$f").o"
    done
    for f in "$CORE"/cores/arduino/*.cpp; do
        avr-g++ -c -w -std=gnu++11 -fpermissive -fno-exceptions -fno-threadsafe-statics $flags "$f" -o "$d/core/$(basename "$f").o"
    done
    rm -f "$d/core.a"; avr-gcc-ar rcs "$d/core.a" "$d"/core/*.o
    # Library: strict warnings, per-function stack usage.
    for f in "$LIB"/*.c; do
        avr-gcc -c -Wall -Wextra -Werror -std=gnu99 -fstack-usage $flags "$f" -o "$d/lib/$(basename "$f").o"
    done
    { echo '#include <Arduino.h>'; cat "$SKETCH"; } > "$d/sketch.cpp"
    avr-g++ -c -Wall -Wextra -std=gnu++11 -fno-exceptions -fno-threadsafe-statics $flags "$d/sketch.cpp" -o "$d/sketch.o"
    avr-gcc -Os -flto -fuse-linker-plugin -Wl,--gc-sections -mmcu=$mcu -Wl,-Map="$d/$name.map" \
        -o "$d/$name.elf" "$d/sketch.o" "$d"/lib/*.o "$d/core.a" -lm
    {
        echo "== $name ($mcu) =="
        avr-size -C --mcu=$mcu "$d/$name.elf"
        avr-size -A "$d/$name.elf" | grep -E "^\.(text|data|bss)"
    } | tee -a "$OUT/sizes.txt"
    # Baseline: the same Arduino calls (Serial, EEPROM, analogRead, digitalWrite)
    # with no BHMS code, so the library's own cost is the difference.
    cat > "$d/baseline.cpp" <<'EOF'
#include <Arduino.h>
#include <EEPROM.h>
static uint32_t boots;
void setup() { pinMode(LED_BUILTIN, OUTPUT); Serial.begin(115200); EEPROM.get(0, boots); EEPROM.put(0, boots + 1); }
void loop() {
  if (Serial.available()) { digitalWrite(LED_BUILTIN, Serial.read() & 1); Serial.write((uint8_t)analogRead(A0)); }
}
EOF
    avr-g++ -c -w -std=gnu++11 -fno-exceptions -fno-threadsafe-statics $flags "$d/baseline.cpp" -o "$d/baseline.o"
    avr-gcc -Os -flto -fuse-linker-plugin -Wl,--gc-sections -mmcu=$mcu -o "$d/baseline.elf" "$d/baseline.o" "$d/core.a" -lm
    {
        echo "-- baseline (Arduino core + Serial + EEPROM, no BHMS) --"
        avr-size -C --mcu=$mcu "$d/baseline.elf" | grep -E "^(Program|Data)"
        # Non-LTO library objects: per-module size and per-function stack depth.
        mkdir -p "$d/nolto"
        for f in "$LIB"/*.c; do
            avr-gcc -c -Os -ffunction-sections -fdata-sections -fstack-usage -std=gnu99 -mmcu=$mcu $inc "$f" \
                -o "$d/nolto/$(basename "$f" .c).o"
        done
        echo "-- library modules, not linked (text data bss) --"
        avr-size "$d"/nolto/*.o | sed "s|$d/nolto/||"
        echo "-- deepest library stack frames (bytes) --"
        cat "$d"/nolto/*.su | sed 's|^[^:]*:[0-9]*:[0-9]*:||' | sort -t$'\t' -k2 -n -r | head -8
    } >> "$OUT/sizes.txt"
}

build atmega328p atmega328p standard ARDUINO_AVR_UNO
build atmega2560 atmega2560 mega ARDUINO_AVR_MEGA2560
cat "$OUT/sizes.txt"
