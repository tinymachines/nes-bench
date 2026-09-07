# The head

`headd.py` runs on the Raspberry Pi 4 and puts the bench under one
script: the bridge over USB serial, the reset and power relays on the
Pi's pins, the scope over SCPI on the LAN, and a UDP request port for
the workstation, with the runs served back over HTTP.

```
python3 head/headd.py --bridge /dev/ttyUSB0 --scope <ip>       # the bench
python3 head/headd.py --bridge <pty> --no-gpio --no-scope       # against tools/fake-bridge.py
python3 tools/bench.py <pi> status
python3 tools/bench.py <pi> run script.txt                      # plays it, fetches runs/<stamp>/
python3 tools/bench.py <pi> bridge STATUS
```

Needs Python 3 with pyserial (`python3-serial`) and, on the Pi, gpiozero,
which Raspberry Pi OS ships. The script's words are in
`docs/script.md`. Addresses (the Pi's, the scope's) go on the command
line or in `bench.local.md`, which git ignores.

What has run: the whole loop against `tools/fake-bridge.py` (a script
with MODE, SET, RESET, AT, TRIG and WAIT; the fetched `bridge.log`
diffed against the model's `pad-log` for the same script by
`tools/compare-logs.py`, every latch agreeing). What has not: the
relays (no Pi wired yet) and the scope's arm-and-capture, which uses
the dialect `ntsc-crt/tools/scope-capture.py` proved on the same
DS1054Z but adds the external-trigger single shot, untested until the
scope is back on the LAN with the bridge's trigger line on EXT TRIG.

On the Pi, one command installs the head as a service from this
checkout (packages, the dialout group, the runs directory, a systemd
unit with the addresses in it, enabled and started; re-run after a
pull to restart on new code):

```
git clone https://github.com/tinymachines/nes-bench && cd nes-bench
bash head/setup.sh --bridge /dev/ttyUSB0 --scope <ip>      # or --no-scope
bash head/setup.sh --dry-run --bridge /dev/ttyUSB0 --scope <ip>   # the steps, run none
```

Tested here with `--dry-run` only; the first real run is the bench's.
