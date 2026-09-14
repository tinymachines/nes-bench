# Build the calibration cart

A tutorial, unrolled from the day the cartridge was built (2026-09-13,
`nes` @ 35cfe6e). It goes from an idea to a ROM file, from the file to
the model's screen, and from there to a cartridge in a console, with
each step ending in something you can check rather than something you
have to believe. Where a step has been done and measured it says so
with its date; where it is yours to do it says that too.

The plan this serves is `calibration-plan.md`. The code is
`crates/nes-console/src/cal.rs` in the `nes` repository, and every
number in this page that is not a date came out of running it.

## 0. What you end up with

- `cal.nes`, 40,976 bytes: an iNES file, mapper 0 (NROM), 32 KiB of
  program, 8 KiB of tiles. Nobody's game: the family's own, so it can
  be copied, served and flashed without a licence question.
- `cal.json` beside it: the manifest. Where every block of the strip
  and every measured region of every screen is, in dots, and what is
  in it, written by the same code that laid the tiles.
- Eight screens on a timer and on the pad, each with a strip along the
  top that spells the screen, the variant, a frame counter and the pad
  byte in black and white blocks.
- Two ways to know the cartridge you hold is this one: its sha256 and
  the crc32 of its body (the reader's own checksum), both below.

## 1. The idea: a frame that names itself

Every earlier comparison on this bench lined pictures up by time: the
Pi's clock on the grabber's frames, the trigger's sample on the scope's
record, a hand on the rest. A calibration screen instead carries its
own name in the picture. Fifteen blocks across, three rows down, each
block two tiles square (16 by 16 dots), white or black: a bit each.

| row | blocks | field |
|---|---|---|
| A | 3 | sync `101` |
| A | 3 | screen id, 0 to 7 |
| A | 6 | variant within the screen |
| A | 1 | hold (Start was pressed) |
| A | 1 | parity of every other field, folded to a bit |
| A | 1 | reserved, 0 |
| B | 3 | sync `010` |
| B | 4 | frame counter bits 11 to 8 |
| B | 8 | frame counter bits 7 to 0 |
| C | 3 | sync `110` |
| C | 4 | frame counter bits 15 to 12 |
| C | 8 | the pad byte the console read at its last poll, A at bit 0 |

A grabbed frame, a decoded scope record and a model frame are then
matched by reading the strip, and the pad's echo is what lets a script
drive the console and the picture prove which byte arrived. The blocks
are white on black in the two palette entries the decoder reads with
the least chroma error ($30 and $0F), and they sit on tile boundaries,
so nothing has to search the picture for them.

## 2. What you need

- The `nes` repository with its siblings checked out and their die
  data fetched (`../2a03`, `../2c02`; the README's build section). The
  console takes a few minutes to build cold because three switch-level
  chips measure their tables first.
- A Rust toolchain. On this workstation the shell needs
  `export PATH="$HOME/.rustup/toolchains/stable-x86_64-unknown-linux-gnu/bin:$PATH"`
  first, because a stray old `rustc` shadows the right one.
- For the part: a flashcart that takes iNES files on a card, or an
  NROM board with a 32 KiB program ROM and an 8 KiB character ROM and
  the means to program them (section 8), and the cartridge reader
  (`cartridge.md`) to prove what you wrote.

## 3. How a cartridge is written in code

The family's cartridges are functions that return bytes
(`testrom.rs`: the pad cartridge, the bars). Those were written as
bare opcodes with comments, which is fine for a program that fits on
one screen. This one has a menu, a timer, a ninety-tile strip and eight
nametables, so `cal.rs` starts with sixty lines of assembler: a `Vec`
of bytes, a label table, and a list of fix-ups for the branches and
jumps that name a label before it exists.

```rust
a.label("main");
a.e(&[LDA_ZP, Z_NMI]);       // wait for the NMI handler's flag
a.br(BEQ, "main");
a.e(&[LDA_IMM, 0x00, STA_ZP, Z_NMI]);
```

`e` appends bytes, `br` a branch resolved later, `jsr` and `jmp`
likewise. The opcodes are named constants, so a line reads as 6502.
`finish()` fills every fix-up in and refuses a branch that is out of
range, which the first build hit: the NMI handler's body is over a
thousand bytes, further than a relative branch reaches, so its skip is
a branch around a `JMP`. The generated ROM is refused by an assertion
if the code runs into the data at `$9000`.

## 4. The memory map and the frame budget

The whole program has one hard constraint: a write to the PPU's memory
while it is drawing corrupts the picture, so every write has to fit in
vertical blanking, about 2,270 CPU cycles a frame. The strip alone is
ninety tiles plus six address writes, the palette sixteen more, the
pad eight reads, and the emphasis and scroll a few more: about 1,700
cycles by counting instructions. There is no room to also decide what
the tiles should be, so:

- **The NMI handler** does only PPU traffic. It counts the frame,
  reads the pad into `$04`, copies the sixteen palette bytes from
  `$80` and the ninety strip tiles from `$20` to the PPU, resets the
  scroll and writes the mask (background on, emphasis bits from `$90`).
- **The main loop**, once per NMI, does everything else: notices new
  button presses (Select steps the screen, Start toggles hold), runs
  the timer (a variant every `VARIANT_FRAMES[screen]` frames,
  `VARIANTS[screen]` of them, then the next screen unless held),
  redraws the nametable when the screen changed, and builds the next
  frame's palette and strip into those buffers.

The consequence is a latency the manifest states: a byte polled in the
blanking that ends frame k is built into the buffers during k+1,
written in the blanking that ends k+1, and seen in frame k+2. The part
and the model share it exactly, and the frame counter names both
frames.

A screen change turns rendering off for one frame while the 1,024
bytes of nametable and attributes copy in from `$A000 + screen * $400`.
The NMI still fires in that frame and still counts it, so the counter
never skips; it just does not touch the PPU while the copy is under
way.

Zero page, for the reader who wants to watch it in the model: `$00-01`
the frame counter, `$02` the screen, `$03` the timer, `$04` the pad,
`$05` the previous pad, `$06` hold, `$09` the variant, `$0A` redraw
requested, `$0B` NMI happened, `$0E` a load is under way.

## 5. The screens

Every screen is a function of tile position, `content(screen, tx,
ty)`, returning a tile and a palette; the nametable and its attribute
table are generated from it, and a check inside the generator refuses
a layout that puts two palettes in one 2-by-2 attribute quadrant. The
backdrop is black on every screen and palette 3's third colour is white
on every screen (the strip's), so a screen has eleven colours of its
own.

| id | screen | content, below the strip |
|---|---|---|
| 0 | strip | nothing: the black and white levels alone |
| 1 | palette | eight patches, 64 by 80 dots, in two rows of four; page p of seven shows hues 2p+1 and 2p+2 at the four lumas, page 6 the greys and the $xD column; the variant (0 to 55) is page times eight plus the emphasis bits, sixty frames each |
| 2 | bars | forty 32-dot cells in the bars' slot order; variant v of eight shows luma v/2 and hues 1 to 11 or 2 to 12, so every hue shows at every luma; 120 frames each |
| 3 | gratings | vertical lines at 1, 2, 4 and 8 dots across the top band, horizontal at the same pitches across the middle, a 1-dot and a 2-dot checkerboard below |
| 4 | edges | black and white fields 64 dots wide, then red and green fields, so there are luma steps both ways and a chroma step |
| 5 | dotcrawl | the 1-dot checkerboard in blue and the 2-dot in orange, each a whole half of the screen |
| 6 | pad | one field 256 by 160 dots, grey with nothing pressed and green with any button; the strip echoes the byte |
| 7 | geometry | a one-dot border at the picture's edge with a full tile every 32 dots as a tick, a one-dot crosshair through (128, 120) |

Screens with one variant last 240 frames each; the cycle runs
unattended, which is how the part and the model agree with nobody at
the pad, and Select and Start are for the sitting that wants to park
on one.

The CHR is twenty tiles: blank, solid in each of the three colours,
the nine grating and line patterns, and the four corners.

## 6. The manifest

`manifest()` walks the same functions and writes JSON: the strip's
geometry and its twelve fields, and for every screen its regions with
either the palette entry it shows on each variant or the pattern it
draws (`v1`, `h4`, `chk2`: the kind, the pitch in dots, the axis). A
tool that reads a picture reads the manifest for where to look; a
rectangle typed by hand into a tool is a bug, because the two would
drift.

```
{"name": "patch0", "x": 0, "y": 64, "w": 64, "h": 80, "entries": [1, 1, ..., 33, 33, ...]}
{"name": "v2", "x": 64, "y": 64, "w": 64, "h": 64, "pattern": "v2", "pitch": 2, "axis": "x", "colour": 48}
```

## 7. Build it, run it in the model, read it back

```bash
cd nes
export PATH="$HOME/.rustup/toolchains/stable-x86_64-unknown-linux-gnu/bin:$PATH"
cargo run --release -p nes-console --example export-testrom -- out/cal.nes cal
cargo run --release -p nes-console --example cal-screens -- out/
cargo test --release -p nes-console --test cal
MUTATE=1 cargo test --release -p nes-console --test cal      # must go red
```

The first line writes `cal.nes` and `cal.json`. The second runs the
cartridge in the console, presses Select the way a hand would, and
writes each screen through the family's own decode as a PPM, printing
what the strip on that frame says (MEASURED 2026-09-13: screen 0 at
frame 7, then every six frames the next, hold set, pad 00). The third
is the gate: the strip reads from the first drawn frame and counts by
one; every region of every screen holds what the manifest says, dot for
dot on the patterns; the timer steps screen 0 to 1 at 240 frames and
the palette screen's variant at 60; the pad byte is echoed two frames
after the blanking that polled it and the pad screen's field is green
the same frame. The fourth reads the strip one tile to the right of
where the manifest puts it and must fail, which it does on the four
tests that read a strip. A check that cannot fail is not a check.

The picture of all eight screens, as the decoder sees them, is the
first thing worth looking at: the dot-crawl checkers come out as flat
colour fields with the crawl in them, which is the decoder telling the
truth about a 1-dot pattern at NTSC's bandwidth, and is what screen 5
is for.

## 8. Onto a cartridge

**The checksums (MEASURED 2026-09-13, `nes` @ 35cfe6e).** The flashcart
copy is this cartridge when both agree:

| | value |
|---|---|
| `cal.nes` sha256 | `4b9d92ebc78ccccce55f150fe237e845b5a27a46c7a28a5fbbe6188a9c8ef6b2` |
| body crc32 (the file after its 16-byte header; the reader's figure) | `21091B99` |

The files are in this repository's `roms/` (gitignored: regenerate
with the export line above), on the Pi at `~/nes-bench/roms/` with a
`SHA256SUMS` to check them (`sha256sum -c SHA256SUMS`), and served at
`tinymachines.ai/nes/cal.nes` with `/nes/cal.json` beside it.

**A flashcart.** Copy `cal.nes` to the card, check its sum on the
machine that holds the card, boot it. The reader (`cartridge.md`) then
dumps what the console sees and prints the crc32 it computed, which
must be the table's. This is the step that is yours; nothing here has
run on the part yet.

**The physical board (the owner's build spec, 2026-09-14).** The board
is the NES CART PCB "discrete mapper board" v3.3 from the blanks page
(`cart-blanks.md`): two 32-pin footprints, U3 for CHR and U4 for PRG,
both taking an SST39SF040 (512 KiB, 5 V parallel flash), programmed in
an XGecu Pro (the TL866 family, XGpro software, device SST39SF040).
NROM needs none of the board's logic, so U5 to U7 stay empty; the
console's lockout is defeated, so the CIC position U2 stays empty too;
the H/V solder jumper follows the header's mirroring bit, which for
this file is vertical (the picture never scrolls and uses one
nametable, so either shows the same thing, but the board and the file
should agree).

The chip is bigger than the image sixteen times over for PRG and
sixty-four for CHR, and an NROM board drives only fifteen and thirteen
of its nineteen address lines, so the image is TILED to fill the chip,
not padded with zeros: every state of the undriven lines then lands on
a copy. `tools/nesprep.py` does the split and the tiling and refuses
the cases that would burn garbage (a header without the magic, a file
shorter than its header, a region that does not divide the chip, a CHR
size of zero, which means CHR RAM):

```bash
python3 tools/nesprep.py roms/cal.nes            # -> roms/cal-flash/prg.bin, chr.bin
python3 tools/nesprep.py --selftest roms/cal.nes # every copy held to its region; MUTATE=1 red
```

MEASURED 2026-09-13 on the exported `cal.nes`:

| image | copies | bytes | sha256 |
|---|---|---|---|
| `prg.bin` (U4) | 16 of 32 KiB | 524288 | `3ca73ce7d67e78412739857f9fe6bccde7e09a03b6ebc5cbe5ab38c771efed94` |
| `chr.bin` (U3) | 64 of 8 KiB | 524288 | `fb61eb01b3218701270f3924570ec2ebcee758c12f39154f99338f7cf826270d` |

Burning, from the same spec: in XGpro select SST, SST39SF040; seat the
chip bottom-justified in the ZIF socket, pin 1 toward the lever, the top
eight positions empty, the arrow on the case matching; read a blank
chip first and stop if its ID is not the part's (a relabelled fake
reads wrong here before it fails in the console); load `prg.bin`,
program, verify; the same for `chr.bin` on the second chip; PRG into
U4, CHR into U3, the jumper to the mirroring the script printed. Then
the reader's dump: crc32 `21091B99` is this ROM, and a wrong wire on an
address line shows up there long before it shows up as a screen you can
interpret.

## 9. What comes next

With the cartridge in the console and the strip reading off the
grabber, C1 of the plan begins: the palette screen through the scope
and the capture path against the model, per entry. The tool for that,
`tools/cal.py`, starts with `grab`, which reads the strip off a grabbed
frame by the manifest's rectangles the way the model's reader does, and
refuses a frame whose strip does not read rather than guessing.
