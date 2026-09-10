#!/usr/bin/env python3
"""The v1 schematic against the wiring tables: one fact, one place.

  python3 tools/check-sheets.py

`tools/draw-schematics.py` carries the v1 sheet's nets in its own
source (it was drafted from `docs/wiring.md` and checked by hand), and
`docs/wiring.md` carries the pin tables the firmware and `bench.svg`
are read from. Two copies drift. This reads the C6's net list out of
the v1 sheet's source and the tables out of wiring.md and holds them
equal: every register input's GPIO, the two counter inputs, the pad's
three lines and the trigger.

It does the same for v1b, whose two copies are the v1b sheet's A1 chip
and the "UNO pins" table in `docs/bench-v1b-uno.md`: every pin either
names the same net in both, or this fails. Nine signal pins is the
floor, so the check cannot pass by comparing nothing.

It then regenerates every sheet into a temporary directory and holds
the committed SVGs to them; the count it reports is counted, not
typed. Exit 1 on any difference, and on nothing to compare.
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


def sheet_v1b_nets():
    """{pin: net} from the v1b sheet's A1 chip, both its lists."""
    src = (ROOT / "tools" / "draw-schematics.py").read_text()
    i = src.index('"A1", "Arduino UNO R3')
    j = src.index("pad_socket(", i)
    out = {}
    for label, net in re.findall(r'\(None, "([^"]+)", "([^"]+)"\)', src[i:j]):
        for pin in re.findall(r"\bD\d+\b|\b5V\b|\bGND\b", label):
            out[pin] = net
    return out


def doc_v1b_pins(universe):
    """{pin: net} from the UNO pins table in docs/bench-v1b-uno.md.

    A row pairs its pins with the nets named in its function cell, in
    order, when the two counts match; rows that name no net (the serial
    pair, the supply) are not compared."""
    md = (ROOT / "docs" / "bench-v1b-uno.md").read_text()
    body = md[md.index("## UNO pins"):]
    body = body[: body.index("\n## ", 1)] if "\n## " in body[1:] else body
    out = {}
    for line in body.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2 or cells[0] in ("pin", "---"):
            continue
        pins = re.findall(r"\bD\d+\b", cells[0])
        nets = [t for t in re.findall(r"\b[A-Z][A-Z0-9_]{2,}\b", cells[1]) if t in universe]
        if pins and len(pins) == len(nets):
            out.update(dict(zip(pins, nets)))
    return out


def check_v1b():
    sheet = sheet_v1b_nets()
    doc = doc_v1b_pins(set(sheet.values()))
    bad = 0
    for pin, net in sorted(doc.items(), key=lambda kv: int(kv[0][1:])):
        if sheet.get(pin) != net:
            print(f"  {pin}: bench-v1b-uno.md says {net}, the v1b sheet says {sheet.get(pin)}")
            bad += 1
    if len(doc) < 9:
        print(f"  only {len(doc)} UNO pins could be compared; the table or the sheet has moved out from under this check")
        bad += 1
    if not bad:
        print(f"check-sheets: {len(doc)} UNO pins on the v1b sheet agree with docs/bench-v1b-uno.md")
    # v1b runs from the UNO's 5 V and the console shares only ground:
    # that is what bench-v1b-uno.md says and what every build step wires
    # (the RED lead stays off the board). Until 2026-09-10 the sheet drew
    # the console's supply pin on the bridge's +5V net anyway, which the
    # wiring list then told a builder to join: two regulators in
    # parallel, one of them behind the Pi's USB fuse. The cheat sheet's
    # derived column is what showed it.
    nl = __import__("loadmod").load(ROOT / "tools" / "netlist.py", "netlist")
    sheets, _off = nl.collect()
    for name, ports in (("bench-v1b", 1), ("bench-v2b", 2)):
        supply = [n for n in sheets[name]
                  if n["part"] == "console controller port" and n["pinname"] == "+5V"]
        if len(supply) != ports:
            print(f"  the {name} sheet's console ports have {len(supply)} supply pins; expected {ports}")
            bad += 1
            continue
        joined = [n["ref"] for n in supply if n["net"] == "+5V"]
        if joined:
            print(f"  the {name} sheet joins the console's +5V pin ({', '.join(joined)}) to the bridge's "
                  f"+5V net: the UNO bridges run from the UNO's 5 V only")
            bad += 1
        else:
            print(f"check-sheets: {name} leaves the console's supply ({ports} port(s)) off the bridge's +5V net")
    return bad


def norm(name):
    """Pin names the same way wherever they are written: no spaces, no
    parenthetical, upper case. '+5 V', '+5V' and 'OUT0 (latch)' are one
    name in three hands."""
    return re.sub(r"\s+|\(.*?\)", "", str(name)).upper()


def doc_port_pinout():
    """The controller port's pinout out of docs/wiring.md, which is the
    one place it is written down since it was measured on this console
    2026-09-09."""
    text = (ROOT / "docs" / "wiring.md").read_text()
    m = re.search(r"\| pin \| name \| direction \| used as \|\n\|[-| ]+\|\n((?:\|.*\n)+)", text)
    if not m:
        return {}
    out = {}
    for line in m.group(1).strip().splitlines():
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) >= 2 and cells[0].isdigit():
            out[int(cells[0])] = norm(cells[1])
    return out


def check_port_pinout():
    """The rule check cannot catch this one. A connector drawn with the
    supply on the wrong pin is perfectly connected and perfectly wrong,
    and it is the error that sends a probe to a pin carrying nothing. So
    the pinout is held to the measurement instead of to itself: the
    schematic's connector symbol and the bring-up tool must both agree
    with the table in wiring.md."""
    want = doc_port_pinout()
    if not want:
        print("  no port pinout table found in docs/wiring.md")
        return 1
    bad = 0
    sys.path.insert(0, str(ROOT / "tools"))
    from loadmod import load
    draw = load(ROOT / "tools" / "draw-schematics.py", "draw", [sys.argv[0], str(ROOT / "docs")])
    seen = {}

    class Probe:
        def chip(self, x, y, w, ref, part, left, right, conn=False, extra=None):
            for no, nm, _net in list(left) + list(right):
                if no is not None:
                    seen[no] = norm(nm)
            return 0
    draw.console_port(Probe(), 0, 0, "J1", {"clk": "CLK", "out0": "OUT0", "d0": "D0"})
    for pin, name in sorted(want.items()):
        if seen.get(pin) != name:
            print(f"  port pin {pin}: wiring.md says {name}, the schematic's connector says {seen.get(pin)}")
            bad += 1

    bu = load(ROOT / "tools" / "bringup.py", "bringup")
    for pin, name in bu.PORT_PINS:
        if want.get(pin) != norm(name):
            print(f"  port pin {pin}: wiring.md says {want.get(pin)}, bringup.py says {norm(name)}")
            bad += 1
    if not bad:
        print(f"check-sheets: {len(want)} port pins agree across wiring.md, the schematic and the bring-up tool")
    return bad


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
    bad += check_v1b()
    bad += check_port_pinout()
    # The committed SVGs are what the generator writes.
    n_sheets = 0
    with tempfile.TemporaryDirectory() as d:
        for gen in ("draw-schematics.py", "breadboard.py"):
            subprocess.run([sys.executable, str(ROOT / "tools" / gen), d], check=True, capture_output=True)
        for p in sorted(Path(d).glob("*.svg")):
            n_sheets += 1
            committed = ROOT / "docs" / p.name
            if not committed.exists() or committed.read_bytes() != p.read_bytes():
                gen = "breadboard.py" if p.name.startswith("breadboard") else "draw-schematics.py"
                print(f"  docs/{p.name} is not what {gen} writes: regenerate it")
                bad += 1
    if not n_sheets:
        print("  the generator wrote no sheets")
        bad += 1
    print(f"check-sheets: the {n_sheets} sheets are current" if not bad else "")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
