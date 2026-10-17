# v1c: the parts for one board

What to have on the bench before soldering one v1c shield (ordered
2026-10-17: five bare boards from JLCPCB, `docs/bench-v1c.md`). The first
table is `docs/fab/bench-v1c-bom.csv`, the board's own bill of materials,
as rendered on 2026-10-17; if the two ever disagree, the CSV is the board
and this page is stale. The second table is what the board needs and the
BOM does not list: the headers, housings, crimps and sockets.

Every part is through-hole. Nothing here is assembled by the fab.

## On the board

| qty | part | refs | footprint | on hand |
|---|---|---|---|---|
| 1 | 74HCT04 | U1 | DIP-14 | yes (the tube of 2026-09-09) |
| 1 | 74HC165 | U2 | DIP-16 | yes (the TI bag) |
| 1 | 74HC595 | U3 | DIP-16 | yes (the box of 30) |
| 1 | PC817 | OK1 | DIP-4 | check: the bench's is on a module |
| 1 | SRD-05VDC-SL-C relay | K1 | SANYOU SRD form C | yes (metered 2026-10-17: COM 1, NO 3, NC 4) |
| 1 | 2N3904 | Q1 | TO-92, E B C | check |
| 1 | 1N4007 | D1 | DO-41, band on pad 1 | check |
| 1 | 100R | R1 | axial, 10.16 mm | yes |
| 1 | 1k | R2 | axial, 10.16 mm | yes |
| 2 | 470R | R3 R4 | axial, 10.16 mm | check |
| 1 | 10k | R5 | axial, 10.16 mm | check |
| 3 | 100 nF ceramic | C1 C2 C3 | 5 mm disc, 5 mm pitch | yes |
| 1 | 100 pF ceramic | C4 | 5 mm disc, 5 mm pitch | yes |
| 3 | Molex KK-254 header, 5 way, vertical (22-27-2051) | J1 J2 J3 | AE-6410-05A | buy |
| 1 | Molex KK-254 header, 4 way, vertical (22-27-2041) | J4 | AE-6410-04A | buy |
| 4 | Keystone 5000 test point, red | TP1 to TP4 | miniature loop | buy |
| 2 | Keystone 5001 test point, black | TP5 TP6 | miniature loop | buy |

TP1 is TRIG, TP2 OUT0, TP3 D0, TP4 CLK at U2's clock pin (after R2 and
C4), TP5 and TP6 ground, as the silkscreen says.

## Off the BOM

| qty | part | for |
|---|---|---|
| 1 set | Arduino UNO stacking headers (one 10, two 8, one 6 way) | A1: the shield onto the UNO, tall enough to clear its USB jack |
| 2 | DIP-16 socket | U2, U3 |
| 1 | DIP-14 socket | U1 |
| 1 | DIP-4 socket, or half a DIP-8 | OK1 (or solder it) |
| 3 | Molex KK-254 housing, 5 way (22-01-3057) | the console cable, the pad cable, the front panel harness |
| 1 | Molex KK-254 housing, 4 way (22-01-3047) | the Pi lead |
| 20 | Molex KK-254 crimp terminal (08-50-0114), plus spares | the four housings |
| 4 | female Dupont sockets on lead | the Pi end of the Pi lead: GPIO17, GPIO27, 5V, GND |

The cables keep today's colours and orders: the controller port as J1
in `docs/cheat-sheet.md`, the front panel brown, red, orange, yellow,
white as J3 in `docs/cheat-sheet-head.md`, and the Pi lead by header
position (5V 2, GND 6, GPIO17 11, GPIO27 13).

## Five boards

The order is five boards and one is built first. For more than one,
multiply the tables; the chips, the relay and the opto are the ones the
drawer may run short of.

## Bring-up

When one is built, the check is the one the breadboard passes:
`tools/bench-check.py --hands head` on the Pi, every row PASS, and the
walk 15 of 15. The test points take the scope's probes where the
breadboard needed clips: TP4 is where the fault of 2026-10-17 (R2 one
row off the clock lead) would have shown in a minute.
