#!/usr/bin/env python3
"""A bridge that is not there: the firmware's line protocol on a pty,
for exercising the head and the tools on a box with no ESP32.

  python3 tools/fake-bridge.py            # prints the pty's path, runs until killed
  python3 tools/fake-bridge.py --hz 60.1  # the console's poll rate

It polls the way a game polls: one latch per frame at the given rate,
eight clocks per poll, the byte the register holds (the pad byte in
PASS, SET's or the AT schedule's in INJECT), and streams the same
`L n hh c` lines. RESET zeroes the index, TRIG n reports the trigger.
The pad byte is whatever --pad says (a hand is not simulated). It is a
stand-in for the protocol, not for the part: nothing about a real
console's timing is in it, and it says so on its first line.
"""
import argparse
import os
import pty
import select
import sys
import time
import tty


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hz", type=float, default=60.0988)
    ap.add_argument("--pad", default="00", help="the original pad's byte, hex")
    ap.add_argument("--link", default=None, help="symlink path to create for the pty")
    a = ap.parse_args()
    master, slave = pty.openpty()
    # Raw: a pty's line discipline would echo the head's commands back
    # as if the bridge had printed them.
    tty.setraw(slave)
    tty.setraw(master)
    path = os.ttyname(slave)
    if a.link:
        try:
            os.unlink(a.link)
        except FileNotFoundError:
            pass
        os.symlink(path, a.link)
    print(path, flush=True)
    mode = "pass"
    pad = int(a.pad, 16)
    set_byte = 0
    schedule = []
    latches = 0
    clocks = 0
    trig_at = -1
    have_latch = False
    byte_at_latch = 0
    clocks_at_latch = 0
    period = 1.0 / a.hz
    next_latch = time.monotonic() + period
    buf = b""

    def out(s):
        os.write(master, (s + "\n").encode())

    out("# fake bridge: the protocol only, no part behind it; MODE PASS")
    while True:
        r, _, _ = select.select([master], [], [], max(0.0, next_latch - time.monotonic()))
        if r:
            try:
                buf += os.read(master, 4096)
            except OSError:
                return
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                line = line.decode(errors="replace").strip()
                if line == "MODE PASS":
                    mode = "pass"; out("# mode pass")
                elif line == "MODE INJECT":
                    mode = "inject"; out("# mode inject")
                elif line.startswith("SET "):
                    set_byte = int(line[4:], 16); out(f"# set {set_byte:02x}")
                elif line.startswith("AT "):
                    n, b = line[3:].split()
                    schedule.append((int(n), int(b, 16))); out(f"# at {int(n)} {int(b, 16):02x}")
                elif line.startswith("TRIG "):
                    trig_at = int(line[5:]); out(f"# trig at {trig_at}")
                elif line == "RESET":
                    latches = 0; clocks = 0; schedule = []; trig_at = -1; have_latch = False; out("# reset")
                elif line == "STATUS":
                    out(f"# mode {mode} latch {latches} clocks {clocks} held {held(mode, pad, set_byte, schedule, latches):02x} pad {pad:02x} schedule {len(schedule)} data -1")
                elif line:
                    out("# ? " + line)
        now = time.monotonic()
        if now >= next_latch:
            next_latch += period
            h = held(mode, pad, set_byte, schedule, latches)
            if have_latch:
                out(f"L {latches - 1} {byte_at_latch:02x} {clocks - clocks_at_latch}")
            latches += 1
            clocks_at_latch = clocks
            byte_at_latch = h
            have_latch = True
            clocks += 8
            if 0 <= trig_at < latches:
                out(f"# trigger at latch {latches - 1}")
                trig_at = -1


def held(mode, pad, set_byte, schedule, latches):
    if mode == "pass":
        return pad
    b = set_byte
    for n, v in schedule:
        if n <= latches:
            b = v
    return b


if __name__ == "__main__":
    sys.exit(main())
