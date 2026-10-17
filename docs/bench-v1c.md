# v1c: v1b as a printed shield, the hands on board

Drawn 2026-10-17. **Not ordered, not built.** v1c is the bridge that
passed bench-check on 2026-10-17, net for net, made into one printed
board: an Arduino UNO shield with the head's reset and power hands on it
as bare parts, every cable on a keyed housing, and a test point under
every scope probe.

Why it exists: on 2026-10-16 the walk read bit 0 in all eight slots and
the reset hand did nothing, and both were leads on the breadboard, one
of them R2 a single row off the clock lead. A printed board has no row to
be off by.

## What is where

| | |
|---|---|
| the schematic | `docs/bench-v1c-1.svg` to `-5.svg`, from `tools/draw-schematics.py` |
| the netlist and BOM | `python3 tools/export-netlist.py --sheet bench-v1c` writes `docs/fab/bench-v1c.net`, `.protel.net` and `-bom.csv` (generated, not committed) |
| the board | `python3 tools/make-pcb.py --sheet bench-v1c --plot` writes `docs/fab/bench-v1c/`: the `.kicad_pcb`, the Gerbers, drill, positions and three layers as SVG (generated, not committed) |
| the routing | `docs/routing/bench-v1c.ses`, recorded once by `python3 tools/route-pcb.py --sheet bench-v1c` (freerouting 2.1.0) and applied on every build |

## The circuit is v1b's, and that is checked

Sheets 1 and 2 are v1b's sheets 1 and 2: J1, U1 (its five spare inputs
tied), U2 with R2 and C4 on its clock pin, U3, R1, C1 to C3, J2 and the
UNO's pins, under v1b's references. `tools/check-sheets.py` holds every
node v1b draws (a part's pin and its net, 73 of them) to the same net on
v1c, so the two cannot drift. Wiring U2's clock pin past R2 makes it fail
(tried 2026-10-17).

Sheet 3 is new: a Keystone 5000 test point on each signal a probe sits on
today (TRIG after R1 on CH1, OUT0 on CH2, D0 on CH4), one on U2 pin 2
after the filter (the probe that would have found R2 in a minute), and
two black 5001s for the probes' grounds.

Sheets 4 and 5 are v1b's sheet 3, the modules replaced by their parts:

- **Reset**: a bare PC817 (OK1) with R3, 470 ohms, from GPIO17. At 3.3 V
  that is about 4.5 mA through the LED. The output is open collector
  across the reset button with no pull-up, as the module was wired with
  VCC open: collector on orange, emitter on yellow.
- **Power**: a bare SRD-05VDC-SL-C (K1), the relay the module carried,
  with its 5 V coil on the Pi's 5 V pin as before. A 2N3904 (Q1) switches
  the coil's low side through R4, 470 ohms (about 5.5 mA of base for a
  71 mA coil). R5, 10k, holds it off while the Pi boots, and a 1N4007
  (D1) takes the coil's kick. GPIO27 high closes COM to NO, the module's
  measured sense. A bare relay beat a footprint for the module because
  modules differ in pinout and in which way their input is active, and
  this one's sense was only ever measured, never read off a datasheet.
- **K1's contact** is in parallel with the front panel's power switch
  (COM on brown, NO on red), carrying the adapter's low voltage. Both of
  its nets are routed 0.8 mm wide. Never mains.

## The grounds

The Pi's ground is its own net, PI_GND. It reaches OK1's LED, Q1's
emitter and R5, and the board joins it to the console's GND nowhere.
The Pi reaches the console's ground through the UNO's USB lead only,
exactly as on v1b. `tools/check-sheets.py` checks four things: no part
touches both grounds, the Pi cable's ground pin is PI_GND, no pin of
that cable is on GND, and PI_GND reaches the hands and nothing else.
Each of those fails when broken (tried 2026-10-17).

What the shield changes about isolation: the Pi's side (PI_5V, PI_GND,
the two drive lines) and the console's side now share one piece of FR4,
separated by spacing and not by modules. Both sides are at low voltage
and, through the USB lead, at one ground potential, so nothing here is a
safety barrier, and nothing was before. The opto still shares nothing but
light, and K1's contact shares nothing with its coil.

## Decisions

- **A shield** (the owner, 2026-10-17), not v2b's ribbon. A1 is the UNO
  itself. Its pads are the shield's headers (`A1_SHIELD` in
  `tools/export-netlist.py`), and `tools/make-pcb.py` holds that table
  to the footprint's geometry: the digital pins on one edge, D0 across
  from A5, and the UNO's 160 mil gap between D7 and D8 (`MUTATE_SHIELD=1`
  swaps D7 and D8 and must be caught). Fit stacking headers, or long
  male headers, into the UNO's sockets.
- **Keyed cables** (the owner, 2026-10-17: a header on the cut cable).
  Molex KK-254 throughout (J1 console, J2 pad, J3 front panel, 5 way; J4
  Pi, 4 way). The housing's friction ramp lets a plug in one way only,
  and it keeps the 0.1 inch pitch every lead on the bench already has.
  JST-XH, the other common keyed family, is 2.5 mm and takes no 0.1 inch
  lead even for a test. The J4 cable ends in four Dupont sockets on the
  Pi's header, at positions 6, 2, 11 and 13.
- **100 by 53.34 mm**, two layers: the UNO's own outline carried on past
  its far end, inside the cheap fabs' 100 mm tier. The registers sit over
  the UNO; the hands, the relay and the cables sit on the extension.
- **Keepouts**, both copper layers and no part: the barrel jack, the USB
  jack with the 16U2's ICSP header and the reset button, and the 328P's
  ICSP header. Each stands taller than the UNO's sockets. Like most
  shields, this one rests on the jacks, so the board over them is bare.
- **Silkscreen names**: TRIG, OUT0, D0, CLK and GND beside the test
  points; CONSOLE, PAD, PANEL and PI beside the cables.

## Routed and checked

334 track segments and 6 vias, **0 unconnected** with the pours filled
and **0 clearance violations** at 200 um, on the finished board, by
KiCad's connectivity engine and shape geometry rather than the router's
own count. `MUTATE=1` (a track onto a pad of another net), `MUTATE_OPEN=1`
(a track deleted) and `MUTATE_SILK=1` all go red on v1c. Silkscreen: no
fault.

## For the owner to look at before an order

- **K1's NO and NC.** The pin numbers are KiCad's SANYOU SRD symbol
  (1 COM, 3 NO, 4 NC). Meter a relay from the drawer before trusting
  them; get them swapped and the console sits on while the Pi is off.
- **R3's 470 ohms.** The module's own input resistor was never read, and
  it worked; 4.5 mA is more drive than it gave, against a PC817's 50
  percent minimum transfer ratio.
- **The headers' height.** Stacking or long male headers, chosen so the
  shield clears the USB jack.

Still open, and the owner's to decide: an enclosure or none, and the
fab house and quantity.
