# Wiring: the bridge, the head, the relays

Authored 2026-09-06 from the published NES-001 controller port pinout,
the 74HCT165, 74HCT04 and 74LVC245 datasheets, and the ESP32's pin
rules; revised 2026-09-07 against the gear photographed in this
directory (`IMG_5660` to `IMG_5675`). Nothing here has been built.
Every line under "Measure first" is a meter check to make before the
console is powered through any of this, because a pinout copied from a
page is a claim, and a 5 V line on an ESP32 pin is a dead ESP32.

The same wiring as a schematic, with the head, the relays and the
scope on one sheet, is `bench-v1.svg`, drawn by
`tools/draw-schematics.py` and held to the tables below by
`tools/check-sheets.py`; the build order and the v2 sheet are in
`bench-build-v1-v2.md`.

## What the photographs settled

- **The console is open, and it is an NES-CPU-10 board** (RP2A03G,
  RP2C02G-0, two Sony CXK5816 SRAMs, SN74LS373N, SN74LS139N, the 3193A
  CIC, a 74HCU04AP; the RF module labelled NES 402TD). The controller
  ports are on their own housings with a crimped harness to a white
  header on the board (`IMG_5666`), so the bridge taps the harness at
  that header with a breakout, and no extension cable is cut. The
  wire colours are still mapped by continuity, not assumed.
- **The port buffers on this board are Toshiba TC40H368P** (U7 and U8,
  `40H368 (CI)` and `(CII)`), a CMOS 40H-series part in the 74LS368's
  role, with 5.6 K pullups R14 and R15 beside them. The model
  (`nes-glue::controller`) is authored from the SN74LS368A datasheet
  as U9 and U10; the function is the same (inverting, three-state) and
  the numbering and part are this board's, for the record. The 165's
  5 V output drives either.
- **The sound stage's parts are as the model has them**: R6 47 K, C20
  and C21 220 pF, C23 1 uF (Rubycon 50 V), R7 20 K, R8 12 K, all
  readable in `IMG_5669`, `IMG_5674`, `IMG_5675`. N7's stage was
  authored from the schematic; the board agrees.
- **The microcontroller is an ESP32-C6-DevKitC-1 v1.2** (`IMG_5662`,
  `IMG_5664`), not a classic ESP32: RISC-V, GPIO0 to 23 on the
  headers, four pulse-counter units, two USB-C ports (one to a UART
  bridge on GPIO16 and 17, one the chip's own USB on GPIO12 and 13).
  Strapping pins 8, 9 and 15 (and 4 and 5, to be safe) are left
  alone. That leaves fourteen usable pins, which is what the bridge
  needs once the D0 monitor is dropped; the pin table below is the
  C6's, and the firmware carries both maps.
- **The reset relay is a PC817 optocoupler module** (`Iso_817_X1`,
  `IMG_5661`): INPUT + and - through its own LED resistor, and an
  output transistor whose collector is OUT (with a pullup to VCC) and
  emitter is GND. Used as an open-collector switch: OUT to the reset
  button's pulled-up pad, GND to its ground pad, VCC unconnected, the
  Pi's pin straight into INPUT +. No 4N35 and no series resistor.
- **The head is a Raspberry Pi 4 Model B** (`IMG_5660`).

## The idea in one paragraph

Three power domains, one shared ground. The console's +5 V powers the
shift register and the inverter, which face the console's port and
speak its 5 V levels, as the pad's own 4021 does. The ESP32's 3.3 V
powers the level shifter that brings the console's latch, clock and
data down to the ESP32, and powers the original pad, so the pad's
4021 speaks 3.3 V and needs no shifting. The ESP32's 3.3 V outputs
drive the register's inputs directly, because the HCT family's input
threshold is 2 V. The ESP32 is powered from the Pi over USB; the
console's +5 V never touches the ESP32's supply.

## Console port (NES-001, front-loader, 7-pin)

Published pinout, looking into the console's socket; the numbering is
the one nesdev and the pad repair guides share. Verify with the meter
before trusting it (see below).

| pin | name | direction | used as |
|---|---|---|---|
| 1 | GND | | common ground |
| 2 | CLK | console to pad | the register's clock, and counted |
| 3 | OUT0 (latch) | console to pad | the register's load, inverted, and counted |
| 4 | D0 (data) | pad to console | the register's serial output |
| 5 | D3 | expansion | not connected |
| 6 | D4 | expansion | not connected |
| 7 | +5 V | | the register's and the inverter's supply |

The pressed level on D0 is LOW (the pad's 4021 pulls the line low; the
console's 74LS368 inverts it, so the CPU reads 1). After the eighth
clock an original pad holds D0 LOW. Both are in the model
(`nes-glue::controller`) and both are measured on an original pad in
B0 before the register's serial input is committed to ground.

## The register: 74HCT165 at the console's 5 V

A 74HC(T)165 and a 4021 are the same machine for this use, eight
parallel inputs shifted out one per clock, with one difference: the
4021 loads while its P/S pin is HIGH, the 165 while its /PL pin is
LOW. OUT0 goes through one inverter, so the 165 loads while OUT0 is
high and holds from its fall, exactly the 4021's behaviour the model
is authored from.

The 165 shifts toward QH and QH is the output, so the first bit out is
input H. The pad's order A, B, Select, Start, Up, Down, Left, Right is
therefore wired H down to A.

| 165 pin | signal | to |
|---|---|---|
| 16 VCC | +5 V | port pin 7 |
| 8 GND | GND | port pin 1 |
| 2 CP (clock) | CLK | port pin 2, direct |
| 15 /CE (clock inhibit) | | GND |
| 1 /PL (load) | not OUT0 | 74HCT04 output; its input from port pin 3 |
| 9 QH (output) | D0 | port pin 4, direct |
| 10 DS (serial in) | | GND (after the eighth bit, LOW, as the pad) |
| 6 H | A | ESP32-C6 GPIO18 |
| 5 G | B | ESP32-C6 GPIO19 |
| 4 F | Select | ESP32-C6 GPIO20 |
| 3 E | Start | ESP32-C6 GPIO21 |
| 14 D | Up | ESP32-C6 GPIO22 |
| 13 C | Down | ESP32-C6 GPIO23 |
| 12 B | Left | ESP32-C6 GPIO10 |
| 11 A | Right | ESP32-C6 GPIO11 |
| 7 /QH | | not connected |

A pressed button is a LOW on its input; the ESP32 writes 0 for
pressed. The 74HCT04 at +5 V: one gate for OUT0, the other five
inputs tied to GND. A 100 nF ceramic across each chip's supply pins.

## Down to the ESP32: 74LVC245 at 3.3 V

The 245's inputs tolerate 5 V while it is powered at 3.3 V, and it is
fast enough for the clock pulse (a few hundred nanoseconds); a resistor
divider would round that pulse into the ESP32's input capacitance and
is not used. Direction pin (1 DIR) HIGH for A to B, /OE (19) to GND,
VCC (20) to the ESP32's 3V3, GND (10) to GND.

| 245 A (5 V in) | signal | 245 B (3.3 V out) | ESP32-C6 | role |
|---|---|---|---|---|
| A1 | OUT0, port pin 3 | B1 | GPIO0 | latch count (PCNT unit 0), poll index |
| A2 | CLK, port pin 2 | B2 | GPIO1 | clock count (PCNT unit 1), clocks per latch |
| A3 to A8 | | | | tied to GND |

The C6 has no input-only pins, so the console side sits on GPIO0 and 1
and the sketch never sets them as outputs. D0 as the console sees it
is not monitored on the C6 (no fourteenth pin to spare); the scope
sees it in the "measure first" list.

## The original pad, on the bridge at 3.3 V

The pad plugs into one of the console's own port housings, whose
harness is unplugged from the board header and plugged into the
bridge's pad side instead; the board header's pins are the console
side. Nothing is cut, and the console's other port stays as it is.

| pad plug pin | signal | to |
|---|---|---|
| 1 | GND | GND |
| 7 | +5 V | ESP32 3V3 (the 4021 runs from 3 V; measured in B0 before it is trusted) |
| 3 | OUT0 | ESP32-C6 GPIO2 (output, the bridge's own latch) |
| 2 | CLK | ESP32-C6 GPIO3 (output, the bridge's own clock) |
| 4 | D0 | ESP32-C6 GPIO6 (input; 3.3 V because the pad is) |

The ESP32 polls the pad every millisecond: OUT0 high for 12
microseconds, low, then eight clocks at a microsecond each, reading D0
before each rising edge. The eight bits go to the register's inputs
in pass mode.

## The trigger

ESP32-C6 GPIO7 through 100 ohms to the scope's rear EXT TRIG (BNC, 1 M
ohm input, trigger level set to 1.5 V, rising edge). A rising edge at
the scripted latch index; the pulse a millisecond long.

## The head: Raspberry Pi 4

- USB to the ESP32 (power and the serial line protocol).
- Ethernet to the LAN the scope is on. The Pi's and the scope's
  addresses live in `bench.local.md`, ignored by git.
- GPIO17 to the PC817 module's INPUT +, INPUT - to the Pi's GND (the
  module has its own LED resistor); the module's OUT to the reset
  button's pulled-up pad and its GND to the button's ground pad, VCC
  left unconnected. Reset held for 100 ms.
- GPIO27 to a relay module's IN; the relay's normally-open contact in
  series with ONE lead of the power adapter's cable to the console's
  DC jack (the NES-001's adapter is AC, and a contact in one lead
  switches either). Never both leads, never the mains side.

## Grounds

Console GND (port pin 1), the bridge's GND plane, the ESP32's GND and
the Pi's GND (through the USB cable) are one net. The console's +5 V
and the ESP32's 3V3 are two supplies that share only that ground. The
scope's probe grounds are already on the console's ground.

## Measure first

With the meter, before anything is powered through the bridge:

1. The controller harness's wire colours against the port's pins by
   continuity, at the board header (`IMG_5666`); write the table into
   `bench.local.md`. Colours are not evidence.
   **Ring it out of circuit.** MEASURED 2026-09-09: a tone through a
   cable still plugged into the console runs through the console's own
   pull-ups and port buffers, and pins that share nothing beep. The
   first pass on this bench put two port pins on one lead, repeatably,
   and it was the instrument talking, not the cable.
2. Console on, nothing plugged in: port pin 7 to pin 1 reads 5 V, pin
   3 and pin 2 read high (idle), pin 4 reads high (pulled up).
3. An original pad on the console's other port, a game running: the
   scope on pin 2 and pin 3 of the used port, to see the latch pulse
   width, the clock pulse width and count, and D0's idle and pressed
   levels. These numbers replace the authored ones above.
4. The pad alone, powered from 3.3 V on the bench with the bridge's
   own poll: D0 follows the buttons. If a pad's 4021 does not run at
   3.3 V (it should from the datasheet), the pad side gets a second
   74LVC245 and 5 V, and this file says so.
5. The reset button's pads with the console on: which pad is ground,
   and the level the other sits at (it should be pulled up); the
   4N35's emitter goes to the ground side.
6. The 165's QH with OUT0 pulsed by hand and the ESP32 holding a known
   byte: the eight bits in the pad's order on the scope.

## Parts

| qty | part |
|---|---|
| 1 | ESP32-C6-DevKitC-1 (on hand) |
| 1 | Raspberry Pi 4 Model B with a USB-C cable to the C6's UART port (on hand) |
| 1 | 74HCT165 |
| 1 | 74HCT04 (or a single-gate 74HCT1G04) |
| 1 | 74LVC245 |
| 1 | PC817 optocoupler module (on hand) |
| 1 | relay module, 3.3 V logic input, contacts rated for the adapter's current |
| 1 | a breakout for the controller harness header, or crimp pins to tap it |
| 3 | 100 nF ceramic capacitors |
| 1 | 100 ohm resistor (trigger) |
| 1 | BNC cable to EXT TRIG |
| | breadboard or perfboard, wire |
