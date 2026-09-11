#!/usr/bin/env python3
"""The breadboard picture: where each part sits, and every wire.

  python3 tools/breadboard.py [outdir]     # -> docs/breadboard-v1b.svg

A schematic says what connects to what. It does not say where to put
anything, and "where" is the whole problem when you are holding a
breadboard for the first time.

So this is split the way everything else here is split. **The placement
is authored**: which column each chip starts in, which lead comes in
where, and that is a judgement nobody can derive. **Every wire is
derived** from `tools/netlist.py`, which reads the schematic. So the
picture cannot show a connection the schematic does not have, or miss
one that it does, and when the schematic changes the wires move.

The hole a pin lands in is computed, not placed: a DIP with its notch to
the left puts pin 1 at the bottom-left and counts anticlockwise, so pin
i of an N-pin package is at column c0+(i-1) in the lower half for the
first N/2, and at column c0+(N-i) in the upper half for the rest. Get
that wrong and every wire is wrong, so `--check` asserts it against the
three chips' known supply pins.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from loadmod import load  # noqa: E402

P = 26                     # hole pitch
COLS = 40
X0 = 200                   # x of column 1
Y_RAIL_TP, Y_RAIL_TN = 196, 222
Y_A = 276                  # first row of the upper half
Y_F = 432                  # first row of the lower half (across the channel)
Y_RAIL_BN, Y_RAIL_BP = 596, 622
BOT_BAND = 662
W, H = 1900, 980

UPPER = "ABCDE"
LOWER = "FGHIJ"

# ------------------------------------------------------------- AUTHORED
# Where things sit. This is the part no netlist can tell you.
#
# AS BUILT, read off the photographs of 2026-09-11 (docs/as-built-v1b.md):
# the three chips went in with their notch toward the HIGHER column
# numbers, so pin 1 is in the lower half at each chip's highest column.
# "notch" says which way; the hole rule below follows it. Columns were
# counted from the printed 10, 20 and 30 marks and are believed to
# within one column; step 3.1 is what proves them.
CHIPS = {
    "U1": {"col": 9, "pins": 14, "notch": "right", "label": "74HCT04", "note": "inverter"},
    "U2": {"col": 17, "pins": 16, "notch": "right", "label": "74HC165", "note": "the pad the console reads"},
    "U3": {"col": 26, "pins": 16, "notch": "right", "label": "74HC595", "note": "the byte the UNO writes"},
}
# Decoupling: rail to rail, in the empty column beside each chip.
CAPS = {"C1": 16, "C2": 25, "C3": 34}
# The trigger resistor, out of the way at the end of the board.
RES = {"R1": (36, 38)}
# The cut cable's lead colours, which are the ones in your hand. Pin
# order is the measured pinout: 1 GND, 2 CLK, 3 OUT0, 4 D0, 5 +5V.
LEAD = {1: ("yellow", "#d9b400"), 2: ("blue", "#1b64c8"), 3: ("black", "#222222"),
        4: ("green", "#1f9c53"), 5: ("red", "#d02b2b")}
PALETTE = ["#7a3fbf", "#0f8f9e", "#b5651d", "#8d1f5e", "#3f6f2a", "#5b5bd6",
           "#a8471f", "#1f7a8c", "#7d4a1f", "#4a4a9c", "#96206a", "#2f7d4f"]

STYLE = """<style>
 text{font-family:ui-sans-serif,'DejaVu Sans',sans-serif}
 .bb{fill:#f6f4ee;stroke:#c9c4b6;stroke-width:2}
 .chan{fill:#e6e2d6;stroke:#c9c4b6;stroke-width:1}
 .hole{fill:#ffffff;stroke:#c2bcae;stroke-width:1}
 .railp{stroke:#d02b2b;stroke-width:2;fill:none}
 .railn{stroke:#1b64c8;stroke-width:2;fill:none}
 .dip{fill:#2b2b2b;stroke:#000;stroke-width:1}
 .dipt{fill:#ffffff;font-size:13px;font-weight:700}
 .dips{fill:#cfcfcf;font-size:10.5px}
 .leg{fill:#c9ccd1;stroke:#8b9096;stroke-width:1}
 .col{fill:#8a8578;font-size:10px}
 .row{fill:#8a8578;font-size:11px;font-weight:700}
 .term{fill:#ffffff;stroke:#333;stroke-width:1.4}
 .termt{font-size:11.5px;font-weight:700;fill:#111}
 .w{fill:none;stroke-width:2.6;stroke-linecap:round;stroke-linejoin:round}
 .wn{font-size:10px;font-weight:700}
 .h1{font-size:24px;font-weight:700;fill:#111}
 .h2{font-size:13px;fill:#444}
 .k{font-size:12px;fill:#111}
 .kb{font-size:12px;font-weight:700;fill:#111}
 .pass{fill:#ffffff;stroke:#333;stroke-width:1.4}
</style>"""


def cx(col):
    return X0 + (col - 1) * P


def cy(row):
    return Y_A + UPPER.index(row) * P if row in UPPER else Y_F + LOWER.index(row) * P


def dip_hole(ref, pin):
    """Which column and half a package pin lands in, counting
    anticlockwise from pin 1 as the package does. Notch to the left: pin
    1 bottom-left, the first half runs left to right along the lower
    row. Notch to the right (the chip turned round): pin 1 bottom-RIGHT,
    the first half runs right to left along the lower row, the second
    half left to right along the upper row."""
    c = CHIPS[ref]
    n, c0 = c["pins"], c["col"]
    h = n // 2
    if c.get("notch", "left") == "right":
        return (c0 + h - pin, "lower") if pin <= h else (c0 + pin - h - 1, "upper")
    if pin <= h:
        return c0 + (pin - 1), "lower"
    return c0 + (n - pin), "upper"


class Draw:
    def __init__(self):
        self.o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">',
                  STYLE, f'<rect width="{W}" height="{H}" fill="#ffffff"/>']

    def add(self, s):
        self.o.append(s)

    def text(self, x, y, s, cls, anchor="start"):
        self.add(f'<text class="{cls}" x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}">{s}</text>')

    def board(self):
        x0, x1 = cx(1) - P, cx(COLS) + P
        self.add(f'<rect class="bb" x="{x0}" y="{Y_RAIL_TP-38}" width="{x1-x0}" height="{Y_RAIL_BP+38-(Y_RAIL_TP-38)}" rx="8"/>')
        self.add(f'<rect class="chan" x="{x0}" y="{cy("E")+P/2}" width="{x1-x0}" height="{cy("F")-cy("E")-P}"/>')
        for y, cls in ((Y_RAIL_TP, "railp"), (Y_RAIL_TN, "railn"), (Y_RAIL_BN, "railn"), (Y_RAIL_BP, "railp")):
            self.add(f'<line class="{cls}" x1="{x0+14}" y1="{y}" x2="{x1-14}" y2="{y}"/>')
            for col in range(1, COLS + 1):
                if col % 6:
                    self.add(f'<circle class="hole" cx="{cx(col)}" cy="{y}" r="3.4"/>')
        for row in UPPER + LOWER:
            for col in range(1, COLS + 1):
                self.add(f'<circle class="hole" cx="{cx(col)}" cy="{cy(row)}" r="3.6"/>')
            self.text(x0 + 8, cy(row) + 4, row, "row")
            self.text(x1 - 8, cy(row) + 4, row, "row", "end")
        for col in range(1, COLS + 1, 5):
            self.text(cx(col), cy("A") - 12, str(col), "col", "middle")
            self.text(cx(col), cy("J") + 20, str(col), "col", "middle")

    def chip(self, ref):
        c = CHIPS[ref]
        n, c0 = c["pins"], c["col"]
        x0, x1 = cx(c0) - P / 2 - 2, cx(c0 + n // 2 - 1) + P / 2 + 2
        yt, yb = cy("E") - 9, cy("F") + 9
        for pin in range(1, n + 1):
            col, half = dip_hole(ref, pin)
            y = cy("F") if half == "lower" else cy("E")
            self.add(f'<rect class="leg" x="{cx(col)-4}" y="{y-7}" width="8" height="14" rx="2"/>')
        self.add(f'<rect class="dip" x="{x0}" y="{yt}" width="{x1-x0}" height="{yb-yt}" rx="3"/>')
        right = c.get("notch", "left") == "right"
        if right:
            self.add(f'<path class="dip" d="M{x1} {(yt+yb)/2-11} a11 11 0 0 1 0 22" fill="#111"/>')
        else:
            self.add(f'<path class="dip" d="M{x0} {(yt+yb)/2-11} a11 11 0 0 0 0 22" fill="#111"/>')
        self.text((x0 + x1) / 2, (yt + yb) / 2 - 2, f"{ref}  {c['label']}", "dipt", "middle")
        self.text((x0 + x1) / 2, (yt + yb) / 2 + 14, c["note"], "dips", "middle")
        pin1_col, _ = dip_hole(ref, 1)
        self.add(f'<circle cx="{cx(pin1_col)}" cy="{yb-9}" r="3" fill="#ffffff"/>')
        self.text(cx(pin1_col), cy("J") + 36, f"{ref} pin 1", "col", "middle")


# Where an off-board thing's terminals sit. Order is the order they are
# first seen in the netlist, which is the order the schematic draws them.
TERMINALS = {
    "J1": {"x": 108, "y": 262, "title": "J1  console cable", "sub": "the plug half, into port 1"},
    "A1": {"x": 1360, "y": 214, "title": "A1  Arduino UNO", "sub": "5 V logic"},
    "J2": {"x": 1660, "y": 214, "title": "J2  pad cable", "sub": "the pad half"},
}


def endpoint(ref, pin, pinname, terms):
    """Where a wire for this pin actually plugs in. A package pin is not
    a hole you can use: the leg is already in it. The wire goes into
    another hole in the same column, which is the same node."""
    if ref in CHIPS:
        col, half = dip_hole(ref, pin)
        row = "C" if half == "upper" else "H"
        return {"x": cx(col), "y": cy(row), "half": half, "at": f"{ref}-{pin} (col {col} row {row})"}
    if ref in CAPS:
        y = Y_RAIL_BP if pin == 1 else Y_RAIL_BN
        return {"x": cx(CAPS[ref]), "y": y, "half": "rail", "at": f"{ref} on the bottom rails"}
    if ref in RES:
        c = RES[ref][0] if pin == 1 else RES[ref][1]
        return {"x": cx(c), "y": cy("H"), "half": "lower", "at": f"{ref} col {c} row H"}
    t = terms[(ref, pinname)]
    return {"x": t["x"], "y": t["y"], "half": "term", "at": f"{ref} {pinname}"}


def jumper(a, b, k):
    """One wire, drawn the way a jumper actually lies: a curve from hole
    to hole, bowed to one side so wires between the same pair of columns
    do not sit on top of each other.

    An earlier version routed these as orthogonal runs in lanes above
    and below the board. Every wire was correct and the picture was
    unreadable: thirty-seven parallel runs with no way for the eye to
    follow one of them. A curve is both more honest about what a jumper
    looks like and much easier to trace."""
    x1, y1, x2, y2 = a["x"], a["y"], b["x"], b["y"]
    dx, dy = x2 - x1, y2 - y1
    dist = max((dx * dx + dy * dy) ** 0.5, 1)
    side = 1 if k % 2 else -1
    bow = min(0.22 * dist, 130) * side
    mx, my = (x1 + x2) / 2 - dy / dist * bow, (y1 + y2) / 2 + dx / dist * bow
    return f"M{x1:.0f} {y1:.0f} Q{mx:.0f} {my:.0f} {x2:.0f} {y2:.0f}", (
        (x1 + 2 * mx + x2) / 4, (y1 + 2 * my + y2) / 4)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir", nargs="?", default=str(ROOT / "docs"))
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()

    nl = load(ROOT / "tools" / "netlist.py", "nl")
    sheets, _off = nl.collect()
    nodes = sheets["bench-v1b"]

    # The pin-to-hole rule is the one thing here that silently wrecks
    # every wire if it is wrong, so it is asserted against pins whose
    # position is known from the packages: a 16-pin part has VCC at 16,
    # top-left, and GND at 8, bottom-right.
    # Notch right, as built: VCC (16) upper at the HIGHEST column, GND
    # (8) lower at the lowest; pin 1 lower at the highest.
    for ref, n in (("U2", 16), ("U1", 14)):
        c0, h = CHIPS[ref]["col"], n // 2
        assert CHIPS[ref]["notch"] == "right"
        assert dip_hole(ref, 1) == (c0 + h - 1, "lower"), dip_hole(ref, 1)
        assert dip_hole(ref, h) == (c0, "lower"), dip_hole(ref, h)
        assert dip_hole(ref, h + 1) == (c0, "upper"), dip_hole(ref, h + 1)
        assert dip_hole(ref, n) == (c0 + h - 1, "upper"), dip_hole(ref, n)
    # And the rule for a chip the other way round, which nothing on this
    # board uses now but the drawing still has to get right.
    CHIPS["_t"] = {"col": 1, "pins": 16, "notch": "left"}
    assert dip_hole("_t", 1) == (1, "lower") and dip_hole("_t", 8) == (8, "lower")
    assert dip_hole("_t", 9) == (8, "upper") and dip_hole("_t", 16) == (1, "upper")
    del CHIPS["_t"]
    if a.check:
        print("breadboard: the pin-to-hole rule holds for both package sizes and both notch directions")
        return 0

    nets = nl.nets_of(nodes)

    # Terminals for the off-board things, in netlist order.
    terms, seen = {}, {r: 0 for r in TERMINALS}
    for n in nodes:
        key = (n["ref"], n["pinname"])
        if n["ref"] in TERMINALS and key not in terms:
            t = TERMINALS[n["ref"]]
            terms[key] = {"x": t["x"], "y": t["y"] + seen[n["ref"]] * 30, "name": n["pinname"]}
            seen[n["ref"]] += 1

    d = Draw()
    d.text(60, 60, "Bridge v1b on the breadboard: where everything goes", "h1")
    d.text(60, 84, "Placement is the board as built on 2026-09-11, read off its photographs: notches toward the high columns, "
                   "pin 1 lower right. Every wire is read out of the schematic, so this cannot show a connection it does not have.", "h2")
    d.board()
    for ref in CHIPS:
        d.chip(ref)
    for ref, t in TERMINALS.items():
        rows = [v for (r, _p), v in terms.items() if r == ref]
        if not rows:
            continue
        y0, y1 = min(v["y"] for v in rows), max(v["y"] for v in rows)
        left = t["x"] < X0
        d.add(f'<rect class="term" x="{t["x"]-(96 if left else 8)}" y="{y0-46}" width="104" height="{y1-y0+58}" rx="5"/>')
        d.text(t["x"] - (92 if left else 4), y0 - 30, t["title"], "kb")
        d.text(t["x"] - (92 if left else 4), y0 - 16, t["sub"], "col")
        for v in rows:
            d.add(f'<circle cx="{v["x"]}" cy="{v["y"]}" r="4" fill="#333"/>')
            d.text(t["x"] - (12 if left else -12), v["y"] + 4, v["name"], "termt", "end" if left else "start")

    # Decoupling sits rail to rail beside its chip, and needs no wire.
    for ref, col in CAPS.items():
        d.add(f'<rect class="pass" x="{cx(col)-9}" y="{Y_RAIL_BN+4}" width="18" height="{Y_RAIL_BP-Y_RAIL_BN-8}" rx="3"/>')
        d.text(cx(col) + 14, (Y_RAIL_BN + Y_RAIL_BP) / 2 + 4, f"{ref} 100nF", "col")
    for ref, (c1, c2) in RES.items():
        d.add(f'<rect class="pass" x="{cx(c1)}" y="{cy("H")-7}" width="{cx(c2)-cx(c1)}" height="14" rx="3"/>')
        d.text((cx(c1) + cx(c2)) / 2, cy("H") - 12, f"{ref} 100R", "col", "middle")
        d.text(cx(c2) + 12, cy("G") + 4, "to the scope EXT TRIG", "col")

    # ---------------------------------------------------------- the wires
    wires = []
    ci = 0
    rails = []
    for net, ns in sorted(nets.items(), key=lambda kv: (kv[0] in ("+5V", "GND"), kv[0])):
        pts = [endpoint(n["ref"], n["pin"], n["pinname"], terms) for n in ns]
        if net in ("+5V", "GND"):
            col = "#d02b2b" if net == "+5V" else "#1b64c8"
            for pt, n in zip(pts, ns):
                if pt["half"] == "rail":
                    continue
                rail = (Y_RAIL_TP if net == "+5V" else Y_RAIL_TN) if pt["half"] == "upper" \
                    else (Y_RAIL_BP if net == "+5V" else Y_RAIL_BN)
                d.add(f'<path class="w" stroke="{col}" opacity="0.9" d="M{pt["x"]:.0f} {pt["y"]:.0f} L{pt["x"]:.0f} {rail}"/>')
                rails.append((net, pt["at"]))
            continue
        if len(pts) < 2:
            continue
        lead = None
        for n in ns:
            if n["ref"] in ("J1", "J2") and isinstance(n["pin"], int) and n["pin"] in LEAD:
                lead = LEAD[n["pin"]]
        colour = lead[1] if lead else PALETTE[ci % len(PALETTE)]
        ci += 0 if lead else 1
        order = sorted(range(len(pts)), key=lambda i: pts[i]["x"])
        for k in range(len(order) - 1):
            p1, p2 = pts[order[k]], pts[order[k + 1]]
            n = len(wires) + 1
            dstr, (mx, my) = jumper(p1, p2, n)
            d.add(f'<path class="w" stroke="{colour}" opacity="0.85" d="{dstr}"/>')
            d.add(f'<circle cx="{mx:.0f}" cy="{my:.0f}" r="9" fill="#ffffff" stroke="{colour}" stroke-width="1.6"/>')
            d.text(mx, my + 4, str(n), "wn", "middle")
            wires.append((n, net + (f", the {lead[0]} lead" if lead else ""), p1["at"], p2["at"], colour))

    # ------------------------------------------------------------ the key
    ky = BOT_BAND + 70
    d.text(60, ky, f"{len(wires)} numbered jumpers, and {len(rails)} short wires to the rails", "h1")
    d.text(60, ky + 22, "Every one of these is read out of the schematic. Red stubs go to the nearest + rail, blue stubs to "
                        "the nearest - rail; they are not numbered because they are all the same instruction.", "h2")
    col_w, per = 600, (len(wires) + 2) // 3
    for i, (n, net, at1, at2, colour) in enumerate(wires):
        cxx = 60 + (i // per) * col_w
        yy = ky + 52 + (i % per) * 19
        d.add(f'<circle cx="{cxx+9}" cy="{yy-4}" r="9" fill="#ffffff" stroke="{colour}" stroke-width="1.6"/>')
        d.text(cxx + 9, yy, str(n), "wn", "middle")
        d.text(cxx + 26, yy, f"{net}:  {at1}  to  {at2}", "k")
    d.add("</svg>")
    out = Path(a.outdir) / "breadboard-v1b.svg"
    out.write_text("\n".join(d.o))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
