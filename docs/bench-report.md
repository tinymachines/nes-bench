# Bench report: B0 to B3, machine side closed, the part's side waiting on the build

Begun 2026-09-06 as B0's report and grown into the bench's running
report as B1, B2 and B3 got their tools before the hardware arrived.
Plan: `docs/bench-plan.md`, first. Nothing here has touched the part
yet: the bridge is not built. What closed is everything the four
milestones could close on the machine, each tool with a green run on a
synthesis and a sabotage run that goes red, and one thing B0 was going to
measure on the part turned out to be measurable on the die first,
which changed the model. The sections are in the order they were
written; the part's side of each milestone is the list at the end.

## What exists

- `firmware/bridge/bridge.ino`: the ESP32 sketch. The console's latch
  and clock counted by the pulse-counter peripheral (rising edges of
  OUT0, falling edges of the clock, 50 ns glitch filter, nothing in an
  interrupt), the original pad polled once a millisecond on the
  bridge's own lines, the 74HCT165's eight inputs written between
  polls, and one line per latch on USB serial at 921600:
  `L <latch index> <byte the register held> <clocks the poll took>`.
  Commands: `MODE PASS`, `MODE INJECT`, `SET hh`, `AT n hh`, `TRIG n`,
  `RESET`, `STATUS`. Compiles for a generic ESP32 under arduino-cli
  with the esp32 core 3.3.11 (281 KB). Not yet run on a board.
- `tools/sniff.py`: the serial side, commands then a stream to a file.
- `tools/compare-logs.py`: two logs latch for latch, histograms of
  clocks per poll, the first latch where clocks or bytes differ, and a
  refusal to compare a log with no polls.
- The model's log: `nes-console`'s `pad-log` example prints the same
  line per latch from a ROM and a script of `AT frame hh` lines, and
  `export-testrom pad` / `pad-dmc` write the polling cartridge (a
  strobe and eight reads every NMI, with or without a looping DMC
  sample at the fastest rate).

## Added 2026-09-07: the head, and the script on both sides

`head/headd.py` is the Pi's daemon: one script (`docs/script.md`) played
onto the bridge, the relays and the scope, the run served back. It ran
end to end against `tools/fake-bridge.py`, a stand-in for the protocol
with no part behind it, and the fetched log was diffed against the
model's for the same script by `tools/compare-logs.py`: every latch
agreeing, the scheduled byte landing at exactly its latch on both
sides (the bridge writes it after latch n-1, the model's controller
applies it at the strobe's rise before latch n; `nes` @ a99b4eb,
`tests/pad_log.rs`). The scope half shares scope-capture's proven
dialect and adds the external-trigger single shot, untested: the scope
was off the LAN when this was written. The relays have no Pi wired.

## Added 2026-09-07: the B1 tool, green on the synthesis before any capture

`tools/b1-score.py runs/<stamp> rom.nes` reads the run's script for
its `TRIG n` and the capture's `.toml` for the rate and the trigger's
sample (which the head reads off the scope's own preamble, so no offset
sign convention is trusted), and runs `nes-console`'s `capture-score`
with the script, the latch and the trigger: the model plays the same
`SET` and `AT` lines to the first frame that completes after latch n,
the record is sliced from the trigger's sample on so the recovery's
first full frame is that frame on the part, and every flat region is
scored through the roundtrip with N6's tolerances. The recovery needs
two full frames after the slice, so the head sets the horizontal offset
to put the trigger early in the record; whether the sign is right is
the first real capture's to say, and the `.toml` will say it.

Its own green run (`SYNTH_TRIGGER=1`): six frames synthesised through
the card model, the fourth scored, the synthesis sliced from inside the
third as a trigger placed there would be, 13 of 13 regions on the bars
cartridge at every frame count tried across its luma-row step.
`MUTATE_TRIGGER=1` slices one frame late and is 1 of 13 at the step
(frames 122), which is what shows the frame selection is checked and
not only the colours; the public site runs both again before it
publishes, and refuses when the sabotage is not red. `nes` @ 59d42c8.

## Added 2026-09-07: the B2 classifier, green on its own synthesis

`tools/b2-align.py` reads the console's CPU-to-PPU alignment off a
three-channel capture (the master clock, M2, ALE) and, with `sweep`,
plays a power-on script through the head N times and prints the
histogram. Its two facts were measured on the dies first: the 2A03's
M2 falls on the very half-step its clk0 falls, a phi1's start, and
rises three early (high 15 of 24, the part's documented 62.5 percent
duty; `v2a03-sim`'s m2-phase, `2a03` @ 51c9b4a), and the 2C02's ALE
rises on the very half-step pclk0 rises, a dot's start, every other dot
while rendering (`v2c02-sim`'s ale-phase, 2,508 of 2,508 rises, `2c02`
@ c3a4b9b). So the offset from an ALE rise to the next M2 fall, in
half-steps on the console's own master clock as the ruler, is the
model's cpu_phase minus ppu_phase, and mod 8 it is the class; the pair
the model runs in, (4, 3), is class 1. A capture whose offsets do not
sit on half-steps, or whose class is not clean, is refused, not
classified.

Its check (`selftest`): the three channels synthesised for 72
alignments at the head's three-channel rate with the measured pin
offsets, every one read back as its class; the synthesised ALE shifted
one half-step (MUTATE) moves the class on all 24. Then the whole path
through the head: `tools/fake-scope.py` answers the head's SCPI with
those synthesised records, a B2 script (power off, arm three channels
on ALE's first rise, power on, capture) played three times by `sweep`,
each run fetched and classified as the alignment the fake was given.
The head's ARM took a channel list, a trigger source, a timebase and a
depth for it (the DS1054Z holds 6 M points at most with three channels,
so B2's window is 6 ms at 1.2 M; B1's stays 60 ms at 12 M on one).

What only the bench can say: whether the part's histogram over a
hundred power-ons is flat over its classes or prefers some, which is
B2's first check, and whether the model's (4, 3) is among them.

## Added 2026-09-07: the B3 tools, a planted divergence found

`tools/b3.py` is B3 in four verbs. `record` turns a run's bridge log
(MODE PASS, a hand on the original pad) into a script: MODE INJECT, SET
the first byte, an AT at every change; the firmware's schedule grew to
two thousand entries for it. `replay` plays that script on the part
once per latch named, each replay from RESET with one capture
triggered at its latch, and scores every capture against the model's
frame at that latch through b1-score; one capture per run, because
reading a record takes seconds while the console runs on, and the arm
comes before the trigger in the script because arming is seconds of
SCPI and a trigger set first can fire unheard, both found here. `agree`
sets two replays' captures at the same latches against each other, the
part against itself, region for region under B1's tolerances. `bisect`
finds the first latch at which a capture disagrees with the model,
assuming divergence is monotone, in about log2 of the span replays.

To test it without a part, `nes-console`'s polling cartridge got a
variant, `pad-paint`, that colours its band with the byte it polled,
and `capture-score` writes its synthesis out as a record with the
trigger's sample beside it (`SYNTH_OUT`); `tools/fake-scope.py --video`
serves that synthesis, at the latch the fake bridge triggered at, under
the run's own script with `--diverge-at N hh` appended, so the "part"
plays a different byte from latch N on. With the divergence planted at
latch 200: replays at 100 and 400 agree and disagree with the model as
they should, two replays agree with each other at both, and `bisect`
over 0..1024 names latch 200 in eleven replays, latch 199 agreeing.
`nes` @ e1839eb.

One bug found by that test and fixed: the synthesis had been written
out after its own trigger slice, with the trigger's sample computed
from the shortened record, so a reader slicing at that sample landed
two frames late, and the bisection named 198. The written record now
recovers the same frame as the in-process path, anchor line for anchor
line.

## Added 2026-09-07: the electronics review's sheets, and what they changed

The bench's electronics review returned four schematics and a build
document (`docs/bench-build-v1-v2.md`, `bench-v1.svg`, `bench-v2.svg`,
`logical-timing.svg`, `pad-adapter.svg`, drawn by
`tools/draw-schematics.py`), with a note of what its own double-check
had amended (the LM1881's pin labels, the relay's supply on the Pi's
rail, an authored width, a build step that contradicted itself, a
decoupling count). Taken in as they came, with two things added so
they cannot drift from the rest: `tools/check-sheets.py` holds the v1
sheet's every C6 pin to the wiring tables and the committed SVGs to
the generator, and the build document embeds the sheets.

One firmware change the timing sheet made visible went into
`bridge.ino` the same day: the 165 loads while OUT0 is high, and the
eight register pins were being written one at a time, so a poll could
latch a byte half old and half new. They are now one store to the GPIO
output register, made only when OUT0 reads low before and after and
deferred to the next loop otherwise; the loop reads the counters and
logs the latch before it writes; and `MUTATE ON` swaps the two
counters' lines so B0's sabotage is a line in a script. The fake
bridge does the same. Compiles for the C6 and the classic ESP32; not
yet run on a board.

v2 (atomic bytes over SPI, a second port, an LM1881 giving every latch
its field and line) and the pad adapter are in the plan as what comes
after the four milestones, with the condition that earns each.

## Added 2026-09-07: the head's capture path on the real instrument

The scope moved to a new network and was missing for a day, which
turned out to be an Ethernet cable that was not seated. Its address
lives in `bench.local.md`, ignored, as the repository rule requires.
With it back, the head's `Scope` class met a real instrument for the
first time. Everything below ran through `head/headd.py` itself, not a
transcription of it, against a DS1054Z on firmware 00.04.05.SP2, with
the front panel saved before the first command and restored after the
last, because the scope belongs to another experiment.

What held, in the order the class does it: the connect and the identify;
`save_setup` at 2,085 bytes and the restore that put the timebase and
the sweep back as found; `arm` with one channel at 5 ms/div and 12
Mpoint, including the memory-depth-only-takes-while-running workaround,
which the instrument confirmed on readback; the single shot reaching
WAIT and then STOP; and `read_record`'s chunked raw read of the whole
record, 12 million points in 27.9 seconds, about 0.43 Msample/s over
TCP, with the `.toml` written beside it.

**The horizontal offset sign is settled, and it was already right.**
The docstring used to say the convention was not trusted and to flip it
if the first real capture put the trigger late. It puts the trigger
early. Armed as above and fired with `:TFORce`, the preamble reports
xorigin -0.028 s at 8 ns per sample, so a positive `MAIN:OFFSet` of four
divisions leaves this:

| | |
|---|---|
| record | 12,000,000 points, 96.0 ms at 125 MSa/s |
| trigger sample | 3,500,000, 29.2 percent in |
| record after the trigger | 68.0 ms, 4.09 NES frames |
| B1's requirement | 2 full frames |

Nothing downstream depends on the sign in any case, because the
trigger's place is read out of the preamble rather than assumed, but
the four divisions are now known to clear B1's recovery requirement
with a frame to spare rather than by hope.

**The capture also re-confirms the timebase, which was not the point of
it.** The probe was still on the console's composite video and the
console was running, so the record carries 1,512 sync pulses at a
median width of 4.664 microseconds, and the colour subcarrier shows up
as a 0.280 microsecond period. A least-squares fit of the sync times
over all 1,512 pulses, residual 53.9 ns, gives a line period against
which two references disagree:

| reference | line rate | this capture reads |
|---|---|---|
| the NES's own master clock, 341 dots | 15745.80 Hz | +5.3 ppm |
| broadcast NTSC | 15734.26 Hz | +739 ppm |

That is the `ntsc-crt` finding again, arrived at from a cold start on a
different network six days later: the console is roughly 733 ppm off
broadcast by construction, and the scope is not the thing that is
wrong. The earlier work put the scope's own error at about -7 ppm; this
capture puts the pair of scope and console within 6 ppm of each other,
which a cheap crystal covers on its own. Anything that scores this
console's video against the broadcast line rate will be wrong by three
quarters of a part per thousand and will look like a timebase fault.

Not closed by any of this: the external trigger has still never been
fired by anything but `:TFORce`, because the bridge that raises it does
not exist yet. What is proven is the arm, the wait, the read and the
record's geometry, which is everything around the trigger.

## What the die said before the part could

B0's check asked for clocks per latch on the part, expecting nine where
a DMC fetch lands on a poll's read. That is a question the switch-level
2A03 can answer, so it was asked first (`2a03`'s
`joy-clock-probe`, `docs/n3-report.md` there):

- On the read a DMC fetch lands on, /OE1 falls with the read, stays low
  through the halt cycles (one continuous pulse), rises during the
  fetch's own read of the sample, and falls again when the core
  re-runs the read with RDY high. Two rising edges: a 4021 shifts
  twice and the core takes the bit after the one it asked for. The
  halt cycles do not pulse it.
- Unless the sample's address has the port's low five bits ($xx16 for
  $4016, $xx17 for $4017): twenty aliases over two loop cadences kept
  /OE1 low through the fetch, and the pad is clocked once. A plain read
  of an alias does not assert the strobe and a fetch from one with the
  core idle does not either, so the strobe's high address bits come
  from the core's held address and its low five from the pins the DMA
  drives. A fact about the die's decoder.

Three changes followed, each with a test that fails without it:

- The 6502's fast core (`tinymachines/6502` @ 89ae24f) re-asks its bus
  at every phi2 of a read held by RDY and keeps the last byte, which is
  what DL does; `MUTATE_HELD=1` keeps the first and is red.
- The 2A03's fast chip (`tinymachines/2a03` @ dbf116b) answers those re-asks
  from a memo while the core is held and lets one through on the
  re-run, unless the alias rule holds; `tests/joypad.rs` holds the
  fast chip's asks per instruction to the die's /OE1 pulses over two
  cadences, {1: 2820, 2: 6} and {1: 2245, 2: 4}, instruction for
  instruction; `MUTATE_QUIET=1` (five asks per collision) is red.
- The console (`tinymachines/nes` @ 2ec0fc3) logs polls; on the
  polling cartridge with the DMC loop the model predicts nine-read
  polls at 21 of 596 latches over 600 frames, recorded in
  `tests/pad_log.rs`.

So the third of B0's checks, the model's DMC fetch schedule beside
the part's nine-clock polls, now has a prediction with an exception the
documentation does not mention. The part decides.

## Added 2026-09-08: the UNO bridge, and what the compiler decided

The bench's electronics review returned a fifth sheet, `bench-v1b.svg`,
after the parts arrived: the bridge on an Arduino UNO with everything
at 5 V, because the 74HC parts on the shelf need a 3.5 V high that a
3.3 V part does not give. It supersedes v1 as the thing to build first.
It is taken in whole, with the generator that draws it, and
`tools/check-sheets.py` now holds its every UNO pin to the document's
own table exactly as it already held v1's to `docs/wiring.md`. Three
mutations were run against that check and all three are red: a pin
moved in the document, a row deleted from it, and a sheet edited away
from what the generator writes.

**The firmware exists and compiles**: `firmware/bridge-uno/bridge-uno.ino`
for `arduino:avr:uno`, 8,018 bytes of flash and 1,521 of SRAM. Writing
it is what turned the sheet into a set of decisions, and four of them
were the document's plan being wrong rather than incomplete.

| what the note planned | what the part allows |
|---|---|
| `SPI.transfer(b)` | `SPI.transfer(~b)`: pressed is LOW |
| a `micros()` field on the L line | four fields, because three tools require exactly four |
| MUTATE as a jumper on D2 and D5 plus a config pin | PCINT21 on the latch line, in software |
| the C6's 2048-entry schedule | 128, which is what 2 KB of SRAM holds |
| `uint64_t` counters and `%llu` | `uint32_t` and `%lu`; avr-libc has no 64-bit printf |

The schedule is the one that mattered, and it is worth stating as a
trap rather than a number. A record with more changes of byte than the
bridge can hold does not fail. It replays a **different input history**
while every L line looks healthy, which is exactly the shape of a false
finding about the console. So the limit is read out of each firmware's
own source, never typed, and refused in three places: `tools/b3.py
record` names it before a run is attempted, `tools/fake-bridge.py`
enforces the same bound so the failure can be rehearsed with no
hardware, and the head raises it as a run error the moment the bridge
answers `# schedule full`. Proven end to end against the fakes: a
120-entry script runs to `done`, a 200-entry script draws 72 refusals
and stops on the line that caused it.

**Two drawings were also wrong, and the corrections came from outside
the review.** The relay modules on hand are 5 V coil parts with opto
inputs, so the v1 sheet's 3.3 V rail was wrong for them; both sheets now
show the Pi's 5 V pin and an active-low input. And both sheets put the
console's video on the scope's CH1, when it is on CH3: that is where
`scope-capture.py` has always defaulted, where the probe was measured
sitting on 2026-09-07, and CH1 is the channel B2's alignment classifier
wants for the master clock. A drawing that claims a channel another tool
needs is the kind of thing that costs an afternoon at the bench.

Still true: nothing here has met the console. What is proven is that the
firmware compiles, the protocol is unchanged, the checks can fail, and
the one new hardware limit cannot silently corrupt a run.

## Added 2026-09-08: the bring-up tool, and the notebook it writes

The parts are on the desk, so the next thing is wiring, and wiring is
where a bench either becomes an instrument or becomes a week of
plausible wrong answers. `tools/bringup.py` is the procedure: fourteen
steps in v1b's build order, each printing what to wire, waiting, and
then **checking something**. It never asks whether a step worked. It
measures with the scope, reads the bridge's own log, or asks for a meter
reading and holds it to a range.

Two of the steps are the ones that matter, and both replace authored
numbers with measured ones:

- **2.1** puts the scope on an original pad's port while a game runs and
  measures the latch pulse width, the clock pulse width, the interval
  between clocks and the polls per second. Those four numbers are marked
  authored throughout `wiring.md` and the timing sheet, and this is what
  retires them.
- **5.1** is B0's first gate arriving early: with the bridge joined and
  a game polling, every poll must carry eight clocks. It listens to the
  bridge for twenty seconds and prints the histogram.

A failed step stops the run, because the next step assumes the last one.
One check refuses rather than reports: if the console's supply pin does
not read about 5 V, the tool will not go on, because a wrong harness map
and a 5 V line on the wrong pin are the same mistake and one of them
costs a part.

**It was rehearsed before it met anything.** Step 0.1 ran against the
real scope. The bridge steps ran against `tools/fake-bridge.py`, which
speaks the same protocol, and the pad check was proven in both
directions: it fails against a stand-in holding nothing and passes
against one holding every button. The supply guard was proven the same
way, with a bad reading and a good one. The rehearsal found a real
defect that would have appeared first on hardware: the command reader
drained the port "until nothing is waiting", which never returns while a
console is polling sixty times a second and the bridge is streaming a
line per poll. It is time-bounded now.

Rehearsal attempts are marked in the log and the notebook excludes them
from the record while saying they happened, because a rehearsal against
a fake is tool development and not bench work.

The record is `docs/lab-notebook.md`, generated from
`docs/lab-log.jsonl`. It shows every attempt, not the successful ones: a
step that took three tries is the part of a notebook worth keeping. It
embeds a photograph once the file is in `docs/lab/` and names it as
pending until then, so it carries no broken images and forgets nothing.

## Added 2026-09-08: the first sitting held, and a counter that counted nothing

The bench has a home base: a Raspberry Pi 4 with the Uno plugged into
it. `head/serial-bridge.py` puts that serial port on the LAN and nothing
is installed on the Pi to do it, because that machine resolves DNS
through DNSCrypt resolvers on another subnet and can reach neither apt
nor GitHub from here. One TCP port serves both the tools, through
pyserial's `socket://`, and avrdude, through `net:`, so the firmware was
compiled on the workstation and flashed across the network, verified at
7,996 bytes.

**Sitting 1 holds.** The scope answers, the port opens, and the sketch
replies to STATUS. That is the first bench work in the notebook that is
not a rehearsal.

**It also produced the first finding, and it came from reading a reply
rather than from a check.** Step 0.3's STATUS line said `latch 482` with
nothing wired to the board at all. Timer1 is a hardware counter and asks
no questions: its input pin was floating, and it took **3,647 latches in
three seconds**, about 1.2 kHz of noise. Nothing failed, and that is the
point. B0's whole first gate is clocks per latch, `AT n hh` is keyed by
latch index, and B3's replay is a latch index throughout. A run begun
before the console was powered would have carried an index that meant
nothing, and every number downstream of it would have looked like a
finding about the part.

The fix is one word twice: the two console-side inputs are
`INPUT_PULLUP` rather than `INPUT`. The console drives both lines hard
when it is on, so a 30 kilohm internal pull-up costs it nothing, and
when it is off or unplugged the pins now sit at a defined level instead
of picking up the room. Measured before and after on the same board:
3,647 latches in three seconds, then **0 in ten**.

Worth keeping for its own sake: this is the shape the plan expects the
bench to have. Not a check going red, but an instrument reporting a
number that had no business being what it was.

## What B0 still needs from the bench

In the plan's order, once the bridge is built per `docs/wiring.md` and
its "measure first" list is done:

1. Clocks per latch on a game without DMC: 8 on every poll over a
   minute; `tools/sniff.py` then `tools/compare-logs.py` against
   `pad-log` on the same cartridge (a dump from the shelf).
2. Latches per second against the scope's field count.
3. Polls per frame beside the model's, by latch index.
4. A game with DMC playing: the nines by latch index against the
   model's, which is where the alias rule is either seen or not.
5. MUTATE on the bridge: the clock counter fed the latch line fails
   the 8-per-latch check.

None of it can be faked here, and the report says so.
