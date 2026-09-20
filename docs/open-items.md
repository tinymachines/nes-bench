# Open items

Things seen on the way that are not closed, each with why it matters
and what closes it. Dated when added; struck through with the date and
the commit when done. Measurements do not live here; a number in an
entry is the one that raised it, with its date.

## The bench (milestone 2026-09-15, `milestone-2026-09-15-rig-and-bridge.md`)

- ~~**Reset and power from the head OPEN** (bring-up 6.2, 6.3)~~ DONE
  2026-09-17: OK1 across the reset button (J3 3 orange to OUT, 4 yellow
  to GND) and K1 across the power switch (J3 1 brown and 2 red), both
  driven from the Pi and both held twice end to end by
  `bench-check.py --hands head`: the polls pause 2.0 s on a reset and
  about 3 s on a power cycle and come back. The console can be brought
  to a known state with no hand on it.
- **A short reset pulse is under the instrument's floor (2026-09-17).** A
  100 ms and a 250 ms hold on GPIO17 left no mark in the poll stream; a
  500 ms hold paused it 0.5 s. The poll stream cannot resolve less than
  about half a second, because the Pi's bridge hands lines over in
  100 ms batches, so this says nothing about whether the console reset.
  The head's hold is 0.5 s for now. Closes with the scope on the latch
  line at 50 ms a division, where a 100 ms gap in the latch train is
  plain, or with the grabber watching the game restart.
- **The pad through the bridge OPEN** (4.2, 5.2), and with it J2's
  lead order, the last check on the as-built sheet.
- **CH2's original lead broke 2026-09-15**; a new lead is on the latch.
- ~~**The Pi's GPIO27 rests with a pull-down (2026-09-17)**, which is the relay
  ON from power-up until the head claims the pin.~~ DONE 2026-09-17 11:56 EDT:
  `gpio=27=op,dh` and `gpio=17=op,dl` in the Pi's boot config (the old file
  kept beside it), the Pi rebooted, and both pins read back as outputs, GPIO27
  high (relay open) and GPIO17 low (reset not pressed). Still to meter: the
  relay's contact open across COM and NO with the Pi freshly booted.

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

- **The multicart's menu ignores Start after a cold boot: CLOSED
  2026-09-18, the bench's own.** It never did. The head kept the last
  bridge session's latch number across the bridge's `RESET`, so a
  `WAIT n` after a `RESET` returned at once whenever the session before
  had passed latch n, and the `ARM` behind it (three seconds of SCPI)
  caught the menu around latch 190, before the press at 200. The runs
  that "ignored" Start show it: from `wait for latch` to `armed` in
  their `head.log` is 3.1 to 4.0 s, the arm alone (024438, 025049,
  025348, 025525, 031324, 031502), where the one that "took" it after
  two resets (025800) spent 12.8 s, a real wait: the two resets'
  five seconds between let the bridge's new count reach the head.
  Fixed in `head/headd.py` (the bridge's `# reset` acknowledgement
  clears the count; 3b22f7f) and asked again: with no reset at all
  (the bridge zeroed with the power off, then power; run 193915), one
  reset (194105) and three (194257), the press takes every time, the
  poll at the Super Mario Bros. title's lines (247, 249) where the
  model's is. The model's side was built on the way and stays:
  `nes-console`'s `Console::reset_button` and `bench-script` (a script
  played with its seconds and its resets; nes @ a2a9f15), which took
  the press after one reset and two before the part was asked again.
  What was written from the wrong reading (a mask gated by cold-boot
  state, in `mario-dissection.md` and `encyclopedia.md`, and the `[ram]`
  knob's motive) is corrected where it stood.
- **split-score's synthetic roundtrip read 0.77: CLOSED 2026-09-19,
  a recovery bug.** The whole-picture correlation of the synthetic
  record with the model's own frame F read 0.77, tied with F+1, where a
  clean synthesis should read 1. None of the stand-in scope's knobs
  mattered (rate, rate error, offset, noise all zero: still 0.7735); an
  offset search found the picture exact (r 1.0000) four samples over,
  half a dot. The capture recovery (`ntsc-crt` `recover_nes`) assumed
  every frame began at subcarrier origin 0, and the NES starts each
  frame at one of three origins a third of a cycle apart; its burst
  lock slid a frame that began elsewhere by 4 or 8 samples to make the
  assumption true, invisible to colour and to flat regions (E2's
  scores are unchanged) and to its own test, whose chain had been
  arranged so the anchored frame was origin 0. v0.2.12 measures the
  origin, locks to it and names it; the synthetic roundtrip reads
  1.0000 at F, the neighbours 0.62 to 0.71.
- **The part's picture sits a quarter dot right of the model's: OPEN,
  a measurement.** `split-score` now prints the registration, the shift
  that best lines the part's frame up with the model's F: 1 to 3
  decoded samples (eight to a dot), 2 on average, on 8 records from
  three sessions (the split, E3's scripted and hand replays), with r
  0.95 to 0.99 there. The synthetic reads 0. Candidates: the DAC's own
  timing of a picture edge against its sync edge, or the scope
  channel's delay on detail against sync. Recorded, not fitted; the
  bars cartridge's sharp edges under the scope alone (E1) would give
  it a number free of the game's content.
  Duck Hunt's field (2026-09-19, `exercise.md`) reads 4 samples.
  **Narrowed 2026-09-20: Duck Hunt's 4 samples is the subcarrier
  origin, not this.** `split-score`'s measurement 6 names the origin on
  both sides, and on all three Duck Hunt records the part's is 4 samples
  ahead of the model's while the registration reads exactly 4; on the
  Super Mario Bros. split the origins agree and the registration reads
  2. So the two are not one quantity, which is what the item below
  supposed: they coincide only where the origin is adrift. What is left
  here is the 2 samples that remain when the origins agree, and the 8
  records' 1 to 3 should be re-read with measurement 6 beside them to
  see which of them were carrying an origin difference too.
- **Duck Hunt's field matches the model's F-1 and F+1, not F: CLOSED
  2026-09-20. The frame is F; what was read is the colour phase.**
  The field at latch 900 is still dot for dot from picture 920 to 929
  (`nes-console`'s `frame-motion` probe), so nothing measured on those
  records could tell F-1 from F+1. Two frames of identical dots differ
  on 9 percent of their decoded samples, and the five candidates fall
  into two classes exactly: F-2, F and F+2 read one number, F-1 and F+1
  another. `split-score`'s new fifth measurement scores the candidates
  twice, once on the samples where they draw different dots (blurred
  over a subcarrier cycle, each candidate at its own best alignment)
  and once on the decoded picture, and two captures with the ducks
  climbing (`exercise/dh-duck.txt` at latch 989, `dh-duck-late.txt` at
  1020) read **F+0** by what was drawn, rms 0.047 against the next
  candidate's 0.117 and 0.158 over a floor of 0.020. The frame rule
  holds on a game that polls at line 249. Trap, recorded: the first
  version of the measurement took the registration fitted against F,
  which on a scrolling game absorbs the difference being measured, and
  `MUTATE_FRAME=1` went green; the alignment is fitted only where no
  candidate is in dispute.
- **Where inside a CPU cycle the console hands a cartridge its /IRQ:
  FITTED 2026-09-20, and the fit is what is open.** blargg's
  `4-scanline_timing` now passes, and getting there needed two things,
  because that ROM brackets the interrupt's arrival to ONE PPU clock and
  the console was wrong by more than that in two independent ways.

  The first was the board's, and it is closed: the A12 filter took nine
  dots of A12 low where the part takes ten. Nine dots is exactly three
  CPU cycles, so the third falling edge of M2 lands on the rise rather
  than before it, and nesdev's "remained low FOR three falling edges" is
  not met. It cost one clock a frame and only with the background at
  $1000, where A12 falls after the pre-render line's last pattern fetch
  and rises at line 0's first: a frame came to 242 clocks on alternate
  frames where the part makes 241. nes-bus 0.1.6, and the console's
  `mmc3-probe` now runs its own cartridge in either mode so the count
  reads straight off.

  The second is the console's and is a fit. The cartridge's /IRQ had no
  delay at all: the level was read at whatever CPU half-cycle came next.
  It is a LINE, and `CART_IRQ_DELAY` now holds it behind the board by
  seventeen master half-steps (twelve to a CPU half-cycle, eight to a
  dot), which is the only grain fine enough for a one-clock bracket.
  `examples/irq-sweep` runs the ROM at every delay and prints what each
  reports: the ROM allows fourteen through twenty-one and no further,
  and seventeen is the middle. That is more than half a CPU cycle,
  which is far too long for a wire from pin 15, so most of what it
  stands in for is likely where inside its cycle the CORE samples IRQ
  rather than anything the cartridge does. **Closes with:** a scope on
  pin 15 against the CPU's phi2 on the bench, which would narrow the
  band to a number and say which end of the path the slack belongs to.
  It costs no game a line either way (a split is 341 dots wide).
- **MMC3's A12 filter counts dots where the part counts M2's falls:
  OPEN, and no ROM here can see it.** Ten dots is the value that agrees
  with the part everywhere blargg looks, but the argument behind it is
  about a phase: whether three M2 falls fit strictly inside a nine-dot
  window depends on where the window starts against the CPU's clock. A
  count of dots cannot express that and a console can, because it owns
  the alignment. The case that decides it is the pre-render line to line
  0 boundary with the background at $1000, where the gap is exactly nine
  dots; every other window in a frame is either two dots or hundreds,
  nowhere near the edge. **Closes with:** the filter rewritten to count
  M2's falling edges, held to the same five ROMs, with the alignment
  swept to show which alignments change the answer and which do not.
- **The part's colour phase is a neighbouring frame's: CAUSE NAMED
  2026-09-20, and what is left is one frame.** The part's subcarrier
  origin is **4 samples ahead of the model's on every Duck Hunt record
  and equal on the Super Mario Bros. split**, and the difference
  survives the two-frame step on all four, so it is a standing offset
  rather than a phase carried wrongly. On the still field and the late
  duck the part's origin equals the model's at F-1 and F+1 exactly,
  which is why those frames scored better: the colour phase was reading
  the origin, as the entry below supposed, and now says so in a number.

  The mechanism is in `ntsc-grid`: a full frame advances the origin 4
  samples and a short one 8, so the sequence alternates between two of
  the three origins and never visits the third. F-1 and F+1 therefore
  always share an origin that F does not, whatever is drawn. That is
  also why measurement 5 names a parity and not a frame.

  A difference of 4 is **one frame's worth**: one side counted a frame
  short that the other counted full. It is not the seed (`Picture`
  starts at phase 0, and on the Super Mario Bros. path that seed is
  right) and it is not the step.

  **Swept over the bank the same day, and the divergence is early and
  rare.** Measurement 6 on eight records, every one of them its own
  `POWER ON`:

  | latch | path | difference | frames missed |
  |---|---|---|---|
  | 8, 60, 124 | the menu's first two seconds | 8 | 2 |
  | 300, 600 | Super Mario Bros. title and level | 0 | 3, wrapped |
  | 900, 989, 1020 | Duck Hunt's field | 4 | 4 |

  Three separate power-ons inside each group read the **same** number,
  so the part's power-on origin is reproducible and this is not a
  power-on lottery the model could never track. The count accumulates
  mod 3, which is why it reads 0 in the middle of the range rather than
  growing: at 300 the model has missed three, not none.

  The shape of it is the finding. The difference is already 8 by frame
  **8** and has not moved by frame 124, so two divergences happen in the
  first eight frames and then none for over a hundred; one more arrives
  by 300 and one more by 900. That points at the moments rendering is
  turned off and on, and above all at the PPU's warm-up, where the part
  ignores writes for the first frames and the model may enable rendering
  a frame earlier or later than the part does.

  **Closes with:** the model's per-frame short/full decisions printed
  from power-on and counted against what each record's difference
  requires. `split-score`'s measurement 6 is the instrument and the
  eight records above are the fixture; what is missing is the model's
  own frame-by-frame parity, which no probe prints yet. A Duck Hunt
  record earlier than latch 900 would bracket the fourth divergence, and
  the bank has none.

  Superseded account, kept because the supposition it makes is exactly
  the one the measurement refuted.

  With the
  frame settled by content, the same records still read the part's
  colour phase closer to the model's F-1 and F+1 than to F: 0.100 and
  0.107 against 0.183 on the still field, 0.113 and 0.117 against 0.121
  on a moving one, and no alignment within a dot and a half repairs it.
  The NES begins each frame at one of three subcarrier origins a third
  of a cycle apart, and `recover_nes` has measured the part's since
  v0.2.12; a third of a cycle is 4 samples on the recovery's grid,
  which is also what the registration reads on this game. So this item
  and the quarter-dot one above may be one quantity seen twice.
  Candidates: which origin the model's encoder gives a frame of that
  parity, against which the part actually starts. Closes with: the
  origin named on both sides, frame by frame, on one record (the
  recovery already names the part's), or the bars cartridge under the
  scope alone.
- **The part's luma misses less on the lowest rows: CLOSED 2026-09-20.
  It is the colour, not the row.** `capture-score`'s new
  `PROFILE=<colour>` reports one colour's luma row by row on both
  sides, over the dots the model draws a settling distance clear of
  anything else. `$22` on the Super Mario Bros. title runs rows 1 to
  207 and the part sits -0.0443 below the model with the difference
  tilting +0.0001 per hundred rows; Duck Hunt's `$21` reads -0.0444
  over rows 1 to 148, `$29` -0.0445 over 157 to 225 and `$18` -0.0283
  over 183 to 239. Two colours at the same rows read -0.0445 and
  -0.0283, and one colour across two thirds of the picture does not
  drift. Nothing in the recovery weakens at the frame's bottom.
- **The vertical sync's first dot: CLOSED 2026-09-18.** Measured on
  the switch-level 2C02 (`2c02`'s `vsync-probe`): the sync begins where
  row 244's horizontal sync begins, dot 280, three broad pulses a row
  apart, and the part's record shows the same shape. The encoder had it
  64 dots late (ntsc-crt v0.2.10 holds it to the die); `poll-line.py`
  places from it. The six tenths of a line was that plus `dissect.py`'s
  line arithmetic (the pre-render line numbered 0 and a dot's drift per
  skipped dot, fixed the same day); with both right the part's poll
  agrees with the model's own recorded strobe position to 0.01 line on
  the menu and 0.03 in the game (`mario-dissection.md`, "Done on the
  part").

- **The triggered frame is one picture late for a game that polls
  after the sync rows: CLOSED 2026-09-18.** Found by `split-score` on
  the first scrolling record (F+1). The console now records every
  latch's PPU position and `run_to_picture_after_latch` places the
  frame from it against the die's onset (nes @ efbcc46,
  `tests/latch_frame.rs`, MUTATE=1 red); `capture-score` and
  `split-score` share the rule and the record names F+0. E2's numbers
  were on a still picture and did not depend on it: rerun the same
  afternoon, the morning's record rescores to the thousandth and a
  third record repeats the hue (`exercise.md`, E2's rerun).

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
  ON THE SCOPE 2026-09-18 (E2, `exercise.md`): the part's title
  decoded from a triggered capture at latch 300 against the model's
  frame at the same latch, twice, at two vertical scales: `$22` (the
  sky) -9.1 degrees both times, `$17` (the title box) -3.0 and -3.1;
  level-dependent, as the eyes' finding said. Two points on the part
  fit a line with no residual, so the number is recorded here and not
  in `knobs.toml` (Programme 1's rule) until the bars cartridge gives
  every level.
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
