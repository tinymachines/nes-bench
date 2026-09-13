# Plan: the trace, from the pad to the picture

Written 2026-09-12, before the code. One input history through the
console's model, and every half-cycle of it in the forms the 6502
stack already reads: the CPU at its pins, the registers, the stack
page, the bus as the program saw it, and the same window run on the
transistor-level chip with every node lit, in the pages that exist.
"Compatible with the 6502 stack" means exactly that: the stack's
formats, the stack's engines, the stack's pages, fed a console's run.

## What is already true

- The console records its CPU every half-cycle when asked
  (`Console::cpu_trace`, gate 1's instrument): the master step, the NMI
  and IRQ inputs, and a `v6502_pins::PinFrame`, which is the pin
  contract the whole 6502 ladder is verified against. A console run is
  a `.pins` trace already; nothing has written it to a file.
- The pin contract's `.stim` script carries the input pins by
  half-cycle (reset, IRQ, NMI, RDY, SO), and RDY is how sprite DMA
  halts the CPU, so a console run's halts are expressible in it.
- The console's CPU is rung 3 (the table-driven core, the 2A03's
  variant of it). Rung 3 is held to rung 0, the switch-level chip, on
  289 recorded traces, and the site's Trace and Halfshot pages are
  rung 0's: they show nodes, and rung 3 has none. Rung 3 refuses
  `TRACE` and `ROWS` for that reason and says so.
- The bench's script (`docs/script.md`) already means the same thing to
  the part and the model: bytes by latch index. `pad-log.rs` runs it on
  the model and logs one line per latch.

## The one new mechanism: a recorded bus

Rung 0 owns a memory. A console's bus is not a memory: a read of $2002
clears a flag, a read of $4016 shifts a pad bit, a write to $8000 on
this cartridge changes which bank the next fetch sees. The
switch-level chip cannot model the console, and should not: the
console's model already did, and wrote down every byte the CPU read.

So: a `RecordedBus` for `v6502-sim`, built from a `.pins` trace. On a
read it answers the byte the recording shows at that half-cycle; on a
write it stores into a shadow RAM (that is where the stack page comes
from); on every access it checks the address and direction against the
recording and refuses at the first half-cycle that differs, naming it.
Under it, rung 0 runs the console's program, instruction for
instruction, because it sees the identical inputs the console's rung 3
saw, and every one of its 1725 nodes is real. A divergence between the
two is not an error in the bus: it is a difference between the
2A03's core and the 6502 die, recorded by half-cycle.

The recording is played from the reset. Rung 0's machine value is more
than its registers, so it is not started cold mid-program; it runs
from power-on to the window, at its own speed. A console frame is
about 59,600 CPU half-cycles, which is two seconds on rung 0; the
title screen's first poll is minutes away, a game's minute is an
hour. That is a batch, not an interaction, and the plan treats it so:
the window is chosen by latch index, the run to it is once, and the
result is kept.

## What a trace carries, and what it may not

Three files per run, beside each other:

- `<name>.pins`: the console's CPU at the pins, one line per half-cycle,
  the pin contract's own text format. It contains every byte the
  program fetched, which is to say **the game's code**. A trace of a
  commercial cartridge is ROM content and is never committed and never
  served, the rule the ROM store already lives by. The traces the site
  shows are of the family's own cartridges (the test cartridge, the
  bars cartridge), which the repositories carry.
- `<name>.stim`: the input pins by half-cycle, so any rung replays the
  same run.
- `<name>.events.json`: what the console knows and the pins do not:
  the frame boundaries by half-cycle; every latch (the fall of the
  strobe) with its index and the byte the script held; every $4016 and
  $4017 read with the bit it returned; every PPU register write with
  the dot and scanline it landed on; every NMI edge; the decoded
  picture of each frame in the window as a PNG beside. Half-cycles
  throughout, never cycles, the pin contract's rule.

## Milestones

**T0: a console run is a file. DONE 2026-09-12** (`nes` @ 8eb30ee,
`crates/nes-console/examples/trace.rs`; the 6502 fix it found is
6df896a there, and 2a03 @ 43581c3 and nes pin it). Usage:

    cargo run --release -p nes-console --example trace -- \
        <rom.nes> <name> [frames] [script.txt] [out_dir]

The script's `SET hh` and `AT n hh` lines are honoured by latch index,
as `pad-log.rs` honours them; `PICTURES=n` sets how many trailing
frames are written as PPM. Out: `<name>.pins`, `<name>.stim`,
`<name>.events.json` and the pictures. One thing changed from the plan
above: there is no window by latch. The pin format runs from `h = 0`
and its parser refuses a trace that starts anywhere else, so a window
needs the machine's state at its first half-cycle, which is T2's
`LOAD` door and not a text file's business. A whole run it is, and
the size is what it is (MEASURED 2026-09-12: 1.69 MB of `.pins` per
NES frame, 59,561 CPU half-cycles per frame; 300 frames of the
family's cartridge came to 507 MB, written in 10 s).

The gates, as run:

- The `.pins` and the `.stim` are parsed back by the pin crate's own
  `parse_trace` and `parse_stim` before either is written, and the
  frames read back are held to the frames recorded by the crate's
  `compare`. A file that does not round-trip is refused.
- Latches are derived from the pins alone (a write to $4016 whose D0
  falls, on the clk0-high frame where the contract puts a write's
  byte), the reads per latch from the pins alone (reads of $4016 on the
  clk0-low frames), and both are held to the board's own poll log,
  which is what `pad-log.rs` prints: a count or a clocks figure that
  differs is refused. On the test cartridge over 12 frames with `SET
  00 / AT 3 01 / AT 6 08`: 9 latches, 8 reads each, both instruments
  agree, and `pad-log.rs` on the same script prints the same 8 closed
  polls.
- The byte the eight reads spell (bit 0 first, as the register shifts)
  is held to the SCRIPT's byte at that latch index, not to the board:
  the script is the oracle. `MUTATE=1` reads the script one latch late
  and went red on 3 of the 9 latches (the ones where the byte changes).

What the family's cartridge showed on its first trace (300 frames,
Start at latch 200 held three latches):

- The multicart's menu polls the pad from frame 10; Start is bit 3 (the
  first run pressed bit 4, which is Up, and the menu ignored it, which
  is a fact about scripts: a wrong byte is honoured exactly).
- The menu flips its CHR bank twice a frame ($BF02 <- $10, $BF03 <-
  $11, the bus-conflict AND leaving the PRG bank at 1) to animate, and
  on Start writes $BF00 <- $00 at frame 213: PRG bank 0, the SMB
  program. Sprite DMA is visible at the pins as 256 writes to $2004
  after every $4014 (60,160 of the run's 72,628 PPU writes).
- **The title screen had one wrong tile: `1 PLAYER GWME`.** The
  events file located the $2007 write ($20 where the ROM's string, read
  through $2007 out of CHR-ROM, carried $0A); the pins walked it back to
  an `LDA ($00),Y` at $8EB9 that read the un-carried address $0300 and
  never did the fixed-up read at $0400, where the $0A had been stored
  at h=14,366,205. Five instructions reproduced it on the 6502 repo's
  `diverge` (rung 0 beside rung 3): after `INY`, rung 3's selector
  asked the stored Y, one instruction stale, because the result was
  still in the hold register and lands through the seam. Fixed in the
  6502 repo (`Datapath::index_after`, `tests/seam.rs`: twenty-two
  register-then-crossing pairs in both directions held to rung 0,
  `MUTATE_SEAM=1` red on the nine ALU cases; a first version of the
  fix passed a one-sided test and jammed this cartridge's menu, which
  the trace also located). Nothing in the ladder's own oracles had this
  sequence. This is what T0 is for, and it paid on the first cartridge.

**T1: the die runs the console's program. DONE 2026-09-12** (`6502` @
4646f3f: `v6502_sim::recorded::RecordedBus`, `rung0_recorded`,
`run_recorded`, `v6502-pins/examples/replay-recorded`, and
`tests/recorded.rs`; `nes` @ 513bf39 for the two things the die found
in the tool). Usage:

    cargo run --release -p v6502-pins --example replay-recorded -- <name.pins> [half-cycles]

The gates, as run:

- The pin golden, all 289 traces, replays through the recorded bus with
  the loads WITHHELD (every byte after h=0 from the record): identical.
  `MUTATE=1` flips one recorded write and the bus refuses at that
  half-cycle. A record naming no `.stim` is refused (exit 2). Rung 0
  runs at about 33,000 half-cycles a second on a record: two seconds a
  NES frame, as expected.
- The test cartridge: bit-exact from reset through ALL TWELVE frames of
  its record (714,732 half-cycles, 356,095 reads and 1,271 writes held
  to it), past the first poll the gate asked for. Two things had to be
  fixed for that, both in the tool and the cartridge, neither in the
  die: the trace's stimulus lines were written at the frame where a
  level first showed, which is one half-cycle late for the pin crate's
  driver (the die found it at the first NMI); and the cartridge never
  set its stack pointer, which powers on at $BD on the 2A03 die and $FD
  on the 6502 die, so the two parted at the first NMI's push. Every
  real program has `LDX #$FF; TXS`; now so does ours (the pad
  cartridge's prediction for the part moved from 596 to 597 polls over
  600 frames, nines unchanged; the flashcart copy must be re-exported).
- The bench's own cartridge: the first differing half-cycle named, with
  the instruction. Rung 0 agrees for 294,364 half-cycles (frame 5) and
  parts where the first sprite DMA releases the core: the die resumes
  its held fetch of $C096 one cycle before the record does. With every
  RDY rise driven one half-cycle later (`RDY_RISE_SHIFT=1`, an
  experiment knob in the example, not a rule) it agrees for 591,074
  (frame 10) and parts at an NMI that fell in the last cycle of a taken
  `BEQ` at $813F: the die finishes the next instruction (`LDA $20`)
  first, which is the taken-branch interrupt delay the part is known
  for, and the console's rung takes the NMI at once.

So the plan's expected candidates sorted themselves: not decimal mode,
not the unofficial opcodes, but the input sample points, twice, and
both closed the same night:

- The taken-branch delay is now rung 3's rule (`6502` @ 9b3ad9a,
  `tests/branch_interrupt.rs`: an edge at every half-cycle around a
  branch taken on its page, not taken, and taken across a page, NMI and
  IRQ, rung 0 beside rung 3; only the on-page taken branch differs, and
  only for the two edges of its second cycle; `MUTATE_BRANCH=1` red).
- The DMA release phase was the record's RDY being the 2A03 rung's
  account of the hold at the PINS, where the 2A03 die re-runs its held
  read with RDY already high and feeds its core one cycle later; a bare
  6502 released as the pin shows it goes straight on. The console's
  trace now carries RDY as the 2A03 feeds its core (`nes`:
  `CpuStep::core_rdy`, in the record and the stimulus alike; the
  package has no RDY pin), and the knob is an experiment again.

And with rung 3 polling as the die does, the cartridge's menu jammed:
NMI off from frame 9, the main loop waiting on a sprite-0 hit at $8504
that never came, while rung 0 on the new record agreed with it to the
last half-cycle, which put the CPU beyond suspicion. The trace's RAM
dump (`RAM=<path>`) against the record's DMA bytes named it: the 2A03
rung's sprite DMA read through the held core's bus, whose memo answers
the core's quiet re-asks, so every address a DMA had read before came
back as it was THEN. A game that never reads its sprite buffer kept its
first frame's sprites for good; this one's sprite 0 stayed at its
power-on row. Fixed in `2a03` @ 54295cc (`Rung::world_read`;
`tests/stalls.rs`, two DMAs with the page rewritten between, ON A BUS,
because on the rung's own image the wrapper is not in the path and the
case passed before the fix; `MUTATE_DMA_MEMO=1` red). The title screen
now has Mario on the ground where the earlier three-way comparison saw
a stray sprite on the underline: the same bug.

MEASURED 2026-09-12, after all three (`nes` @ 77c9118): the
switch-level 6502 agrees with the console's 300-frame record of the
cartridge over all 17,868,314 half-cycles with no knob (8,843,686
reads and 90,471 writes held to the record, 148,683 reads answered
under RDY low, about 28,500 half-cycles a second). One more half-cycle
had to be learned on the way: the rung feeds its core AFTER the step
that decides a hold, so the level a step records is in force from the
next step and belongs in frame h + 1; written into frame h the die was
held one cycle early at every DMA.

**T2: the stack's instruments, fed a console. DONE 2026-09-13** (`6502`
repository: `v6502_pins::Window` and the `.window` text, `cut_window`,
`rung0_window`, `run_window`, `Bus::half_step`, halfwave's `WINDOW`,
`Machine.fromWindow`, the Halfshot page's and the Trace page's
`?window=`, `tools/check-halfshot.mjs`'s record group,
`web/_window-test.html`). The `LOAD` door became a WINDOW: a piece of a
record with the machine standing at its first half-cycle (the four
planes, the half-cycle, the last fetch, as halfwave's own `STATE` words),
the frames, the inputs in force, and the shadow of memory, one text
file, cut by `replay-recorded --window A B out.window` after rung 0 has
run the record to A. The service stands in one with `WINDOW <name>`, the
wasm machine with `Machine.fromWindow(text)` (one bus enum behind the
one machine, so every page method works), and the pages with
`?window=name`. The bus follows the chip's own half-cycle count through
a hook every other bus ignores, so history, the service and the pages
needed no driver; a rewind inside a window is a restore to its origin
and a run forward, because a record is read and never rolled back.

The gates, as run (MEASURED 2026-09-13):

- A window cut from every golden trace with room for one restores and
  agrees with itself to its end; a flipped window frame is refused
  (`MUTATE=1`). Workspace green with the goldens required.
- The two windows shipped at `6502.tinymachines.ai/windows/` are the
  family's test cartridge's first pad poll and its seventh (`SET 00`,
  `AT 6 08`): 356 half-cycles each, a window ends on a phi2 frame.
- `_window-test.html`: the wasm machine steps the seventh poll's window
  to its end, agrees with the record at every half-cycle, refuses
  nothing, counts eight reads of $4016 whose D0 bits spell $08, and a
  rewind inside the window lands on the frame the forward run showed.
- The Halfshot page's export of both windows validates cold: every
  frame held to the window's record (a flipped byte in the export is
  caught by name), no program, the head segment labelled "cut inside an
  instruction". The export's eight reads of $4016 carry the pad's bits
  on the data bus. Three things the page had to learn: a window's
  frames start at the origin, not 0; only RAM reads back what was
  written (a strobe to $4016 is not a byte); and a seek past the
  window's end used to loop forever.
- halfwave's `WINDOW padpoll6 / STEP 300 / ROWS` returns 300 rows whose
  data column shows the same eight reads and bits, the chip agreeing
  with the record at the end (`differs: null`, `refusal: null`).

**T3: the console's overlays. DONE 2026-09-13** (`nes` @ 5214e36: the
trace writes `<name>.overlay`; `6502`: the window carries the console's
lines, the Halfshot page shows them, `web/_halfshot-window-test.html`
holds them). Decided as T2 showed: the Halfshot page, which already
stood in a window with a strip, a plate and a memory window, gained the
console rather than a page of its own. The console's trace tool writes
its events as text beside the record, one line per event with the
half-cycle as the line's second field (`latch`, `read`, `ppu`, `cart`,
`nmi`, an anchor `dot` every 256 half-cycles of where that half-cycle
falls in the PPU's frame, `alignment` and `picture` with `-` for a
half-cycle); the window cutter copies the lines inside a window without
knowing what they mean, and the page reads them. Under the plate, inside
a window:

- The picture of the frame being drawn through the window (a P6 PPM the
  window names, decoded onto a canvas; the frame index is the one the
  events count, so the pictures are asked for by `FRAMES_PPM=2,8` for
  the polls in frames 2 and 8, not 3 and 9, which the first cut got
  wrong).
- The pad column: the latch in force with its index and the script's
  byte, the reads of $4016 since it, the bit this read returned and its
  bit number, the byte the bits so far spell (bit 0 first), and at the
  eighth read whether it is the latch's byte read back.
- The PPU column: frame, line and dot counted by the alignment from the
  window's anchor (never converted, always counted), the last register
  write with its own frame, line and dot, and the last NMI edge.
- The stack page, $0100 to $01FF from memory as it stood at the frame,
  S marked and the live entries above it emphasised.

The gate, as run (MEASURED 2026-09-13): `_halfshot-window-test.html`
boots the page in an iframe on the seventh poll's window, walks the
eight frames that read $4016, holds each bit to the data bus's D0, and
at the eighth read the byte spelled on the page is the latch's, $08,
and the page says so; the PPU column places the last read at frame 8,
line 243, dot 95 (vertical blank, where the test cartridge's handler
polls); the stack page marks S at $01FC; the picture drawn is frame 8.
Both windows' exports still validate cold.

**T4: against the part.** The same latch index on both sides: the
bridge's log line (latch, byte, clocks) against the events file's
reads per latch; the scope's frame at `TRIG n` against the window's
decoded frame; and the half-cycle of latch n in the trace against the
trigger's sample in the record, which gives the console's CPU
half-cycle for any sample the scope took. This is C2 of the closed
cycle seen from the model's side, and it needs the wiring.

## Decided here

- **Half-cycles, never converted.** The pin contract's rule holds in
  every file this plan adds.
- **The recorded bus refuses; it never fills in.** A read the recording
  does not have at that half-cycle is a stop with a name, not a zero.
- **Rung 0 runs from reset.** No cold start mid-program; the window is
  reached, not jumped to.
- **A trace of a commercial cartridge stays on the workstation.** The
  site shows the family's own cartridges. The bench's Super Mario Bros.
  and Duck Hunt trace lives beside its dump in the ROM store.
