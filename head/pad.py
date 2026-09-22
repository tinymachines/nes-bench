#!/usr/bin/env python3
"""A Bluetooth gamepad as the console's hand.

  python3 head/pad.py --list
  python3 head/pad.py --dry-run                 # the byte, as it changes
  python3 head/pad.py --device /dev/input/event5 --dry-run

The bridge already takes an arbitrary byte into the console: `SET hh`
puts it on the 74HC595, the six grey lines carry it to the 74HCT165,
and the milestone of 2026-09-15 walked all fifteen test bytes through
to the console's own D0 line. Nothing about that path changes here.
What was missing was a hand: the only one the bench had was the
original pad wired to the bridge's own lines, which needs somebody
sitting at the breadboard.

So this is a hand and nothing else. A pad pairs to the Pi through
BlueZ, the kernel gives it to us as an event device, and every change
of the eight buttons becomes one `SET hh`. Classic and BLE pads both
arrive here the same way, which is the reason this reads evdev rather
than speaking Bluetooth itself: the radio and the profile are BlueZ's
problem, already solved, and a DualSense (Classic) and an 8BitDo (BLE)
are the same file by the time they reach this file.

WHAT THIS IS WORTH BEYOND PLAYING. The head logs every `L <latch>
<byte> <clocks>` line the bridge prints, and `tools/b3.py` already
turns such a log into an AT schedule the bridge replays latch for
latch. So a session played with a pad in hand is a recording, in the
format the model's `pad-log` prints and `tools/compare-logs.py` diffs.
A minute of real play becomes a deterministic script for the scope.

PURE STDLIB, ON PURPOSE. python-evdev is a C extension and the head is
a Pi that has to come back after a card reflash. The event device is a
documented 24-byte (or 16-byte) struct and the device list is a text
file in /proc, so both are read here directly. The one ioctl is
EVIOCGABS, and only for an analog stick's range, which is the
difference between measuring the range and assuming it.

THE BIT ORDER IS NOT DECIDED HERE. It is `nes_glue::controller`'s
`Buttons::as_byte`: bit 0 A, 1 B, 2 Select, 3 Start, 4 Up, 5 Down,
6 Left, 7 Right, set = pressed. One fact, one place; this file quotes
it and `tools/check-pad.py` holds the quote to the Rust.
"""
from __future__ import annotations

import argparse
import fcntl
import struct
import sys
from pathlib import Path

# ------------------------------------------------------------ the protocol
# linux/input.h. The event struct is a timeval and three fields; native
# sizes, because a 32-bit Pi OS and a 64-bit one differ in the timeval
# and `struct` gets that right only without a byte-order prefix.
EVENT_FMT = "llHHi"
EVENT_SIZE = struct.calcsize(EVENT_FMT)

EV_SYN, EV_KEY, EV_ABS = 0x00, 0x01, 0x03
SYN_REPORT = 0

BTN_SOUTH, BTN_EAST, BTN_NORTH, BTN_WEST = 0x130, 0x131, 0x133, 0x134
BTN_SELECT, BTN_START = 0x13A, 0x13B
BTN_DPAD_UP, BTN_DPAD_DOWN, BTN_DPAD_LEFT, BTN_DPAD_RIGHT = 0x220, 0x221, 0x222, 0x223

ABS_X, ABS_Y, ABS_HAT0X, ABS_HAT0Y = 0x00, 0x01, 0x10, 0x11

# The eight, in `Buttons::as_byte`'s order. The index IS the bit.
NAMES = ["A", "B", "Select", "Start", "Up", "Down", "Left", "Right"]
A, B, SELECT, START, UP, DOWN, LEFT, RIGHT = range(8)

# AUTHORED, not measured: which button on a modern pad is which on the
# part. The face buttons go in pairs because a pad has four where the
# NES has two, and a hand reaching for X expecting B is a worse bench
# than one extra alias. RetroArch's convention for the two that matter:
# the bottom face button is B and the right one is A, which puts A to
# the right of B exactly as the moulding does.
BUTTONS = {
    BTN_SOUTH: B, BTN_WEST: B,
    BTN_EAST: A, BTN_NORTH: A,
    BTN_SELECT: SELECT, BTN_START: START,
    BTN_DPAD_UP: UP, BTN_DPAD_DOWN: DOWN,
    BTN_DPAD_LEFT: LEFT, BTN_DPAD_RIGHT: RIGHT,
}


class Pad:
    """The eight buttons, fed one event at a time.

    Three sources reach the same eight bits: the face and shoulder
    buttons as EV_KEY, the hat as EV_ABS (which is how xpad and most
    BLE pads report a d-pad), and the left stick as EV_ABS past a
    deadzone. A pad that reports the d-pad both ways is common, so the
    sources are ORed rather than latched.
    """

    def __init__(self, deadzone=0.5, ranges=None):
        self.keys = [False] * 8       # from EV_KEY
        self.hat = [False] * 8        # from ABS_HAT0X/Y
        self.stick = [False] * 8      # from ABS_X/ABS_Y
        self.deadzone = deadzone
        self.ranges = ranges or {}    # axis -> (min, max), measured by EVIOCGABS
        self.impossible = 0           # frames the sources asked for Up+Down or Left+Right
        self.unknown = {}             # codes seen and not mapped, for --dry-run to report

    # -- the eight bits as the register wants them -------------------
    @property
    def byte(self) -> int:
        """`Buttons::as_byte`: bit 0 = A, set = pressed.

        The interlock is here. A real pad's d-pad pivots on one post, so
        Up and Down cannot both close and neither can Left and Right;
        several games read a pair that silicon cannot produce and do
        something undefined with it. A stick at an exact diagonal plus a
        hat can ask for it, so when both are asked for NEITHER is sent,
        which is what the moulding does, and the count is kept because a
        guard that absorbs a thing silently is worse than no guard.
        """
        bits = [self.keys[i] or self.hat[i] or self.stick[i] for i in range(8)]
        if (bits[UP] and bits[DOWN]) or (bits[LEFT] and bits[RIGHT]):
            self.impossible += 1
            if bits[UP] and bits[DOWN]:
                bits[UP] = bits[DOWN] = False
            if bits[LEFT] and bits[RIGHT]:
                bits[LEFT] = bits[RIGHT] = False
        b = 0
        for i, on in enumerate(bits):
            if on:
                b |= 1 << i
        return b

    # -- one event ---------------------------------------------------
    def feed(self, etype: int, code: int, value: int) -> None:
        if etype == EV_KEY:
            if code in BUTTONS:
                self.keys[BUTTONS[code]] = value != 0
            elif value:
                self.unknown[code] = self.unknown.get(code, 0) + 1
        elif etype == EV_ABS:
            if code == ABS_HAT0X:
                self.hat[LEFT], self.hat[RIGHT] = value < 0, value > 0
            elif code == ABS_HAT0Y:
                self.hat[UP], self.hat[DOWN] = value < 0, value > 0
            elif code in (ABS_X, ABS_Y):
                f = self._axis(code, value)
                if f is None:
                    return
                if code == ABS_X:
                    self.stick[LEFT], self.stick[RIGHT] = f <= -self.deadzone, f >= self.deadzone
                else:
                    self.stick[UP], self.stick[DOWN] = f <= -self.deadzone, f >= self.deadzone

    def _axis(self, code: int, value: int):
        """The stick as -1..1, using the range the kernel reports for this
        pad. With no range measured the stick is ignored rather than
        guessed at: a wrong range is a d-pad that sticks, and a pad with
        a hat loses nothing."""
        r = self.ranges.get(code)
        if not r:
            return None
        lo, hi = r
        mid = (lo + hi) / 2
        span = (hi - lo) / 2
        return 0.0 if span == 0 else (value - mid) / span


# ------------------------------------------------------- finding the pad
def find_pads():
    """Every gamepad the kernel has, from /proc/bus/input/devices.

    The tell is a `js` handler: the joystick layer claims gamepads and
    nothing else, so this needs no capability bitmap and no ioctl. A
    keyboard that also reports BTN_ codes does not get one.
    """
    out = []
    try:
        text = Path("/proc/bus/input/devices").read_text()
    except OSError:
        return out
    for block in text.split("\n\n"):
        name = handlers = None
        for line in block.splitlines():
            if line.startswith("N: Name="):
                name = line.split("=", 1)[1].strip().strip('"')
            elif line.startswith("H: Handlers="):
                handlers = line.split("=", 1)[1].split()
        if not name or not handlers:
            continue
        if not any(h.startswith("js") for h in handlers):
            continue
        ev = next((h for h in handlers if h.startswith("event")), None)
        if ev:
            out.append((name, f"/dev/input/{ev}"))
    return out


def abs_ranges(fd, axes=(ABS_X, ABS_Y)):
    """EVIOCGABS for each axis: the range this pad actually reports.

    struct input_absinfo is six s32 (value, minimum, maximum, fuzz,
    flat, resolution). The ioctl number is _IOR('E', 0x40 + axis,
    input_absinfo), assembled here because there is no stdlib helper.
    An axis the pad does not have simply fails, and its range stays
    absent, which `Pad._axis` treats as "no stick".
    """
    ranges = {}
    size = struct.calcsize("6i")
    for axis in axes:
        req = (2 << 30) | (size << 16) | (ord("E") << 8) | (0x40 + axis)
        try:
            raw = fcntl.ioctl(fd, req, bytes(size))
        except OSError:
            continue
        _, lo, hi, _, _, _ = struct.unpack("6i", raw)
        if hi > lo:
            ranges[axis] = (lo, hi)
    return ranges


def events(f, stop=None):
    """The event stream, decoded. Reads whole structs and refuses a
    stream it cannot decode rather than reporting plausible buttons: a
    kernel built with 64-bit time on a 32-bit userland gives a struct
    this size does not match, and the tell is an event type no input
    device has.

    A read returning None means "nothing yet, ask again", which is how
    a caller that has to stay responsive (the head, which must honour
    an abort while the hand is resting) waits without blocking. b"" is
    still end of stream. `stop` is polled between reads.
    """
    while not (stop and stop()):
        raw = f.read(EVENT_SIZE)
        if raw is None:
            continue
        if not raw or len(raw) < EVENT_SIZE:
            return
        _, _, etype, code, value = struct.unpack(EVENT_FMT, raw)
        if etype > 0x1F:
            raise ValueError(
                f"event type {etype} from a {EVENT_SIZE}-byte struct: this kernel's "
                "input_event is not the size this build of python computes")
        yield etype, code, value


def stream(f, pad=None, rest=0, stop=None):
    """The byte, once per SYN_REPORT, and only when it changed.

    A pad sends a burst of events and then a SYN_REPORT to say the
    burst is one moment. Sending on each event would put a diagonal on
    the wire as two bytes, one of them a direction the hand never
    asked for, and at 60 polls a second the console can see it.

    `rest` is what the register already holds, not an assumption about
    the pad: the bridge's INJECT byte is 0 until a SET says otherwise,
    so a caller that opened the session with `SET 00` leaves the
    default alone. It is a parameter rather than a constant because
    starting from "unknown" would send a byte on the first report even
    when the hand is not touching the pad, and starting from the wrong
    value would swallow a button that was already held at connect.
    """
    pad = pad or Pad()
    last = rest
    for etype, code, value in events(f, stop):
        if etype == EV_SYN and code == SYN_REPORT:
            b = pad.byte
            if b != last:
                last = b
                yield b
        else:
            pad.feed(etype, code, value)


# ------------------------------------------------------------------ main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--list", action="store_true", help="the gamepads the kernel has, and exit")
    ap.add_argument("--device", help="/dev/input/eventN (default: the first gamepad)")
    ap.add_argument("--dry-run", action="store_true", help="print the byte, send nothing")
    ap.add_argument("--deadzone", type=float, default=0.5)
    a = ap.parse_args()

    pads = find_pads()
    if a.list:
        for name, path in pads:
            print(f"{path}  {name}")
        if not pads:
            print("no gamepad: pair one with bluetoothctl, and check it appears in /proc/bus/input/devices")
        return 0 if pads else 1

    path = a.device
    if not path:
        if not pads:
            print("no gamepad found; --list says what the kernel has", file=sys.stderr)
            return 1
        path, name = pads[0][1], pads[0][0]
        print(f"# {path}  {name}")

    with open(path, "rb", buffering=0) as f:
        pad = Pad(deadzone=a.deadzone, ranges=abs_ranges(f.fileno()))
        if not pad.ranges:
            print("# no analog range from this pad: the hat and the buttons only")
        try:
            for b in stream(f, pad):
                held = " ".join(n for i, n in enumerate(NAMES) if b >> i & 1) or "-"
                print(f"SET {b:02x}    {held}")
        except KeyboardInterrupt:
            pass
    if pad.impossible:
        print(f"# {pad.impossible} frame(s) asked for a direction pair the pad's pivot cannot make; neither was sent")
    if pad.unknown:
        print("# codes seen and not mapped: " + ", ".join(f"0x{c:x} x{n}" for c, n in sorted(pad.unknown.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
