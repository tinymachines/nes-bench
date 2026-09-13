# 2026-09-13: the bridge on the breadboard, read off the eye while it was built

The BRIO's timed frames (`scripts/grab.sh`, every five minutes) and a few
aimed close-ups (`tools/eye.py grab --zoom 200|300 --pan --tilt`) read
against the cheat sheet (`docs/cheat-sheet.md`, the pin table per chip).
The board was being wired while this was read, so every line carries the
time of the frame it came from; a later frame outranks an earlier one.

## What the eye can and cannot resolve

The camera is on an arm off to one side, so a chip's legs (3 mm above
the board) sit about a fifth of a hole pitch away from their holes in
the picture: a wire is placed by the HOLE row it enters, a pin by
counting legs from the chip's end, and a one-column call is worth a
second look by hand. A camera straight over the board would remove
that. Hands in the frame hide everything; the frame is retaken.

## The board as built (12:05 to 12:25 frames)

Two breadboards side by side, head to tail (the column numbers of the
left one run the other way). The chips are on the right board, pin 1
at the high-column end of each, left side (rows f to j) toward the
board's middle:

| chip | columns | pin 1 | rail stubs seen (right side, rows a to e) |
|---|---|---|---|
| U3 74HC595 | 6 to 13 | col 13, left | 16 VCC to +, 13 /OE to GND, 10 /SRCLR to +: all three RIGHT |
| U2 74HC165 | 18 to 25 | col 25, left | 16 VCC to +, 15 /CE to GND, 10 DS to GND: all three RIGHT |
| U1 74HCT04 | 28 to 34 | col 34, left | 14 VCC to +, 13 6A, 11 5A, 9 4A to GND: all four RIGHT |

Grey stubs go to the outer rail column (nearer the red line, +5 V),
brown to the inner (nearer the blue line, GND); the console lead's
yellow (GND) sits in the inner column at about column 16: RIGHT.

## Findings, in the order they matter

1. **U2 74HC165 ground wire is one hole high.** The grey wire from the
   left board lands in the row of pin 7 (/QH, no connection in the
   plan), one column above the end pin 8 (GND, column 18). Counted from
   the bottom leg in a zoom-300 frame at 12:22, hole rows aligned. Move
   it one hole toward column 18. Without it the 165 has no ground.
2. **U1 74HCT04 left-side ground wires.** Three grey wires are meant
   for pins 3 (2A), 5 (3A) and 7 (GND). The first two read right; the
   third reads between pin 6 (3Y, an output) and pin 7. Check it is on
   the END pin.
3. **The console CLK (blue lead) on U2.** The plan puts it on pin 2 (CP,
   column 24). The 12:22 frame reads it on the hole row of pin 3 (E,
   column 23), with the first leg hidden under the wire, so this is the
   least certain call here. Check by counting from the top: CP is the
   SECOND hole down from the chip's top end.
4. **Polarity of the left board's rail and the two red links.** The
   grey ground wires and the U3 pin-8 wire all come from the left
   board's rail; the two red wires tie the left board's rail pair to the
   right board's. Both links are red, so nothing in the picture says
   which is + and which is GND, and a hand was in every frame of that
   corner. Meter it: left board rail to right board rail, same colour
   line to same colour line.
5. **Console D0 (green lead)** is parked in row b at about column 14,
   nothing else on that column yet; it has to reach U2 pin 9 (QH,
   column 18, right side). OUT0 (black lead) reads on U1 pin 1: RIGHT.
6. **An empty two-way housing** sits across the rail pair at column 14.
   Nothing in it; if it is not a probe point, take it out before power.

Not judged: the ten-way ribbon from the Pi into the left board (columns
about 44 to 53) and the UNO ribbon's header at the top of the left
board are not on the v1b breadboard sheet, which has the Pi on four
jumpers to the relay and PC817 modules only.
