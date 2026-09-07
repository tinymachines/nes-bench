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

Nothing here is built yet. Captures and dumps of cartridges are never
committed (`captures/`, `roms/` and `*.nes` are ignored); the family's
own test and bars cartridges are the only ROMs any repository carries.

MIT.
