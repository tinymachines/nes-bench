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

**T1: the die runs the console's program.** `RecordedBus` in
`v6502-sim`, and `replay-recorded` in `v6502-pins`: a `.pins` and
`.stim` in, rung 0 run under them, its frames compared field by field
with the console's by the comparison the crate already has. Gate:
bit-exact at the pins from reset to the title screen's first poll on
the test cartridge; on the bench's own cartridge the first differing
half-cycle named, with the instruction that was executing. Expected
candidates, to be confirmed or cleared rather than assumed: decimal
mode, which the 2A03 core lacks and the die has; the unofficial
opcodes; the RDY sample points around sprite DMA. MUTATE: one data bit
flipped in the recording must be reported at its half-cycle, and a
recording with its `.stim` withheld must refuse to run.

**T2: the stack's instruments, fed a console.** A `LOAD` door in
`halfwave` and in the site's wasm machine that takes a recorded bus
and a stimulus instead of a program; the Trace page's `?trace=` and the
Halfshot page's, so a window of a console run is shown by the pages as
they are; `check-halfshot.mjs` on an export of it. Gate: the halfshot
of the test cartridge's first poll validates cold, and its rows show
the pad's eight bits on the data bus at the eight reads of $4016.

**T3: the console's overlays.** What the 6502 pages have no column
for: the stack page ($0100 to $01FF from the shadow RAM, with S), the
pad column (latch index, bit number, the byte so far), the PPU column
(register, dot, scanline) and the decoded frame of the window beside
the strip. Either a console trace page in the 6502 site or the Trace
page reading the events file; decided when T2 shows which is less
code. Gate: the byte read back off the bus bits at latch n equals the
script's byte at n, on the page.

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
