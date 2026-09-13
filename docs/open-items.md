# Open items

Things seen on the way that are not closed, each with why it matters
and what closes it. Dated when added; struck through with the date and
the commit when done. Measurements do not live here; a number in an
entry is the one that raised it, with its date.

## The calibration cartridge (plan 2026-09-13)

- **C0 of `calibration-plan.md`: machine side DONE 2026-09-13 (`nes` @
  35cfe6e), part side OPEN.** `cal.nes` and its manifest are in
  `roms/`, on the Pi and served. Open: the ROM onto the flashcart or
  the physical cart (the tutorial is `build-the-cal-cart.md`), the
  reader's dump against crc32 `21091B99`, the screens seen cycling on
  the grabber, and the first strip read off a grabbed frame, which is
  `tools/cal.py grab` (C1's first tool).
- **C1: machine side built (`tools/cal.py`, self-test green, mutation red), part side OPEN:** scope records of the palette screen per variant with the cart in the console, then grabber frames. **C2 to C4: not started.**

## Model side

- **The model's hue against the part (2026-09-12).** On the title
  screen the two eyes agree to 0.7 degrees and the model sits 12.6 and
  14.1 degrees off them on the saturated colours (`eyes-vs-scope.md`).
  RERUN 2026-09-13 on the model with its CPU and sprite DMA corrected:
  12.61 and 14.1, the same to the second decimal, so the hue is the
  picture chain's and nothing upstream of it. LOCATED 2026-09-13
  (`eyes-vs-scope.md`, "Where the hue lives"): the part's analogue
  output under the eyes session's load, the level-dependent slew the
  wiki calls differential phase distortion, not the decoder (signal
  and decoded stages differ alike), not the table or the die (every
  hue speaks the table on the switch-level 2C02), not hue 12 (the
  same screen recorded earlier sits within four degrees). Closes
  with: the bars cartridge captured under the eyes' load and with the
  scope alone, and the wiki's voltage-dependent RC stage in the
  encoder with its constant fitted per load, MUTATE red.
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
  neither eye had at its instant. That sprite turned out to be the
  2A03 rung's stale sprite DMA (below, done), not a moment's
  difference; the moment question stands and closes with C2's trigger,
  which ties the model's frame to a latch. RERUN 2026-09-13 on the
  fixed model: the sprite is gone and the figure stands where the
  console's does; the numbers did not move.
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

- ~~**Rung 3 takes an NMI that falls in the last cycle of a taken branch
  at once; the die waits one instruction (2026-09-12).**~~ DONE
  2026-09-12, `6502` @ 9b3ad9a (`tests/branch_interrupt.rs`, PROBE=1
  for the table, `MUTATE_BRANCH=1` red).
- ~~**The 2A03 rung's DMA release is reported one half-cycle before the
  die resumes (2026-09-12).**~~ ANSWERED 2026-09-12: the record's RDY
  was the pin's account; the 2A03 feeds its core one cycle later
  (`2a03` `rung.rs`, measured on its die), and a bare 6502 released as
  the pin shows it goes straight on. The trace now writes the core's
  level (`nes` `CpuStep::core_rdy`); the replay's `RDY_RISE_SHIFT` is
  an experiment knob again.
- ~~**The 2A03 rung's sprite DMA copied the page as it was last read
  (2026-09-12).**~~ DONE 2026-09-12, `2a03` @ 54295cc: the DMA's reads
  went through the held core's memo. Found by rung 0 agreeing with a
  record whose game had jammed; `tests/stalls.rs` two DMAs on a bus,
  `MUTATE_DMA_MEMO=1` red. The three-way comparison's stray sprite on
  the underline was this.
- ~~**The flashcart's pad cartridge is stale (2026-09-12).**~~
  RE-EXPORTED 2026-09-13 (`docs/procedures/2026-09-13-pad-cartridge-for-the-flashcart.md`):
  `pad.nes` crc `599C4188`, 597 polls over 600 frames, in `roms/`, on
  the Pi and served at `/nes/pad.nes` with its hash recorded. Writing
  the card is yours; the checksum in the procedure says which
  cartridge the card holds.

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
- ~~**The camera is not aimed at the board (2026-09-11).**~~ DONE
  2026-09-13: a Logitech BRIO on an arm over the breadboard, `tools/eye.py`
  with measured defaults and three framings (`head/README.md`). The
  QuickCam is gone. Was: every frame
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

- **The console shows the menu's SMB logo with garbled tiles
  (2026-09-13).** A grabber frame taken while the new eye was being set
  up: the DUCK HUNT letters and the ® are drawn right, the SUPER MARIO
  BROS logo box is filled with wrong pattern-table tiles. The menu flips
  its CHR bank twice a frame for the animation ($BF02/$BF03), so a CHR
  bank line or a cartridge-connector contact is the first suspect; the
  model draws the logo right from the same bytes. Closes with: reseat
  the cartridge and grab again; if it stays, the scope on the CHR bank
  bit of the mapper latch, and a second grab after the OSCR reader has
  had the cartridge (its dump was clean, so the ROM is not it).
  Seen once: the timed screen frame at 12:02 the same day draws the
  logo right, with nothing touched between, so it is intermittent, and
  the five-minute screen frames are now the watch for it (a garbled
  frame in `captures/pi/` with a good one either side is the evidence
  to bring to the scope).

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
