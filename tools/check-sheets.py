#!/usr/bin/env python3
"""The v1 schematic against the wiring tables: one fact, one place.

  python3 tools/check-sheets.py

`tools/draw-schematics.py` carries the v1 sheet's nets in its own
source (it was drafted from `docs/wiring.md` and checked by hand), and
`docs/wiring.md` carries the pin tables the firmware and `bench.svg`
are read from. Two copies drift. This reads the C6's net list out of
the v1 sheet's source and the tables out of wiring.md and holds them
equal: every register input's GPIO, the two counter inputs, the pad's
three lines and the trigger. It also regenerates the four sheets into a
temporary directory and holds the committed SVGs to them. Exit 1 on any
difference, and on nothing to compare.
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
draw_bench = __import__("draw-bench")


def sheet_nets():
    src = (ROOT / "tools" / "draw-schematics.py").read_text()
    # The v1 sheet is the first esp32c6(...) call: its two pin lists,
    # up to the note that follows them.
    i = src.index("    esp32c6(sh, ")  # the first CALL, not the def
    j = src.index("sh.note(", i)
    block = src[i:j]
    return dict(re.findall(r'\(None, "(GPIO\d+)", "([A-Z0-9_]+)"\)', block))


def main():
    w = draw_bench.read_wiring()
    want = {}
    names = {"A": "REG_A", "B": "REG_B", "Select": "REG_SEL", "Start": "REG_START", "Up": "REG_UP", "Down": "REG_DOWN", "Left": "REG_LEFT", "Right": "REG_RIGHT"}
    for _num, _letter, signal, g in w["buttons"]:
        want[f"GPIO{g}"] = names[signal]
    want[f"GPIO{w['con']['A1'][2]}"] = "LATCH_IN"
    want[f"GPIO{w['con']['A2'][2]}"] = "CLK_IN"
    want[f"GPIO{w['pad']['OUT0'][1]}"] = "PAD_LATCH"
    want[f"GPIO{w['pad']['CLK'][1]}"] = "PAD_CLK"
    want[f"GPIO{w['pad']['D0'][1]}"] = "PAD_D0"
    want[f"GPIO{w['trig']}"] = "TRIG"
    got = sheet_nets()
    bad = 0
    for g, net in sorted(want.items(), key=lambda kv: int(kv[0][4:])):
        if got.get(g) != net:
            print(f"  {g}: wiring.md says {net}, the v1 sheet says {got.get(g)}")
            bad += 1
    extra = {g: n for g, n in got.items() if g not in want}
    if extra:
        print(f"  the v1 sheet names pins wiring.md does not: {extra}")
        bad += 1
    if not want:
        print("nothing to compare")
        return 1
    print(f"check-sheets: {len(want)} C6 pins on the v1 sheet agree with docs/wiring.md" if not bad else f"check-sheets: {bad} disagreement(s)")
    # The committed SVGs are what the generator writes.
    with tempfile.TemporaryDirectory() as d:
        subprocess.run([sys.executable, str(ROOT / "tools" / "draw-schematics.py"), d], check=True, capture_output=True)
        for p in sorted(Path(d).glob("*.svg")):
            committed = ROOT / "docs" / p.name
            if not committed.exists() or committed.read_bytes() != p.read_bytes():
                print(f"  docs/{p.name} is not what draw-schematics.py writes: regenerate it")
                bad += 1
    print("check-sheets: the four sheets are current" if not bad else "")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
