# Plan: the calibration cartridge

Written 2026-09-13, the evening the breadboard reached its baseline and
the parts for a physical cartridge came together. One cartridge, built
in code like the family's others, whose every screen is designed to be
MEASURED: off the part through the scope, the grabber and the camera,
and off the model through the same decoder, with the same tool reading
both. Colour, resolution, filtering and the pad, in that order of
difficulty, and the pad closing the loop the bench was built for. The
milestones of `bench-plan.md` (B0 to B3) and `closed-cycle-plan.md`
stand; this is the cartridge that makes their comparisons cheap to
state and hard to fudge.

## What is already true

- **A cartridge is a function.** `nes-console/src/testrom.rs` builds
  the pad, pad-dmc, pad-paint and bars cartridges as bytes, and
  `export-testrom <out> <kind>` writes them as iNES. The bars
  cartridge already cycles four luma rows on a frame timer with no
  input, so the part and the model run it identically unattended.
- **A capture is scored against the model through one decoder.**
  `capture-score` finds flat regions in the model's own frame, sets a
  settling margin from the decoder's chroma filter (`margin_dots`), and
  scores luma, hue and saturation per region off a scope record; the
  bench's `b1-score.py` drives it. `eyes.py` scores the grabber against
  the scope's decoded record and against the model. `hue-stage`
  measured where the hue error lives (the part's output under load).
- **The pad is scriptable both ways.** The bridge's `MODE INJECT`,
  `SET hh`, `AT n hh` hold a byte at a latch index; the model takes the
  same script through `set_pad`; the trace example holds the byte the
  eight reads spell to the script as oracle, and the die replays the
  record.
- **The eyes are fixed.** The BRIO is in its mount with named views;
  the grabber delivers whole 720x480 frames; the scope is armed by
  script and fired by the bridge's trigger.

## The one new mechanism: a frame that names itself

Every comparison so far has aligned pictures by time (the Pi's clock,
the scope's trigger sample) or by hand. A calibration screen carries
its own name and frame number IN THE PICTURE: a strip of high-contrast
blocks along the top rows, screen id and a frame counter in binary,
white on black in the two greys the decoder reads with the least
chroma error. A grabbed frame, a decoded scope frame and a model frame
are then matched by reading the strip, not by guessing which frame the
trigger caught. The strip is also the auto-pad's readout: the pad
screen echoes the byte the console read at its last poll into eight
more blocks, so the loop script to bridge to console to picture to
grabber closes on a byte, and a byte either matches the script or does
not.

The strip is drawn from tiles, so its geometry is the PPU's own: block
edges fall on tile boundaries and the reader knows where to look from
the manifest (below), never by searching the picture.

## The cartridge

NROM, 32 KiB PRG and 8 KiB CHR, like the others, so it flashes to the
same cart and dumps on the same reader. Screens, each a nametable and a
palette, selected two ways: an auto-cycle on a frame timer (the model
and the part agree unattended, as the bars do) and by the pad (Select
steps the screen, Start holds it), so a sitting can park on one.

| id | screen | what it measures | read how |
|---|---|---|---|
| 0 | **strip only** on the backdrop | that the strip reads at all; the black and white levels | grabber, scope: sync, blanking, the two levels the rest is scaled by |
| 1 | **palette** | all 64 entries as flat patches, the four rows of luma, backdrop $0F; a second pass per emphasis bit (eight variants on the timer) | scope record through `capture-score`'s regions; grabber through `eyes.py`'s model comparison; the hue table and the part's DAC, per entry |
| 2 | **bars** | the existing bars screen, kept as is | already scored; the continuity check against the old measurements |
| 3 | **gratings** | vertical lines at 1, 2, 4 and 8 dots, then horizontal; a checkerboard | resolution: contrast at each pitch off the grabber and the decoder, against the model's own contrast at that pitch (an MTF, four points) |
| 4 | **edges** | a black-to-white step and a white-to-black step, wide flat fields either side, in luma only; then the same step between two saturated colours | filtering: the edge response of the grabber and of the decoder, ringing and rise, against the model; the chroma step against the luma step says where the bandwidth lives |
| 5 | **dot crawl** | a fine colour grid that alternates chroma phase frame to frame | the three-frame phase cycle: the decoder's comb, the grabber's, and whether the model's frame parity matches the part's |
| 6 | **pad** | the strip's echo of the last poll's byte, the poll count in BCD, and a field that changes colour on the frame a button lands | auto-pad: the echoed byte against the script's byte at that latch; latency: the frame the field changes, off the grabber, against the latch the bridge logged |
| 7 | **geometry** | a one-tile border at the active area's edge, a crosshair at centre, ticks every 32 dots | overscan and the grabber's crop; the scope's line timing against the model's |

Every screen carries the strip. Screens 1 and 5 run on the timer even
when parked, because what they measure is a cycle.

**The manifest.** `export-testrom cal <out>` writes `cal.nes` and,
beside it, `cal.json`: for every screen, every region worth measuring
(rectangles in dots, what palette entry or pattern is there, what the
strip encodes) and the vectors, derived from the same generator that
laid the tiles. Nothing about the picture is typed twice; a tool that
reads the picture reads the manifest for where to look.

## The tool: `tools/cal.py`

One reader for every eye, in the bench repo, driving the model through
`nes-console` and the decoder through `ntsc-crt`'s examples the way
`b1-score.py` and `eyes.py` already do:

    python3 tools/cal.py model  cal.nes [--screen N]      # the model's frames and their expected readings
    python3 tools/cal.py grab   cal.nes <frames.jpg...>   # read the strip, match the screen, score
    python3 tools/cal.py scope  cal.nes <record.u8> <rate> # the decoded record, the same scoring
    python3 tools/cal.py pad    cal.nes <script.txt> <frames...> # echoed bytes against the script
    python3 tools/cal.py report <run-dir>                 # one table per screen, MEASURED and dated

Every reading is a comparison with the model's reading of the same
screen through the same path, never with a typed target: the palette
patch is right when it agrees with the model's decoded patch within
the tolerance `capture-score` already carries; the grating is right
when its contrast ratio to the model's is within a stated band. Where
the part and the model disagree, the tool says which screen, which
region and by how much, and that difference is the finding, the way
the hue stage was.

## Milestones

**C0: the cartridge exists and runs on both sides. MACHINE SIDE DONE
2026-09-13** (`nes` @ 35cfe6e: `crates/nes-console/src/cal.rs`, its
test `tests/cal.rs`, `export-testrom cal`, `cal-screens`). What was
planned as `cal_program()` in `testrom.rs` became its own module with
a small label-resolving assembler, because eight screens, a timer, a
pad-driven menu and a ninety-tile strip are too much program to write
as bare bytes and keep honest. Two things the build decided:

- The strip is three rows of fifteen blocks, each two tiles square,
  not one row: the NMI's blanking budget is the limit (the PPU writes
  measured by counting at about 1,700 of the 2,270 cycles), so the
  main loop builds the tiles and the palette for the next frame and
  the NMI only copies them. The price is a two-frame latency from the
  blanking that polls the pad to the frame whose strip echoes it,
  identical on the part and the model, and stated in the manifest.
- The strip costs one colour (palette 3, colour 3, white on every
  screen) and the backdrop is black on every screen, so a screen has
  eleven colours of its own. The palette screen therefore shows eight
  64-by-80-dot patches a page over seven pages, and the bars screen
  eleven hues a variant over eight variants, every hue at every luma
  across them; both are in the manifest per variant.

The gates, as run: the five tests of `tests/cal.rs` are green (the
strip reads from the first drawn frame and counts by one; Select steps
all eight screens and every manifest region holds its entry or its
pattern dot for dot; the timer steps screen 0 to 1 at 240 frames and
the palette screen's variant at 60; the pad byte echoes two frames
after the blanking that polled it and the pad screen's field turns
green the same frame), and `MUTATE=1`, the reader one tile right,
goes red on the four that read a strip. The eight screens were looked
at through the family's own decode (`cal-screens`).

The files (MEASURED 2026-09-13, exported from `nes` @ 35cfe6e):

| file | bytes | sha256 | body crc32 |
|---|---|---|---|
| `cal.nes` | 40976 | `4b9d92ebc78ccccce55f150fe237e845b5a27a46c7a28a5fbbe6188a9c8ef6b2` | `21091B99` |
| `cal.json` | the manifest beside it, 8 screens, 69 regions, 12 strip fields | in `roms/SHA256SUMS` | |

In `roms/` here and on the Pi (`sha256sum -c SHA256SUMS`), and served
at `tinymachines.ai/nes/cal.nes` with `/nes/cal.json` beside it.

**C0, the part's side: OPEN.** The ROM onto the flashcart (or the
physical cart, `docs/build-the-cal-cart.md`), the reader's dump against
the CRC above, the auto-cycle and Select seen on the grabber, and the
first strip read off a grabbed frame: `tools/cal.py grab`, which is
C1's first tool and not yet written.

**C1: colour. MACHINE SIDE BUILT 2026-09-13, PART SIDE OPEN.**
`tools/cal.py` exists (`nes-bench` @ 4cbd14b): `grab` finds the console's
grid in a grabber frame from the strip's own structure (every offset
that reads a strip, then the one whose band best matches the ideal
strip drawn from the bits read, because the decode smears every edge
and a step's energy ties), reads the strip by the manifest's rectangles,
refuses a frame that does not read, and scores the flat regions of the
screen against the model's decoded picture of the same screen and
variant; `scope` decodes a record, reads its strip, and runs
`capture-score` to the same frame; `model` measures the frame offset
(MEASURED: a strip that reads c is the model's frame c + 3 from
power-on). `selftest` reads the model's eight screens and the same
pictures re-sampled to the grabber's geometry at offsets the tool is
not told, JPEG-compressed: all found within a sample; the decode path
puts the strip one row above the manifest (the comb's line delay) and
the finder follows the picture; `MUTATE=1`, half a block off, is red on
all sixteen. The scorer's own synthetic roundtrip on the palette screen
(`capture-score cal.nes 250` and `310`: variants 0 and 1, emphasis 0
and 1) reads all eight patches of a page within the N6 tolerances, the
green run before any capture. What remains is the part: the cartridge
in the console, a scope record of the palette screen per variant, and
`cal.py scope` on each; then the grabber's frames through `cal.py
grab`. Screen 1 through the scope and `capture-score`'s
regions, and through the grabber and `eyes.py`'s path, against the
model. Gate: all 64 entries scored at each luma with the margin rule,
the table of differences dated in `docs/calibration.md`; the eight
emphasis variants likewise. A regression: the bars screen scores what
it scored on 2026-09-06 within tolerance. What C1 delivers is the
part's DAC as a table beside the transcribed one, per entry, not per
hue as `hue-stage` did.

**C2: resolution and filtering.** Screens 3, 4 and 5 off the grabber
and the scope. Gates: the four-point MTF and the two edge responses
for each eye, against the model's, in one figure each; the dot-crawl
parity stated (the part's frame parity against the model's). The
grabber's own bandwidth becomes a measured thing, which every later
grabber comparison is corrected by or at least stated against.

**C3: the pad, closed.** Screen 6 with the bridge in INJECT mode and a
script of `AT n hh` lines. Gates: every echoed byte read off the
grabber equals the script's byte at that latch (the strip is the
oracle's witness; the bridge's log and the model's `set_pad` agree with
both); the latency from latch to the field's change, in frames, off
the grabber, matches the model's; `MUTATE=1` reads the script one
latch late and must go red on every change. This is B1's comparison
with a cartridge that reports its own input, and the first turn of the
auto-pad: a script drives the part and the picture proves it.

**C4: the camera as a fourth eye.** The BRIO on the TV or the grabber's
monitor, its frame read by the same strip reader after a perspective
fix from the geometry screen's border. Gate: the strip reads; the
palette patches score within a stated wider tolerance; what the camera
cannot measure is stated (its own white balance and gamma), so a
camera frame is never mistaken for a capture.

## Rules, stated once

- The cartridge is the family's own: it is committed as code, exported
  on demand, and may be served like the pad and bars cartridges. No
  commercial ROM content enters this plan.
- Every target is the model's reading through the same path, never a
  typed number. Tolerances are stated once, in the tool, with the
  measurement they came from.
- A reading names its frame by the strip. A frame without a readable
  strip is refused, not guessed.
- The manifest is derived from the generator. A rectangle typed by
  hand is a bug.
- MEASURED lines carry their date and the run directory; the public
  site gets them only through the boarding scripts.

## Decided here

- NROM, one ROM, screens by timer and by pad: no second cartridge for
  the pad, no mapper the reader does not already dump.
- The strip is binary blocks on tiles, not text: a decoder reads it in
  three lines of code and a camera reads it after one perspective fix.
- The first eye for C1 is the scope, as in B1: it is the one whose
  transfer function is known. The grabber's is C2's output, not C1's
  input.
- Order: C0, C1, C3, C2, C4. The pad loop (C3) comes before resolution
  because it is the bench's purpose and needs only what C0 builds.
