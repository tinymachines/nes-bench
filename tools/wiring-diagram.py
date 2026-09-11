#!/usr/bin/env python3
"""The wiring diagram: the packages as they sit, every wire at right angles.

  python3 tools/wiring-diagram.py [outdir]   # -> docs/wiring-v1b.svg
  python3 tools/wiring-diagram.py --check    # exit 1 if the committed one is stale

The breadboard sheet (tools/breadboard.py) says which hole everything
goes in, and its curved jumpers are hard to follow once there are twenty
of them. This is the same wiring drawn the other way: each chip is its
DIP package seen from above, notch to the left, pin 1 bottom left and
the pins numbered the way the package numbers them; every wire is
horizontal or vertical; every net has its own track and its own colour
and is named at its left end. Rails run along the top and the bottom of
the sheet, as they do on the board.

Placement of the parts along the row is the one authored thing here,
and it is the same left-to-right order as the breadboard sheet. Every
wire is read out of the schematic through tools/netlist.py, so this
cannot show a connection the schematic does not have or miss one it
does, and it asserts both: a net on the schematic with no drawn pin
stops the tool, and so does a drawn pin the schematic does not know.

Routing is a channel router with one track per net. A net whose pins
are all on top edges lives in the top channel; all bottom, the bottom
channel; a net with pins on both edges has a track in each channel and
one vertical between two parts joining them. Verticals cross tracks at
right angles and never share an x; a dot marks a junction, and nothing
else is ever a connection.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from loadmod import load  # noqa: E402

PITCH = 24          # pin pitch on the drawn packages
STUB = 18           # pin stub outside the body
TRACK = 15          # spacing between tracks in a channel
COL = 13            # spacing between around-verticals in a gap
GAP = 132           # between parts along the row
BODY = 170          # height of a body: the pin names run up inside it from both edges
HPITCH = 30         # pin pitch on the header parts, whose names are longer
HEADING_H = 60
LEFT = 70

# ------------------------------------------------------------- AUTHORED
# The parts along the row, left to right, as on the breadboard. A DIP
# is drawn from its pin count; a header part lists its pins by edge.
ROW = [
    ("J1", {"kind": "header", "label": "J1 console cable", "sub": "the plug half, into port 1",
            "top": [(1, "GND"), (2, "CLK"), (3, "OUT0"), (4, "D0"), (5, "+5V")], "bottom": []}),
    ("U1", {"kind": "dip", "pins": 14, "label": "U1 74HCT04", "sub": "inverter"}),
    ("U2", {"kind": "dip", "pins": 16, "label": "U2 74HC165", "sub": "the pad the console reads"}),
    ("U3", {"kind": "dip", "pins": 16, "label": "U3 74HC595", "sub": "the byte the UNO writes"}),
    ("A1", {"kind": "header", "label": "A1 Arduino UNO", "sub": "5 V logic",
            # The UNO's digital header is its top edge, D13 at the left
            # as the board is usually held; power is on the bottom edge.
            "top": [(None, "D13 SCK"), (None, "D11 MOSI"), (None, "D10"), (None, "D8"), (None, "D7"),
                    (None, "D6"), (None, "D5 (T1)"), (None, "D3"), (None, "D2 (INT0)")],
            "bottom": [(None, "5V"), (None, "GND"), (None, "USB-B"), (None, "D0, D1")]}),
    ("R1", {"kind": "header", "label": "R1 100R", "sub": "trigger",
            "top": [(1, "1")], "bottom": [(2, "2")]}),
    ("J2", {"kind": "header", "label": "J2 pad cable", "sub": "the pad half",
            "top": [(1, "GND"), (2, "CLK"), (3, "OUT0"), (4, "D0"), (5, "+5V")], "bottom": []}),
]
# Decoupling, drawn between the bottom rails beside its chip.
CAPS = {"C1": "U1", "C2": "U2", "C3": "U3"}
# The cut cable's lead colours, by pin, both halves (docs/cheat-sheet.md).
LEAD = {1: "yellow", 2: "blue", 3: "black", 4: "green", 5: "red"}
RAIL_COLOUR = {"+5V": "#d02b2b", "GND": "#1b64c8"}
PALETTE = ["#7a3fbf", "#0f8f9e", "#b5651d", "#8d1f5e", "#3f6f2a", "#5b5bd6", "#c2185b",
           "#00796b", "#e65100", "#4527a0", "#2e7d32", "#6d4c41", "#0277bd", "#ad1457",
           "#558b2f", "#ef6c00", "#283593", "#00838f", "#9e9d24", "#d84315", "#1565c0",
           "#6a1b9a", "#f9a825", "#37474f"]

STYLE = """<style>
 text{font-family:ui-sans-serif,'DejaVu Sans',sans-serif;fill:#222}
 .title{font-size:24px;font-weight:700}
 .sub{font-size:13px;fill:#555}
 .ref{font-size:14px;font-weight:700}
 .note{font-size:12px;fill:#555}
 .pin{font-family:ui-monospace,'DejaVu Sans Mono',monospace;font-size:11.5px}
 .pinno{font-family:ui-monospace,'DejaVu Sans Mono',monospace;font-size:11.5px;fill:#666}
 .net{font-family:ui-monospace,'DejaVu Sans Mono',monospace;font-size:12px;font-weight:700;paint-order:stroke;stroke:#fff;stroke-width:3px;stroke-linejoin:round}
 .rail{font-family:ui-monospace,'DejaVu Sans Mono',monospace;font-size:11px;font-weight:700}
 .lead{font-size:11.5px;font-style:italic;fill:#555}
 .body{fill:#f4f2ea;stroke:#222;stroke-width:1.6}
 .hdr{fill:#eef2f7;stroke:#222;stroke-width:1.4}
 .cap{fill:#fff;stroke:#222;stroke-width:1.2}
 .stub{stroke:#222;stroke-width:1.6}
 .wire{fill:none;stroke-width:2.2;stroke-linejoin:miter}
 .railline{fill:none;stroke-width:3}
 .notch{fill:#fff;stroke:#222;stroke-width:1.2}
</style>"""


class Part:
    def __init__(self, ref, spec, x):
        self.ref, self.spec, self.x = ref, spec, x
        self.pins = {}          # key -> (edge, x); key is pin number or pin name
        if spec["kind"] == "dip":
            n = spec["pins"]
            half = n // 2
            self.w = (half - 1) * PITCH + 2 * 20
            for i in range(half):
                px = x + 20 + i * PITCH
                self.pins[i + 1] = ("bottom", px)
                self.pins[n - i] = ("top", px)
        else:
            cols = max(len(spec["top"]), len(spec["bottom"]), 1)
            self.w = (cols - 1) * HPITCH + 2 * 22
            for edge in ("top", "bottom"):
                for i, (no, name) in enumerate(spec[edge]):
                    self.pins[no if no is not None else name] = (edge, x + 22 + i * HPITCH)
        self.right = x + self.w

    def names(self):
        """What the pins are called on the package, for the labels."""
        if self.spec["kind"] == "dip":
            return {}
        return {(no if no is not None else name): name for edge in ("top", "bottom") for no, name in self.spec[edge]}


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class Draw:
    def __init__(self):
        self.o = []
        self.min_font = None

    def add(self, s):
        self.o.append(s)

    def text(self, x, y, s, cls="pin", anchor="start"):
        self.add(f'<text class="{cls}" x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}">{esc(s)}</text>')

    def line(self, x1, y1, x2, y2, cls="stub", colour=None):
        st = f' stroke="{colour}"' if colour else ""
        self.add(f'<line class="{cls}" x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}"{st}/>')

    def poly(self, pts, colour, cls="wire"):
        d = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        self.add(f'<polyline class="{cls}" points="{d}" stroke="{colour}"/>')

    def dot(self, x, y, colour):
        self.add(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.4" fill="{colour}"/>')


def build():
    nl = load(ROOT / "tools" / "netlist.py", "nl")
    sheets, offsheet = nl.collect()
    nodes = sheets["bench-v1b"]
    nets = nl.nets_of(nodes)

    # ---------------------------------------------------------- the row
    parts, x = {}, LEFT
    for ref, spec in ROW:
        p = Part(ref, spec, x)
        parts[ref] = p
        x = p.right + GAP
    row_right = x - GAP
    W = row_right + LEFT

    # Every drawn pin that the schematic knows, and every schematic pin
    # that is drawn. The netlist keys DIP pins by number and header pins
    # by name (they have no number on the sheet).
    def key_of(n):
        return n["pin"] if n["pin"] is not None else n["pinname"]

    drawn = {(ref, k) for ref, p in parts.items() for k in p.pins}
    for n in nodes:
        if n["ref"] in CAPS or n["net"] in nl.NC:
            continue
        k = (n["ref"], key_of(n))
        assert k in drawn, f"{n['ref']} pin {key_of(n)} ({n['pinname']}, net {n['net']}) is on the schematic and not on this drawing"
    wanted = {(n["ref"], key_of(n)) for n in nodes}
    for k in drawn:
        assert k in wanted, f"{k[0]} pin {k[1]} is drawn and the schematic has no such pin"

    # -------------------------------------------------------- the nets
    # Endpoints: (part, key, edge, x). Rails go to the rails; a net with
    # one end that leaves the sheet is a flag at that pin.
    signal, flags = {}, {}
    for net, ns in nets.items():
        if net in nl.RAILS:
            continue
        ends = [(n["ref"], key_of(n)) for n in ns if n["ref"] not in CAPS]
        if len(ends) == 1:
            assert net in offsheet, f"net {net} has one end and is not off-sheet"
            flags[ends[0]] = f"{net}: {offsheet[net]}"
            continue
        signal[net] = [(ref, k, *parts[ref].pins[k]) for ref, k in ends]

    # Tracks: one per net per channel, shortest span nearest the row.
    def span(ends):
        xs = [e[3] for e in ends]
        return min(xs), max(xs)

    top_nets, bot_nets, mixed = [], [], []
    for net, ends in signal.items():
        edges = {e[2] for e in ends}
        (mixed if len(edges) == 2 else top_nets if edges == {"top"} else bot_nets).append(net)

    # The around-vertical of a mixed net: a gap inside its span, the
    # emptiest, nearest its middle; a column of its own in that gap.
    gaps = [((parts[a].right + parts[b].x) / 2) for (a, _), (b, _) in zip(ROW, ROW[1:])]
    gap_use = [0] * len(gaps)
    around = {}
    for net in sorted(mixed, key=lambda n: span(signal[n])[1] - span(signal[n])[0]):
        lo, hi = span(signal[net])
        mid = (lo + hi) / 2
        inside = [i for i, g in enumerate(gaps) if lo < g < hi]
        cands = inside or list(range(len(gaps)))
        i = min(cands, key=lambda i: (gap_use[i] if inside else 0, abs(gaps[i] - mid)))
        k = gap_use[i]
        gap_use[i] += 1
        offset = ((k + 1) // 2) * COL * (1 if k % 2 else -1)
        around[net] = gaps[i] + offset
    assert max(gap_use, default=0) * COL < GAP - 40, "a gap holds more verticals than it has room for"

    def tracks(names, channel):
        """Track index per net in a channel, shortest span first."""
        order = []
        for net in names:
            ends = [e for e in signal[net] if e[2] == channel]
            xs = [e[3] for e in ends] + ([around[net]] if net in around else [])
            order.append((max(xs) - min(xs), net, xs))
        order.sort()
        return {net: (i, xs) for i, (_s, net, xs) in enumerate(order)}

    top = tracks(top_nets + mixed, "top")
    bot = tracks(bot_nets + mixed, "bottom")

    # ------------------------------------------------------- geometry
    y_top = HEADING_H + 40 + 2 * 22 + 12 + len(top) * TRACK + STUB + 10   # body top
    y_bot = y_top + BODY
    def track_y_top(i):
        return y_top - STUB - 14 - i * TRACK
    def track_y_bot(i):
        return y_bot + STUB + 14 + i * TRACK
    rail_top = {"GND": track_y_top(len(top)) - 8, "+5V": track_y_top(len(top)) - 30}
    rail_bot = {"GND": track_y_bot(len(bot)) + 8, "+5V": track_y_bot(len(bot)) + 30}
    H = rail_bot["+5V"] + 70

    d = Draw()
    d.add(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
          f'aria-label="Bridge v1b wiring diagram">')
    d.add(STYLE)
    d.add(f'<rect x="0" y="0" width="{W}" height="{H}" fill="#ffffff"/>')
    d.add(f'<g class="sheet-heading" data-height="{HEADING_H}">')
    d.text(24, 30, "Bridge v1b: every wire, at right angles, on the packages as they sit", "title")
    d.text(24, 46, "Notch left, pin 1 bottom left, numbered as the package is. One track and one colour per net, named "
                   "at its left end; a dot is a junction, a crossing is nothing. Every wire is read out of the schematic.", "sub")
    d.add("</g>")

    # Rails, top and bottom, joined at the left end.
    for rail, ys in (("+5V", (rail_top["+5V"], rail_bot["+5V"])), ("GND", (rail_top["GND"], rail_bot["GND"]))):
        c = RAIL_COLOUR[rail]
        xl = LEFT - (30 if rail == "+5V" else 16)
        for y in ys:
            d.line(xl, y, row_right + 20, y, "railline", c)
            d.text(row_right + 26, y + 4, rail, "rail")
        d.line(xl, ys[0], xl, ys[1], "railline", c)
    d.text(LEFT - 34, rail_top["+5V"] - 8, "rails joined end to end, as on the board", "note")

    # Parts.
    for ref, p in parts.items():
        spec = p.spec
        names = p.names()
        if spec["kind"] == "dip":
            d.add(f'<rect class="body" x="{p.x}" y="{y_top}" width="{p.w}" height="{BODY}" rx="4"/>')
            d.add(f'<circle class="notch" cx="{p.x}" cy="{y_top + BODY / 2:.1f}" r="9"/>')
            d.add(f'<rect x="{p.x - 10}" y="{y_top + BODY / 2 - 10:.1f}" width="10" height="20" fill="#fff"/>')
            d.text(p.x + p.w / 2, y_top + BODY / 2 - 2, spec["label"], "ref", "middle")
            d.text(p.x + p.w / 2, y_top + BODY / 2 + 13, spec["sub"], "note", "middle")
        else:
            d.add(f'<rect class="hdr" x="{p.x}" y="{y_top}" width="{p.w}" height="{BODY}" rx="4"/>')
            d.text(p.x + p.w / 2, y_top + BODY / 2 - 2, spec["label"], "ref", "middle")
            d.text(p.x + p.w / 2, y_top + BODY / 2 + 13, spec["sub"], "note", "middle")
        for k, (edge, px) in p.pins.items():
            if edge == "top":
                d.line(px, y_top, px, y_top - STUB)
            else:
                d.line(px, y_bot, px, y_bot + STUB)
            # Names run up the inside of the body along the pin, as on a
            # package drawing, so a six-letter name fits a 24 px pitch.
            # Numbers sit beside the stub outside.
            if spec["kind"] == "dip":
                nm = next((n["pinname"] for n in nodes if n["ref"] == ref and n["pin"] == k), "")
                if edge == "top":
                    d.text(px + 4, y_top - 6, str(k), "pinno")
                    d.add(f'<text class="pin" x="{px + 3.5:.1f}" y="{y_top + 12:.1f}" text-anchor="end" '
                          f'transform="rotate(-90 {px + 3.5:.1f} {y_top + 12:.1f})">{esc(nm)}</text>')
                else:
                    d.text(px + 4, y_bot + 14, str(k), "pinno")
                    d.add(f'<text class="pin" x="{px + 3.5:.1f}" y="{y_bot - 12:.1f}" text-anchor="start" '
                          f'transform="rotate(-90 {px + 3.5:.1f} {y_bot - 12:.1f})">{esc(nm)}</text>')
            else:
                # The schematic's name keys the pin; the parentheses it
                # carries there are noise on a package drawing.
                nm = names[k].replace(" (", " ").replace(")", "")
                if edge == "top":
                    d.add(f'<text class="pin" x="{px + 3.5:.1f}" y="{y_top + 12:.1f}" text-anchor="end" '
                          f'transform="rotate(-90 {px + 3.5:.1f} {y_top + 12:.1f})">{esc(nm)}</text>')
                else:
                    d.add(f'<text class="pin" x="{px + 3.5:.1f}" y="{y_bot - 12:.1f}" text-anchor="start" '
                          f'transform="rotate(-90 {px + 3.5:.1f} {y_bot - 12:.1f})">{esc(nm)}</text>')
                if isinstance(k, int) and ref in ("J1", "J2"):
                    d.add(f'<text class="lead" x="{px + 15:.1f}" y="{y_top + 12:.1f}" text-anchor="end" '
                          f'transform="rotate(-90 {px + 15:.1f} {y_top + 12:.1f})">{k} {LEAD[k]}</text>')
        # No-connect pins: an x at the stub end.
        for n in nodes:
            if n["ref"] == ref and n["net"] in nl.NC and key_of(n) in p.pins:
                edge, px = p.pins[key_of(n)]
                y = y_top - STUB - 8 if edge == "top" else y_bot + STUB + 8
                d.line(px - 5, y - 5, px + 5, y + 5)
                d.line(px - 5, y + 5, px + 5, y - 5)

    # Decoupling: a cap standing between the bottom rails beside its chip.
    for cref, host in CAPS.items():
        cx = parts[host].right + 30
        y1, y2 = rail_bot["GND"], rail_bot["+5V"]
        d.line(cx, y1, cx, y2, "stub")
        cy = (y1 + y2) / 2
        d.add(f'<rect class="cap" x="{cx - 5}" y="{cy - 6:.1f}" width="10" height="12"/>')
        d.text(cx + 9, cy + 4, f"{cref} 100nF", "note")

    # Supply pins straight to their rails.
    for net in ("+5V", "GND"):
        for n in nets[net]:
            if n["ref"] in CAPS:
                continue
            p = parts[n["ref"]]
            edge, px = p.pins[key_of(n)]
            c = RAIL_COLOUR[net]
            if edge == "top":
                d.line(px, y_top - STUB, px, rail_top[net], "wire", c)
                d.dot(px, rail_top[net], c)
            else:
                d.line(px, y_bot + STUB, px, rail_bot[net], "wire", c)
                d.dot(px, rail_bot[net], c)

    # Signal nets.
    colours = {net: PALETTE[i % len(PALETTE)] for i, net in enumerate(sorted(signal))}
    for net, ends in signal.items():
        c = colours[net]
        for channel, table, ty, y_edge in (("top", top, track_y_top, y_top - STUB), ("bottom", bot, track_y_bot, y_bot + STUB)):
            if net not in table:
                continue
            i, xs = table[net]
            y = ty(i)
            lo, hi = min(xs), max(xs)
            d.line(lo, y, hi, y, "wire", c)
            for e in ends:
                if e[2] == channel:
                    d.line(e[3], y_edge, e[3], y, "wire", c)
            for xx in xs:
                if lo < xx < hi:
                    d.dot(xx, y, c)
            d.text(lo + 4, y - 3 if channel == "top" else y + 11, net, "net")
        if net in around:
            xa = around[net]
            d.line(xa, track_y_top(top[net][0]), xa, track_y_bot(bot[net][0]), "wire", c)

    # Off-sheet flags at single-ended pins: a short line on and a
    # sentence, horizontal, in the bottom channel where nothing else runs
    # at that x. A flag on a top pin would sit in the tracks, so the
    # parts above keep those pins on their bottom edge.
    per_part = {}
    for (ref, k), text in sorted(flags.items(), key=lambda kv: parts[kv[0][0]].pins[kv[0][1]][1]):
        edge, px = parts[ref].pins[k]
        assert edge == "bottom", f"off-sheet pin {ref} {k} must be on a bottom edge"
        i = per_part.get(ref, 0)
        per_part[ref] = i + 1
        # Two flags on one part step down so their sentences do not sit
        # on each other.
        drop = 26 + 18 * i
        d.line(px, y_bot + STUB, px, y_bot + STUB + drop, "wire", "#444")
        d.text(px - 6, y_bot + STUB + drop + 4, text, "net", "end")

    d.add(f'<text class="note" x="{W - 24}" y="{H - 16}" text-anchor="end">'
          f'{len(signal)} nets on tracks, {len(around)} of them crossing the row; {len(nets["+5V"]) + len(nets["GND"])} '
          f'supply pins on the rails. drawn by tools/wiring-diagram.py</text>')
    d.add("</svg>")
    return "\n".join(d.o) + "\n", len(signal), len(around)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir", nargs="?", default=str(ROOT / "docs"))
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    svg, n, m = build()
    out = Path(a.outdir) / "wiring-v1b.svg"
    if a.check:
        if out.exists() and out.read_text() == svg:
            print(f"wiring-diagram: {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out} is current ({n} nets, {m} crossing the row)")
            return 0
        print(f"wiring-diagram: {out} is stale: run python3 tools/wiring-diagram.py")
        return 1
    out.write_text(svg)
    print(f"wrote {out}  ({n} nets on tracks, {m} crossing the row)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
