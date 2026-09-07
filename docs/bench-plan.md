# Bench plan: the part and the model under identical inputs

Written 2026-09-06, before any firmware. The console sketch's machine
milestones N0 to N8 are closed; every open item in their reports is a
bench or desk item. This plan makes the bench a machine the
workstation drives, so those items close unattended, repeat, and
become gates rather than sessions.

Gear on hand: an NES-001 with original pads and cartridges, a Rigol
DS1054Z on the LAN with one channel on the console's video (the
captures of 2026-09-02 came from it), an Open Source Cartridge Reader
for dumping the cartridges, ESP32 boards, Raspberry Pi 4s, relays.

## The loop

The console learns everything it ever learns from a hand through two
lines on the controller port: a latch pulse, then eight clock pulses
that shift eight bits out of a 4021 in the pad. The model's controller
(`nes-glue::controller`) is authored from exactly that: the 4021 loads
while OUT0 is high, its fall latches the buttons, each read of $4016
clocks one bit out, A first. So an input history is a sequence of
bytes indexed by latch count since reset, and it means the same thing
to the part and to the model.

The bridge sits between the console's port and the pad:

- **Sniff.** Count latches since reset and clocks per latch in
  hardware; log the byte the shift register held at each latch.
- **Inject.** Hold a scripted byte, keyed by latch index, instead of
  the pad's.
- **Trigger.** Raise a line at a chosen latch index for the scope's
  external trigger, so a capture lands on a known frame of a known
  input history.

Two relays, reset and power, put the whole session under the script.
The head is a Raspberry Pi 4 on the LAN: it takes scripts from the
workstation, drives the bridge over USB serial, drives the relays from
its own pins, and talks SCPI to the scope. The workstation runs the
model on the same script and compares.

## Why a shift register, not software

A clock pulse on the port is a few hundred nanoseconds wide and the
next bit has to be on the data line before the next read, about seven
microseconds later. A 74HCT165 does that in tens of nanoseconds and
never misses; an ESP32 interrupt has two to three microseconds of
latency under its RTOS and would mostly make it. An occasional wrong
bit would look exactly like a finding about the part. So the register
is the pad, the console clocks it as it clocks a 4021, and the ESP32
only writes the register's eight inputs between polls and counts pulses
with its pulse-counter peripheral, which needs no CPU in the path.

The original pad plugs into the bridge, not the console. The ESP32
polls it on its own latch and clock, at a kilohertz, with the pad
powered at 3.3 V so its 4021 speaks 3.3 V logic, and copies the state
into the register. A press reaches the console within a millisecond,
and what the console read on each poll is by construction what the
register held.

## Milestones

Each closes on a gate stated here, before the code exists. Tolerances
are stated with the gate, and a gate that passes without the thing it
gates is a broken gate (MUTATE, as everywhere in the family).

### B0: the sniff

The bridge in pass mode, a game cartridge in the console, a hand on
the original pad. The log is one line per latch: latch index, the
byte, clocks in the interval.

Gate:
- Clocks per latch on a game without DMC: 8 on every poll over a
  minute of play, the count of other values printed and zero.
- Latch rate against the frame rate: the latch count over a scoped
  minute against the field count on the video channel, on a game that
  polls once a frame; the ratio 1 within the count's own resolution.
- The same game on the model, its $4016 strobe falls counted per
  frame: the same polls per frame as the part, printed side by side.
- On a game with DMC playing: the polls that counted 9 clocks, listed
  by latch index, beside the model's DMC fetch schedule on the same
  input history (the record replayed, B3's mechanism used early). The
  agreement is the measurement; a disagreement is a finding about
  either.
- MUTATE: the bridge's clock counter fed the latch line must fail the
  8-per-latch check.

### B1: inject

A script: reset, then bytes by latch index, a trigger at latch T. The
part runs it through the bridge; the model runs it through
`set_pad` at the same polls. The scope, triggered at T on EXT TRIG,
captures the frame; `ntsc-crt`'s recovery reads it back; the model's
frame at the same poll is rendered through the same chain (the N6
roundtrip, which closed on the bars cartridge 13 of 13 regions at all
four luma rows).

Gate:
- The bars cartridge first, terminated: the N6 gate's regions and
  tolerances, on the part, which is the bench item N6 left open and
  the answer to whether the +28% saturation of the untriggered
  captures was the probe or the DAC.
- Then a game: the recovered frame at T against the model's, scored
  the way N6 scores (luma, hue and saturation per region over the
  frame's flat regions, the tolerances N6's report states). The first
  region that fails, named.
- Reset to first latch: the latch index of the first poll after the
  reset relay releases, on the part over 20 resets, against the
  model's; the spread recorded.
- MUTATE: the script shifted by one latch on the model only must fail
  the frame comparison on a game whose picture depends on the input.

### B2: relays and the unattended items

The reset and power relays under the script; the scope's remaining
channels on the master clock, M2 and ALE.

Gate:
- Alignment over power-ons: 100 scripted power-ons, the CPU phase
  against the master clock read off the capture each time, the
  histogram over the four (or more) alignments printed. The model's
  `Alignment::MEASURED` (cpu_phase 4, ppu_phase 3) was one
  measurement; this is the distribution, and whether the console has
  a preferred alignment is the finding.
- The reset chain: the hold from the relay's release to the first
  fetch, on the capture, replacing the labelled placeholder in
  `nes-glue`.
- AUDIO_OUT under the mixer ROMs (the N7 item) with the scope's spare
  channel on the audio jack, scored against the model's stage.
- Not here: the DMC address register under a sprite-DMA collision
  needs an address bus, sixteen channels; it stays a logic-analyser
  item and says so.
- MUTATE: the alignment classifier fed a capture with the master
  clock channel shifted by one period must move the histogram.

### B3: record and replay

A human run on the original pad, logged by B0, replayed by B1 on the
part and on the model. The part replayed against its own recording is
the determinism check on the part; the model against the part is the
gate.

Gate:
- Part against part: two replays of one record, captures triggered at
  the same K latch indices, agree region for region under the B1
  tolerances. A game that does not (one that seeds from uninitialised
  RAM or from frame timing) is recorded as such, by name.
- Model against part: the first latch index at which a triggered
  capture and the model's frame disagree, located by bisection over
  the trigger index, and named. A run that never disagrees over its
  length is the result the family exists to produce.

## The pieces, and where they live

- `firmware/`: the ESP32 sketch. A line protocol over USB serial, in
  the shape of `halfwave`'s: `MODE PASS` / `MODE INJECT`, `SET hh` (the
  byte to hold now), `AT n hh` (the byte to hold from latch n), `TRIG
  n`, `RESET` (zero the counters), and a stream of `L n hh c` lines,
  one per latch. Text, so the daemon and a terminal read the same
  thing.
- `head/`: the Pi's daemon. Takes a script over UDP from the
  workstation, plays it onto the bridge and the relays, arms and reads
  the scope over SCPI, and returns the log and the capture. The Pi's
  address and the scope's live in `bench.local.md`, ignored, never in
  a commit.
- `tools/`: the workstation side. The script format, the model runner
  (the `nes` console on the same script, its frames rendered through
  `ntsc-crt`), the comparison, and the checks each gate names.

## What this closes, and what it does not

Closes, from the family's reports: N5's gate 3 (a real cartridge, now
dumped from the shelf), N6's terminated bars capture and the probe
versus DAC question, N7's audio under the mixer ROMs, N8's pad in
hand, the alignment over power-ons, the reset chain's hold. Adds the
DMC double-clock on the joypad read as a measurement the model
predicts.

Does not close: the DMC address register under a collision (needs the
address bus), the shell on a real screen (a desk item, not a bench
one), and anything about the PPU's internals the video signal does
not carry.
