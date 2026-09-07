#!/usr/bin/env python3
"""The bridge over USB serial: send commands, stream its lines to stdout
and a file. B0's host side, run on the Pi or wherever the ESP32 is.

  python3 tools/sniff.py /dev/ttyUSB0 out.log [-c "MODE PASS" -c "RESET"] [-s 60]

Every line the bridge prints is written as is: `L n hh c` per latch and
`# ...` for everything else. -c sends a command before listening (any
number, in order); -s stops after that many seconds (default: until
Ctrl-C). Needs pyserial.
"""
import argparse
import sys
import time

import serial


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("port")
    ap.add_argument("out")
    ap.add_argument("-c", "--command", action="append", default=[], help="a line to send first")
    ap.add_argument("-s", "--seconds", type=float, default=None)
    ap.add_argument("-b", "--baud", type=int, default=921600)
    a = ap.parse_args()
    s = serial.Serial(a.port, a.baud, timeout=0.1)
    time.sleep(0.3)
    for c in a.command:
        s.write((c + "\n").encode())
    t0 = time.time()
    with open(a.out, "w") as f:
        try:
            while a.seconds is None or time.time() - t0 < a.seconds:
                line = s.readline().decode(errors="replace").rstrip("\r\n")
                if not line:
                    continue
                print(line)
                f.write(line + "\n")
                f.flush()
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
