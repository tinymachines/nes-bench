# Order the v2b board

**Status: open.** Nothing has been sent to anybody. This document is the
task, and every step marked **you** is yours: it spends money and it
leaves this machine, so no tool here does it.

## What is being ordered

`bench-v2b`, the two-port bridge: **100 by 100 mm, two layers**, through
hole throughout. Placed, netted, poured and routed by
`tools/make-pcb.py`, and checked on the finished file rather than on the
router's word: **0 unconnected items, 0 clearance violations**.

It is not the board on the bench. **v1b is the build**, on a breadboard,
and it is what sitting 3 onward is about. This board is the second
build, and ordering it now is a lead-time decision rather than a
readiness one: it arrives while v1b is still being brought up.

**Re-routed 2026-09-10 evening, before any order.** The cheat sheet's
derived wiring showed the console ports' 5 V pins on the board's +5V
net, which would have paralleled the console's regulator with the UNO's
USB supply. Both pins are no-connects now, the routing was redone and
recorded, and the checks below pass on the new board. Make the set fresh
as the steps say; a set made before this note is the wrong board.

**Two things about v2b are open and neither is fixed by a board.** Its L
line has six fields where three tools require exactly four, and its
CSYNC interrupt load is arithmetic rather than a measurement. Both are
written up in `docs/bench-v1b-uno.md`. Ordering the board does not
settle them and does not commit anything to them; the copper is the same
either way.

## Before anything is uploaded

**The tools.** `docs/fab/` is generated and not committed, so the set has
to be made fresh from the current schematic:

```
python3 tools/netlist.py --erc          # the schematic must be clean first
python3 tools/export-netlist.py --check
python3 tools/make-pcb.py --plot
```

The last one must print, and the numbers matter more than the words:

- `silkscreen: 0 fault(s)`
- `0 unconnected, 0 clearance violation(s)`
- `fabrication set: 15 files`

If it prints anything else, stop and say so; do not send a set that the
tool did not pass.

**You, with your own eyes.** Open `docs/fab/bench-v2b/bench-v2b-top-silk.svg`
and read the reference designators. That is the sheet you will be
holding when you place parts, and no check here can tell you whether a
label is somewhere useful, only whether it is on top of something else.

## What to send

Everything in `docs/fab/bench-v2b/` with these extensions, zipped flat:

| file | what it is |
|---|---|
| `bench-v2b-F_Cu.gbr`, `-B_Cu.gbr` | the two copper layers |
| `bench-v2b-F_Mask.gbr`, `-B_Mask.gbr` | solder mask |
| `bench-v2b-F_Silkscreen.gbr`, `-B_Silkscreen.gbr` | silkscreen |
| `bench-v2b-F_Paste.gbr`, `-B_Paste.gbr` | paste (no SMD parts, so both are empty; send them anyway) |
| `bench-v2b-Edge_Cuts.gbr` | the outline |
| `bench-v2b-PTH.drl`, `-NPTH.drl` | the drill files, metric |

Not sent: the `.kicad_pcb`, the `.svg` views, the positions CSV, this
folder's README. They are for people, not for the fab. The positions CSV
is for a pick and place house, and there is nothing here to place by
machine.

## The options to choose

| option | value | why |
|---|---|---|
| size | 100 x 100 mm | the cheap tier at every fab |
| layers | 2 | |
| thickness | 1.6 mm | the default, and what a DIP socket expects |
| quantity | 5 | usually the minimum, and usually the same price as 1 |
| min track / clearance | 0.25 mm / 0.20 mm | authored in `tools/make-pcb.py`, and checked against what KiCad exported |
| min drill | 0.4 mm | the vias. Component holes are 0.8 and 1.0 mm |
| surface finish | HASL, lead free is fine | nothing here is fine pitch |
| mask / silk | any colour, white silk | |
| controlled impedance | no | |
| panelisation | no | |

Nothing on this board is near any fab's limit. If an order form warns
about a rule, that is worth reading rather than clicking through: it
means one of the numbers above is not what was sent.

**One check the fab gives you for free.** Every fab renders the Gerbers
in its own viewer before you pay. That renderer is not KiCad and not
this repository, so it is the one independent look anything gets. Read
it: both copper layers, the silkscreen, the outline, the drill overlay.
If the outline is missing or the board comes out the wrong size, stop.

## Order alongside

From `docs/parts.md`, the parts v2b needs that are not already in a
drawer:

- **LM1881N, buy two.** The one real order. An old National part, mostly
  resellers now.
- **680k resistor**, one, for the LM1881's RSET. Marked *check* rather
  than *to order*: look in the drawer first.
- **A second 74HC165.** Marked on hand, from the TI bag; confirm there
  are two before ordering nothing.

The board also wants, and the parts list does not yet name because they
are the board's rather than the schematic's:

- **A 2x10 IDC header and a ribbon** to the UNO. A1 is a cable, not a
  shield.
- **DIP sockets**, optional: 2 x DIP-16, 2 x DIP-16, 1 x DIP-14, 1 x
  DIP-8. Sockets are worth it on a bench board that will be probed.
- **Five way 2.54 mm headers**, four of them, for J1 to J4.

## What to report back

The fab, what it cost, the lead time, and whether its viewer showed
anything the tools did not. That last one is the interesting field: if
it does, the tools are missing a check and that is worth more than the
board.

## Observations

_(to be filled in as the cycle runs)_
