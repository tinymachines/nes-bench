# B0 report: the sniff, machine side closed, the part's side waiting on the build

Written 2026-09-06. Plan: `docs/bench-plan.md`, first. Nothing here has
touched the part yet: the bridge is not built. What closed is
everything B0 could close on the machine, and one thing B0 was going
to measure on the part turned out to be measurable on the die first,
which changed the model.

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
not only the colours; the public site's boarding runs both and refuses
to board if the mutation is not red. `nes` @ 59d42c8.

## What the die said before the part could

The gate asked for clocks per latch on the part, expecting nine where
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

- Rung 3 of the 6502 (`tinymachines/6502` @ 89ae24f) re-asks its bus
  at every phi2 of a read held by RDY and keeps the last byte, which is
  what DL does; `MUTATE_HELD=1` keeps the first and is red.
- The 2A03's rung (`tinymachines/2a03` @ dbf116b) answers those re-asks
  from a memo while the core is held and lets one through on the
  re-run, unless the alias rule holds; `tests/joypad.rs` holds the
  rung's asks per instruction to the die's /OE1 pulses over two
  cadences, {1: 2820, 2: 6} and {1: 2245, 2: 4}, instruction for
  instruction; `MUTATE_QUIET=1` (five asks per collision) is red.
- The console (`tinymachines/nes` @ 2ec0fc3) logs polls; on the
  polling cartridge with the DMC loop the model predicts nine-read
  polls at 21 of 596 latches over 600 frames, recorded in
  `tests/pad_log.rs`.

So the B0 gate's third bullet, the model's DMC fetch schedule beside
the part's nine-clock polls, now has a prediction with an exception the
documentation does not mention. The part decides.

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
