# Wiring: the bridge, the head, the relays

Authored 2026-09-06 from the published NES-001 controller port pinout,
the 74HCT165, 74HCT04 and 74LVC245 datasheets, and the ESP32's pin
rules. Nothing here has been built. Every line under "Measure first"
is a meter check to make before the console is powered through any of
this, because a pinout copied from a page is a claim, and a 5 V line
on an ESP32 pin is a dead ESP32.

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
| 6 H | A | ESP32 GPIO16 |
| 5 G | B | ESP32 GPIO17 |
| 4 F | Select | ESP32 GPIO18 |
| 3 E | Start | ESP32 GPIO19 |
| 14 D | Up | ESP32 GPIO21 |
| 13 C | Down | ESP32 GPIO22 |
| 12 B | Left | ESP32 GPIO23 |
| 11 A | Right | ESP32 GPIO25 |
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

| 245 A (5 V in) | signal | 245 B (3.3 V out) | ESP32 | role |
|---|---|---|---|---|
| A1 | OUT0, port pin 3 | B1 | GPIO34 | latch count (PCNT unit 0), poll index |
| A2 | CLK, port pin 2 | B2 | GPIO35 | clock count (PCNT unit 1), clocks per latch |
| A3 | D0, port pin 4 | B3 | GPIO36 | the line the console sees, sampled to verify the register |
| A4 to A8 | | | | tied to GND |

GPIO34, 35, 36 are input-only on the ESP32 and cannot be driven by
mistake, which is why they carry the console side.

## The original pad, on the bridge at 3.3 V

The pad's plug goes into a socket on the bridge (the console end of
the cut extension cable), not into the console.

| pad plug pin | signal | to |
|---|---|---|
| 1 | GND | GND |
| 7 | +5 V | ESP32 3V3 (the 4021 runs from 3 V; measured in B0 before it is trusted) |
| 3 | OUT0 | ESP32 GPIO26 (output, the bridge's own latch) |
| 2 | CLK | ESP32 GPIO27 (output, the bridge's own clock) |
| 4 | D0 | ESP32 GPIO32 (input; 3.3 V because the pad is) |

The ESP32 polls the pad every millisecond: OUT0 high for 12
microseconds, low, then eight clocks at a microsecond each, reading D0
before each rising edge. The eight bits go to the register's inputs
in pass mode.

## The trigger

ESP32 GPIO33 through 100 ohms to the scope's rear EXT TRIG (BNC, 1 M
ohm input, trigger level set to 1.5 V, rising edge). A rising edge at
the scripted latch index; the pulse a millisecond long.

## The head: Raspberry Pi 4

- USB to the ESP32 (power and the serial line protocol).
- Ethernet to the LAN the scope is on. The Pi's and the scope's
  addresses live in `bench.local.md`, ignored by git.
- GPIO17 through 330 ohms to a 4N35's LED (anode), cathode to GND; the
  4N35's transistor across the reset button's pads, emitter to the pad
  that measures as ground. Reset held for 100 ms.
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

1. The extension cable's wire colours against the plug's pins by
   continuity, both halves; write the table into `bench.local.md`.
   Colours vary by maker and are not evidence.
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
| 1 | ESP32 dev board (any with GPIO16 to 36 exposed) |
| 1 | Raspberry Pi 4 with a USB cable to the ESP32 |
| 1 | 74HCT165 |
| 1 | 74HCT04 (or a single-gate 74HCT1G04) |
| 1 | 74LVC245 |
| 1 | 4N35 optocoupler and a 330 ohm resistor |
| 1 | relay module, 3.3 V logic input, contacts rated for the adapter's current |
| 1 | NES controller extension cable, cut in the middle |
| 3 | 100 nF ceramic capacitors |
| 1 | 100 ohm resistor (trigger) |
| 1 | BNC cable to EXT TRIG |
| | breadboard or perfboard, wire |
