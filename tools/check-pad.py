#!/usr/bin/env python3
"""The gamepad hand, checked without a gamepad.

  python3 tools/check-pad.py
  MUTATE=1 python3 tools/check-pad.py    # must go red

`head/pad.py` turns a pad's events into the byte the bridge's `SET`
takes. Two things can go wrong in it and neither shows up as a crash:

  1. **The bit order drifts from the model.** The byte's meaning is
     `nes_glue::controller::Buttons::as_byte` in the sibling console
     repository, bit 0 A through bit 7 Right. If those two ever
     disagree the console plays a game with the buttons shuffled, which
     looks like a wiring fault and is not one. So the Rust is parsed
     here and held to the Python's own list. SKIPS without the sibling
     checkout; REQUIRE_NES=1 makes the skip a failure, NES=<path> names
     one.
  2. **The event decoding is plausible but wrong.** A pad is a stream
     of structs; feeding it the wrong shape gives buttons, just not the
     ones the hand pressed. So a stream is built here byte for byte and
     the bytes that come out are asserted, including the cases a real
     hand produces constantly: a diagonal arriving as two events before
     one SYN_REPORT, a repeat that must not be re-sent, and a direction
     pair the pad's pivot cannot make.

There is no pad and no bridge in any of this, which is the point: the
Pi is not always up, and this has to be able to fail on the desk.
"""
from __future__ import annotations

import io
import os
import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "head"))

import pad as padmod  # noqa: E402

MUTATE = os.environ.get("MUTATE") == "1"
REQUIRE_NES = os.environ.get("REQUIRE_NES") == "1"

if MUTATE:
    # The two face buttons swapped: every byte below that names A or B
    # is now wrong, and the model check is untouched, so a run that
    # still passes proves the stream assertions are not looking.
    padmod.BUTTONS[padmod.BTN_EAST] = padmod.B
    padmod.BUTTONS[padmod.BTN_SOUTH] = padmod.A

fails: list[str] = []
oks = 0
skips = 0


def ok(cond, why):
    global oks
    if cond:
        oks += 1
    else:
        fails.append(why)


def ev(etype, code, value):
    return struct.pack(padmod.EVENT_FMT, 0, 0, etype, code, value)


def syn():
    return ev(padmod.EV_SYN, padmod.SYN_REPORT, 0)


def play(*chunks, ranges=None):
    """A stream through `pad.stream`, returning the bytes it yielded and
    the Pad, so the interlock count can be read afterwards."""
    p = padmod.Pad(ranges=ranges)
    f = io.BytesIO(b"".join(chunks))
    return list(padmod.stream(f, p)), p


# ------------------------------------------------ 1. against the model
nes = Path(os.environ.get("NES", ROOT.parent / "nes"))
src = nes / "crates/nes-glue/src/controller.rs"
if not src.exists():
    print(f"SKIP the model's bit order: {src} absent")
    skips += 1
else:
    text = src.read_text()
    body = text[text.find("pub fn as_byte"):]
    body = body[:body.find("\n    }")]
    pairs = []
    for m in re.finditer(r"self\.(\w+) as u8\)(?:\s*<<\s*(\d+))?", body):
        pairs.append((int(m.group(2) or 0), m.group(1)))
    order = [n for _, n in sorted(pairs)]
    ok(len(order) == 8, f"as_byte names {len(order)} buttons, want 8")
    ok([n.lower() for n in padmod.NAMES] == order,
       f"the model's order is {order}, this tool's is {[n.lower() for n in padmod.NAMES]}")
    ok([s for s, _ in sorted(pairs)] == list(range(8)),
       f"as_byte's shifts are {[s for s, _ in sorted(pairs)]}, want 0..7")

# The bit the bring-up sitting names out loud, so the tool, the model
# and the procedure cannot drift apart in a pair.
bringup = ROOT / "tools/bringup.py"
if not bringup.exists():
    print("SKIP the bring-up's named bit: tools/bringup.py absent")
    skips += 1
else:
    m = re.search(r'SET ([0-9a-f]{2}) is (\w+) pressed', bringup.read_text())
    if not m:
        print("SKIP the bring-up's named bit: no 'SET hh is <button> pressed' line")
        skips += 1
    else:
        want_byte, want_name = int(m.group(1), 16), m.group(2)
        bit = padmod.NAMES.index(want_name.capitalize()) if want_name.capitalize() in padmod.NAMES else None
        ok(bit is not None and 1 << bit == want_byte,
           f"bringup says SET {want_byte:02x} is {want_name}; this tool puts {want_name} at bit {bit}")

# ----------------------------------------------- 2. the stream decoded
BIT = {n: 1 << i for i, n in enumerate(padmod.NAMES)}

seq, _ = play(ev(padmod.EV_KEY, padmod.BTN_EAST, 1), syn())
ok(seq == [BIT["A"]], f"the right face button alone should be {BIT['A']:#04x}, got {[hex(b) for b in seq]}")

seq, _ = play(ev(padmod.EV_KEY, padmod.BTN_SOUTH, 1), syn())
ok(seq == [BIT["B"]], f"the bottom face button alone should be {BIT['B']:#04x}, got {[hex(b) for b in seq]}")

# A diagonal: two events, ONE moment. The wrong design sends two bytes
# and the console sees a direction the hand never asked for.
seq, _ = play(ev(padmod.EV_ABS, padmod.ABS_HAT0X, -1),
              ev(padmod.EV_ABS, padmod.ABS_HAT0Y, -1), syn())
ok(seq == [BIT["Left"] | BIT["Up"]],
   f"up and left in one report should be one byte {BIT['Left'] | BIT['Up']:#04x}, got {[hex(b) for b in seq]}")

# A repeat is not a change. A pad that reports at 100 Hz would otherwise
# put 100 identical SET lines a second on a serial link shared with the
# latch stream.
seq, _ = play(ev(padmod.EV_KEY, padmod.BTN_START, 1), syn(), syn(), syn())
ok(seq == [BIT["Start"]], f"three reports of one press should send one byte, got {[hex(b) for b in seq]}")

# Press, then release.
seq, _ = play(ev(padmod.EV_KEY, padmod.BTN_START, 1), syn(),
              ev(padmod.EV_KEY, padmod.BTN_START, 0), syn())
ok(seq == [BIT["Start"], 0], f"press then release should be {BIT['Start']:#04x} then 0, got {[hex(b) for b in seq]}")

# The interlock: a hat left and a stick right in the same moment is a
# pair the moulding cannot make. NEITHER goes, and it is counted.
#
# Left is HELD first, so the interlock has something to take away. The
# obvious version of this test starts from rest, resolves to 0, and
# passes whether the interlock fired or not, because 0 is also what a
# pad doing nothing sends: it would assert the resting state and call
# it a guard.
seq, p = play(ev(padmod.EV_ABS, padmod.ABS_HAT0X, -1), syn(),
              ev(padmod.EV_ABS, padmod.ABS_X, 32767), syn(),
              ranges={padmod.ABS_X: (-32768, 32767)})
ok(seq == [BIT["Left"], 0],
   f"left held, then right as well, should be {BIT['Left']:#04x} then neither, got {[hex(b) for b in seq]}")
ok(p.impossible >= 1, "the impossible pair was dropped without being counted")

# The stick, past the deadzone and inside it, on the range the kernel
# reports rather than an assumed one.
seq, _ = play(ev(padmod.EV_ABS, padmod.ABS_Y, -32768), syn(),
              ranges={padmod.ABS_Y: (-32768, 32767)})
ok(seq == [BIT["Up"]], f"the stick held up should be {BIT['Up']:#04x}, got {[hex(b) for b in seq]}")

seq, _ = play(ev(padmod.EV_ABS, padmod.ABS_Y, -1000), syn(),
              ranges={padmod.ABS_Y: (-32768, 32767)})
ok(seq == [], f"the stick inside the deadzone should send nothing, got {[hex(b) for b in seq]}")

# With no measured range the stick is ignored, not guessed at.
seq, _ = play(ev(padmod.EV_ABS, padmod.ABS_Y, -32768), syn())
ok(seq == [], f"a stick with no measured range should be ignored, got {[hex(b) for b in seq]}")

# An unmapped button is counted and reported, not silently eaten.
seq, p = play(ev(padmod.EV_KEY, 0x13C, 1), syn())
ok(seq == [] and p.unknown.get(0x13C) == 1, f"an unmapped code should be counted, got {p.unknown}")

# A reader that has nothing yet says None and is asked again; b"" is
# the end. This is what lets the head sit on a resting pad and still
# honour an abort, so it is checked rather than assumed.
class Trickle:
    def __init__(self, chunks):
        self.chunks = list(chunks)

    def read(self, _n):
        return self.chunks.pop(0) if self.chunks else b""


seq = list(padmod.stream(Trickle([None, None, ev(padmod.EV_KEY, padmod.BTN_START, 1), None, syn()])))
ok(seq == [BIT["Start"]], f"a reader that waits should still decode, got {[hex(b) for b in seq]}")

# `stop` ends the stream even while events keep arriving. Measured
# against the same stream unstopped, because "it yielded nothing" is
# also what a stream that never decoded anything yields.
drumming = [ev(padmod.EV_KEY, padmod.BTN_START, 1), syn(),
            ev(padmod.EV_KEY, padmod.BTN_START, 0), syn()] * 25
free = list(padmod.stream(Trickle(drumming)))
ok(len(free) == 50, f"a button drummed 25 times should send 50 bytes, got {len(free)}")
looks = [0]


def after_ten():
    looks[0] += 1
    return looks[0] > 10


cut = list(padmod.stream(Trickle(drumming), stop=after_ten))
ok(0 < len(cut) < len(free), f"stop should cut the stream short, got {len(cut)} of {len(free)}")

# A stream whose struct size is wrong must refuse rather than decode
# plausible buttons out of a misalignment.
bad = b"".join(ev(padmod.EV_KEY, padmod.BTN_EAST, 1) for _ in range(4))[1:]
try:
    list(padmod.stream(io.BytesIO(bad + bad)))
    ok(False, "a misaligned stream decoded without complaint")
except ValueError:
    oks += 1

# --------------------------------------------------------------- verdict
for f in fails:
    print(f"FAIL {f}")
print(f"\n{oks} check(s) agree, {len(fails)} disagree, {skips} skipped.")
if skips and REQUIRE_NES:
    print("REQUIRE_NES=1: a skip is a failure")
    sys.exit(1)
sys.exit(1 if fails else 0)
