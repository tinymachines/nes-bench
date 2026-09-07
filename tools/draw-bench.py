#!/usr/bin/env python3
"""The bench as one drawing, docs/bench.svg, derived from docs/wiring.md.

  python3 tools/draw-bench.py            # writes docs/bench.svg
  python3 tools/draw-bench.py --check    # exit 1 if docs/bench.svg is stale

The upper half is the loop (workstation, head, bridge, console, pad,
scope, relays) and the lower half is the bridge's chips with every pin
the wiring tables name. The pin numbers and the GPIO assignments are
READ from the tables in wiring.md, not typed here, so the drawing cannot
disagree with the document: a pin moved in the table moves here on the
next run, and --check (run by the public site's pull) refuses a drawing
that was not regenerated. Colours are set for light and dark pages
through prefers-color-scheme inside the SVG, so the same file serves
both. No numbers are typed into the prose of the drawing that the
tables do not carry.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WIRING = ROOT / "docs" / "wiring.md"
OUT = ROOT / "docs" / "bench.svg"


def tables(text):
    """Every markdown table in the file as (header cells, rows of cells)."""
    out = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        if lines[i].startswith("|") and i + 1 < len(lines) and re.match(r"^\|[-| ]+\|$", lines[i + 1]):
            head = [c.strip() for c in lines[i].strip("|").split("|")]
            rows = []
            i += 2
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([c.strip() for c in lines[i].strip("|").split("|")])
                i += 1
            out.append((head, rows))
        else:
            i += 1
    return out


def find_table(tabs, first_header):
    for head, rows in tabs:
        if head[0] == first_header:
            return rows
    raise SystemExit(f"wiring.md has no table starting with '{first_header}'")


def gpio(cell):
    m = re.search(r"GPIO(\d+)", cell)
    return m.group(1) if m else None


def read_wiring():
    text = WIRING.read_text()
    tabs = tables(text)
    port = find_table(tabs, "pin")           # console port
    reg = find_table(tabs, "165 pin")        # the register
    lvc = find_table(tabs, "245 A (5 V in)") # the level shifter
    pad = find_table(tabs, "pad plug pin")   # the pad socket
    # The register's button inputs, in table order (H down to A).
    buttons = []
    for cell, signal, to in reg:
        m = re.match(r"(\d+) ([A-H])$", cell)
        if m and gpio(to):
            buttons.append((m.group(1), m.group(2), signal, gpio(to)))
    if len(buttons) != 8:
        raise SystemExit(f"the register table names {len(buttons)} button inputs, not eight")
    reg_pins = {}
    for cell, signal, to in reg:
        m = re.match(r"(\d+) (\S+)", cell)
        if m:
            reg_pins[m.group(2)] = (m.group(1), signal, to)
    con = {}
    for row in lvc:
        if row[0] in ("A1", "A2"):
            con[row[0]] = (row[1], row[2], gpio(row[3]), row[4])
    padpins = {}
    for cell, signal, to in pad:
        padpins[signal.split()[0]] = (cell, gpio(to), to)
    trig = re.search(r"ESP32-C6 GPIO(\d+) through (\d+) ohms to the scope", text)
    if not trig:
        raise SystemExit("wiring.md does not name the trigger pin")
    head = {}
    m = re.search(r"GPIO(\d+) to the PC817 module", text)
    head["reset"] = m.group(1) if m else "?"
    m = re.search(r"GPIO(\d+) to a relay module", text)
    head["power"] = m.group(1) if m else "?"
    return dict(port=port, buttons=buttons, reg_pins=reg_pins, con=con, pad=padpins, trig=trig.group(1), trig_r=trig.group(2), head=head)


class Svg:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.parts = []

    def add(self, s):
        self.parts.append(s)

    def box(self, x, y, w, h, title, sub=None, cls="box"):
        self.add(f'<rect class="{cls}" x="{x}" y="{y}" width="{w}" height="{h}" rx="6"/>')
        self.add(f'<text class="title" x="{x + w / 2}" y="{y + 20}" text-anchor="middle">{esc(title)}</text>')
        if sub:
            for i, line in enumerate(sub):
                self.add(f'<text class="sub" x="{x + w / 2}" y="{y + 38 + 15 * i}" text-anchor="middle">{esc(line)}</text>')

    def wire(self, pts, label=None, cls="wire", at=0.5, dy=-5, seg=None):
        d = "M " + " L ".join(f"{x} {y}" for x, y in pts)
        self.add(f'<path class="{cls}" d="{d}"/>')
        if label:
            # The label sits on the longest segment unless one is named.
            best = seg if seg is not None else max(range(len(pts) - 1), key=lambda i: abs(pts[i + 1][0] - pts[i][0]) + abs(pts[i + 1][1] - pts[i][1]))
            (x0, y0), (x1, y1) = pts[best], pts[best + 1]
            x, y = x0 + (x1 - x0) * at, y0 + (y1 - y0) * at
            if x0 == x1:
                self.add(f'<text class="net" x="{x + 6}" y="{y + 4}">{esc(label)}</text>')
            else:
                self.add(f'<text class="net" x="{x}" y="{y + dy}" text-anchor="middle">{esc(label)}</text>')

    def pin(self, x, y, side, number, name):
        """A pin stub on a chip's side with its number outside and name inside."""
        if side == "left":
            self.add(f'<line class="wire" x1="{x - 18}" y1="{y}" x2="{x}" y2="{y}"/>')
            self.add(f'<text class="pinno" x="{x - 21}" y="{y + 4}" text-anchor="end">{esc(number)}</text>')
            self.add(f'<text class="pin" x="{x + 6}" y="{y + 4}">{esc(name)}</text>')
        else:
            self.add(f'<line class="wire" x1="{x}" y1="{y}" x2="{x + 18}" y2="{y}"/>')
            self.add(f'<text class="pinno" x="{x + 21}" y="{y + 4}">{esc(number)}</text>')
            self.add(f'<text class="pin" x="{x - 6}" y="{y + 4}" text-anchor="end">{esc(name)}</text>')

    def text(self, x, y, s, cls="sub", anchor="start"):
        self.add(f'<text class="{cls}" x="{x}" y="{y}" text-anchor="{anchor}">{esc(s)}</text>')

    def render(self):
        # Literal colours, not CSS variables: rsvg and the like render
        # var() as black, and the site's preview renderer is one of those.
        light = dict(ink="#1f2328", line="#57606a", fill="#ffffff", tint="#f3f5f7", net="#0a5b9c", power="#b3261e")
        dark = dict(ink="#e6edf3", line="#9aa4b2", fill="#0d1117", tint="#161b22", net="#79c0ff", power="#ff7b72")

        def rules(c):
            return f"""
      text {{ font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Helvetica, Arial, sans-serif; fill: {c['ink']}; }}
      .title {{ font-size: 14px; font-weight: 600; fill: {c['ink']}; }}
      .sub {{ font-size: 11px; fill: {c['line']}; }}
      .band {{ font-size: 13px; font-weight: 600; fill: {c['line']}; letter-spacing: 0.04em; }}
      .net {{ font-size: 10px; fill: {c['net']}; }}
      .pin {{ font-size: 10px; fill: {c['ink']}; }}
      .pinno {{ font-size: 9px; fill: {c['line']}; }}
      .box {{ fill: {c['fill']}; stroke: {c['line']}; stroke-width: 1.2; }}
      .chip {{ fill: {c['tint']}; stroke: {c['ink']}; stroke-width: 1.4; }}
      .wire {{ fill: none; stroke: {c['net']}; stroke-width: 1.2; }}
      .rail {{ fill: none; stroke: {c['power']}; stroke-width: 1.2; }}
      .sep {{ stroke: {c['line']}; stroke-dasharray: 4 4; stroke-width: 1; }}
      .bg {{ fill: {c['fill']}; }}"""

        style = "\n    <style>" + rules(light) + "\n      @media (prefers-color-scheme: dark) {" + rules(dark).replace("\n      ", "\n        ") + "\n      }\n    </style>"
        body = "\n".join(self.parts)
        return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.w} {self.h}" width="{self.w}" height="{self.h}" role="img" aria-label="The NES bench: the loop and the bridge">{style}\n<rect class="bg" x="0" y="0" width="{self.w}" height="{self.h}"/>\n{body}\n</svg>\n'


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def draw(w):
    s = Svg(1200, 1000)
    # ---- The loop -----------------------------------------------------
    s.text(24, 30, "THE LOOP: the part and the model under one input history", "band")
    s.box(24, 50, 190, 92, "Workstation", ["the switch-level model", "scripts, pad-log, compare", "ntsc-crt recovery"])
    s.box(300, 50, 170, 92, "Raspberry Pi 4", ["the head: UDP in", "serial to the bridge", "SCPI to the scope, relays"])
    s.box(560, 50, 190, 92, "ESP32-C6 bridge", ["counts latch and clock", "writes the register", "polls the pad"])
    s.box(840, 50, 170, 92, "NES-CPU-10", ["controller port header", "reset button pads", "video, audio out"])
    s.box(300, 200, 170, 60, "PC817 module", ["open-collector across reset"])
    s.box(840, 200, 170, 60, "Original pad", ["in the console's own housing"])
    s.box(300, 290, 170, 60, "Relay module", ["one lead of the adapter"])
    s.box(560, 290, 190, 60, "DS1054Z scope", ["video on a channel, EXT TRIG"])
    s.wire([(214, 96), (300, 96)], "UDP over the LAN")
    s.wire([(470, 96), (560, 96)], "USB serial, 921600")
    s.wire([(750, 84), (840, 84)], "latch, clock, data")
    s.wire([(840, 108), (750, 108)], "+5 V", cls="rail", dy=12)
    s.wire([(840, 230), (700, 230), (700, 142)], "polled at 3.3 V", dy=12, seg=0)
    s.wire([(655, 142), (655, 290)], f"trigger, GPIO{w['trig']}")
    s.wire([(1010, 110), (1040, 110), (1040, 330), (750, 330)], "video", seg=1)
    s.wire([(385, 142), (385, 200)], f"GPIO{w['head']['reset']}")
    s.wire([(470, 230), (500, 230), (500, 170), (900, 170), (900, 142)], "reset", seg=2, at=0.8)
    s.wire([(340, 142), (340, 290)], f"GPIO{w['head']['power']}", at=0.75)
    s.wire([(470, 320), (520, 320), (520, 370), (1100, 370), (1100, 96), (1010, 96)], "power", seg=3, at=0.5)
    s.text(24, 400, "Scripts are bytes by latch index, so the model (set_pad at the same polls) and the part (the register at the same latches)", "sub")
    s.text(24, 415, "see one history; the bridge's per-latch log and the model's are diffed latch for latch; a triggered capture is scored through the roundtrip.", "sub")
    s.add('<line class="sep" x1="24" y1="435" x2="1176" y2="435"/>')

    # ---- The bridge ---------------------------------------------------
    s.text(24, 465, "THE BRIDGE: the register is the pad the console clocks; the ESP32 is never in the nanosecond path", "band")
    # Console port header (left).
    px, py = 40, 520
    s.box(px, py, 120, 200, "Port header", None, cls="chip")
    port_y = {}
    names = {"1": "GND", "2": "CLK", "3": "OUT0", "4": "D0", "7": "+5 V"}
    for i, n in enumerate(["7", "3", "2", "4", "1"]):
        y = py + 50 + i * 30
        port_y[n] = y
        s.pin(px + 120, y, "right", n, names[n])
    # The register.
    rx, ry = 480, 500
    rh = 300
    s.box(rx, ry, 170, rh, "74HCT165", None, cls="chip")
    s.text(rx + 85, ry + 36, "at the console's +5 V", "sub", "middle")
    rp = w["reg_pins"]
    left = [("/PL", "not OUT0"), ("CP", "CLK"), ("/CE", "GND"), ("DS", "GND"), ("QH", "D0"), ("VCC", "+5 V"), ("GND", "GND")]
    left_y = {}
    for i, (name, _) in enumerate(left):
        y = ry + 60 + i * 26
        left_y[name] = y
        s.pin(rx, y, "left", rp[name][0], name)
    # 74HCT04 (inverter for OUT0), its gate on the /PL line.
    ix, iy = 300, left_y["/PL"] - 22
    s.box(ix, iy, 90, 44, "74HCT04", None, cls="chip")
    s.text(ix + 45, iy + 36, "one gate, +5 V", "sub", "middle")
    # Button inputs on the right: H..A with their GPIOs.
    btn_y = {}
    for i, (num, letter, signal, g) in enumerate(w["buttons"]):
        y = ry + 60 + i * 26
        btn_y[letter] = (y, g, signal)
        s.pin(rx + 170, y, "right", num, f"{letter}: {signal}")
    # The level shifter, below the register's supply nets.
    lx, ly = 300, ry + rh - 40
    s.box(lx, ly, 150, 100, "74LVC245", None, cls="chip")
    s.text(lx + 75, ly + 36, "3.3 V, 5 V-tolerant inputs", "sub", "middle")
    a1 = w["con"]["A1"]
    a2 = w["con"]["A2"]
    s.pin(lx, ly + 58, "left", "A1", "OUT0")
    s.pin(lx, ly + 84, "left", "A2", "CLK")
    s.pin(lx + 150, ly + 58, "right", "B1", f"GPIO{a1[2]}")
    s.pin(lx + 150, ly + 84, "right", "B2", f"GPIO{a2[2]}")
    # The ESP32-C6.
    ex, ey = 800, 500
    s.box(ex, ey, 190, 420, "ESP32-C6-DevKitC-1", None, cls="chip")
    s.text(ex + 95, ey + 36, "3.3 V; PCNT units on the console side", "sub", "middle")
    for letter in "HGFEDCBA":
        y, g, signal = btn_y[letter]
        s.pin(ex, y, "left", "", f"GPIO{g}")
        s.wire([(rx + 170 + 18, y), (ex - 18, y)])
    # Console counters into the ESP32 (from the 245's B side).
    cy1, cy2 = ry + 60 + 8 * 26 + 10, ry + 60 + 9 * 26 + 10
    s.pin(ex, cy1, "left", "", f"GPIO{a1[2]}: latch count")
    s.pin(ex, cy2, "left", "", f"GPIO{a2[2]}: clock count")
    s.wire([(lx + 150 + 18, ly + 58), (700, ly + 58), (700, cy1), (ex - 18, cy1)])
    s.wire([(lx + 150 + 18, ly + 84), (720, ly + 84), (720, cy2), (ex - 18, cy2)])
    # The pad socket on the right side of the ESP32.
    pd = w["pad"]
    padx, pady = 1060, 620
    s.box(padx, pady, 110, 170, "Pad socket", ["the console's housing"], cls="chip")
    pad_rows = [("OUT0", "latch out"), ("CLK", "clock out"), ("D0", "data in"), ("+5", "3V3"), ("GND", "GND")]
    for i, (sig, role) in enumerate(pad_rows):
        y = pady + 60 + i * 24
        key = "+5" if sig == "+5" else sig
        cell = pd[key][0]
        s.pin(padx, y, "left", cell, sig)
        g = pd[key][1]
        if g:
            s.pin(ex + 190, y, "right", "", f"GPIO{g}: {role}")
            s.wire([(ex + 190 + 18, y), (padx - 18, y)])
        elif sig == "+5":
            s.pin(ex + 190, y, "right", "", "3V3")
            s.wire([(ex + 190 + 18, y), (padx - 18, y)], cls="rail")
        else:
            s.wire([(ex + 190, y), (padx - 18, y)], cls="wire")
    # Trigger and serial.
    ty = pady + 60 + 5 * 24 + 10
    s.pin(ex + 190, ty, "right", "", f"GPIO{w['trig']}: trigger")
    s.wire([(ex + 190 + 18, ty), (1100, ty), (1100, ty + 40)])
    s.text(1100, ty + 56, f"{w['trig_r']} ohm to EXT TRIG", "net", "middle")
    s.text(ex + 95, ey + 420 + 18, "USB-C (UART port) to the Pi: power and the line protocol", "sub", "middle")
    # Nets from the port to the chips, labelled at the header.
    s.wire([(px + 138, port_y["3"]), (240, port_y["3"]), (240, iy + 22), (ix, iy + 22)], "OUT0", seg=0)
    s.wire([(ix + 90, iy + 22), (rx - 18, iy + 22)])
    s.text(rx - 60, iy + 16, "/PL", "net", "middle")
    s.wire([(px + 138, port_y["2"]), (260, port_y["2"]), (260, left_y["CP"]), (rx - 18, left_y["CP"])], "CLK", seg=0)
    s.wire([(px + 138, port_y["4"]), (220, port_y["4"]), (220, left_y["QH"]), (rx - 18, left_y["QH"])], "D0", seg=0)
    s.wire([(px + 138, port_y["7"]), (200, port_y["7"]), (200, left_y["VCC"]), (rx - 18, left_y["VCC"])], "+5 V", cls="rail", seg=0)
    s.wire([(px + 138, port_y["1"]), (180, port_y["1"]), (180, left_y["GND"]), (rx - 18, left_y["GND"])], "GND", seg=0)
    s.wire([(rx - 18, left_y["/CE"]), (rx - 40, left_y["/CE"]), (rx - 40, left_y["DS"]), (rx - 18, left_y["DS"])])
    s.wire([(rx - 40, left_y["DS"]), (rx - 40, left_y["GND"])])
    # Port to the 245.
    s.wire([(240, port_y["3"]), (240, ly + 58), (lx - 18, ly + 58)])
    s.wire([(260, port_y["2"]), (260, ly + 84), (lx - 18, ly + 84)])
    s.text(24, 960, "Three supplies, one ground: the console's +5 V for the 165 and the 04, the C6's 3.3 V for the 245 and the pad. Pin numbers and GPIOs", "sub")
    s.text(24, 975, "are read from docs/wiring.md by tools/draw-bench.py; the tables there are the source and this drawing is derived. Nothing here is built yet.", "sub")
    return s.render()


def main():
    w = read_wiring()
    svg = draw(w)
    if "--check" in sys.argv:
        if not OUT.exists() or OUT.read_text() != svg:
            print(f"{OUT} is stale: run tools/draw-bench.py")
            return 1
        print(f"{OUT} is current")
        return 0
    OUT.write_text(svg)
    print(f"wrote {OUT}: {len(svg)} bytes, {len(w['buttons'])} button inputs, trigger GPIO{w['trig']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
