# Open items

Things seen on the way that are not closed, each with why it matters
and what closes it. Dated when added; struck through with the date and
the commit when done. Measurements do not live here; a number in an
entry is the one that raised it, with its date.

## Model side

- **The model's hue against the part (2026-09-12).** On the title
  screen the two eyes agree to 0.7 degrees and the model sits 12.6 and
  14.1 degrees off them on the saturated colours (`eyes-vs-scope.md`).
  Where in the chain: the encoder's palette phase
  (`ntsc-source-nes`), the burst the model synthesises, or the decoder
  reading its own synthesis. Closes with: one flat colour encoded and
  decoded by the model beside the same colour decoded off the scope
  record (`title1.u8` has the logo brown and the lettering cyan),
  the phase difference measured per stage, and the stage named.
- **C0's mutation is stated, not run (2026-09-12).** The closed-cycle
  plan says a different ROM must fail the flat-block agreement.
  `eyes.py compare` needs a `MUTATE=1` that swaps the ROM for the
  family's test cartridge and must exit red.
- **The model's frame is a frame, the part's is a moment
  (2026-09-12).** The three-way used frame 180 from power-on with no
  input; the model's title showed a small sprite on the underline that
  neither eye had at its instant. Harmless on a static screen, wrong
  on any animated one. Closes with C2's trigger, which ties the
  model's frame to a latch.
- **The chip repositories' suites were run as they run by default
  (2026-09-12).** 2c02 gave 16 tests and 2a03 14 on the pin bump; the
  golden tests skip without their files unless required. Rerun both
  with their `REQUIRE` variables set before the next release of
  either.
- **Re-board the console's record on the public site (2026-09-12).**
  The /nes page's figures come from the record `board-nes.py` writes;
  the console moved to 5ecc62d (mapper 66, new pins) and the record is
  older. `board-nes.py --board` in the public checkout, then deploy.

- **The console's CPU runs the fixed rung 3 only once the pins move
  (2026-09-12).** The 2a03 and nes repositories pin `v6502-micro` and
  `v6502-pins` at 89ae24f, one commit before the seam fix
  (`trace-plan.md`, T0). Closes with: both pins bumped, the console
  rebuilt, and the cartridge trace rerun showing `GAME`.
- **The trace is a whole run (2026-09-12).** 1.69 MB per frame, from
  reset, because the pin format starts at h=0. A window needs T2's
  `LOAD` door; until then a long run is a large file under `/mnt/tm`.
- **The 6502's own oracles never paired an index increment with a
  crossing form (2026-09-12).** The pin golden's 256-opcode traces set
  registers by loads; blargg's instruction tests pass without the
  sequence. `tests/seam.rs` now holds twenty-two pairs, all authored, in both
  directions after a one-sided first version let a wrong fix through.
  What would close it properly: a recorded context in the table's
  recorder that ends in an ALU write to X or Y, so the selector's
  staleness is measured rather than patched around.

- **Rung 3 takes an NMI that falls in the last cycle of a taken branch
  at once; the die waits one instruction (2026-09-12).** Found by the
  bench's cartridge record replayed on rung 0 (`trace-plan.md`, T1):
  h=591,074, `BEQ` at $813F, then `LDA $20`. Closes with: a test in
  `v6502-micro` that drives an NMI edge at every half-cycle around a
  taken branch (page crossed and not) on rung 0 beside rung 3, red
  before the rule and green after, MUTATE red; then the 2a03 and nes
  pins bumped and the cartridge record replayed further.
- **The 2A03 rung's DMA release is reported one half-cycle before the
  die resumes (2026-09-12).** At the first sprite DMA of the
  cartridge's record the die resumes its held fetch a cycle before the
  record does; with every RDY rise a half-cycle later the two agree
  through five more frames. Which is early, the reported level or the
  die, is a 2A03 question: closes with the 2A03 rung's reported hold
  held to the 2A03 die's own golden at the release edge, and the
  `RDY_RISE_SHIFT` knob retired.
- **The flashcart's pad cartridge is stale (2026-09-12).** The test
  cartridge now sets its stack pointer at reset; its prediction for the
  part is 597 polls over 600 frames, not 596. Re-export with
  `export-testrom` and reflash before sitting 5's compare-logs.

## The grabber and its driver

- **A kernel update on the Pi silently removes `/dev/video2`
  (2026-09-11).** The Roxio driver is an out-of-tree module under the
  running kernel's `updates/`; a new kernel has none. After any
  `apt full-upgrade` that brings a kernel, run
  `head/roxio-em28xx/build.sh` on the Pi. Closes with a DKMS packaging
  of the same tree, or a note in the upgrade habit.
- **One kernel warning per open (2026-09-11).** `v4l_querycap` warns
  that the driver's capabilities are not a superset of its device
  capabilities. Harmless, noisy in `dmesg`. Closes with the driver's
  `vidioc_querycap` reporting exactly `device_caps | DEVICE_CAPS`.
- **Upstream (2026-09-12).** Two of the patch's pieces are not bench
  specific: the EM2980 chip id and Roxio board, and `querystd`
  answering with the standard in force for built-in decoders. Worth a
  submission to linux-media once the bench has used them for a while.

## The bench, before and during the sittings

- **The head and the bring-up bridge both want the UNO's port
  (2026-09-12).** `serial-bridge.service` holds `/dev/ttyACM0`; the
  head is not started. Closes at C1 with `Conflicts=` between the two
  units and the head carrying a `bridge` word for the bring-up tool's
  questions.
- **The camera is not aimed at the board (2026-09-11).** Every frame
  so far is the windows. Aim it, grab a frame, then the head's `PHOTO`
  word.
- **Nothing is on the sound card's input (2026-09-11).** The C-Media
  input is mic level, mono, 0 to 16 gain. The console's audio out
  wants an attenuator or the line kept low; then `EARS` in the head and
  the N7 comparison against the model's stage.
- **The inverter's five spare inputs (2026-09-10).** On the schematic
  as pins to GND since 2026-09-10, so the wiring list and the cheat
  sheet say to tie them. Sitting 3 has to do it: a floating CMOS input
  oscillates.
- **The ribbon and breakout headers are not on the breadboard sheet
  (2026-09-11).** The sheet draws the chips at their real columns and
  the cables as off-board terminals; where the nine-pin ribbon header
  and the two breakouts sit is not recorded. Once sitting 3 fixes
  them, put their columns into `tools/breadboard.py` so the sheet is
  the board.

## The card and the reader

- **`tools/oscr-card.py` is not written (2026-09-12).** The refresh
  and the first pull were done by hand with the checks the tool is to
  carry (`card-plan.md`). The udev mount exists and works.
- **The reader identifies a cartridge by 512 bytes (2026-09-12).** On
  a banked board it can name a different game (it named Super Mario
  Bros. for the combination cartridge) and dump with the wrong sizes.
  Nothing to fix in the reader; the note is that a named cartridge is
  not a checked one until the dump's checksum matches.

## The workstation

- **The API services run on the system Python's user site
  (2026-09-11).** `~/.local/lib/python3.10` was wiped by an unrelated
  install and two services broke on their next restart. A venv per
  service, named in each unit, would end that class of outage. The
  public deploy now tests on the unit's interpreter and refuses if it
  cannot import uvicorn; the 6502 deploy runs under systemd's
  environment and needs the same guard.
