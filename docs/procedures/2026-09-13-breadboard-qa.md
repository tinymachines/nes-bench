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

## Third look, 21:20: the lights on, the grid re-read, the junctions on the photograph

Room light back, the camera's own exposure holding the level (mean 105).
The named views re-taken; against the 18:50 set every view shifted the
same few pixels and none stood out, so the wiring is as it was. The
hole grid was re-read for this pose (`board-overlay.py --recalibrate`:
each row's five holes found as dips and fitted as an even progression,
worst 7 px; the column anchors moved by the shift the chip crop
measured, 150 right and 22 down, because a wire's edge dents a row's
profile at half a pitch and the automatic column vote numbered those as
columns). The junction overlay drawn on this frame puts every ring on
its hole: `docs/lab/board-junctions-v1b.png`.

## Fourth look, 22:55: the camera locked down again after a USB drop

A second camera plugged into the Pi's hub tripped an over-current, the
hub's branch re-enumerated and the BRIO fell off the bus for good until
the user replugged it and locked the mount ("locked down"). It came
back pulled back and turned: a column is about 17.5 px now against 20,
the perspective small, the board sitting 3.75 degrees turned in the
frame. The grid was read afresh under rulers (`docs/board-map.json`,
anchors every fifth column from 40 to 1 and the hole rows in two bands),
every named view's aim carried through the measured similarity (scale
0.926, worst residual 18 px on the fit points, inside a pan step), the
views re-taken, and the junction overlay redrawn on the new frame: every
ring on its hole. Focus re-swept: 20. The wiring reads as at 21:20.

## Fifth look, 2026-09-14 12:06: the J1 to U3 chain wired

The user's batch: the /PL link and the eight Q lines between the 165
and the 595. The camera had not moved, but the breadboards had, about
150 px left and 90 px up in the frame (measured by matching a chip body
and two printed numbers between the frames), so the hole map was
re-read off the new board frame: the rows and rails as luma dips in
bands inside the picture, the columns from the dips of all ten hole
rows voted along each row and numbered from the printed 35 and 30 under
rulers. The rail columns then needed a 13 px correction: the dip finder
had taken the +5V holes for GND, which the ringed close-ups showed at
once (a ring beside the red line instead of the blue). Every view's aim
was carried through the shift and the set re-taken.

Reading a wire's end from above has a limit that this batch made
plain: a Dupont wire's stripped end stands a few millimetres proud of
the board, and the camera sees it from one side, so a raised end reads
up to half a pitch from its hole while a seated end reads at it. The
rule used: a landing is settled where the bare end is seen at the hole
(the map's rings projected onto the zoom-500 views, so each close-up
carries its column numbers), and left as a check where it is not. A
close look at three focus values (20, 28, 36) was taken over U3; 20 is
right, 36 is blur, so the wire ends are not far enough above the board
for focus to separate them.

What settled: /PL (teal, U1-2 to U2-1), Q_B (blue, U3-1 to U2-5),
Q_SEL and Q_START (grey, to U2-4 and U2-3), Q_A (brown, U3-15 to U2-6,
its end proud of the hole), and the four rails-side lines into U2-11 to
U2-14, a neat diagonal (23 f, 22 g, 21 h, 20 i). The chips' orientation
also settled: the notch and the pin-1 dot of all three face the
high-column end, and the round mark at the far end of each is the
mould's ejector pin, which is what the earlier look had been unable to
tell from a dot.

What did not: on U3's middle side the four grey lines from U2's rails
side land in columns 10, 9, 9 and 8, so pin 5 (Q_DOWN) carries two
wires and pin 7 (Q_RIGHT) none, seen in two views. The greys are one
colour, so the eye cannot say which of the two on pin 5 belongs on
pin 7; the note on the sheet says to move the one from U2-11, and that
the SPI loopback of the next batch shows a swapped pair if the wrong
one moves. The grey from the strip to U1-1 reads between columns 34 and
35 and stays a check. The as-built sheet is rev E: 38 pins done, 6 to
check.

## Sixth look, 13:55: the U3 wire moved, the brown seated

The user moved the second wire off U3-5 and pushed the brown home. The
boards had moved on the desk again (126 px down, 4 px left: the three
chip bodies and a printed number matched between frames; the chip
bodies stand proud and read 7 px further than the board, so the
printed number and the blue Q_B wire's known hole set the last 7 px),
so the map was shifted by that, the views re-aimed, and two fresh
close looks taken with the holes projected onto them. U3's middle side
now carries one wire per column, 13 down to 7, each bare end seen at
its hole (10 a, 9 b, 8 c, 7 d); the brown's bare end enters the U2-6
hole. Both checks closed; the sheet is rev F, 40 pins done, 4 to
check, all four on the strip side and the rails' feed. Which grey
moved is not visible, so the Q pairing still rests on the SPI loopback.

## The rig, 2026-09-15 01:10: the camera on the frame, a fresh baseline

The BRIO is fixed to a metal frame over the boards, looking straight
down. The first mount had the frame's short side along the board and
lost U3's low columns off the bottom edge; turned 90 degrees the whole
board sits in one 1080p frame at about 24 px a column, with the column
pitch the same at both ends (no perspective to model, and none of the
raised-end parallax that cost the U1-1 read). Focus re-swept: 25. The
hole map was read afresh (`docs/board-map.json`: hole centres by
template correlation along six rows, the rows and rails as luma dips at
both ends), and it names a `frame_rotate` so the overlay and the map
keep the earlier convention in the turned frame. Every named view's
aim was carried through the similarity between the last desk map and
the rig map (worst residual 20 px at zoom 100) and the set re-taken; a
3 by 3 grid of zoom-300 frames with the map's holes projected onto
them shows the rings on the holes across the whole board, out to
column 48.

Read against the rig set, every pin settled before reads the same. The
UNO batch: D2 and the console's CLK share a two-pin housing in column
24 (both on U2-2, settled); D5 and the console's OUT0 share one at
columns 35 and 34 (still a check: the housing is pulled diagonal and
its two pins may both be in column 35); the three SPI leads cross over
U3 and hide their own landings, the black one's housing standing in
column 7 rather than 9, the white and grey ends not found on U3 at all,
and no +5V link visible at column 7 (pin 10) now. The pad's cable lands
on the middle board, which the map does not cover yet: extending the
map to the middle board is the next tool step. The sheet is rev G.

A note on the clock: the Pi stamps its frames in London time, and the
rig baseline above was first written up as 06:10 EDT from those
stamps; it was 01:10 EDT. The timed grabs carry their own zone file
for this reason; the by-hand grabs do not, and a stamp read off a
by-hand frame is London's.

Looked again at 01:26 EDT after the user reported the SPI leads
re-routed and D5 seated in column 34: the board frame and the close-ups
differ from the baseline only by sensor noise (worst block 18 of 255,
against 182 when the camera turned), so whatever was changed is not on
this board yet. The two checks stand for the morning.

## Second rig pose, 01:45: the UNO direct, the map read automatically

The user re-ran the UNO's leads direct from its header (the UNO now
sits at the frame's top right on a screw-terminal shield) and shifted
the boards right on the frame. The map was read off the new frame
without a hand in it: every hole centre by normalised correlation with
a hole template (1,201 found), the two five-row groups and the rail
pair as even progressions (the second group looked for across the chip
gap only, or the next board's rows win the fit), the columns walked
leftward from the board's last hole with an adaptive pitch (25 px at
column 1, 23 at column 45: the lens), anchors every fifth column and
the map interpolating between them. That is now
`board-overlay.py --read`, which also carries every view's aim through
the similarity between the old map and the new; on the previous frame
it reproduces the hand-read map, and on this one the rings sit on the
holes out to column 50. `tools/view-rings.py` is the reading
instrument, promoted from the scratchpad.

What settled: /SRCLR's link to +5V at column 7 (hidden before under
the SPI leads), the UNO's 5 V into the +5V rail at column 5, the
console's CLK at U2-2, every Q line and every rail link as before.

What the eye cannot settle, and why: a Dupont housing hides which of
its positions carries a pin, and anything raised reads outward from
the frame's centre by about a pixel per 5 mm of height per 100 px of
offset (the lens is about 142 mm over the board: a 200 mm field at
1080p), so a housing standing across two columns reads to the eye's
half-column limit and no further. Three such stand on this board: the
D5 yellow's at columns 35 and 34 (the yellow in the higher one), and
two on U3's rails side across columns 11 to 10 and 9 to 7, the SPI
leads' landings. The console's OUT0 (thin orange) has its bare end at
column 33, row i, one column past U1-1. These are the morning's meter
checks, and the case for aiming the second camera low along the chip
row, where a housing's pins are in plain view. The sheet is rev H:
40 pins done, 7 to check.

## Metered, later on 2026-09-15: U1-1 and the SPI pins

The user put a meter on U1-1 and on U3's pins 11, 12 and 14 after the
morning's list: the UNO's D5 and the console's OUT0 reach U1 pin 1,
and the three SPI leads reach their pins. Fresh close-ups differ from
the previous look by sensor noise only, which is the point: the eye
reads the same housings it could not settle, and the meter settles
them. Recorded as MEASURED on the sheet, rev I. One check remains,
the UNO's ground into the GND rail row.

## The ground, settled: every pin of the right board done

The UNO's ground reaches the rails through its USB cable from the Pi
(the user, 2026-09-15), which is what the design says and the reason
no ground lead is on the board: the UNO's 5 V and ground power all
three boards' rails; the console's port (J1-1) and the pad (J2-1) are
on that ground and the console's own 5 V (port pin 5) is not carried,
so the two supplies meet only at ground; the power and reset breakout
touches the console only through the PC817's LED and the relay's
contact, with no wire from the Pi's ground to the bridge or the
console. The as-built sheet has no checks left on the chip pins: 47
pins done.

## The middle board mapped, 2026-09-15

`board-overlay.py --read` now reads every board the map names, each in
the camera-y band it sits in: the two five-row groups, the rail pair
(looked for beyond both groups, the side with more holes winning) and
the columns walked from the board's last hole. The middle board lies
the other way up from the right board (a to e toward the right board,
f to j toward its own rails, the pair below), so a row side is named
by what it faces and carries its printed letters. The rings sit on the
holes across the middle board out to column 52 (the rest is under the
UNO's leads). The map also places single-row parts: J2, the pad-side
housing, at columns 9 to 13 on the rails side, and R1 at columns 47
to 49. Both are checks on the sheet for the same reason as before:
which row and column a housing's pins are in cannot be read from
above. The overlay draws one panel per board, the middle board above
the right one as they lie. Rev J: 47 pins done, 7 to check, all seven
on the middle board's two parts.

## The register read back through the console, 2026-09-15 evening

With the console polling (the multicart's menu) and the bridge in
MODE INJECT, bytes were SET one at a time and D0 read on the scope's
CH4, triggered on the latch's fall on CH2 (20 us/div; the traces read
off the scope's own screenshots, since the DS1054Z's waveform query
came back empty over the LAN). The latch is 3.6 us wide; the first
clock follows the fall by about 7 us and the rest at 13 us, eight in
all, then DS (ground) shows. Pressed reads LOW on D0.

What read right, twice each: 00 (nothing pressed), ff (everything),
01 (A alone), 80 (Right alone), 03 (A and B), 7f (A to Left). What did
not: 02, 04, 08, 10, 20 and 40 (one bit alone, B to Left) each showed
the pressed bit only as a sliver at its own position and then LOW at
position 8 (Right); 06 (B and Select) showed B at position 2 and
Select at position 8. So the register, the six grey lines and the 165
carry every bit when the byte has A pressed or several bits pressed,
and lose a lone middle bit to the Right position. The eye cannot see
this; a probe on CH1 can: U3 pin 1 (QB) with SET 02, then U2 pin 5 (G)
with the same, splits the 595 from the 165 in two captures.

## The trigger on CH1, and the same walk after the rewire

Step 6.1 holds: with the trigger lead moved to CH1, TRIG 20 stopped
the scope. The walk of single bits through the register reads as
before after the blue was replaced: A and Right alone right, every
byte with A pressed right, and a lone bit from B to Left shown for a
sliver at its own position and then LOW from the Right position on.
The bridge's own per-poll clock counts scatter (a third of the polls
at eight, the rest from 0 to 16 in pairs that sum to 16) while its
running totals are exactly eight a latch: the loop reads the latch
counter and the clock counter at different moments, so clocks of the
next poll are booked to the last one; that is the firmware's
bookkeeping, not the console, and the fix is to capture the clock
count in the latch's own interrupt.

The reading that fits every byte: the falling edge of D0 (a pressed
bit arriving at the 165's output) puts an extra rising edge on the
165's clock (CP, U2 pin 2), which shifts the register one place too
far. A lone bit then shows only until the extra shift (the sliver), and
the ground on DS arrives one clock early (the LOW from the Right
position). With A pressed the falling edge happens at the load, when
CP is inhibited, so those bytes read right; a byte of consecutive
pressed bits has no falling edge inside the poll. One capture decides
it: CH1 on U2 pin 2 with 02 held, looking for a glitch at the moment
D0 falls, about 7 us after the latch.

## B0 gate 1 held: eight clocks on every poll, after the firmware learned to read at the edge

The scatter in the bridge's per-poll clock counts was the firmware's,
in three layers, each found by the gate and fixed in turn (the hexes
built with `firmware/build-uno.sh`, flashed through the Pi with
avrdude, the console polling throughout):

1. The loop read Timer1 (latches) and the clock counter a few
   instructions apart while the console's clocks came 13 us apart and
   the loop was busy printing: 377 of 1,203 polls booked wrong. The
   clock count is now snapshotted in the latch's pin-change interrupt.
2. That interrupt told a rise from a fall by reading the pin, and a
   3.6 us pulse can be over by the time the interrupt runs: 7 of 1,202
   missed, each a 0 followed by a 16. It now asks Timer1 whether the
   hardware count moved.
3. The loop still took the latch count from Timer1, which can step
   before the interrupt that snapshots the clocks has run: 2 of 1,202.
   The loop now reads the interrupt's own pair, latches and snapshot,
   in one breath.

Three runs after that: 1,202, 1,203 and 1,202 polls in 20 s, every one
eight clocks. MUTATE ON still reports one clock a latch, so the gate
can still go red.

With the bookkeeping exact, the bridge's own count of the console's
clock edges was read again with a lone middle bit held (02, 40, 06)
against 00, 7f and ff: 481 polls each, eight edges every poll, no
ninth. So whatever shifts the 165 once too often is not a full-swing
edge on the clock line at the UNO's D2; if it is a spike on the 165's
CP, it is one too short for the AVR's edge detector (a cycle, 62 ns)
and long enough for the 74HC165 (about 10 ns). The capture on U2 pin
2 is still the one that decides it.

## The sliver, seen close: D0's own edge cuts it short

Triggered on D0's fall with 02 held, at 1 us/div
(`docs/lab/15-d0-fall-crosstalk.png`): D0 starts down at the 165's
first shift, reaches only 1.9 V, and is back high within about 50 ns
with a slow tail; the latch line on CH2 shows a blip of half a volt
each way at the same instant, though nothing drives it. A pressed bit
was never presented for a bit-time: the register shifted again within
tens of nanoseconds of its output starting to fall. The blip on the
latch line is the mechanism made visible: D0's edge couples into the
lines that share its cable, harmlessly into OUT0 and, on the clock
line, as a spike that the 74HC165 takes for a rising edge (it needs
about 10 ns) and the UNO's edge detector does not (it needs a cycle,
62 ns, which is why the bridge still counts eight). The 165's output
falling clocks the 165, which lifts its output: a lone pressed bit
lasts as long as the loop, and the ground on DS then arrives a clock
early. With A pressed the fall lands inside the load, when the clock
is inhibited, and a run of pressed bits has no fall inside the poll:
those bytes read clean.

The fix is at the clock pin: a series resistor and a small capacitor
on U2 pin 2 (1 kilohm from the CLK lead to the pin, 100 pF from the
pin to ground: 100 ns against a 50 ns spike, and nothing against the
console's microseconds-wide clock), and the CLK and D0 leads kept
apart on the board. The capture on U2 pin 2 would show the spike
itself; the fix can be tried without it, since the walk of single
bits is the check.

## The walk after the RC, 2026-09-15 afternoon: unchanged

The user reports a 1 k and 100 pF added at U2 pin 2. The walk of
single bits through the register reads exactly as before: A and Right
alone right, every byte with A pressed right, a lone bit from B to
Left shown for a sliver and then the Right position low; and three
multi-bit bytes (55, aa, 1b) read as the model "every falling edge of
D0 outside the load adds one shift" predicts, bit for bit. So the
extra clock does not come in on the clock lead, or the RC is not
between the lead and the pin: the eye, on the rearranged boards (the
map re-read for the new pose), finds the blue D2 and the console's red
CLK landing direct in a housing at column 24 and no resistor or
capacitor beside U2. The mechanism that fits an RC-proof spike is
ground bounce: the 165's QH pulls the console's D0 line, the cable and
a 1x probe down hard, its ground pin lifts on the rail links' length,
and the clock pin, idle high, dips and recovers as the chip sees it.
The fix for that is a 100 nF straight across U2 pins 8 and 16 with the
shortest leads possible (the design has one, and the two on the rails
at columns 17 and 29 are not it), the probes on 10x, and a short
ground lead from U2 pin 8 to the rail. The walk stays the check.

R2 and C4 are on the schematic (sheet 1, band 3) and the cheat sheet
from this revision, as built by the user; they are checks on the
as-built sheet until the eye or a meter places them.

## The rig locked, 2026-09-15 night

The BRIO raised about six inches, levelled and taped; the two side
cameras aimed and velcroed; a bench light over the board. At this
height the zoom-100 frame puts 11.1 px on a hole, both ways (the
first raised pose had 9.2 along the rows: a tilt, corrected), and the
whole backing board is in frame; a zoom-500 close-up puts 53 px on a
hole. The hole finder does not resolve 11 px holes, so the map is read
per board off a zoom-250 frame (`--read --zoomed`: the map put into
zoom-100 coordinates, which every view and overlay uses), each board
in its own frame and band, columns 1 to 56 on both, and the as-built
photograph is drawn on those frames. The named views were carried
through the similarity between the old map and the new (scale 0.484,
worst residual 8 px) and re-taken: the rings sit on the holes in
every one. Focus 18. `docs/rig.md` has the dimensions and each
camera's job and scale; the side eyes' baseline frames are in the lab
folder.
