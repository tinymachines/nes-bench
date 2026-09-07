# nes-bench

The part and the model under identical inputs, compared at the scope.

The console family (`6502`, `2a03`, `2c02`, `ntsc-crt`, `nes-bus`, `nes`)
is a switch-level NES that runs cartridges. Everything it does not yet
know about the part waits on a bench: a scope on the console's video
and audio, an original pad, a hand pressing reset. This repository is
the bench made scriptable, so those items close unattended and repeat.

The bridge sits inline between the console's controller port and an
original pad. A shift register on the bridge is the pad the console
clocks; an ESP32 sets its eight inputs between polls and counts the
console's latch and clock pulses in hardware; a Raspberry Pi 4 on the
LAN is the head, taking scripts from the workstation, driving the
reset and power relays, and triggering the scope. Nothing on a
microcontroller is in the nanosecond path: that is the shift
register's job, as it is in the pad.

- `docs/bench-plan.md`: the milestones B0 to B3 with their gates,
  written before any firmware.
- `docs/wiring.md`: the pin table to build from, and the measurements
  to make with a meter before the console is powered through it.

- `docs/bench-report.md`: the bench's running report, B0 to B3 on the
  machine side (the firmware compiles, the head and every tool run
  against fakes with red mutations, the model logs polls) and the
  part's side waiting on the build. The die answered B0's DMC question
  first and the model changed for it.
- `docs/bench.svg`: the bench as one drawing, the loop above and the
  bridge's chips with every pin below. Derived: `tools/draw-bench.py`
  reads the pin tables in `docs/wiring.md`, so the drawing cannot
  disagree with the document (`--check` refuses a stale one).
- `firmware/bridge/`: the ESP32 sketch (arduino-cli, esp32 core 3.x;
  the bench's board is an ESP32-C6-DevKitC-1).
- `head/`: the Pi's daemon, the bench under one script (UDP in, the
  bridge over serial, relays, the scope over SCPI, runs served back over
  HTTP); `docs/script.md` is the script's words, shared with the model.
- `tools/`: `bench.py` (the workstation's client), `b1-score.py` (a
  run's triggered capture against the model's frame at the same poll,
  through the roundtrip), `b2-align.py` (the alignment class off a
  three-channel capture, the histogram over power-ons, its self-test),
  `b3.py` (record a run as a script, replay it with captures, the part
  against itself, bisect to the first divergent latch),
  `fake-scope.py` (the head's SCPI subset with synthesised records, and
  with `--video` the model's own frames at the bridge's trigger latch,
  a divergence plantable),
  `sniff.py` (the
  bridge over serial alone), `compare-logs.py` (two poll logs, latch for
  latch), `fake-bridge.py` (the protocol with no part behind it, for
  running the head on a box without an ESP32), `draw-bench.py`.

The bridge is not built yet. Captures and dumps of cartridges are never
committed (`captures/`, `roms/` and `*.nes` are ignored); the family's
own test and bars cartridges are the only ROMs any repository carries.

MIT.
