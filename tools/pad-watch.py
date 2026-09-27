#!/usr/bin/env python3
"""Which button is pressed, live, from the pad on the P4.

  python3 tools/pad-watch.py --pi HOST              # 60 seconds, then exits
  python3 tools/pad-watch.py --pi HOST --seconds 0  # until Ctrl-C

firmware/pad-usb prints "B hh" on the serial console every time the
pad's byte CHANGES. This follows that output on the bench head and
names the buttons, so a person pressing buttons can read the answer
instead of decoding hex.

IT DOES NOT OPEN THE SERIAL PORT. The pad-log unit on the head already
holds /dev/p4-uart and appends to /tmp/pad.log, and two readers on one
port split its bytes between them without a word, which is a trap this
bench has already fallen into. So this tails the log file, which any
number of readers can share. If the log is not growing, start the unit:

  sudo systemd-run --unit=pad-log --collect /bin/sh -c \\
    "stty -F /dev/p4-uart 115200 raw -echo -hupcl clocal; exec cat /dev/p4-uart >> /tmp/pad.log"

THE BUTTON NAMES ARE NOT TYPED HERE. They come from head/pad.py's
NAMES, which tools/check-pad.py holds to nes_glue's Buttons::as_byte,
so bit 0 is A here because it is A in the console model.

It exits on its own after --seconds (60 by default), so it can be run
with a leading ! in a Claude Code session without needing a Ctrl-C.
"""
import argparse
import pathlib
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "head"))
from pad import NAMES  # noqa: E402

LOG = "/tmp/pad.log"


def describe(b):
    held = [NAMES[i] for i in range(8) if b >> i & 1]
    if b == 0xFF:
        return "ALL EIGHT: D0 is floating. Is the 10k pullup still in?"
    if not held:
        return "(nothing)"
    note = ""
    if b & 0x30 == 0x30 or b & 0xC0 == 0xC0:
        # An original d-pad's rocker cannot close opposite contacts. Two
        # at once is a wiring or a membrane fault, not a thumb.
        note = "   <- opposite directions together: not a thumb"
    return " + ".join(held) + note


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pi", required=True, help="the bench head, user@host (bench.local.md; never committed)")
    ap.add_argument("--seconds", type=float, default=60, help="how long to watch; 0 for until Ctrl-C")
    a = ap.parse_args()

    # -n0: only what happens from now on, not the history in the file.
    cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", a.pi, f"tail -n0 -F {LOG}"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)
    end = time.time() + a.seconds if a.seconds else None
    seen = 0
    print(f"watching the pad for {a.seconds:g} s. Press buttons." if a.seconds else "watching the pad. Ctrl-C to stop.",
          flush=True)
    try:
        import select
        while True:
            if end and time.time() >= end:
                break
            r, _, _ = select.select([p.stdout], [], [], 0.25)
            if not r:
                continue
            line = p.stdout.readline()
            if not line:
                break
            line = line.strip()
            if not line.startswith("B "):
                continue
            try:
                b = int(line.split()[1], 16)
            except (IndexError, ValueError):
                continue
            seen += 1
            print(f"  {b:02X}  {b:08b}  {describe(b)}", flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        p.terminate()
    if not seen:
        print("nothing arrived. Is pad-log running on the head, and is the pad pressed?")
    else:
        print(f"{seen} change(s).")


if __name__ == "__main__":
    main()
