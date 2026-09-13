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

## Second pass, 12:40 to 12:55, after the reboot: grounds, +5 V and the J1 side

The BRIO's arm had moved (refocused: the sweep peaks at 20, 25 is
within noise, the presets keep 25) and a second eye is on the timer
(`side`: a QuickCam low on the console side). The board is three
breadboards side by side: the left one carrying the rail the supply
lands on, a middle one whose left rail is fed from it, and the right
one with the three chips. Read off zoom-200 and zoom-300 frames.

Right, with the confidence the eye can give:

- Left board rail: + is the column by the red line, GND the column by
  the black line. The two red links leave it from + (column 60) and
  GND (column 58) and land on the right board's rail + (outer, by the
  red line) and GND (inner, by the blue line) respectively, as traced
  along the bottom of the frame. Both links are red, so a meter is the
  proof.
- Orange (+) and brown (GND) stubs at the left rail's columns 51 and 52
  feed the middle board's left rail, + to the column by the pink line,
  GND to the column by the blue line.
- The five grey ground wires all start in the middle board's GND
  column: HCT04 pins 3, 5 and 7, the 595's pin 8, and the 165's wire
  (still on pin 7, finding 1 of the first pass, unchanged).
- Right board rail stubs unchanged and right, except the 165's DS stub
  (pin 10, column 19) which is gone: see the J1 findings.
- J1 yellow (GND) sits in the right board's GND column at about
  column 16: right.
- Three empty two-way probe headers, one across each rail pair.

Not seen: what feeds the left board's rail (the top of the left board
is outside every frame).

J1 findings, worth a hand check each, most likely wrong first:

7. **Green (D0) is on the 165's pin 10 row (DS), one hole above pin 9
   (QH), and the DS ground stub that was there is gone.** D0 must be on
   the bottom pin (column 18) and DS back to GND. As it stands the
   console reads the shift register's serial INPUT, and that input is
   driven by the console.
8. **Black (OUT0) reads on the HCT04's second row from the top (pin 2,
   1Y, the inverter's output), not the top row (pin 1, 1A).** If so the
   console drives the inverter's output. Pin 1 is the top hole of the
   left side, column 34, the end with the dot.
9. **A short grey stub joins the HCT04's pin-1 column (34) to the
   middle-board column where the UNO ribbon's BLUE wire (D2, CON_CLK)
   lands.** The plan has pin 1 fed by the ribbon's YELLOW (D5,
   CON_OUT0), two positions further up the header. Move the stub's
   middle-board end two holes up, to the yellow's column.
10. **The brown diagonal from the middle board to the 165's top-left:**
    its lower end reads on the top or second row (pin 1 /PL or pin 2
    CP); its upper end reads one to two columns below the ribbon's blue,
    where nothing else is. If it is the D2-to-CP link (jumper 3), both
    ends want the blue's column and pin 2.
11. Blue (CLK) reads on the 165's pin 2 (CP) in the zoom-200 frame and
    on pin 1 in the zoom-300 frame: one hole of doubt. CP is the second
    hole from the top end.

The eye's limit, stated once more: at this camera angle a lead's
housing and a chip's legs sit off their holes by a fraction of a pitch,
so every one-column call above is a question for a meter, not a
verdict. Six continuity beeps settle the J1 side: OUT0 to U1-1, U1-2
to U2-1, CLK to U2-2, D0 to U2-9, U2-10 to GND, U1-1 to UNO D5.

## Baseline, 15:40: the camera fixed, the wiring as left

The BRIO is fastened in place. Focus re-swept: 20 (twice). A board frame
taken ten minutes later sits within one pixel of the baseline frame, so
the named close-ups in `docs/eye-views.json` stay aimed:
`tools/eye.py views --pi <pi>` takes all of them into
`captures/views-<stamp>/`, and a later read is a comparison with this one.

What the baseline shows, against the v1b sheet (the pin-by-pin state is
`docs/build-status-v1b.json`, drawn as the as-built wiring sheet):

- Done: every ground and supply stub on all three chips, U2's ground
  moved to pin 8 and DS grounded, U1's pin-7 ground on its end pin, the
  rails and their links, J1's four leads (GND on the rail, CLK on U2-2,
  OUT0 on U1-1, D0 on U2-9), and the UNO's D2 to U2-2.
- Check: the short grey from the UNO strip to U1-1 starts one hole low,
  on the green (D3) instead of the yellow (D5); U2's and U3's pin-1 marks
  do not resolve on camera (U1's face the top, as wired); the UNO's 5 V
  and GND into the rails are off camera.
- Seen: two yellow ceramic capacitors across the rails where the plan
  has one 100 nF beside each chip; the red link that carries GND;
  the power and reset breakout's housing parked on the right board.

## Second baseline, 18:50: the camera moved, a splitter added, the room dark

The BRIO was repositioned and fastened again; a composite splitter now
feeds the scope and the grabber together, and the grabber shows the
console running (the multicart's game), so the splitter passes video
and sync. The room's light had changed: the frame at the old manual
exposure was dark, and exposures above the frame time turned out to be
clamped at 1080p (1000 and 2000 read back and did not brighten, with or
without the dynamic frame rate), so the presets and the timed grabs now
leave exposure to the camera. Focus re-swept: 20 again.

The board sits about 148 px right and 15 px down in the new frame, not
uniformly (the camera turned as well as moved), so each named view was
re-aimed by finding its 15:40 close-up in the new board frame; two
views (`j1-cap`, `u2-rail`) did not match well enough and keep their
shifted aim. The set was re-taken (`captures/views-20260913T184548`)
and every view lands within 20 px of its aim at zoom 100, inside the
pan and tilt step. Read against the 15:40 set, view by view, the
wiring is the same: the four checks of the baseline stand, nothing
moved, nothing added on the sheet's nets. In this light the close-ups
are noisier than at 15:40; the bench lamp back on would restore the
first baseline's legibility.
