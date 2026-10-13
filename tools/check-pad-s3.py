#!/usr/bin/env python3
"""The pad-s3 sheets against the firmware: one fact, one place.

  python3 tools/check-pad-s3.py

tools/draw-pad-s3.py carries the XIAO pin table the sheets are drawn
from; firmware/pad/pad.ino carries the S3 pin numbers it compiles with.
Two copies drift. This reads the four signal GPIOs out of each and holds
them equal, then regenerates the three sheets and holds the committed
SVGs to them. Four pins is the floor, so it cannot pass by comparing
nothing. Exit 1 on any difference.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))


def firmware_pins():
    """The S3 branch of firmware/pad's pin block: the #else arm after the P4's."""
    src = (ROOT / "firmware" / "pad" / "pad.ino").read_text()
    m = re.search(r"#else\n(.*?)#endif", src[src.index("CONFIG_IDF_TARGET_ESP32P4\n// Exactly"):], re.S)
    if not m:
        sys.exit("check-pad-s3: the S3 pin block was not found in firmware/pad/pad.ino")
    pins = dict(re.findall(r"static const int (PAD_LATCH|PAD_CLOCK|PAD1_DATA|MODE_SW|LED_PIN) = (\d+);", m.group(1)))
    return {k: int(v) for k, v in pins.items()}


def main():
    draw = __import__("draw-pad-s3")
    sheet = {net: gpio for _pin, gpio, net, _what in draw.PINS if isinstance(gpio, int)}
    fw = firmware_pins()
    pairs = [("PAD_LATCH", "PAD_LATCH"), ("PAD_CLK", "PAD_CLOCK"), ("PAD_D0", "PAD1_DATA"), ("MODE_SW", "MODE_SW"), ("", "LED_PIN")]
    bad = 0
    n = 0
    for net, name in pairs:
        if net not in sheet or name not in fw:
            print(f"  MISSING  sheet {net!r} or firmware {name}")
            bad = 1
            continue
        n += 1
        same = sheet[net] == fw[name]
        print(f"  {'ok  ' if same else 'DIFF'} {name:10s} firmware GPIO{fw[name]}  sheet GPIO{sheet[net]}")
        bad |= not same
    if n < 4:
        print(f"  only {n} pins compared; four is the floor")
        bad = 1
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "draw-pad-s3.py"), "--check"], capture_output=True, text=True)
    print(r.stdout.rstrip())
    bad |= r.returncode != 0
    print("check-pad-s3: the sheets, the firmware and the SVGs agree" if not bad else "check-pad-s3: disagreement")
    return int(bad)


if __name__ == "__main__":
    sys.exit(main())
