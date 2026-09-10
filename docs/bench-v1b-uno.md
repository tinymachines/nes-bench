# v1b: the bridge on the Arduino UNO, all at 5 V

Added 2026-09-08 after the parts arrived. Supersedes v1 as the thing
to build first; v1 stays in the set as the C6 version for when v2's
counters need it.

## Why

The 74HC parts that arrived (HC165, HC595) need a 3.5 V high at
5 V. The ESP32-C6 gives 3.3 V. The UNO's ATmega328P is a 5 V part, so
with it in the middle every signal on the console side is 5 V and in
spec, and three things fall out:

- No 74LVC245: the UNO reads the console's OUT0 and CLK directly.
- No 74LS245 up-shifter with pullups: the UNO drives the 595 at 5 V.
- The pad is polled at the 5 V it was built for. Measure-first item 4
  (does the 4021 run at 3.3 V) no longer gates anything.

## Parts (all on hand)

| ref | part | from |
|---|---|---|
| A1 | Arduino UNO R3 | the pile |
| U1 | SN74HCT04N | the tube that arrived 2026-09-09. HCT: 2.0 V input threshold, safe on the 2A03's NMOS OUT0 |
| U2 | SN74HC165N | the TI bag |
| U3 | SN74HC595N | the box of 30 |
| C1..C3 | 100 nF | |
| R1 | 100 R (+ two 1 k if EXT TRIG needs a divider) | |
| J1 | console port header harness | |
| J2 | the console's other port housing | |
| | DIP-14 and DIP-16 sockets | the kit |

## UNO pins

| pin | function | why this pin |
|---|---|---|
| D13, D11 | SCK, MOSI to U3 | hardware SPI, 4 MHz, 8 bits in 2 us |
| D10 | RCLK to U3 | one rising edge moves the byte; pulsed only while D5 reads low |
| D5 | CON_OUT0 | Timer1 external clock input (T1): a 16-bit hardware counter of latch rising edges. Also readable as a level for the write gate |
| D2 | CON_CLK | INT0, falling-edge ISR: clocks per poll |
| D3 | TRIG | rises at latch T, one loop late |
| D6, D7, D8 | PAD_LATCH, PAD_CLK, PAD_D0 | the bridge's own pad poll, at 5 V |
| D0, D1 | serial to the Pi over the UNO's USB | 115200 |
| 5V, GND | the bridge's supply and ground | from the Pi through USB |

Timer1 in external-clock mode counts edges synchronously with the
16 MHz clock, so a pulse must be longer than one CPU cycle (62.5 ns)
to count; the console's latch pulse is microseconds. There is no
glitch filter; if the L stream ever shows a latch count that is not
one per poll, add a 100 pF to ground on D5 and record it.

## Firmware, delta from `bridge.ino`

The protocol in `docs/script.md` is unchanged, so `headd.py` and the
tools need nothing beyond the serial speed.

- `write_register(b)`: `SPI.transfer(~b)`, then if `digitalRead(5)`
  is LOW, pulse D10 high for one instruction and read D5 again; if it
  went HIGH across the pulse, flag the next L line. The complement is
  not cosmetic: pressed is LOW at the register. SPI is MSB first and
  the first bit sent travels furthest, so bit 7 sent first puts our
  bit 0 on QA, which is the A button. Reverse either and the pad is
  silently mirrored.
- Latch count: read `TCNT1` (16-bit), keep a 32-bit running total,
  handle wrap. Clock count: a volatile counter in the INT0 ISR.
- Loop order: read counts, emit L, then write. Fixed 64-byte line
  buffer, no `String`. Schedule cursor, not a scan.
- The schedule holds 128 entries, not the C6's 2048. This part has
  2 KB of SRAM in total and the compiler is the authority: at 256 it
  reports 2161 bytes of globals, 105 percent, and refuses to link; at
  128 it reports 1521 and leaves 527 for the stack. `tools/b3.py
  record` refuses a longer record before the run, `tools/fake-bridge.py`
  is bounded the same way so the failure can be rehearsed, and the head
  stops any run in which the bridge answers `# schedule full`.
- There is no `Serial.printf` on the AVR core and avr-libc's printf
  carries no 64-bit conversion, so the C6's `uint64_t` counters and
  `%llu` would have compiled to nothing useful. Every counter here is
  `uint32_t` and `%lu`: the latch index wraps after 2.2 years at 60
  polls a second.
- The L line stays at four fields, `L n hh c`. A timestamp is v2's
  `t_us` and does not belong here: `tools/b3.py`, `tools/compare-logs.py`
  and `head/headd.py` all require exactly four, so a fifth field would
  break the record, the comparison and the head's latch tracking at
  once. The head already timestamps what it receives.
- `MUTATE ON`: no jumper and no config pin. D5 is PD5, which is also
  PCINT21, so the latch line can raise a pin-change interrupt while
  Timer1 goes on counting it in hardware. Under MUTATE the clock
  counter is fed by that interrupt on rises only, and INT0 stops
  feeding it. That is B0's stated sabotage, the clock counter fed the
  latch line, done in software with nothing to forget to move back. A
  mutated run reports one clock per latch instead of eight, so the
  8-per-latch gate is red.

## Build order (replaces v1's)

1. Meter the harness (unchanged).
2. Meter the port with the console on (unchanged).
3. Scope the original pad in the other port for the four pulse widths
   (unchanged; these replace every authored number).
4. U1 + U2 + wire links on H..A, console on, QH on the scope: the
   pattern appears in pad order. Proves the console side alone.
5. UNO + U3 + J2, console off: `STATUS` shows the pad byte following
   the buttons; `SET 08` puts 08 on U3's outputs (meter them).
6. Join: U3 outputs to U2 inputs, D5 and D2 to J1 pins 3 and 2, GND
   to GND. Console on, `MODE PASS`, a game: L lines, 8 per latch.
7. Trigger, reset, power as before.

## What v1b gives up

- The C6's 50 ns glitch filter and its second hardware counter. The
  UNO has one external timer input free (T0 is used by `millis`).
- Wi-Fi and BLE on the bridge. Irrelevant; the Pi is the head.
- v2's six counted lines. Those go on the classic ESP32 (8 PCNT
  units) when v2 is built, with the UNO still owning the 5 V register
  and pad side. Two microcontrollers, each in its own voltage domain,
  joined only by the Pi's USB.

## v2b, the UNO version of v2, added 2026-09-09

`bench-v2b.svg` is v1b plus a second 165/595 pair on the same SPI chain
and an LM1881 whose 5 V outputs go straight into the UNO. It removes the
last 74LVC245 from the UNO designs and it removes the second
microcontroller: every count lands on the UNO, Timer1's hardware input
on LATCH1 and interrupts for the rest. The README that came with the
sheets says to build v1b, then v2b.

Two things about it are open, and both are named here rather than drawn
as settled:

- **Its L line has six fields**, `L <latch> <byte> <clocks> <t_us>
  <field> <line>`, plus `L2` for the second port and an `F` line per
  field. This document already records that a fifth field breaks
  `tools/b3.py`, `tools/compare-logs.py` and `head/headd.py`, all of
  which require exactly four. v2b therefore cannot be built without a
  protocol version and three tools updated together, and that is a
  decision, not an oversight. The four field line is v1b's and stays.
- **The CSYNC load is authored.** The sheet says 15.7 kHz on INT1 is
  about 5 percent of a 16 MHz part. That is arithmetic, not a
  measurement, and it is the number that decides whether one UNO can
  carry all six counted lines. Measure it before trusting it.

## Amendments made when the firmware was written, 2026-09-08

The sketch is `firmware/bridge-uno/bridge-uno.ino`, and it compiles:
8,018 bytes of flash, 24 percent, and 1,521 bytes of SRAM, 74 percent.
Writing it settled six things this document had left open or wrong, and
the bullets above now say what was built rather than what was planned.

- `SPI.transfer(b)` had to become `SPI.transfer(~b)`, and the bit order
  through the 595 into the 165 had to be reasoned about rather than
  assumed. Both are silent-mirror bugs.
- The `micros()` field would have broken three tools that require four.
- The MUTATE jumper and its D4 config pin are not needed; PCINT21 on
  the latch line does it in software.
- The schedule does not fit and never could; 128 is measured, not
  chosen, and three places now refuse rather than truncate.
- The 64-bit counters do not exist on this part.
- The relay modules on hand are 5 V coil parts with opto inputs, so the
  v1 sheet's 3.3 V rail was wrong for them too; both sheets now show
  the Pi's 5 V pin and an active-low input.

One part changed after all of that, 2026-09-09: **U1 is an SN74HCT04N
now, not an HC04.** HCT's input threshold is 2.0 V rather than HC's
3.5 V, which is what makes it safe on the 2A03's NMOS OUT0 output, and
the "LS04 until measured" hedge this document carried is gone with it.
The same part does the C6 sheets' 3.3 V to 5 V job in two gates, so no
LS245 and no pullups remain anywhere in the set.

One correction that came from the instrument rather than the compiler:
both sheets put the console's video on the scope's CH1. It is on CH3.
That is where `scope-capture.py` has always defaulted, it is where the
probe actually sits (measured 2026-09-07, 1,512 sync pulses), and CH1
is B2's master-clock channel, so the drawing was claiming the one
channel the alignment classifier needs for something else.
