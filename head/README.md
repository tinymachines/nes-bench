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

## The Arduino on the Pi, reached from the workstation

Added 2026-09-08, when the bench got a Raspberry Pi as its home base
with the Uno plugged into it.

`serial-bridge.py` runs on the Pi and puts that serial port on the LAN.
It is standard library only. Since 2026-09-11 it runs as a real systemd
unit from the Pi's own checkout of this repository (`~/nes-bench`),
enabled, so it is there after a reboot:

```
bash head/serial-bridge-install.sh            # on the Pi, from the checkout
```

which writes `/etc/systemd/system/serial-bridge.service` (port
`/dev/ttyACM0`, 115200, listening on 6545), enables and starts it. Re-run
after a `git pull` to restart on new code.

Before that it was a transient `systemd-run` unit started by hand from a
copy of the script in the home directory, twice lost: once because the
copy was in `/tmp` and a reboot took it, once because the transient unit
does not survive a reboot either. A **user** unit was tried before that
and is the wrong choice: without lingering enabled the user manager
stops when the last ssh session closes and takes the service with it,
which presents as a bridge that works while you are watching and is
gone when you come back.

Then, from the workstation, one port serves both jobs:

```
python3 tools/bringup.py --session 1 --bridge socket://<pi>:6545

avrdude -c arduino -p atmega328p -P net:<pi>:6545 -b 115200 -D \
        -U flash:w:bridge-uno.ino.hex:i
```

pyserial understands `socket://` with no extra code, and avrdude 8 takes
`net:`. It complains three times about `ioctl("TIOCMGET")` because a
socket is not a tty and it cannot toggle DTR; that is harmless, because
the bridge opens the serial port as each client connects and closes it
when they go, so every connection gets the same reset a local open would
have given it. Holding the port open across connections would work for
the tools and quietly fail for flashing.

**The Pi's clock was months out until 2026-09-11**, because its resolver
still pointed at a gateway network that no longer existed, so it could
reach neither a time server nor apt nor GitHub (`scripts/pi-net-cleanup.sh`
is what fixed it, and says what it found). It syncs now. The rule that
came out of that period still holds: every timestamp in the log is
written by `tools/bringup.py` on the workstation, and the scope's own
record carries its time, so nothing here depends on the Pi's clock.

This split is the one the plan describes: the Pi holds the hardware, the
workstation holds the model, the log and the record.
