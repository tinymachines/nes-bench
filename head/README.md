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

What has run: the whole loop against `tools/fake-bridge.py`, and since
2026-09-18 the whole loop on the bench: the head as a unit on the Pi,
`exercise/e2-title.txt` played twice with the reset from GPIO17, the
trigger at latch 300 on CH1 (the DS1054Z has no EXT input; `ARM` on
`EXT` is refused by name) and a two-channel 12 M point capture read off
the scope in about a minute, during which the head answers no request
(`bench.py run` waits through it). The account is in
`docs/exercise.md`, and, once the console's switch was off, `POWER ON`
and `POWER OFF` from a head script: the console silent with the relay
open, 713 polls in the 12 s it was on, silent again after (run
`20260918-004151`). Every word in `docs/script.md` has now run on the
part.

On the Pi, one command installs the head as a service from this
checkout (packages, the dialout group, the runs directory, a systemd
unit with the addresses in it, enabled and started; re-run after a
pull to restart on new code):

```
git clone https://github.com/tinymachines/nes-bench && cd nes-bench
bash head/setup.sh --bridge /dev/nes-bridge --baud 115200 --scope <ip>   # the UNO bridge; or --no-scope
bash head/setup.sh --dry-run --bridge /dev/nes-bridge --baud 115200 --scope <ip>   # the steps, run none
```

Installed for real on 2026-09-18. `--baud` is the firmware's: the UNO
bridge v1b talks at 115200, the ESP32 sheet at 921600, which is
`headd.py`'s default. The unit `Conflicts=serial-bridge.service`, so
starting the head stops the serial bridge and `sudo systemctl start
serial-bridge` (for `bringup.py` or `bench-check.py` over port 6545)
stops the head; `sudo systemctl start nes-bench-head` takes the port
back. When the head stops, `ExecStopPost` puts GPIO17 and GPIO27 back
low with pinctrl (reset released, the console off), because gpiozero
leaves the pins as inputs on exit and a floating relay input is a
console that may power itself.

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

## Eyes: the camera and the composite grabber

Two capture devices are on the Pi as of 2026-09-11: a Logitech QuickCam
Pro 9000 on `/dev/video0` (a frame with `v4l2-ctl --stream-to`, or
`ffmpeg -f v4l2`), and a Roxio Video Capture USB (`/dev/video2` when this
was written; the stable name is `/dev/v4l/by-id/usb-1b80_Roxio_Video_Capture_USB_*-video-index0`,
and the tools use it), which
takes the console's composite video and needs the driver in
`roxio-em28xx/` (its README has the story, the recipe and the limit:
400 of 480 lines). A C-Media USB sound card is ALSA card 3 for audio.
Neither is a head verb yet; that is the next step once the camera is
aimed at the board. `tools/eyes.py pair` and `compare` put the grabber
beside the scope: the same composite recorded both ways, decoded both
ways, and scored on the console's pixel grid.

## The eye on the board (added 2026-09-13)

A Logitech BRIO on an arm over the breadboard, on the Pi's USB 2 hub
(so 1080p, not the 4K it can do on USB 3), at
`/dev/v4l/by-id/usb-046d_Logitech_BRIO_*-video-index0`. Plugging it in
moved the grabber from `/dev/video2` to `/dev/video0`, which is why every
tool now names a device by its by-id path. `tools/eye.py` on the
workstation drives it over ssh: `grab NAME [--preset board|column|chips]`
applies the settings (all UVC controls through `v4l2-ctl`), lets the
sensor settle, keeps one frame as `captures/NAME.jpg` and writes every
control as the camera reported it back into `captures/NAME.toml`;
`sweep NAME` steps the lens and scores the chip column's sharpness;
`show` prints the controls. The measured defaults (the tool's header):
focus 25 manual, exposure 333 manual at gain 0, auto white balance
(about 3200 K under the bench light), zoom 100 for the whole board,
160 with one degree of pan for the chip column, 300 for one chip.

Both eyes also run on a timer. `scripts/grab.sh board|screen|all` on the
Pi files one frame of each under `~/captures/YYYY/MM/DD/<stamp>_<type>.jpg`
(the board frame the way the `board` preset takes it, the screen frame
off the grabber, and since the same afternoon a `side` frame from the
second eye, a QuickCam Pro 9000 set low on the console side looking
across the board, which shows what stands proud of it: housings,
headers, which row a lead is in), one lock over both cameras so a hand-run grab and the
timer's do not fail each other, and a line per frame in
`~/captures/grab.log`. `scripts/install-grab-cron.sh --tz America/New_York`
put it on the crontab every five minutes (2026-09-13; the Pi's own clock
is on London time, so the zone is on the cron line and the log line
carries the offset). `scripts/pull-captures.sh <pi> [days]` brings the
day's frames to the workstation under `captures/pi/` and names the newest
of each: the frame a QA pass of the wiring reads.

