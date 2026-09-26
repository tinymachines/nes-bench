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
    # The block ends at the chip's own extra line, not at the next
    # pad_socket call: sheet 3 sits between the two and also names a
    # 5V and a GND pin (the Pi's), which used to land in this table.
    j = src.index('extra="5 V logic', i)
    out = {}
    for label, net in re.findall(r'\(None, "([^"]+)", "([^"]+)"\)', src[i:j]):
        for pin in re.findall(r"\bD\d+\b|\b5V\b|\bGND\b", label):
            out[pin] = net
    return out


def check_head():
    """The head sheet's Pi pins against the cheat sheet's jumper table.
    Both name the Pi's pins by header position, and a jumper lands on a
    position, so the two carrying different numbers is a wrong wire.
    Four rows is the floor: the check cannot pass on nothing."""
    src = (ROOT / "tools" / "draw-schematics.py").read_text()
    i = src.index("def _v1b_body_3")     # the v1 sheet draws a Pi too, with no positions
    i = src.index('"PI", "Raspberry Pi 4 Model B"', i)
    j = src.index("conn=True", i)
    sheet = {name: int(pos) for pos, name in re.findall(r'\((\d+), "([^"]+)", "[^"]+"\)', src[i:j])}
    cs = __import__("cheatsheet")
    doc = {name: pos for name, pos, _to, _role in cs.PI_HEADER}
    bad = 0
    for name in sorted(set(doc) | set(sheet)):
        if doc.get(name) != sheet.get(name):
            print(f"  Pi {name}: cheatsheet.py says position {doc.get(name)}, the head sheet says {sheet.get(name)}")
            bad += 1
    if len(doc) < 4:
        print("  the cheat sheet's Pi table has fewer than four rows")
        bad += 1
    if not bad:
        print(f"check-sheets: {len(doc)} Pi header positions agree between the head sheet and the cheat sheet")
    return bad


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


def check_padble():
    """The pad-ble sheet's GPIO pins against the firmware that will run.

    This is the tie that was missing from pad-adapter.svg, and its
    absence cost two defects on 2026-09-21: the sheet carried the S3's
    pin numbers on a board that was a C6, and both pullups sat on one
    pad. A drawing with nothing to be held to always agrees with itself.

    The firmware is the right thing to hold it to rather than a prose
    table, because a disagreement between them is silent in the worst
    way: you wire the board exactly as the drawing says, flash firmware
    that polls three other pins, and get a pad that reads nothing with
    no error anywhere. The two files have to say one thing.
    """
    ino = ROOT / "firmware/pad-ble/pad-ble.ino"
    if not ino.exists():
        print("  firmware/pad-ble/pad-ble.ino absent: nothing to hold the pad-ble sheet to")
        return 1
    src = ino.read_text()
    fw = dict(re.findall(r"static const int (\w+)\s*=\s*(\d+);", src))

    # What the firmware's name means as a net on the sheet. The pad's
    # data lines are the only ones that differ in spelling, because the
    # schematic names a net after the signal and the firmware after the
    # pin it reads it on.
    means = {"PAD_LATCH": "PAD_LATCH", "PAD_CLOCK": "PAD_CLK",
             "PAD1_DATA": "PAD1_D0", "MODE_SW": "NC", "LED_PIN": "NC"}

    # The sheet's U1 block, read the way sheet_nets reads the v1 sheet's.
    ds = (ROOT / "tools" / "draw-schematics.py").read_text()
    # Inside sheet_padble, not from the top of the file: sheet_pad names
    # a U1 of the same part, and its MODE_SW and LED ARE wired. Anchoring
    # on the part string alone read the wrong sheet and reported the
    # other one's pins, which this check caught on its first run.
    fn = ds.index("def sheet_padble(")
    i = ds.index('"U1", "ESP32-C6-DevKitC-1 v1.2"', fn)
    j = ds.index("sh.twopin(", i)
    sheet = dict(re.findall(r'\(None, "(GPIO\d+)", "([A-Z0-9_]+)"\)', ds[i:j]))

    bad = 0
    for name, net in sorted(means.items()):
        if name not in fw:
            print(f"  the firmware does not declare {name}, which the pad-ble sheet is held to")
            bad += 1
            continue
        pin = f"GPIO{fw[name]}"
        if sheet.get(pin) != net:
            print(f"  {name}: the firmware puts it on {pin}, the pad-ble sheet has {pin} as {sheet.get(pin)!r}, want {net!r}")
            bad += 1
    extra = {g: n for g, n in sheet.items() if g not in {f"GPIO{fw[k]}" for k in means if k in fw}}
    if extra:
        print(f"  the pad-ble sheet draws GPIO pins the firmware does not name: {extra}")
        bad += 1

    # The sheet's own claim, in its note, that these are the pins the
    # BRIDGE firmware already polls a pad on. If that stops being true
    # the note is a lie and poll_pad needs editing after all.
    bridge = (ROOT / "firmware/bridge/bridge.ino").read_text()
    if "CONFIG_IDF_TARGET_ESP32C6" in bridge:
        c6 = bridge[bridge.index("#if CONFIG_IDF_TARGET_ESP32C6"):bridge.index("#else")]
        bf = dict(re.findall(r"static const int (\w+)\s*=\s*(-?\d+);", c6))
        for a, b in (("PAD_LATCH", "PAD_LATCH"), ("PAD_CLOCK", "PAD_CLOCK"), ("PAD1_DATA", "PAD_DATA")):
            if a in fw and b in bf and fw[a] != bf[b]:
                print(f"  the pad-ble sheet says these are the bridge's own pad pins, but {a} is "
                      f"GPIO{fw[a]} there and GPIO{bf[b]} in firmware/bridge")
                bad += 1
    if not bad:
        print(f"check-sheets: {len(means)} pad-ble pins agree between the sheet and firmware/pad-ble")
    return bad


def check_padble_p4():
    """The P4 sheet against the header it was read from and the firmware.

    Held differently from check_padble, and deliberately. That one
    parses the sheet's source for a literal pin block; this sheet has
    no literal block to parse, because its pins are BUILT from
    tools/p4_header.py, so parsing the source would only prove that a
    loop exists. What is worth checking is the three-way agreement:
    the header module, the drawn netlist and the firmware.

    The third leg is the one that would hurt silently. Wire the board
    exactly as the drawing says, flash firmware that polls three other
    pins, and the pad reads nothing with no error anywhere.
    """
    sys.path.insert(0, str(ROOT / "tools"))
    import p4_header as ph
    import netlist as nl_mod

    bad = 0
    sheets, _offsheet = nl_mod.collect()
    if "pad-ble-p4" not in sheets:
        print("  the P4 sheet draws nothing: netlist.collect() has no pad-ble-p4")
        return 1
    u1 = {n["pinname"]: n for n in sheets["pad-ble-p4"] if n["ref"] == "U1"}

    # 1. Every wire the header module claims is drawn, on that pin.
    for net, (pin, name) in ph.PAD_BLE.items():
        node = u1.get(name)
        if node is None:
            print(f"  the P4 sheet draws no {name} on U1, which p4_header says carries {net}")
            bad += 1
            continue
        if str(node.get("pin")) != str(pin):
            print(f"  {name}: the P4 sheet has it on pin {node.get('pin')}, p4_header says P6 pin {pin}")
            bad += 1
        if node["net"] != net:
            print(f"  {name}: the P4 sheet calls it {node['net']!r}, p4_header says {net!r}")
            bad += 1

    # 2. No pin the board has already spoken for got drawn anyway.
    for name, node in u1.items():
        if name in ph.RESERVED:
            print(f"  the P4 sheet wires {name}, which is {ph.RESERVED[name]}")
            bad += 1

    # 3. The firmware's P4 block polls the pins the sheet draws, and its
    #    two spare pins are free on this header rather than a codec's.
    src = (ROOT / "firmware/pad-ble/pad-ble.ino").read_text()
    fw = dict(re.findall(r"static const int (\w+)\s*=\s*(\d+);", src))
    p4 = dict(re.findall(r"static const int (\w+)\s*=\s*(\d+);",
                         src[src.index("#if CONFIG_IDF_TARGET_ESP32P4"):src.index("#else")]))
    for fwname, net in (("PAD_LATCH", "PAD_LATCH"), ("PAD_CLOCK", "PAD_CLK"), ("PAD1_DATA", "PAD1_D0")):
        want = ph.PAD_BLE[net][1]
        if f"GPIO{fw.get(fwname)}" != want:
            print(f"  {fwname}: the firmware polls GPIO{fw.get(fwname)}, the P4 sheet draws {want}")
            bad += 1
    for spare in ("MODE_SW", "LED_PIN"):
        g = f"GPIO{p4.get(spare)}"
        if g not in ph.free():
            print(f"  the P4 build puts {spare} on {g}, which is not free on header P6")
            bad += 1

    # 4. The USB build polls the same three pins, and its keymap is the
    #    same FILE, not a copy. Two sketches drifting on pins would be
    #    silent: wire for one, flash the other, read nothing.
    usb = ROOT / "firmware/pad-usb/pad-usb.ino"
    if usb.exists():
        u = dict(re.findall(r"static const int (\w+)\s*=\s*(\d+);", usb.read_text()))
        for fwname, net in (("PAD_LATCH", "PAD_LATCH"), ("PAD_CLOCK", "PAD_CLK"), ("PAD1_DATA", "PAD1_D0")):
            want = ph.PAD_BLE[net][1]
            if f"GPIO{u.get(fwname)}" != want:
                print(f"  pad-usb {fwname}: polls GPIO{u.get(fwname)}, the P4 sheet draws {want}")
                bad += 1
        km = ROOT / "firmware/pad-usb/keymap.h"
        if not km.is_symlink():
            print("  firmware/pad-usb/keymap.h is a copy, not a symlink: the two builds will drift")
            bad += 1
        elif km.resolve() != (ROOT / "firmware/pad-ble/keymap.h").resolve():
            print(f"  firmware/pad-usb/keymap.h points at {km.resolve()}, not pad-ble's")
            bad += 1

    if not bad:
        print(f"check-sheets: {len(ph.PAD_BLE)} P4 pins agree between p4_header, the sheet, pad-ble and pad-usb")
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
    bad += check_head()
    bad += check_padble()
    bad += check_padble_p4()
    # The committed SVGs are what the generator writes.
    n_sheets = 0
    with tempfile.TemporaryDirectory() as d:
        for gen in ("draw-schematics.py", "breadboard.py", "wiring-diagram.py"):
            subprocess.run([sys.executable, str(ROOT / "tools" / gen), d], check=True, capture_output=True)
        for p in sorted(Path(d).glob("*.svg")):
            n_sheets += 1
            committed = ROOT / "docs" / p.name
            if not committed.exists() or committed.read_bytes() != p.read_bytes():
                gen = ("breadboard.py" if p.name.startswith("breadboard") else
                       "wiring-diagram.py" if p.name.startswith("wiring") else "draw-schematics.py")
                print(f"  docs/{p.name} is not what {gen} writes: regenerate it")
                bad += 1
    if not n_sheets:
        print("  the generator wrote no sheets")
        bad += 1
    print(f"check-sheets: the {n_sheets} sheets are current" if not bad else "")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
