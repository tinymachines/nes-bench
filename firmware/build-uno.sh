#!/bin/bash
# Build an UNO sketch with the Arduino AVR core and nothing else.
#
#   firmware/build-uno.sh firmware/bridge-uno /tmp/build     # -> /tmp/build/sketch.hex
#   scp /tmp/build/sketch.hex <pi>:/tmp/bridge.hex
#   ssh <pi> avrdude -c arduino -p atmega328p -P /dev/ttyACM0 -b 115200 -D -U flash:w:/tmp/bridge.hex:i
#
# arduino-cli is not installed here, but its data directory is, with the
# arduino:avr core 1.8.8 and avr-gcc 7.3.0 under ~/.arduino15: the build
# guide's `arduino-cli compile --fqbn arduino:avr:uno` comes down to these
# commands. Flags are the core's own (platform.txt), minus the warnings.
# The serial-bridge unit on the Pi opens the port per connection, so
# avrdude gets the port whenever no client is attached. 2026-09-15.
set -e
SK=$1; OUT=$2; mkdir -p "$OUT"
A=$HOME/.arduino15/packages/arduino; CORE=$A/hardware/avr/1.8.8; BIN=$A/tools/avr-gcc/7.3.0-atmel3.6.1-arduino7/bin
CF="-c -g -Os -w -ffunction-sections -fdata-sections -flto -fno-fat-lto-objects -mmcu=atmega328p -DF_CPU=16000000L -DARDUINO=10819 -DARDUINO_AVR_UNO -DARDUINO_ARCH_AVR -I$CORE/cores/arduino -I$CORE/variants/standard -I$CORE/libraries/SPI/src"
CXX="$BIN/avr-g++ $CF -std=gnu++11 -fpermissive -fno-exceptions -fno-threadsafe-statics -Wno-error=narrowing"
CC="$BIN/avr-gcc $CF -std=gnu11"
( echo '#include <Arduino.h>'; cat "$SK"/*.ino ) > "$OUT/sketch.cpp"
$CXX "$OUT/sketch.cpp" -o "$OUT/sketch.o"
$CXX $CORE/libraries/SPI/src/SPI.cpp -o "$OUT/SPI.o"
OBJS="$OUT/sketch.o $OUT/SPI.o"
for f in $CORE/cores/arduino/*.c; do $CC "$f" -o "$OUT/$(basename "$f").o"; OBJS="$OBJS $OUT/$(basename "$f").o"; done
for f in $CORE/cores/arduino/*.cpp; do $CXX "$f" -o "$OUT/$(basename "$f").o"; OBJS="$OBJS $OUT/$(basename "$f").o"; done
$BIN/avr-gcc -w -Os -g -flto -fuse-linker-plugin -Wl,--gc-sections -mmcu=atmega328p -o "$OUT/sketch.elf" $OBJS -lm
$BIN/avr-objcopy -O ihex -R .eeprom "$OUT/sketch.elf" "$OUT/sketch.hex"
$BIN/avr-size -A "$OUT/sketch.elf" | grep -E "^\.(text|data|bss)"
