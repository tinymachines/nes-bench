#!/usr/bin/env python3
"""Draws the nes-bench schematics as SVG: v1 (docs/wiring.md as built),
v2 (the extended bridge), the logical/timing diagram, and the pad
adapter. Net-label schematic convention: every pin carries the name of
its net; same name, same wire. Power pins are rails. Nothing here is
built or measured; every timing number on the logical sheet is marked
authored until B0 replaces it.
"""
import sys
from pathlib import Path

PITCH = 26
STYLE = """
  <style>
    text { font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; fill: #1f2328; }
    .title { font-size: 15px; font-weight: 700; font-family: ui-sans-serif, system-ui, sans-serif; }
    .sub { font-size: 11px; fill: #57606a; font-family: ui-sans-serif, system-ui, sans-serif; }
    .ref { font-size: 12px; font-weight: 700; }
    .part { font-size: 10px; fill: #57606a; }
    .pin { font-size: 9.5px; }
    .pinno { font-size: 9px; fill: #57606a; }
    .linkflag { fill: #fdf3e3; stroke: #a35c00; stroke-width: 1.1; }
    .linkno { font-size: 9px; fill: #a35c00; font-weight: 700; }
    .net { font-size: 9.5px; fill: #0a5b9c; font-weight: 600; }
    .rail5 { font-size: 9px; fill: #b3261e; font-weight: 700; }
    .rail3 { font-size: 9px; fill: #b35c00; font-weight: 700; }
    .gnd { font-size: 9px; fill: #1f2328; font-weight: 700; }
    .note { font-size: 10px; fill: #57606a; font-family: ui-sans-serif, system-ui, sans-serif; }
    .box { fill: #ffffff; stroke: #1f2328; stroke-width: 1.3; }
    .offsheet { fill: #eaf3fb; stroke: #0a5b9c; stroke-width: 1.1; }
    .conn { fill: #f3f5f7; stroke: #1f2328; stroke-width: 1.3; }
    .zone { fill: none; stroke: #57606a; stroke-dasharray: 5 4; stroke-width: 1; }
    .lead { stroke: #1f2328; stroke-width: 1; }
    .wire { stroke: #0a5b9c; stroke-width: 1.2; fill: none; }
    .w5 { stroke: #b3261e; stroke-width: 1.2; fill: none; }
    .w3 { stroke: #b35c00; stroke-width: 1.2; fill: none; }
    .wg { stroke: #1f2328; stroke-width: 1.2; fill: none; }
    .lane { stroke: #1f2328; stroke-width: 1.4; fill: none; }
    .lanelbl { font-size: 11px; font-weight: 700; }
    .win { fill: #b3261e; fill-opacity: 0.10; stroke: none; }
    .safe { fill: #1a7f37; fill-opacity: 0.12; stroke: none; }
    .mark { stroke: #0a5b9c; stroke-width: 1.2; stroke-dasharray: 3 3; }
    .auth { font-size: 9px; fill: #b3261e; font-family: ui-sans-serif, system-ui, sans-serif; font-style: italic; }
  </style>
"""

RAIL_CLASS = {"+5V": "rail5", "3V3": "rail3", "GND": "gnd", "VBAT": "rail3"}

# Nets that leave the drawing: a cable, a radio link, a mains lead, an
# instrument input. They have one end on the sheet on purpose, and the
# rule check reads this same set so it can tell them from a wire that
# stops in mid air. Drawn with an off-sheet flag rather than a plain
# label, so the sheet says it too.
OFFSHEET = {
    "PI_USB": "USB to the Pi", "serial": "115200 to the Pi", "LAN": "SCPI over the LAN",
    "EXT_TRIG": "scope EXT TRIG", "VIDEO": "console composite video", "radio": "BLE",
    "USB_HID": "USB to a host", "AC_LEAD_A": "AC adapter lead", "AC_LEAD_B": "AC adapter lead",
    "PWR_DRIVE": "from the Pi's GPIO27", "RESET_PAD": "console reset pads",
    "RESET_GND": "console reset pads",
}



# ------------------------------------------------------------------ layout
# Authored arrangement, derived coordinates: the same split as the PCB
# placer and the breadboard sheet. A sheet says which band, column and
# row each part sits in; nothing below types an x or a y. The body is
# drawn twice, once to measure every part where it stands and once to
# draw it where the measurements say it goes, so adding a pin to a chip
# moves its neighbours instead of quietly overlapping them.
#
# The reason this exists: a sheet whose coordinates are authored has an
# authored SIZE, and a page has a fixed one. bench-v1b was 1900 by 1000
# and landed on a letter page at 63%, which puts a 9.5 px pin name at
# 4.5 pt. `plan()` derives the size from the parts and `fits()` refuses
# an arrangement that will not print.

CHARW = 6.2        # advance of the pin/net monospace at its own size
NOTE_CHARW = 5.4   # advance of the note sans at 10 px
PART_CHARW = 6.0   # advance of the part-name sans at 10 px
NOTE_LH = 13
LEAD = 26          # pin lead length: the gap a net flag hangs in
GAP = 30           # between columns of a band
BAND_GAP = 24      # between bands
PAD = 22           # band box to sheet edge
BAND_TOP = 26      # band label to the first part
HEADING_H = 60     # the sheet's own title and subtitle, above the first band


def flagw(name, links=()):
    """How far a net flag reaches out past the end of a pin lead. The
    drawing code below is what these numbers describe; if a flag is
    drawn wider than this says, parts overlap on a derived sheet."""
    if name in RAIL_CLASS:
        return max(16.0, CHARW * len(name) / 2 + 6)
    if name in links:
        return 20 + CHARW * len(name) + 6.6 * len(links[name])
    if name in OFFSHEET:
        return 10 + CHARW * len(name)
    if name in ("NC", "", None):
        return 8.0
    return CHARW * len(name) + 18


def plan(measured, target=None):
    """Coordinates for every slot, and the sheet size they imply.

    `measured` is slot -> (x0, y0, x1, y1) about that slot's anchor.
    Columns are as wide as their widest part, rows as tall as their
    tallest, and a band is as wide as its widest row. Returns
    (plan, w, h, bands) where bands maps a band index to its box."""
    keys = list(measured)
    out, bandbox = {}, {}
    y = HEADING_H + 6      # clear of the sheet's own heading
    for b in sorted({k[0] for k in keys}):
        ks = [k for k in keys if k[0] == b]
        cols, rows = sorted({k[1] for k in ks}), sorted({k[2] for k in ks})
        colw, colpad = {}, {}
        for c in cols:
            bx = [measured[k] for k in ks if k[1] == c]
            colw[c] = max(v[2] - v[0] for v in bx)
            colpad[c] = max(-v[0] for v in bx)
        rowh, rowpad = {}, {}
        for r in rows:
            bx = [measured[k] for k in ks if k[2] == r]
            rowh[r] = max(v[3] - v[1] for v in bx)
            rowpad[r] = max(-v[1] for v in bx)
        cx, colx = 0.0, {}
        for c in cols:
            colx[c] = cx
            cx += colw[c] + GAP
        ry, rowy = 0.0, {}
        for r in rows:
            rowy[r] = ry
            ry += rowh[r] + BAND_GAP
        bw = cx - GAP
        bh = ry - BAND_GAP
        bandbox[b] = (PAD, y, bw + 2 * BAND_TOP, bh + BAND_TOP + 16)
        for k in ks:
            out[k] = (PAD + BAND_TOP + colx[k[1]] + colpad[k[1]],
                      y + BAND_TOP + rowy[k[2]] + rowpad[k[2]])
        y += bh + BAND_TOP + 16 + BAND_GAP
    wide = max(v[2] for v in bandbox.values())
    bandbox = {b: (v[0], v[1], wide, v[3]) for b, v in bandbox.items()}
    return out, PAD + wide + PAD, y - BAND_GAP + PAD, bandbox


def fits(name, w, h, box, floor_pt=5.0, smallest_px=9.0):
    """Refuse an arrangement that will not print.

    `box` is the drawing area of the page it is going on, in the same
    96 dpi units. The sheet is placed at min(bw/w, bh/h), so the
    smallest text on it prints at that fraction of `smallest_px`, times
    0.75 pt per unit. Below about 5 pt a pin name on a printed sheet is
    a smudge, and the whole point of the package is that somebody can
    build from it at the bench."""
    scale = min(box[0] / w, box[1] / h)
    pt = smallest_px * scale * 0.75
    assert pt >= floor_pt, (
        f"{name} is {w:.0f} by {h:.0f} and would place at {scale*100:.0f}% "
        f"in a {box[0]:.0f} by {box[1]:.0f} box, printing its smallest text at "
        f"{pt:.1f} pt. The floor is {floor_pt} pt. Give the band fewer columns, "
        f"move a band onto a second sheet, or give the sheet a bigger page.")
    return scale


def laid(path, title, sub, body, box, links=None):
    """Draw `body` twice: measure, then place."""
    m = Sheet(0, 0, title, sub, measure=True, links=links)
    body(m)
    p, w, h, bands = plan(m.boxes)
    fits(Path(path).name, w, h, box)
    sh = Sheet(w, h, title, sub, plan=p, bands=bands, links=links)
    for b, (bx, by, bw, bh) in sorted(bands.items()):
        sh.zone(bx, by, bw, bh, m.bands.get(b, ""))
    body(sh)
    sh.done(path)

class Sheet:
    def __init__(self, w, h, title, sub, measure=False, plan=None, bands=None, links=None):
        self.w, self.h = w, h
        self.measuring, self.plan, self.bandbox = measure, plan, bands or {}
        self.links = links or {}
        self.boxes, self.bands, self.cur = {}, {}, None
        if measure:
            self.o = []
            return
        # The heading is its own group, and says how tall it is. A sheet
        # read on its own needs to name itself; the same sheet placed in
        # a frame does not, because the title block already does, and
        # two bold titles a hand's width apart is how a package starts
        # looking like a slide deck.
        self.o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-label="{title}">',
                  STYLE, f'<rect x="0" y="0" width="{w}" height="{h}" fill="#ffffff"/>',
                  f'<g class="sheet-heading" data-height="{HEADING_H}">',
                  f'<text class="title" x="24" y="30">{title}</text>',
                  f'<text class="sub" x="24" y="46">{sub}</text>', '</g>']

    def add(self, s):
        self.o.append(s)

    # ------------------------------------------------------ derived layout
    def slot(self, band, col, row=0, label=None):
        """Name the place the next part goes. Returns the (x, y) to draw
        it at, which is (0, 0) while measuring and the derived
        coordinate afterwards, so a part-drawing helper needs no idea
        which pass it is in."""
        self.cur = (band, col, row)
        if label:
            self.bands[band] = label
        if self.measuring:
            self.boxes.setdefault(self.cur, (0.0, 0.0, 0.0, 0.0))
            return 0, 0
        return self.plan[self.cur]

    def grow(self, x0, y0, x1, y1):
        """Record how much room the part just drawn wanted. Only the
        measuring pass keeps it."""
        if not self.measuring or self.cur is None:
            return
        b = self.boxes[self.cur]
        self.boxes[self.cur] = (min(b[0], x0), min(b[1], y0), max(b[2], x1), max(b[3], y1))

    def text(self, x, y, s, cls, anchor="start"):
        if self.measuring:
            return
        s = s.replace("&", "&amp;").replace("<", "&lt;")
        self.add(f'<text class="{cls}" x="{x}" y="{y}" text-anchor="{anchor}">{s}</text>')

    def note(self, x, y, lines):
        self.grow(x, y - 11, x + NOTE_CHARW * max(len(l) for l in lines),
                  y + NOTE_LH * (len(lines) - 1) + 5)
        if self.measuring:
            return
        for i, l in enumerate(lines):
            self.text(x, y + i * NOTE_LH, l, "note")

    def zone(self, x, y, w, h, label):
        if self.measuring:
            return
        self.add(f'<rect class="zone" x="{x}" y="{y}" width="{w}" height="{h}" rx="6"/>')
        self.text(x + 8, y + 14, label, "sub")

    def netlabel(self, x, y, name, side):
        """A net flag at the end of a pin lead. Rails get their symbol."""
        if self.measuring:
            return
        if name in self.links:
            dest = self.links[name]
            w = flagw(name, self.links)
            if side == "R":
                self.add(f'<path class="linkflag" d="M{x+w} {y} L{x+w-10} {y-9} L{x} {y-9} '
                         f'L{x} {y+9} L{x+w-10} {y+9} Z"/>')
                self.text(x + 6, y + 3.5, name, "net")
                self.text(x + w - 13, y + 3.5, dest, "linkno", "end")
            else:
                self.add(f'<path class="linkflag" d="M{x-w} {y} L{x-w+10} {y-9} L{x} {y-9} '
                         f'L{x} {y+9} L{x-w+10} {y+9} Z"/>')
                self.text(x - w + 14, y + 3.5, name, "net")
                self.text(x - 6, y + 3.5, dest, "linkno", "end")
            return
        if name in RAIL_CLASS:
            cls = RAIL_CLASS[name]
            if name == "GND":
                self.add(f'<line class="wg" x1="{x}" y1="{y}" x2="{x}" y2="{y+8}"/>'
                         f'<line class="wg" x1="{x-6}" y1="{y+8}" x2="{x+6}" y2="{y+8}"/>'
                         f'<line class="wg" x1="{x-3}" y1="{y+11}" x2="{x+3}" y2="{y+11}"/>')
            else:
                self.add(f'<line class="{"w5" if name == "+5V" else "w3"}" x1="{x}" y1="{y}" x2="{x}" y2="{y-9}"/>'
                         f'<line class="{"w5" if name == "+5V" else "w3"}" x1="{x-5}" y1="{y-9}" x2="{x+5}" y2="{y-9}"/>')
                self.text(x, y - 11, name, cls, "middle")
            return
        if name in OFFSHEET:
            w = 8 + 6.2 * len(name)
            x0 = x if side == "R" else x - w
            self.add(f'<path class="offsheet" d="M{x0} {y-8} L{x0+w-8} {y-8} L{x0+w} {y} '
                     f'L{x0+w-8} {y+8} L{x0} {y+8} Z"/>')
            self.text(x0 + 5, y + 3.5, name, "net")
            return
        if name in ("NC", ""):
            self.add(f'<line class="lead" x1="{x-3}" y1="{y-3}" x2="{x+3}" y2="{y+3}"/><line class="lead" x1="{x-3}" y1="{y+3}" x2="{x+3}" y2="{y-3}"/>')
            return
        tw = 6.2 * len(name) + 10
        if side == "L":
            self.add(f'<path class="wire" d="M{x},{y} l-6,-6 h-{tw} v12 h{tw} z"/>')
            self.text(x - 9, y + 3.5, name, "net", "end")
        else:
            self.add(f'<path class="wire" d="M{x},{y} l6,-6 h{tw} v12 h-{tw} z"/>')
            self.text(x + 9, y + 3.5, name, "net", "start")

    def chip(self, x, y, w, ref, part, left, right, conn=False, extra=None):
        """left/right: list of (pin number, pin name, net). Returns height."""
        n = max(len(left), len(right))
        h = n * PITCH + 50
        # The part number goes inside the box, so the box is at least as
        # wide as the part number. The extra line goes under it, where a
        # note on a symbol belongs, and is measured: it used to be drawn
        # inside and ran out through the right-hand wall of every
        # connector on the sheet.
        w = max(w, 14 + PART_CHARW * len(part))
        lw = max([flagw(net, self.links) for _, _, net in left], default=0)
        rw = max([flagw(net, self.links) for _, _, net in right], default=0)
        self.grow(x - (LEAD + lw if left else 0), y,
                  max(x + w + (LEAD + rw if right else 0),
                      x + (PART_CHARW * len(extra) if extra else 0)),
                  y + h + (17 if extra else 0))
        if self.measuring:
            return h
        self.add(f'<rect class="{"conn" if conn else "box"}" x="{x}" y="{y}" width="{w}" height="{h}" rx="3"/>')
        self.text(x + 6, y + 14, ref, "ref")
        self.text(x + 6, y + 26, part, "part")
        if extra:
            self.text(x + 1, y + h + 13, extra, "part")
        for i, (no, nm, net) in enumerate(left):
            py = y + 50 + i * PITCH + 6
            self.add(f'<line class="lead" x1="{x-26}" y1="{py}" x2="{x}" y2="{py}"/>')
            self.text(x + 5, py + 3.5, nm, "pin")
            if no is not None: self.text(x - 4, py - 2, str(no), "pinno", "end")
            self.netlabel(x - 26, py, net, "L")
        for i, (no, nm, net) in enumerate(right):
            py = y + 50 + i * PITCH + 6
            self.add(f'<line class="lead" x1="{x+w}" y1="{py}" x2="{x+w+26}" y2="{py}"/>')
            self.text(x + w - 5, py + 3.5, nm, "pin", "end")
            if no is not None: self.text(x + w + 4, py - 2, str(no), "pinno", "start")
            self.netlabel(x + w + 26, py, net, "R")
        return h

    def twopin(self, x, y, ref, part, net_a, net_b, horizontal=True):
        """A resistor or capacitor drawn as a labelled box between two nets."""
        self.grow(x - flagw(net_a, self.links), y - 16,
                  x + 80 + flagw(net_b, self.links), y + 16)
        if self.measuring:
            return
        if horizontal:
            self.netlabel(x, y, net_a, "L")
            self.add(f'<line class="lead" x1="{x}" y1="{y}" x2="{x+18}" y2="{y}"/>'
                     f'<rect class="box" x="{x+18}" y="{y-7}" width="44" height="14"/>'
                     f'<line class="lead" x1="{x+62}" y1="{y}" x2="{x+80}" y2="{y}"/>')
            self.text(x + 40, y - 10, ref, "pinno", "middle")
            self.text(x + 40, y + 4, part, "pin", "middle")
            self.netlabel(x + 80, y, net_b, "R")

    def bank(self, x, y, refs, part, net_a, net_b):
        """N identical parts between the same two nets, drawn once and
        labelled as a range. Every reference in `refs` is a separate
        part: the drawing is compact, the netlist is complete, and
        tools/netlist.py records all of them."""
        label = refs[0] if len(refs) == 1 else f"{refs[0]}..{refs[-1]}"
        self.grow(x - flagw(net_a, self.links), y - 16,
                  x + 80 + flagw(net_b, self.links), y + 16)
        if self.measuring:
            return len(refs)
        self.netlabel(x, y, net_a, "L")
        self.add(f'<line class="lead" x1="{x}" y1="{y}" x2="{x+18}" y2="{y}"/>'
                 f'<rect class="box" x="{x+18}" y="{y-7}" width="44" height="14"/>'
                 f'<line class="lead" x1="{x+62}" y1="{y}" x2="{x+80}" y2="{y}"/>')
        self.text(x + 40, y - 10, label, "pinno", "middle")
        self.text(x + 40, y + 4, part, "pin", "middle")
        self.netlabel(x + 80, y, net_b, "R")
        return len(refs)

    def done(self, path):
        self.add("</svg>")
        Path(path).write_text("\n".join(self.o))
        print(path)


# --------------------------------------------------------------- shared parts
def console_port(sh, x, y, ref, nets, supply="+5V"):
    """The NES-001 controller port, numbered as the pin numbers moulded
    into THIS console's housing.

    MEASURED 2026-09-09, bring-up steps 1.1 and 1.2. This used to carry
    the published pinout: D3 on 5, D4 on 6, the supply on 7. On this
    console the supply is on **pin 5**, and pins 6 and 7 are not carried
    by the controller cable at all. A continuity run out of circuit
    found five conductors on pins 1 to 5, and the scope then read 5.000
    V flat on the pin 5 lead while pin 3 idled low and pin 2 idled high.
    The published table is a published table; this is the board.

    What sits on pins 6 and 7 on the console side is unknown, because
    nothing reaches them through the cable to measure with.

    `supply` is the net the console's 5 V lands on. The C6 sheets run
    their register from it. v1b passes "NC": that bridge runs from the
    UNO's own 5 V and shares only ground with the console, so the RED
    lead stays off the board (bench-v1b-uno.md, build step 3.1). The
    sheet used to draw it on +5V regardless, which put two regulators
    in parallel on the wiring list; check-sheets.py now refuses that."""
    used = supply != "NC"
    return sh.chip(x, y, 130, ref, "console controller port", [], [
        (1, "GND", "GND"), (2, "CLK", nets["clk"]), (3, "OUT0", nets["out0"]),
        (4, "D0", nets["d0"]), (5, "+5V", supply), (6, "n/c", "NC"), (7, "n/c", "NC")], conn=True,
        extra="MEASURED 2026-09-09: supply on 5, 6 and 7 not carried"
              + ("" if used else "; pin 5 not used here"))


def pad_socket(sh, x, y, ref, latch, clk, d0, vcc="3V3"):
    """The pad end of a cut controller cable, numbered as `console_port`
    is: the supply on pin 5, nothing carried on 6 and 7. It is the same
    cable, so it has the same conductors."""
    return sh.chip(x, y, 130, ref, "original pad, on the bridge", [
        (1, "GND", "GND"), (2, "CLK", clk), (3, "OUT0", latch), (4, "D0", d0),
        (5, "+5V", vcc), (6, "n/c", "NC"), (7, "n/c", "NC")], [], conn=True,
        extra="the pad half of the cut cable")


def hct165(sh, x, y, ref, pl, cp, qh, inputs, part="74HCT165  at +5V"):
    """inputs: nets for H..A (A button first out)."""
    left = [(1, "/PL", pl), (2, "CP", cp), (15, "/CE", "GND"), (10, "DS", "GND"), (16, "VCC", "+5V"), (8, "GND", "GND")]
    names = ["H", "G", "F", "E", "D", "C", "B", "A"]
    nos = [6, 5, 4, 3, 14, 13, 12, 11]
    right = [(9, "QH", qh), (7, "/QH", "NC")] + [(nos[i], names[i], inputs[i]) for i in range(8)]
    return sh.chip(x, y, 140, ref, part, left, right, extra="H shifts out first")


def esp32c6(sh, x, y, left, right):
    return sh.chip(x, y, 190, "U4", "ESP32-C6-DevKitC-1 v1.2", left, right, extra="RISC-V, BLE 5, Wi-Fi 6")


# ------------------------------------------------------------------- sheet v1
def sheet_v1():
    sh = Sheet(2000, 1180, "nes-bench bridge v1: the pad the console clocks, one port",
               "as wired in docs/wiring.md, 2026-09-07. Net labels: same name, same wire. Three supplies, one ground. Not yet built.")
    sh.zone(20, 60, 1040, 660, "CONSOLE SIDE, +5V logic")
    console_port(sh, 60, 90, "J1", {"clk": "CON_CLK", "out0": "CON_OUT0", "d0": "CON_D0"})
    sh.chip(400, 90, 130, "U1", "74HCT04  at +5V", [(1, "1A", "CON_OUT0"), (14, "VCC", "+5V"), (7, "GND", "GND")],
            [(2, "1Y", "/PL")], extra="5 spare inputs to GND")
    hct165(sh, 720, 90, "U2", "/PL", "CON_CLK", "CON_D0",
           ["REG_A", "REG_B", "REG_SEL", "REG_START", "REG_UP", "REG_DOWN", "REG_LEFT", "REG_RIGHT"])
    sh.note(60, 380, ["OUT0 high: U1 drives /PL low, the 165 loads its eight inputs", "(transparent while low: do not write REG_* now).",
                      "OUT0 falls: /PL high, the byte is held; QH shows H (A button).", "Each CLK rising edge shifts: G, F, E, D, C, B, A, then DS = GND.",
                      "Pressed = LOW on the input, as the pad's 4021 drives D0."])
    sh.twopin(160, 520, "C1", "100nF", "+5V", "GND")
    sh.twopin(160, 570, "C2", "100nF", "+5V", "GND")
    sh.note(300, 524, ["across U1 pins 14-7"])
    sh.note(300, 574, ["across U2 pins 16-8"])

    sh.zone(1080, 60, 900, 660, "BRIDGE SIDE, 3V3 logic")
    sh.chip(1220, 90, 150, "U3", "74LVC245  at 3V3", [
        (1, "DIR", "3V3"), (19, "/OE", "GND"), (2, "A1", "CON_OUT0"), (3, "A2", "CON_CLK"), (4, "A3..A8", "GND"),
        (20, "VCC", "3V3"), (10, "GND", "GND")],
        [(18, "B1", "LATCH_IN"), (17, "B2", "CLK_IN")], extra="5V tolerant inputs, A to B")
    sh.twopin(1220, 360, "C3", "100nF", "3V3", "GND")
    sh.note(1330, 364, ["across U3 pins 20-10"])
    esp32c6(sh, 1600, 90, [
        (None, "GPIO0", "LATCH_IN"), (None, "GPIO1", "CLK_IN"), (None, "GPIO2", "PAD_LATCH"), (None, "GPIO3", "PAD_CLK"),
        (None, "GPIO6", "PAD_D0"), (None, "GPIO7", "TRIG"), (None, "3V3", "3V3"), (None, "GND", "GND"), (None, "USB-UART", "PI_USB")],
        [(None, "GPIO18", "REG_A"), (None, "GPIO19", "REG_B"), (None, "GPIO20", "REG_SEL"), (None, "GPIO21", "REG_START"),
         (None, "GPIO22", "REG_UP"), (None, "GPIO23", "REG_DOWN"), (None, "GPIO10", "REG_LEFT"), (None, "GPIO11", "REG_RIGHT")])
    sh.note(1500, 400, ["GPIO0: PCNT unit 0, rising edges = latch index", "GPIO1: PCNT unit 1, falling edges = clocks per poll",
                        "50 ns glitch filter on both; no ISR in the path", "8, 9, 15 strapping; 12, 13 USB; 16, 17 UART: untouched"])
    sh.twopin(1500, 500, "R1", "100R", "TRIG", "EXT_TRIG")
    sh.note(1500, 530, ["to DS1054Z rear EXT TRIG, 1.5 V rising edge"])
    pad_socket(sh, 1220, 420, "J2", "PAD_LATCH", "PAD_CLK", "PAD_D0")
    sh.note(1100, 680, ["J2: the pad powered at 3V3 so its 4021 speaks 3V3; measure-first item 4"])

    sh.zone(20, 740, 1960, 420, "HEAD AND RELAYS")
    sh.chip(60, 770, 170, "PI", "Raspberry Pi 4 Model B", [], [
        (None, "USB-A", "PI_USB"), (None, "GPIO17", "RST_DRIVE"), (None, "GPIO27", "PWR_DRIVE"),
        (None, "5V", "PI_5V"), (None, "GND", "GND"), (None, "ETH", "LAN")],
        conn=True, extra="the head: headd.py")
    sh.chip(480, 770, 150, "OK1", "PC817 module", [(None, "IN+", "RST_DRIVE"), (None, "IN-", "GND")],
            [(None, "OUT", "RST_PAD"), (None, "GND", "RST_GND"), (None, "VCC", "NC")], extra="open collector across reset")
    sh.chip(880, 770, 160, "K1", "relay module, 5 V coil", [(None, "IN", "PWR_DRIVE"), (None, "GND", "GND"), (None, "VCC", "PI_5V")],
            [(None, "NO", "AC_LEAD_A"), (None, "COM", "AC_LEAD_B")], extra="opto in, active low")
    sh.chip(1300, 770, 160, "SCOPE", "Rigol DS1054Z", [(None, "EXT TRIG", "EXT_TRIG"), (None, "CH3", "VIDEO"), (None, "LAN", "LAN")], [],
            conn=True, extra="SCPI over the LAN")
    sh.chip(1700, 770, 200, "CON", "NES-001 (NES-CPU-10)", [(None, "reset pad", "RST_PAD"), (None, "reset gnd", "RST_GND"),
                                                             (None, "video", "VIDEO"), (None, "DC jack", "AC_LEAD_A"), (None, "adapter", "AC_LEAD_B")], [], conn=True)
    sh.note(60, 1000, ["Grounds: J1 pin 1, the bridge plane, U4 GND and the Pi GND (through USB) are one net. The console's +5V and the C6's 3V3 share only that net.",
                      "Reset: GPIO17 high lights the module's LED; its transistor pulls the console's pulled-up reset pad to the reset ground pad for 100 ms.",
                      "Power: GPIO27 low turns K1 on (opto input, VCC from the Pi's 5 V pin: the modules on hand are 5 V coil parts). Its normally-open",
                      "contact goes in series with one lead of the AC adapter cable, never the mains side, never both leads.",
                      "Authored pulse widths for B0 to replace: latch high a few us, clock low a few hundred ns, ~7 us between clocks, 60 polls/s."])
    sh.done(OUT / "bench-v1.svg")



# --------------------------------------------------------------- sheet v1b
# Two sheets of paper, one schematic. The netlist tools collect both
# bodies under the name bench-v1b, so the rule check still sees a whole
# design; what is split is the paper. Nets that continue on the other
# sheet carry a link flag with the sheet number in it, which is what the
# flag is for: a reader who wants the other end of Q_START is told where
# it is instead of being left to search.
LETTER = None   # set at import: the drawing area of a landscape letter page

V1B_TITLE = "nes-bench bridge v1b: the UNO version, one supply, one port"
V1B_SUB = ("the ATmega328 is a 5 V part, so the register, the pad and the console share one domain. "
           "2026-09-08. Not built; pulse widths authored until B0.")
Q_NETS = ["Q_A", "Q_B", "Q_SEL", "Q_START", "Q_UP", "Q_DOWN", "Q_LEFT", "Q_RIGHT"]


def _v1b_body_1(sh):
    band = "THE CONSOLE PORT, THE INVERTER AND THE REGISTER, ALL AT +5V"
    console_port(sh, *sh.slot(0, 0, label=band), "J1",
                 {"clk": "CON_CLK", "out0": "CON_OUT0", "d0": "CON_D0"}, supply="NC")
    x, y = sh.slot(0, 1)
    sh.chip(x, y, 130, "U1", "74HCT04  at +5V",
            [(1, "1A", "CON_OUT0"), (14, "VCC", "+5V"), (7, "GND", "GND")],
            [(2, "1Y", "/PL")], extra="2.0 V threshold: safe on NMOS OUT0")
    hct165(sh, *sh.slot(0, 2), "U2", "/PL", "CON_CLK", "CON_D0",
           part="74HC165  at +5V (the TI bag)", inputs=Q_NETS)
    band2 = "DECOUPLING, AND WHAT THE CONSOLE ACTUALLY DOES"
    sh.bank(*sh.slot(1, 0, label=band2), ["C1", "C2", "C3"], "100nF", "+5V", "GND")
    sh.note(*sh.slot(1, 1), ["one 100nF across each of U1, U2 and U3,", "at the chip's own supply pins"])
    sh.note(*sh.slot(1, 2), [
        "OUT0 high: U1 drives /PL low and the 165 loads its eight inputs. It is transparent while low,",
        "so the byte must already be in U3 (sheet 2). OUT0 falls, /PL goes high, the byte is held, and",
        "QH shows A. Each CLK rising edge shifts the next bit out: B, Select, Start, Up, Down, Left,",
        "Right, then DS = GND, so the ninth read and later return 1 as an original pad does.",
        "Pressed is LOW, which is what the pad's own 4021 drives."])


def _v1b_body_2(sh):
    band = "THE UNO, THE OUTPUT REGISTER AND THE BRIDGE'S OWN PAD, ALL AT +5V"
    pad_socket(sh, *sh.slot(0, 0, label=band), "J2", "PAD_LATCH", "PAD_CLK", "PAD_D0", vcc="+5V")
    x, y = sh.slot(0, 1)
    sh.chip(x, y, 190, "A1", "Arduino UNO R3 (ATmega328P)", [
        (None, "D13 SCK", "SCK"), (None, "D11 MOSI", "MOSI"), (None, "D10", "RCLK"),
        (None, "D5 (T1)", "CON_OUT0"), (None, "D2 (INT0)", "CON_CLK"), (None, "D3", "TRIG"),
        (None, "5V", "+5V"), (None, "GND", "GND"), (None, "USB-B", "PI_USB")],
        [(None, "D6", "PAD_LATCH"), (None, "D7", "PAD_CLK"), (None, "D8", "PAD_D0"),
         (None, "D0, D1", "serial")], extra="5 V logic, 16 MHz")
    x, y = sh.slot(0, 2)
    sh.chip(x, y, 140, "U3", "74HC595  at +5V", [
        (14, "SER", "MOSI"), (11, "SRCLK", "SCK"), (12, "RCLK", "RCLK"), (13, "/OE", "GND"),
        (10, "/SRCLR", "+5V"), (16, "VCC", "+5V"), (8, "GND", "GND")],
        [(15, "QA", "Q_A"), (1, "QB", "Q_B"), (2, "QC", "Q_SEL"), (3, "QD", "Q_START"),
         (4, "QE", "Q_UP"), (5, "QF", "Q_DOWN"), (6, "QG", "Q_LEFT"), (7, "QH", "Q_RIGHT"),
         (9, "QH'", "NC")], extra="one RCLK edge = one byte")
    band2 = "THE TRIGGER, AND WHY THESE PINS"
    sh.twopin(*sh.slot(1, 0, label=band2), "R1", "100R", "TRIG", "EXT_TRIG")
    sh.note(*sh.slot(1, 1), ["to the DS1054Z's rear EXT TRIG. Check the input's",
                             "rating first; if 5 V exceeds it, a 2:1 divider",
                             "(two 1k) after R1."])
    sh.note(*sh.slot(1, 2), [
        "D5 is Timer1's external clock input (T1): a 16-bit hardware counter of",
        "OUT0 rising edges, which is the latch index. D2 (INT0) takes a falling-edge",
        "ISR counting clocks per poll, 480/s, nothing for a 16 MHz part. D3 rises at",
        "latch T, one loop late (~100 us); a 74LS74 makes it edge-exact later.",
        "SPI clocks 8 bits into U3 in 2 us at 4 MHz and one RCLK edge moves them to",
        "its outputs in ~10 ns, so the console never sees half a byte. The firmware",
        "still only pulses RCLK while D5 reads low. Serial 115200 to the Pi over USB."])
    band3 = "THE HEAD, THE RELAYS AND THE SCOPE (unchanged from v1 except the relay supply)"
    sh.note(*sh.slot(2, 0, label=band3), [
        "Pi GPIO17 to a PC817 or one TLP281 channel, to the console's reset pads, 100 ms.",
        "Pi GPIO27 to the relay module's IN (active low); relay VCC from the Pi's 5 V pin,",
        "because the Songle SRD-05VDC and the Tongling board are 5 V coil parts."])
    sh.note(*sh.slot(2, 1), [
        "One normally-open contact in series with one lead of the AC adapter cable, never",
        "the mains side and never both. Grounds: J1 pin 1, the bridge, the UNO GND and the",
        "Pi GND through USB are one net. Scope: video on CH3, EXT TRIG from R1, SCPI by LAN."])


def sheet_v1b():
    """One schematic on two landscape letter sheets."""
    cross = {"CON_OUT0": "2", "CON_CLK": "2"}
    laid(OUT / "bench-v1b-1.svg", V1B_TITLE + "  (sheet 1 of 2: the console side)", V1B_SUB,
         _v1b_body_1, LETTER, links={**cross, **{q: "2" for q in Q_NETS}})
    back = {"CON_OUT0": "1", "CON_CLK": "1"}
    laid(OUT / "bench-v1b-2.svg", V1B_TITLE + "  (sheet 2 of 2: the bridge side)", V1B_SUB,
         _v1b_body_2, LETTER, links={**back, **{q: "1" for q in Q_NETS}})


# ------------------------------------------------------------------- sheet v2
def sheet_v2():
    sh = Sheet(2400, 1290, "nes-bench bridge v2: two ports, atomic bytes, the frame counted in hardware",
               "extends v1 with 74HC595s on SPI (one RCLK edge updates both registers), an LM1881 sync separator, and a second pad. Nothing built; every number authored until B0.")
    sh.zone(20, 60, 1440, 780, "CONSOLE SIDE, +5V logic")
    console_port(sh, 60, 90, "J1", {"clk": "CON1_CLK", "out0": "CON1_OUT0", "d0": "CON1_D0"})
    console_port(sh, 60, 360, "J3", {"clk": "CON2_CLK", "out0": "CON2_OUT0", "d0": "CON2_D0"})
    sh.chip(400, 90, 130, "U1", "74HCT04  at +5V", [(1, "1A", "CON1_OUT0"), (3, "2A", "CON2_OUT0"), (14, "VCC", "+5V"), (7, "GND", "GND")],
            [(2, "1Y", "/PL1"), (4, "2Y", "/PL2")], extra="4 spare inputs to GND")
    hct165(sh, 720, 90, "U2", "/PL1", "CON1_CLK", "CON1_D0", ["Q1A", "Q1B", "Q1SEL", "Q1START", "Q1UP", "Q1DOWN", "Q1LEFT", "Q1RIGHT"])
    hct165(sh, 720, 440, "U6", "/PL2", "CON2_CLK", "CON2_D0", ["Q2A", "Q2B", "Q2SEL", "Q2START", "Q2UP", "Q2DOWN", "Q2LEFT", "Q2RIGHT"])
    sh.chip(1140, 90, 140, "U5", "74HC595  at 3V3", [
        (14, "SER", "MOSI"), (11, "SRCLK", "SCK"), (12, "RCLK", "RCLK"), (13, "/OE", "GND"), (10, "/SRCLR", "3V3"), (16, "VCC", "3V3"), (8, "GND", "GND")],
        [(15, "QA", "Q1A"), (1, "QB", "Q1B"), (2, "QC", "Q1SEL"), (3, "QD", "Q1START"), (4, "QE", "Q1UP"), (5, "QF", "Q1DOWN"),
         (6, "QG", "Q1LEFT"), (7, "QH", "Q1RIGHT"), (9, "QH'", "CHAIN")], extra="port 1 byte")
    sh.chip(1140, 440, 140, "U7", "74HC595  at 3V3", [
        (14, "SER", "CHAIN"), (11, "SRCLK", "SCK"), (12, "RCLK", "RCLK"), (13, "/OE", "GND"), (10, "/SRCLR", "3V3"), (16, "VCC", "3V3"), (8, "GND", "GND")],
        [(15, "QA", "Q2A"), (1, "QB", "Q2B"), (2, "QC", "Q2SEL"), (3, "QD", "Q2START"), (4, "QE", "Q2UP"), (5, "QF", "Q2DOWN"),
         (6, "QG", "Q2LEFT"), (7, "QH", "Q2RIGHT"), (9, "QH'", "NC")], extra="port 2 byte, chained")
    sh.note(60, 640, ["Why the 595s: sixteen bits shift in over SPI at any time; nothing changes at the 165s until one RCLK",
                      "rising edge moves both bytes to the outputs in one ~10 ns step. A tear during a load becomes impossible,",
                      "and the firmware still only pulses RCLK while both OUT0 lines read low. 3V3 outputs into HCT inputs",
                      "(Vih 2.0 V) is in spec. 3 GPIOs replace 8; port 2 costs none. DS on both 165s to GND: bit 9+ reads 1."])
    sh.bank(160, 760, ["C1", "C2"], "100nF", "+5V", "GND")
    sh.note(300, 764, ["U1, U2, U6 supply pins; C5 for U8"])
    sh.bank(560, 760, ["C3", "C4"], "100nF", "3V3", "GND")
    sh.note(700, 764, ["U5, U7 (and U3) supply pins"])

    sh.zone(1480, 60, 900, 780, "SYNC SEPARATOR, +5V")
    sh.chip(1640, 90, 150, "U8", "LM1881N  at +5V", [
        (2, "VIDEO IN", "VID_AC"), (6, "RSET", "RSET"), (8, "VCC", "+5V"), (4, "GND", "GND")],
        [(1, "CSYNC", "CSYNC_5"), (3, "VSYNC", "VSYNC_5"), (5, "BURST", "NC"), (7, "ODD/EVEN", "NC")], extra="composite sync out")
    sh.twopin(1640, 330, "C6", "100nF", "VIDEO", "VID_AC")
    sh.note(1780, 334, ["AC couple from the console's video (75R load present)"])
    sh.twopin(1640, 380, "R2", "680k", "RSET", "GND")
    sh.twopin(1640, 430, "C7", "100nF", "RSET", "GND")
    sh.note(1520, 500, ["Tap VIDEO after Q1 (the AUX/RF input), the point the", "scope already probes; a 1k series R protects the tap.",
                        "VSYNC: one falling edge per field, 60.0988/s.", "CSYNC: one falling edge per line plus the vsync block;",
                        "the NES has no serrations, so count = lines - 2 (measure).",
                        "Both are 5V outputs: through the 245 like the port lines."])

    sh.zone(20, 860, 2360, 410, "BRIDGE SIDE, 3V3 logic")
    sh.chip(200, 890, 150, "U3", "74LVC245  at 3V3", [
        (1, "DIR", "3V3"), (19, "/OE", "GND"), (2, "A1", "CON1_OUT0"), (3, "A2", "CON1_CLK"), (4, "A3", "CON2_OUT0"), (5, "A4", "CON2_CLK"),
        (6, "A5", "VSYNC_5"), (7, "A6", "CSYNC_5"), (8, "A7,A8", "GND"), (20, "VCC", "3V3"), (10, "GND", "GND")],
        [(18, "B1", "LATCH1"), (17, "B2", "CLK1"), (16, "B3", "LATCH2"), (15, "B4", "CLK2"), (14, "B5", "VSYNC"), (13, "B6", "CSYNC")],
        extra="six lines down to 3V3")
    esp32c6(sh, 620, 890, [
        (None, "GPIO0", "LATCH1"), (None, "GPIO1", "CLK1"), (None, "GPIO10", "CLK2"), (None, "GPIO11", "CSYNC"),
        (None, "GPIO21", "LATCH2"), (None, "GPIO22", "VSYNC"), (None, "3V3", "3V3"), (None, "GND", "GND"), (None, "USB-UART", "PI_USB")],
        [(None, "GPIO18", "SCK"), (None, "GPIO19", "MOSI"), (None, "GPIO20", "RCLK"), (None, "GPIO2", "PAD_LATCH"), (None, "GPIO3", "PAD_CLK"),
         (None, "GPIO6", "PAD1_D0"), (None, "GPIO23", "PAD2_D0"), (None, "GPIO7", "TRIG")])
    sh.note(520, 1200, ["PCNT unit 0: LATCH1 rises (latch index, port 1)", "PCNT unit 1: CLK1 falls (clocks per poll, port 1)",
                        "PCNT unit 2: CLK2 falls (clocks per poll, port 2)", "PCNT unit 3: CSYNC falls (line counter)",
                        "GPIO21, GPIO22: ISR, 60/s each, timestamp + PCNT3 snapshot", "(a 3 us ISR latency is 5% of a 63.5 us line)",
                        "All 14 free pins used; 4, 5, 8, 9, 12, 13, 15, 16, 17 untouched"])
    pad_socket(sh, 1200, 890, "J2", "PAD_LATCH", "PAD_CLK", "PAD1_D0")
    pad_socket(sh, 1560, 890, "J4", "PAD_LATCH", "PAD_CLK", "PAD2_D0")
    sh.note(1200, 1160, ["Both pads share the bridge's own latch and clock; each has its own D0. Polled together at 1 kHz."])
    sh.twopin(1900, 920, "R1", "100R", "TRIG", "EXT_TRIG")
    sh.note(1900, 950, ["EXT TRIG; fires at a latch index,", "or at (field, line)"])
    sh.note(1200, 1220, ["L line, v2:  L <latch> <byte> <clocks> <t_us> <field> <line>", "L2 line for port 2. F line per field: F <field> <t_us> <lines>.",
                        "MUTATE ON swaps PCNT 0 and 1 pins at runtime (B0's red run).",
                        "Head and relays: unchanged from v1 (Pi GPIO17 reset, GPIO27 power)."])
    sh.note(60, 600, ["C6 -> 595 level: the C6's 3.3 V SCK, MOSI, RCLK each pass through two gates of a second 74HCT04 (U9, +5V):",
                      "HCT accepts a 3.3 V high, and two inversions give a full 5 V non-inverted copy. No LS245, no pullups."])
    sh.done(OUT / "bench-v2.svg")


# ------------------------------------------------------------- logical sheet
# --------------------------------------------------------------- sheet v2b
V2B_TITLE = "nes-bench bridge v2b: the UNO version, two ports, sync counted, one supply"
V2B_SUB = ("v1b plus a second 165/595 pair on the same SPI chain and an LM1881 whose 5 V outputs go "
           "straight into the UNO. 2026-09-09. Not built.")
Q1_NETS = ["Q1A", "Q1B", "Q1SEL", "Q1START", "Q1UP", "Q1DOWN", "Q1LEFT", "Q1RIGHT"]
Q2_NETS = ["Q2A", "Q2B", "Q2SEL", "Q2START", "Q2UP", "Q2DOWN", "Q2LEFT", "Q2RIGHT"]


def _v2b_body_1(sh):
    band = "PORT 1: THE CONSOLE PORT, THE INVERTER AND ITS REGISTER, ALL AT +5V"
    console_port(sh, *sh.slot(0, 0, label=band), "J1",
                 {"clk": "CON1_CLK", "out0": "CON1_OUT0", "d0": "CON1_D0"}, supply="NC")
    x, y = sh.slot(0, 1)
    sh.chip(x, y, 130, "U1", "74HCT04  at +5V",
            [(1, "1A", "CON1_OUT0"), (3, "2A", "CON2_OUT0"), (14, "VCC", "+5V"), (7, "GND", "GND")],
            [(2, "1Y", "/PL1"), (4, "2Y", "/PL2")],
            extra="4 spare inputs to GND")
    hct165(sh, *sh.slot(0, 2), "U2", "/PL1", "CON1_CLK", "CON1_D0",
           part="74HC165  at +5V", inputs=Q1_NETS)
    band2 = "WHAT THE CONSOLE DOES, AND WHAT MAY NOT MOVE WHILE IT DOES IT"
    sh.note(*sh.slot(1, 0, label=band2), [
        "OUT0 high: U1 drives /PL1 low and U2 loads its eight inputs. It is transparent while low, so the",
        "byte must already be on U5's outputs (sheet 3). OUT0 falls, /PL1 goes high, the byte is held, and",
        "QH shows A. Each CLK rising edge shifts the next bit out. DS to GND means the ninth read and",
        "later return 1 to the console, which is what an original pad does. Pressed is LOW.",
        "Port 2 is the same circuit on sheet 2. It shares this inverter, U1's second channel, and",
        "the SPI chain; it has its own register, its own pad and its own D0."])


def _v2b_body_2(sh):
    band = "PORT 2: THE SECOND CONSOLE PORT AND ITS REGISTER, ALL AT +5V"
    console_port(sh, *sh.slot(0, 0, label=band), "J3",
                 {"clk": "CON2_CLK", "out0": "CON2_OUT0", "d0": "CON2_D0"}, supply="NC")
    hct165(sh, *sh.slot(0, 1), "U6", "/PL2", "CON2_CLK", "CON2_D0",
           part="74HC165  at +5V", inputs=Q2_NETS)
    band2 = "DECOUPLING, AND WHY THE REGISTERS ARE WRITTEN THE WAY THEY ARE"
    sh.bank(*sh.slot(1, 0, label=band2), ["C1", "C2", "C3", "C4", "C5", "C6"], "100nF", "+5V", "GND")
    sh.note(*sh.slot(1, 1), ["one across each of U1, U2, U5,", "U6, U7 and U8, at its own",
                             "supply pins"])
    sh.note(*sh.slot(1, 2), [
        "Two SPI.transfer() calls, port 2's byte first and then port 1's, and one RCLK",
        "edge updates both registers together. A tear during a load is impossible, and the",
        "firmware still only pulses RCLK while both OUT0 lines read low.",
        "The UNO's outputs are 5 V, so HC parts at 5 V see real highs everywhere. There is",
        "not one level shifter on any sheet of this drawing."])


def _v2b_body_3(sh):
    band = "THE UNO AND THE TWO OUTPUT REGISTERS ON ONE SPI CHAIN, ALL AT +5V"
    x, y = sh.slot(0, 0, label=band)
    sh.chip(x, y, 200, "A1", "Arduino UNO R3 (ATmega328P)", [
        (None, "D13 SCK", "SCK"), (None, "D11 MOSI", "MOSI"), (None, "D10", "RCLK"),
        (None, "D5 (T1)", "CON1_OUT0"), (None, "D2 (INT0)", "CON1_CLK"),
        (None, "D3 (INT1)", "CSYNC"), (None, "D4 (PCINT)", "CON2_OUT0"),
        (None, "D9 (PCINT)", "CON2_CLK"), (None, "A0 (PCINT)", "VSYNC")],
        [(None, "A1", "TRIG"), (None, "D6", "PAD_LATCH"), (None, "D7", "PAD_CLK"),
         (None, "D8", "PAD1_D0"), (None, "A2", "PAD2_D0"), (None, "5V", "+5V"),
         (None, "GND", "GND"), (None, "USB-B", "PI_USB")], extra="serial 115200 to the Pi")
    x, y = sh.slot(0, 1)
    sh.chip(x, y, 140, "U5", "74HC595  at +5V", [
        (14, "SER", "MOSI"), (11, "SRCLK", "SCK"), (12, "RCLK", "RCLK"), (13, "/OE", "GND"),
        (10, "/SRCLR", "+5V"), (16, "VCC", "+5V"), (8, "GND", "GND")],
        [(15, "QA", "Q1A"), (1, "QB", "Q1B"), (2, "QC", "Q1SEL"), (3, "QD", "Q1START"),
         (4, "QE", "Q1UP"), (5, "QF", "Q1DOWN"), (6, "QG", "Q1LEFT"), (7, "QH", "Q1RIGHT"),
         (9, "QH'", "CHAIN")], extra="port 1's byte, shifted in second")
    x, y = sh.slot(0, 2)
    sh.chip(x, y, 140, "U7", "74HC595  at +5V", [
        (14, "SER", "CHAIN"), (11, "SRCLK", "SCK"), (12, "RCLK", "RCLK"), (13, "/OE", "GND"),
        (10, "/SRCLR", "+5V"), (16, "VCC", "+5V"), (8, "GND", "GND")],
        [(15, "QA", "Q2A"), (1, "QB", "Q2B"), (2, "QC", "Q2SEL"), (3, "QD", "Q2START"),
         (4, "QE", "Q2UP"), (5, "QF", "Q2DOWN"), (6, "QG", "Q2LEFT"), (7, "QH", "Q2RIGHT"),
         (9, "QH'", "NC")], extra="port 2's byte, chained from U5")
    band2 = "WHAT COUNTS WHAT, AND THE HEAD"
    sh.note(*sh.slot(1, 0, label=band2), [
        "LATCH1 on Timer1's external clock: hardware, and the",
        "reference every software count is checked against.",
        "CLK1 on INT0, CSYNC on INT1. LATCH2, CLK2 and VSYNC",
        "on pin-change ISRs. The 8-per-latch and polls-per-field",
        "gates cross-check them; a count that stays green under",
        "MUTATE (the D2/D5 jumper swap, D4 the config pin) is a",
        "broken count. A1 rises at latch T or at (field, line).",
        "L <latch> <byte> <clocks> <t_us> <field> <line>;",
        "L2 for port 2; F <field> <t_us> <lines>."])
    sh.note(*sh.slot(1, 1), [
        "Head and relays, unchanged from v1b. Pi GPIO17 to a",
        "PC817 or one TLP281 channel, to the console's reset",
        "pads, 100 ms. Pi GPIO27 to the relay module's IN",
        "(active low); relay VCC from the Pi's 5 V pin, because",
        "the modules on hand are 5 V coil parts. One",
        "normally-open contact in series with one lead of the AC",
        "adapter cable, never the mains side and never both.",
        "Scope: video on CH3, EXT TRIG from R1 (sheet 4),",
        "SCPI over the LAN."])


def _v2b_body_4(sh):
    band = "THE SYNC SEPARATOR, THE BRIDGE'S OWN PADS AND THE TRIGGER, ALL AT +5V"
    x, y = sh.slot(0, 0, label=band)
    sh.chip(x, y, 150, "U8", "LM1881N  at +5V", [
        (2, "VIDEO IN", "VID_AC"), (6, "RSET", "RSET"), (8, "VCC", "+5V"), (4, "GND", "GND")],
        [(1, "CSYNC", "CSYNC"), (3, "VSYNC", "VSYNC"), (5, "BURST", "NC"), (7, "ODD/EVEN", "NC")],
        extra="5 V outputs: no 245 needed")
    pad_socket(sh, *sh.slot(0, 1), "J2", "PAD_LATCH", "PAD_CLK", "PAD1_D0", vcc="+5V")
    pad_socket(sh, *sh.slot(0, 2), "J4", "PAD_LATCH", "PAD_CLK", "PAD2_D0", vcc="+5V")
    band2 = "THE PASSIVES ON THIS SHEET"
    sh.twopin(*sh.slot(1, 0, label=band2), "C7", "100nF", "VIDEO", "VID_AC")
    sh.twopin(*sh.slot(1, 1), "R2", "680k", "RSET", "GND")
    sh.twopin(*sh.slot(1, 2), "C8", "100nF", "RSET", "GND")
    sh.twopin(*sh.slot(1, 3), "R1", "100R", "TRIG", "EXT_TRIG")
    band3 = "WHERE THESE SIGNALS COME FROM AND WHAT THEY ARE WORTH"
    sh.note(*sh.slot(2, 0, label=band3), [
        "C7 AC couples the console's video, tapped after Q1 at the AUX/RF",
        "input with a 1k series resistor: the point the scope already probes.",
        "VSYNC: one falling edge per field, 60.0988/s.",
        "CSYNC: one per line plus the vsync block. The NES emits no",
        "serrations, so the count per field is lines minus k, and k is",
        "measured rather than assumed."])
    sh.note(*sh.slot(2, 1), [
        "R1 goes to the DS1054Z's rear EXT TRIG. Check the input's rating",
        "first; if 5 V exceeds it, a 2:1 divider (two 1k) after R1.",
        "Both pads are polled by the same PAD_LATCH and PAD_CLK and answer",
        "on their own D0, so one poll reads both. They are the pad halves",
        "of two cut controller cables, and they run at the 5 V they were",
        "built for."])


def sheet_v2b():
    """One schematic on four landscape letter sheets."""
    q1 = {q: "3" for q in Q1_NETS}
    q2 = {q: "3" for q in Q2_NETS}
    laid(OUT / "bench-v2b-1.svg", V2B_TITLE + "  (sheet 1 of 4: port 1)", V2B_SUB, _v2b_body_1,
         LETTER, links={"CON1_OUT0": "3", "CON1_CLK": "3", "CON2_OUT0": "2,3", "/PL2": "2", **q1})
    laid(OUT / "bench-v2b-2.svg", V2B_TITLE + "  (sheet 2 of 4: port 2)", V2B_SUB, _v2b_body_2,
         LETTER, links={"CON2_OUT0": "1,3", "CON2_CLK": "3", "/PL2": "1", **q2})
    laid(OUT / "bench-v2b-3.svg", V2B_TITLE + "  (sheet 3 of 4: the UNO and the registers)",
         V2B_SUB, _v2b_body_3, LETTER,
         links={"CON1_OUT0": "1", "CON1_CLK": "1", "CON2_OUT0": "1,2", "CON2_CLK": "2",
                "CSYNC": "4", "VSYNC": "4", "TRIG": "4", "PAD_LATCH": "4", "PAD_CLK": "4",
                "PAD1_D0": "4", "PAD2_D0": "4",
                **{q: "1" for q in Q1_NETS}, **{q: "2" for q in Q2_NETS}})
    laid(OUT / "bench-v2b-4.svg", V2B_TITLE + "  (sheet 4 of 4: sync, the pads and the trigger)",
         V2B_SUB, _v2b_body_4, LETTER,
         links={"CSYNC": "3", "VSYNC": "3", "TRIG": "3", "PAD_LATCH": "3", "PAD_CLK": "3",
                "PAD1_D0": "3", "PAD2_D0": "3"})


def sheet_logic():
    sh = Sheet(1500, 900, "nes-bench: the logic of one poll, and what is counted",
               "timing lanes for one controller read on the part; widths marked authored are B0 measure-first item 3's to replace")
    L, R = 200, 1440
    lanes = [("OUT0 (console)", 90), ("/PL = not OUT0", 150), ("165 state", 210), ("CLK (console)", 280), ("D0 (165 QH)", 350),
             ("PCNT 0 (latch)", 430), ("PCNT 1 (clock)", 490), ("ESP32 loop", 560), ("safe to write", 630)]
    for name, y in lanes:
        sh.text(L - 10, y + 4, name, "lanelbl", "end")
        sh.add(f'<line x1="{L}" y1="{y+22}" x2="{R}" y2="{y+22}" stroke="#d0d7de" stroke-width="1"/>')
    # time scale: latch at t0=260px, high for 40px; clocks every 70px from 340
    t0, hw = 260, 40
    clk = [400 + i * 75 for i in range(8)]
    cw = 12
    hi, lo = -18, 18

    def lane_path(y, segs):
        d = f"M{L},{y+lo}"
        for (x1, x2, level) in segs:
            yy = y + (hi if level else lo)
            d += f" L{x1},{y+lo if level else y+hi} L{x1},{yy} L{x2},{yy}"
        d += f" L{R},{y+lo}"
        return d
    # OUT0: low, high pulse, low
    sh.add(f'<path class="lane" d="M{L},{90+lo} L{t0},{90+lo} L{t0},{90+hi} L{t0+hw},{90+hi} L{t0+hw},{90+lo} L{R},{90+lo}"/>')
    sh.text(t0 + hw / 2, 90 + hi - 6, "STA $4016 = 1 ... = 0", "auth", "middle")
    sh.text(t0 + hw / 2, 90 + lo + 14, "high ~3 us (authored)", "auth", "middle")
    # /PL: high, low pulse, high
    sh.add(f'<path class="lane" d="M{L},{150+hi} L{t0},{150+hi} L{t0},{150+lo} L{t0+hw},{150+lo} L{t0+hw},{150+hi} L{R},{150+hi}"/>')
    sh.add(f'<rect class="win" x="{t0}" y="{140}" width="{hw}" height="{90}"/>')
    sh.text(t0 + hw + 6, 150 + lo, "load window: 165 is transparent, inputs must not change", "auth")
    # 165 state
    sh.text(L + 4, 210 + 4, "holding previous", "pin")
    sh.text(t0 + hw + 30, 210 + 4, "held: A on QH", "pin")
    for i, x in enumerate(clk):
        nm = ["B", "Sel", "Start", "Up", "Down", "Left", "Right", "DS=0"][i]
        sh.text(x + cw + 4, 210 + 4, nm, "pin")
    # CLK: high idle, low pulses
    d = f"M{L},{280+hi}"
    for x in clk:
        d += f" L{x},{280+hi} L{x},{280+lo} L{x+cw},{280+lo} L{x+cw},{280+hi}"
    d += f" L{R},{280+hi}"
    sh.add(f'<path class="lane" d="{d}"/>')
    sh.text(clk[0], 280 + lo + 14, "LDA $4016: /OE1 low ~500 ns (authored); 4021 and 165 shift on the rising edge", "auth")
    sh.text(clk[1] + 20, 280 + hi - 6, "~7 us between reads (authored)", "auth")
    # D0 bits: show A pressed (low) at first, rest high, last low
    bits = [0, 1, 1, 1, 1, 1, 1, 1, 0]  # A pressed, DS low after 8
    edges = [t0 + hw] + [x + cw for x in clk]
    d = f"M{L},{350+hi}"
    for i, x in enumerate(edges):
        y = 350 + (lo if bits[i] == 0 else hi)
        d += f" L{x},{350+ (hi if i == 0 else (lo if bits[i-1] == 0 else hi))} L{x},{y}"
        nxt = edges[i + 1] if i + 1 < len(edges) else R
        d += f" L{nxt},{y}"
    sh.add(f'<path class="lane" d="{d}"/>')
    sh.text(t0 + hw + 4, 350 + lo + 14, "A pressed: LOW", "pin")
    sh.text(clk[7] + cw + 4, 350 + lo + 14, "9th+ read: LOW (console reads 1)", "pin")
    # PCNT marks
    sh.add(f'<line class="mark" x1="{t0}" y1="{430-14}" x2="{t0}" y2="{430+18}"/>')
    sh.text(t0 + 5, 430 + 4, "+1 on OUT0 rising edge: latch index n", "net")
    for x in clk:
        sh.add(f'<line class="mark" x1="{x}" y1="{490-14}" x2="{x}" y2="{490+18}"/>')
    sh.text(clk[0] + 5, 490 + 4, "+1 per CLK falling edge: 8 per poll, 9 on a DMC collision (alias rule excepted)", "net")
    # ESP loop
    for i in range(0, 14):
        x = L + 30 + i * 90
        sh.add(f'<line x1="{x}" y1="{560-12}" x2="{x}" y2="{560+12}" stroke="#57606a" stroke-width="1"/>')
    sh.text(L + 34, 560 - 16, "loop ~100 us: read PCNT deltas, emit L, then write the byte", "note")
    # safe window
    sh.add(f'<rect class="safe" x="{L}" y="{618}" width="{t0-L-8}" height="{28}"/>')
    sh.add(f'<rect class="safe" x="{t0+hw+8}" y="{618}" width="{R-(t0+hw+8)}" height="{28}"/>')
    sh.text(L + 6, 630 + 4, "write allowed", "pin")
    sh.text(t0 + hw + 14, 630 + 4, "write allowed (v1: OUT0 reads low before and after; v2: RCLK edge is atomic anyway)", "pin")

    # counting model
    sh.zone(20, 690, 1460, 190, "WHAT A RUN IS: the same history on both sides")
    def mono(x, y, lines):
        for i, l in enumerate(lines):
            sh.text(x, y + i * 13, l, "pin")
    mono(40, 725, [
        "latch index n     count of OUT0 rising edges since RESET. Part: PCNT 0. Model: $4016 strobe rises in nes-glue::controller.",
        "byte at n         what the register held when OUT0 fell at n. Part: written after latch n-1 (v1) or moved by RCLK after n-1 (v2). Model: set_pad before latch n.",
        "clocks at n       CLK falling edges between latch n and n+1. Part: PCNT 1 delta. Model: $4016 reads. 8 expected; 9 on a DMC collision.",
        "t_us at n (v2)    micros() at detection, jitter one loop. Gives latch interval and, against F lines, polls per field without the scope.",
        "field f, line l   (v2) VSYNC falling edges since RESET; CSYNC falling edges since the last VSYNC. Model: h at the strobe, mapped by B2's alignment class.",
        "trigger           EXT TRIG rises at latch T (v1) or at (f, l) (v2); the scope's single shot lands on a known frame of a known history.",
        "",
        "Script (docs/script.md) -> head (Pi) -> bridge over USB serial -> 165 -> console.    Console -> L lines -> head -> runs/<stamp>/bridge.log.",
        "Same script -> nes-console pad-log -> the same L lines.    compare-logs.py: first latch where byte or clocks differ.    b1-score: capture at T vs model frame at T.",
        "MUTATE (v2 command): PCNT 0 and 1 swapped -> 8-per-latch check must go red.  A gate that stays green under MUTATE is a broken gate.",
    ])
    sh.done(OUT / "logical-timing.svg")


# ------------------------------------------------------------ pad adapter
def sheet_pad():
    sh = Sheet(1700, 940, "OG pad to BLE / USB HID adapter: the bridge's pad poll, made portable",
               "ESP32-S3 for USB HID + BLE; ESP32-C6 works for BLE only (its USB port is serial/JTAG, not a device controller). Nothing built.")
    sh.zone(20, 60, 720, 560, "PADS, polled at 3V3 exactly as the bridge polls them")
    pad_socket(sh, 160, 90, "J1", "PAD_LATCH", "PAD_CLK", "PAD1_D0")
    pad_socket(sh, 160, 340, "J2", "PAD_LATCH", "PAD_CLK", "PAD2_D0")
    sh.note(340, 100, ["The pad's 4021 is a CMOS part rated 3 to 18 V.", "At 3V3 its D0 is 3V3 logic and needs no shifter.",
                       "Measure-first item 4 on the bench settles this", "before any adapter is built; if a pad will not run",
                       "at 3V3, add a 74LVC245 and feed the pad 5 V.",
                       "", "Poll: OUT0 high 12 us, low, 8 clocks at 1 us,", "read D0 before each rising edge. 1 kHz.",
                       "The same poll_pad() as firmware/bridge/bridge.ino."])
    sh.bank(400, 300, ["R1", "R2"], "10k", "PAD1_D0", "3V3")
    sh.note(340, 330, ["pullups on D0 (both pads): unplugged reads 'nothing pressed'"])

    sh.zone(760, 60, 920, 560, "CONTROLLER AND POWER")
    sh.chip(900, 90, 190, "U1", "ESP32-S3-DevKitC-1 (or C6)", [
        (None, "GPIO4", "PAD_LATCH"), (None, "GPIO5", "PAD_CLK"), (None, "GPIO6", "PAD1_D0"), (None, "GPIO7", "PAD2_D0"),
        (None, "GPIO15", "MODE_SW"), (None, "GPIO16", "LED"), (None, "3V3", "3V3"), (None, "GND", "GND")],
        [(None, "USB D+/D-", "USB_HID"), (None, "5V in", "VBUS"), (None, "BLE", "radio")], extra="TinyUSB HID + NimBLE HID")
    sh.chip(1300, 90, 150, "U2", "TP4056 + protection", [(None, "IN+", "VBUS"), (None, "IN-", "GND")],
            [(None, "BAT+", "VBAT"), (None, "BAT-", "GND"), (None, "OUT+", "VBAT_SW")], extra="LiPo charger module")
    sh.chip(1300, 340, 150, "U3", "MCP1700-3302 LDO", [(None, "VIN", "VBAT_SW"), (None, "GND", "GND")], [(None, "VOUT", "3V3")],
            extra="or the devkit's own 3V3 from VBUS")
    sh.twopin(800, 400, "SW1", "slide", "MODE_SW", "GND")
    sh.note(900, 404, ["open = gamepad HID, closed = keyboard HID"])
    sh.twopin(800, 450, "SW2", "power", "VBAT", "VBAT_SW")
    sh.twopin(800, 500, "LED1", "+330R", "LED", "GND")
    sh.note(800, 540, ["Power: on USB, VBUS feeds the devkit and charges the cell; unplugged, the cell through",
                       "the LDO. A 500 mAh cell runs an S3 in BLE modem sleep for a day (authored; measure).",
                       "Skip the battery entirely for a USB-only cable adapter: the S3 devkit alone is the whole thing."])

    sh.zone(20, 640, 1660, 290, "WHAT THE HOST SEES")
    def mono(x, y, lines):
        for i, l in enumerate(lines):
            sh.text(x, y + i * 13, l, "pin")
    mono(40, 675, [
        "Keyboard mode   BLE HID keyboard (or USB HID keyboard). Buttons map to keys: A=x B=z Select=RShift Start=Enter D-pad=arrows (configurable).",
        "                Works with any phone, tablet or PC, browser emulators included, with no game-controller support needed. iOS accepts BLE keyboards natively.",
        "Gamepad mode    BLE HID gamepad report (8 buttons + hat). Android, Windows, Linux, macOS and Steam take generic HID gamepads;",
        "                iOS only takes MFi, Xbox and PlayStation layouts, so keyboard mode is the iOS answer. USB HID gamepad on the S3 works everywhere.",
        "Bench mode      Wi-Fi: the adapter streams pad bytes over UDP to the head at 1 kHz, keyed by its own poll count. The head schedules them as AT lines",
        "                onto the bridge, so a hand on a wireless pad becomes a scripted, logged, replayable history. Same L format, one more source.",
        "Two pads        one adapter, two HID interfaces (or two report IDs); both polled on the shared latch and clock.",
        "Latency         1 kHz poll + BLE 7.5 ms connection interval: 8 to 10 ms authored; USB HID 1 ms polling: ~2 ms authored. Measure with the bench's own trigger.",
    ])
    sh.done(OUT / "pad-adapter.svg")


OUT = Path(sys.argv[1] if len(sys.argv) > 1 else ".")

# The page a laid sheet is drawn to fit. Asked of the frame rather than
# typed here: the title block's height is part of this number.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import sheetframe as _sf  # noqa: E402
LETTER = _sf.drawing_box("ansi-a")

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    sheet_v1()
    sheet_v1b()
    sheet_v2()
    sheet_v2b()
    sheet_logic()
    sheet_pad()
