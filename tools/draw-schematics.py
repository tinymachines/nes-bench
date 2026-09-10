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
    .pinno { font-size: 8px; fill: #57606a; }
    .net { font-size: 9.5px; fill: #0a5b9c; font-weight: 600; }
    .rail5 { font-size: 9px; fill: #b3261e; font-weight: 700; }
    .rail3 { font-size: 9px; fill: #b35c00; font-weight: 700; }
    .gnd { font-size: 9px; fill: #1f2328; font-weight: 700; }
    .note { font-size: 10px; fill: #57606a; font-family: ui-sans-serif, system-ui, sans-serif; }
    .box { fill: #ffffff; stroke: #1f2328; stroke-width: 1.3; }
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


class Sheet:
    def __init__(self, w, h, title, sub):
        self.w, self.h = w, h
        self.o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-label="{title}">',
                  STYLE, f'<rect x="0" y="0" width="{w}" height="{h}" fill="#ffffff"/>',
                  f'<text class="title" x="24" y="30">{title}</text>',
                  f'<text class="sub" x="24" y="46">{sub}</text>']

    def add(self, s):
        self.o.append(s)

    def text(self, x, y, s, cls, anchor="start"):
        s = s.replace("&", "&amp;").replace("<", "&lt;")
        self.add(f'<text class="{cls}" x="{x}" y="{y}" text-anchor="{anchor}">{s}</text>')

    def note(self, x, y, lines):
        for i, l in enumerate(lines):
            self.text(x, y + i * 13, l, "note")

    def zone(self, x, y, w, h, label):
        self.add(f'<rect class="zone" x="{x}" y="{y}" width="{w}" height="{h}" rx="6"/>')
        self.text(x + 8, y + 14, label, "sub")

    def netlabel(self, x, y, name, side):
        """A net flag at the end of a pin lead. Rails get their symbol."""
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
        self.add(f'<rect class="{"conn" if conn else "box"}" x="{x}" y="{y}" width="{w}" height="{h}" rx="3"/>')
        self.text(x + 6, y + 14, ref, "ref")
        self.text(x + 6, y + 26, part, "part")
        if extra:
            self.text(x + 6, y + 38, extra, "part")
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
        if horizontal:
            self.netlabel(x, y, net_a, "L")
            self.add(f'<line class="lead" x1="{x}" y1="{y}" x2="{x+18}" y2="{y}"/>'
                     f'<rect class="box" x="{x+18}" y="{y-7}" width="44" height="14"/>'
                     f'<line class="lead" x1="{x+62}" y1="{y}" x2="{x+80}" y2="{y}"/>')
            self.text(x + 40, y - 10, ref, "pinno", "middle")
            self.text(x + 40, y + 4, part, "pin", "middle")
            self.netlabel(x + 80, y, net_b, "R")

    def done(self, path):
        self.add("</svg>")
        Path(path).write_text("\n".join(self.o))
        print(path)


# --------------------------------------------------------------- shared parts
def console_port(sh, x, y, ref, nets):
    """The NES-001 7-pin controller port as seen at the board header."""
    return sh.chip(x, y, 130, ref, "console controller port", [], [
        (1, "GND", "GND"), (2, "CLK", nets["clk"]), (3, "OUT0", nets["out0"]),
        (4, "D0", nets["d0"]), (5, "D3", "NC"), (6, "D4", "NC"), (7, "+5V", "+5V")], conn=True,
        extra="looking into the console's socket")


def pad_socket(sh, x, y, ref, latch, clk, d0, vcc="3V3"):
    return sh.chip(x, y, 130, ref, "original pad, on the bridge", [
        (1, "GND", "GND"), (2, "CLK", clk), (3, "OUT0", latch), (4, "D0", d0),
        (5, "D3", "NC"), (6, "D4", "NC"), (7, "+5V", vcc)], [], conn=True)


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
        (None, "USB-A", "PI_USB"), (None, "GPIO17", "RST_DRIVE"), (None, "GPIO27", "PWR_DRIVE"), (None, "GND", "GND"), (None, "ETH", "LAN")],
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
def sheet_v1b():
    sh = Sheet(1900, 1000, "nes-bench bridge v1b: the UNO version, one supply, one port",
               "the ATmega328 is a 5 V part, so the register, the pad and the console share one domain. 2026-09-08. Not built; pulse widths authored until B0.")
    sh.zone(20, 60, 1860, 640, "EVERYTHING AT +5V (the UNO's own 5 V pin, fed by its USB from the Pi)")
    console_port(sh, 60, 90, "J1", {"clk": "CON_CLK", "out0": "CON_OUT0", "d0": "CON_D0"})
    sh.chip(400, 90, 130, "U1", "74HCT04  at +5V", [(1, "1A", "CON_OUT0"), (14, "VCC", "+5V"), (7, "GND", "GND")],
            [(2, "1Y", "/PL")], extra="2.0 V threshold: safe on NMOS OUT0")
    hct165(sh, 720, 90, "U2", "/PL", "CON_CLK", "CON_D0", part="74HC165  at +5V (the TI bag)", inputs=["Q_A", "Q_B", "Q_SEL", "Q_START", "Q_UP", "Q_DOWN", "Q_LEFT", "Q_RIGHT"])
    sh.chip(1140, 90, 140, "U3", "74HC595  at +5V", [
        (14, "SER", "MOSI"), (11, "SRCLK", "SCK"), (12, "RCLK", "RCLK"), (13, "/OE", "GND"), (10, "/SRCLR", "+5V"), (16, "VCC", "+5V"), (8, "GND", "GND")],
        [(15, "QA", "Q_A"), (1, "QB", "Q_B"), (2, "QC", "Q_SEL"), (3, "QD", "Q_START"), (4, "QE", "Q_UP"), (5, "QF", "Q_DOWN"),
         (6, "QG", "Q_LEFT"), (7, "QH", "Q_RIGHT"), (9, "QH'", "NC")], extra="one RCLK edge = one byte")
    sh.chip(1560, 90, 190, "A1", "Arduino UNO R3 (ATmega328P)", [
        (None, "D13 SCK", "SCK"), (None, "D11 MOSI", "MOSI"), (None, "D10", "RCLK"), (None, "D5 (T1)", "CON_OUT0"),
        (None, "D2 (INT0)", "CON_CLK"), (None, "D3", "TRIG"), (None, "5V", "+5V"), (None, "GND", "GND"), (None, "USB-B", "PI_USB")],
        [(None, "D6", "PAD_LATCH"), (None, "D7", "PAD_CLK"), (None, "D8", "PAD_D0"), (None, "D0, D1", "serial")], extra="5 V logic, 16 MHz")
    pad_socket(sh, 1140, 400, "J2", "PAD_LATCH", "PAD_CLK", "PAD_D0", vcc="+5V")
    sh.twopin(160, 440, "C1..C3", "100nF", "+5V", "GND")
    sh.note(300, 444, ["one across each of U1, U2, U3"])
    sh.twopin(160, 500, "R1", "100R", "TRIG", "EXT_TRIG")
    sh.note(380, 504, ["to DS1054Z rear EXT TRIG. Check the input's rating first;", "if 5 V exceeds it, a 2:1 divider (two 1k) after R1."])
    sh.note(60, 560, ["Why this works where the C6 needed shifters: every UNO pin is 5 V, so HC parts at 5 V see real highs,",
                      "the console's OUT0 and CLK are read directly, and the pad runs at the 5 V it was built for.",
                      "Why the 595 stays: SPI clocks 8 bits in 2 us at 4 MHz, then one RCLK edge moves them in ~10 ns.",
                      "No two-store PORT write, no window argument; the firmware still pulses RCLK only while D5 reads low."])
    sh.note(1380, 400, ["D5 is Timer1's external clock input (T1): a 16-bit", "hardware counter of OUT0 rising edges = latch index.",
                        "D2 (INT0) falling-edge ISR counts clocks per poll,", "480/s, nothing for a 16 MHz part.",
                        "D3 rises at latch T (one loop late, ~100 us); the", "74LS74 option makes it edge-exact later.",
                        "Serial 115200 to the Pi over the UNO's own USB."])
    sh.zone(20, 720, 1860, 260, "HEAD AND RELAYS (unchanged from v1 except the relay supply)")
    sh.note(40, 750, ["Pi GPIO17 -> PC817 (or one TLP281 channel) -> console reset pads, 100 ms pulse.",
                      "Pi GPIO27 -> relay module IN (active low). Relay module VCC from the Pi's 5 V pin: the Songle SRD-05VDC and the",
                      "Tongling 2-channel board are 5 V coil modules with opto inputs; a 3.3 V GPIO driving the input low turns them on.",
                      "Normally-open contact in series with one lead of the AC adapter cable, never the mains side.",
                      "Grounds: J1 pin 1, the bridge, the UNO GND and the Pi GND (through USB) are one net.",
                      "Scope: video on CH3 at the AUX/RF input (CH1 is B2's master clock), EXT TRIG from R1, SCPI over the LAN from the Pi."])
    sh.done(OUT / "bench-v1b.svg")

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
    sh.twopin(160, 760, "C1,C2", "100nF", "+5V", "GND")
    sh.note(300, 764, ["U1, U2, U6 supply pins; C5 for U8"])
    sh.twopin(560, 760, "C3,C4", "100nF", "3V3", "GND")
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
    sh.note(60, 640, ["Why the 595s: sixteen bits shift in over SPI at any time; nothing changes at the 165s until one RCLK",
                      "rising edge moves both bytes to the outputs in one ~10 ns step. A tear during a load becomes impossible,",
                      "and the firmware still only pulses RCLK while both OUT0 lines read low. 3V3 outputs into HCT inputs",
                      "(Vih 2.0 V) is in spec. 3 GPIOs replace 8; port 2 costs none. DS on both 165s to GND: bit 9+ reads 1."])
    sh.twopin(160, 760, "C1,C2", "100nF", "+5V", "GND")
    sh.note(300, 764, ["U1, U2, U6 supply pins; C5 for U8"])
    sh.twopin(560, 760, "C3,C4", "100nF", "3V3", "GND")
    sh.note(700, 764, ["U5, U7 (and U3) supply pins"])
    sh.done(OUT / "bench-v2.svg")


# ------------------------------------------------------------- logical sheet
# --------------------------------------------------------------- sheet v2b
def sheet_v2b():
    sh = Sheet(2300, 1320, "nes-bench bridge v2b: the UNO version, two ports, sync counted, one supply",
               "v1b plus a second 165/595 pair on the same SPI chain and an LM1881 whose 5 V outputs go straight into the UNO. 2026-09-09. Not built.")
    sh.zone(20, 60, 1460, 780, "CONSOLE SIDE AND REGISTERS, +5V")
    console_port(sh, 60, 90, "J1", {"clk": "CON1_CLK", "out0": "CON1_OUT0", "d0": "CON1_D0"})
    console_port(sh, 60, 360, "J3", {"clk": "CON2_CLK", "out0": "CON2_OUT0", "d0": "CON2_D0"})
    sh.chip(400, 90, 130, "U1", "74HCT04  at +5V", [(1, "1A", "CON1_OUT0"), (3, "2A", "CON2_OUT0"), (14, "VCC", "+5V"), (7, "GND", "GND")],
            [(2, "1Y", "/PL1"), (4, "2Y", "/PL2")], extra="4 spare inputs to GND")
    hct165(sh, 720, 90, "U2", "/PL1", "CON1_CLK", "CON1_D0", part="74HC165  at +5V", inputs=["Q1A", "Q1B", "Q1SEL", "Q1START", "Q1UP", "Q1DOWN", "Q1LEFT", "Q1RIGHT"])
    hct165(sh, 720, 440, "U6", "/PL2", "CON2_CLK", "CON2_D0", part="74HC165  at +5V", inputs=["Q2A", "Q2B", "Q2SEL", "Q2START", "Q2UP", "Q2DOWN", "Q2LEFT", "Q2RIGHT"])
    sh.chip(1140, 90, 140, "U5", "74HC595  at +5V", [
        (14, "SER", "MOSI"), (11, "SRCLK", "SCK"), (12, "RCLK", "RCLK"), (13, "/OE", "GND"), (10, "/SRCLR", "+5V"), (16, "VCC", "+5V"), (8, "GND", "GND")],
        [(15, "QA", "Q1A"), (1, "QB", "Q1B"), (2, "QC", "Q1SEL"), (3, "QD", "Q1START"), (4, "QE", "Q1UP"), (5, "QF", "Q1DOWN"),
         (6, "QG", "Q1LEFT"), (7, "QH", "Q1RIGHT"), (9, "QH'", "CHAIN")], extra="port 1 byte (shifted in second)")
    sh.chip(1140, 440, 140, "U7", "74HC595  at +5V", [
        (14, "SER", "CHAIN"), (11, "SRCLK", "SCK"), (12, "RCLK", "RCLK"), (13, "/OE", "GND"), (10, "/SRCLR", "+5V"), (16, "VCC", "+5V"), (8, "GND", "GND")],
        [(15, "QA", "Q2A"), (1, "QB", "Q2B"), (2, "QC", "Q2SEL"), (3, "QD", "Q2START"), (4, "QE", "Q2UP"), (5, "QF", "Q2DOWN"),
         (6, "QG", "Q2LEFT"), (7, "QH", "Q2RIGHT"), (9, "QH'", "NC")], extra="port 2 byte, chained")
    sh.note(60, 640, ["Two SPI.transfer() calls (port 2 byte first, then port 1) and one RCLK edge update both registers together.",
                      "The UNO's outputs are 5 V, so HC parts at 5 V see real highs everywhere. No shifters on this sheet at all.",
                      "DS on both 165s to GND: reads after the eighth clock return 1 to the console, as an original pad does."])
    sh.twopin(160, 760, "C1..C5", "100nF", "+5V", "GND")
    sh.note(300, 764, ["one across each of U1, U2, U5, U6, U7, U8"])

    sh.zone(1500, 60, 780, 780, "SYNC SEPARATOR, +5V, straight into the UNO")
    sh.chip(1660, 90, 150, "U8", "LM1881N  at +5V", [
        (2, "VIDEO IN", "VID_AC"), (6, "RSET", "RSET"), (8, "VCC", "+5V"), (4, "GND", "GND")],
        [(1, "CSYNC", "CSYNC"), (3, "VSYNC", "VSYNC"), (5, "BURST", "NC"), (7, "ODD/EVEN", "NC")], extra="5 V outputs: no 245 needed")
    sh.twopin(1660, 330, "C6", "100nF", "VIDEO", "VID_AC")
    sh.note(1800, 334, ["AC couple from the console's video, 1k series"])
    sh.twopin(1660, 380, "R2", "680k", "RSET", "GND")
    sh.twopin(1660, 430, "C7", "100nF", "RSET", "GND")
    sh.note(1540, 500, ["VSYNC: one falling edge per field, 60.0988/s.", "CSYNC: one per line plus the vsync block; the NES",
                        "emits no serrations, so count/field = lines - k (measure k).", "CSYNC at 15.7 kHz on INT1 is ~5% of a 16 MHz",
                        "part; VSYNC and port-2 lines on pin-change interrupts."])

    sh.zone(20, 860, 2260, 440, "THE UNO (all pins 5 V) AND THE HEAD")
    sh.chip(200, 890, 200, "A1", "Arduino UNO R3 (ATmega328P)", [
        (None, "D13 SCK", "SCK"), (None, "D11 MOSI", "MOSI"), (None, "D10", "RCLK"), (None, "D5 (T1)", "CON1_OUT0"), (None, "D2 (INT0)", "CON1_CLK"),
        (None, "D3 (INT1)", "CSYNC"), (None, "D4 (PCINT)", "CON2_OUT0"), (None, "D9 (PCINT)", "CON2_CLK"), (None, "A0 (PCINT)", "VSYNC")],
        [(None, "A1", "TRIG"), (None, "D6", "PAD_LATCH"), (None, "D7", "PAD_CLK"), (None, "D8", "PAD1_D0"), (None, "A2", "PAD2_D0"),
         (None, "5V", "+5V"), (None, "GND", "GND"), (None, "USB-B", "PI_USB")], extra="serial 115200 to the Pi")
    sh.note(560, 900, ["Counters: LATCH1 on Timer1's external clock (hardware, the reference). CLK1 on INT0, CSYNC on INT1,",
                       "LATCH2, CLK2, VSYNC on pin-change ISRs. Every software count is cross-checked against the hardware",
                       "one by the 8-per-latch and polls-per-field gates; a count that fails under MUTATE (D2/D5 jumper swap,",
                       "D4 config pin) is a broken count. Trigger A1 rises at latch T or at (field, line), one loop late.",
                       "L <latch> <byte> <clocks> <t_us> <field> <line>; L2 for port 2; F <field> <t_us> <lines>."])
    sh.note(1400, 900, ["Head and relays: the Pi, unchanged. GPIO17 -> PC817 or TLP281 -> reset pads.",
                        "GPIO27 -> relay IN (active low), relay VCC from the Pi's 5 V pin (5 V coil modules).",
                        "One NO contact in series with one lead of the AC adapter cable. Scope: CH3 video, EXT TRIG",
                        "from A1 through 100R (divider if the input's rating needs it), SCPI over the LAN.",
                        "Pads J2 and J4 as on v1b, at 5 V, sharing PAD_LATCH and PAD_CLK, own D0 each."])
    sh.done(OUT / "bench-v2b.svg")


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
    sh.twopin(400, 300, "R1,R2", "10k", "PAD1_D0", "3V3")
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

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    sheet_v1()
    sheet_v1b()
    sheet_v2()
    sheet_v2b()
    sheet_logic()
    sheet_pad()
