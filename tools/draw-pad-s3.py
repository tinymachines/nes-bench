#!/usr/bin/env python3
"""The pad-s3 sheets: one original pad on a Seeed XIAO ESP32S3 with a cell,
a USB keyboard with a host and a BLE keyboard without. Drawing package
TM-NESB-004 (docs/package-pad-s3.json).

  python3 tools/draw-pad-s3.py          # -> docs/pad-s3-{system,pins,progress}.svg
  python3 tools/draw-pad-s3.py --check  # regenerate to a temp dir and compare

AUTHORED, NOT MEASURED, and the sheets say so on every band. No XIAO
has been on this bench; two are on the order list. What IS measured is
the firmware's other target: the same sketch (firmware/pad) on the
ESP32-P4 kit did both paths end to end on 2026-10-13 (docs/pad-build.md),
so the parts of these sheets that are about the pad poll, the two
report shapes and the sink rule are drawn from a working build. The
parts about the XIAO's pins, its charger and the cell are read from
Seeed's wiki and from the parts on the desk, and the progress sheet is
where each of them turns from authored to measured, one row at a time.

The pin numbers are read from Seeed's XIAO ESP32S3 pin map (the wiki
page "Getting Started", read 2026-10-13): D3 GPIO4, D4 GPIO5, D5
GPIO6, D8 GPIO7, D6 GPIO43 TX, D7 GPIO44 RX, user LED GPIO21. The S3's
strapping pins are GPIO0, 3, 45 and 46; none is used. The same four
numbers are what firmware/pad compiles for the S3 with, and
tools/check-pad-s3.py holds the two to each other.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
ds = __import__("draw-schematics")
Sheet = ds.Sheet
DOCS = ROOT / "docs"

# One place for the pins. tools/check-pad-s3.py reads these out of the
# firmware too and holds them equal.
PINS = [
    # (XIAO pin, GPIO, net, what)
    ("D3", 4, "PAD_LATCH", "latch, driven: OUT0 on the pad"),
    ("D4", 5, "PAD_CLK", "clock, driven"),
    ("D5", 6, "PAD_D0", "data, read; R1 10k up to 3V3"),
    ("D8", 7, "MODE_SW", "mode switch to GND: low at boot forces BLE"),
    ("3V3", None, "3V3", "the pad's supply: the 4021 is rated 3 to 18 V, measured at 3.3 V on 2026-09-27"),
    ("GND", None, "GND", "the pad's ground"),
    ("5V", None, "VBUS", "the socket's VBUS; nothing wired here"),
    ("BAT+", None, "CELL+", "pad on the underside, the one AWAY from the socket"),
    ("BAT-", None, "CELL-", "pad on the underside, the one NEAREST the socket (Seeed's own note)"),
    ("D6/D7", "43/44", "TX/RX", "the log: Serial lives here once the socket is the keyboard"),
    ("LED", 21, "", "the user light, lit LOW; the sketch lights it on any button"),
]


def band(sh, y0, rows, bottom, what, label_x=40, text_x=150):
    """Labelled rows: the label in its own column, because SVG collapses
    the runs of spaces a typed column would need."""
    y = y0
    for label, lines in rows:
        sh.text(label_x, y, label, "pin")
        for l in lines:
            sh.text(text_x, y, l, "pin")
            y += 15
        y += 3
    assert y <= bottom, f"the {what} band overflows its zone by {y - bottom} px"


def sheet_system():
    sh = Sheet(1560, 740, "pad-s3: one original pad, one XIAO ESP32S3, one cell",
               "A USB keyboard when a host configures it, a BLE keyboard when none does: firmware/pad, the sketch the "
               "ESP32-P4 kit runs today. AUTHORED 2026-10-13 against Seeed's pin map and the parts on the desk; no XIAO here yet.")
    sh.zone(20, 66, 420, 430, "THE PAD: an original controller, polled at 1 kHz")
    sh.chip(120, 120, 170, "J1", "original NES pad", [],
            [(1, "GND", "GND"), (2, "CLK", "PAD_CLK"), (3, "OUT0", "PAD_LATCH"), (4, "D0", "PAD_D0"), (5, "VCC", "3V3")],
            conn=True, extra="a 4021 inside; lead colours: TM-NESB-003 sheet 5")
    sh.note(40, 330, [
        "poll_pad: OUT0 high 12 us to load, its fall latches,",
        "eight clocks, D0 read before each rising edge.",
        "A pressed button reads LOW. Bit 0 is A, the order",
        "nes_glue::controller::Buttons::as_byte gives.",
        "The same routine on the bridge, pad-usb, pad-ble",
        "and pad: one poll, measured on the P4 at 3.3 V.",
    ])

    sh.zone(460, 66, 620, 430, "THE XIAO: USB and the radio on one die, the charger on the board")
    sh.chip(620, 110, 230, "U1", "Seeed XIAO ESP32S3",
            [(None, "D3 GPIO4", "PAD_LATCH"), (None, "D4 GPIO5", "PAD_CLK"), (None, "D5 GPIO6", "PAD_D0"),
             (None, "D8 GPIO7", "MODE_SW"), (None, "3V3", "3V3"), (None, "GND", "GND")],
            [(None, "USB-C", "HOST"), (None, "BAT+", "CELL+"), (None, "BAT-", "CELL-"), (None, "BLE 5", "AIR")],
            extra="plain, not Sense; antenna fitted before power")
    sh.note(480, 350, [
        "THE SINK FOLLOWS THE HOST (measured on the P4): a host configures the device",
        "within 1.5 s: USB, and the radio never starts. No host: BLE. A host arriving later",
        "takes the reports; a host gone 2 s hands them back to BLE. SW1 low at boot: BLE",
        "regardless, so the pad can charge from a PC without the PC taking the keyboard.",
    ])
    sh.twopin(500, 450, "R1", "10k", "PAD_D0", "3V3")
    sh.twopin(760, 450, "SW1", "mode", "MODE_SW", "GND")

    sh.zone(1100, 66, 440, 430, "THE CELL: on the XIAO's own charger")
    sh.chip(1180, 110, 200, "BT1", "LiPo 3.7 V 2000 mAh", [],
            [(None, "+", "CELL+"), (None, "-", "CELL-")], conn=True, extra="JST lead; 7.4 Wh on the label")
    sh.note(1120, 250, [
        "OPTION A (drawn): the cell on the BAT pads. The",
        "XIAO charges it from its socket and runs from it",
        "with the socket empty. Seeed's table says 100 mA",
        "fast charge, so an empty cell is a day on charge.",
        "",
        "OPTION B (in the drawer): a TP4056 USB-C board",
        "with the DW01 protection pair. Its OUT is the",
        "cell's own voltage, too low for the 5V pin, and",
        "two chargers on one cell is one too many. It",
        "earns a place only if the cell turns out to have",
        "no protection of its own, or 100 mA is too slow.",
        "DECIDE AT THE BENCH WITH A METER.",
    ])

    sh.zone(20, 512, 1520, 210, "WHAT IS MEASURED, WHAT IS AUTHORED, WHAT IS NEXT")
    band(sh, 542, [
        ("MEASURED", ["firmware/pad on the ESP32-P4 kit, 2026-10-13: USB typed into a laptop, BLE typed into an iPhone, one binary;",
                      "the pad at 3.3 V; both report shapes held to each other on the desk (82 checks per ID)."]),
        ("AUTHORED", ["every XIAO pin number (Seeed's map, read 2026-10-13); the cell on the BAT pads; the charge current; the S3's",
                      "secure-connections pairing (the P4 needed legacy because its radio is a second chip over SDIO; the S3's is not)."]),
        ("COMPILES", ["firmware/pad for esp32s3, USBMode=default, 49 percent of the default app partition."]),
        ("NEXT", ["a XIAO arrives: lsusb shows 303a on its socket before anything is flashed; flash pad; a host sees a keyboard;",
                  "then no host, the radio, a phone pairs with SC; then the cell on the pads, the socket's current in and out."]),
        ("TRAP", ["the XIAO's one socket is the keyboard once TinyUSB takes it: the log is on D6/D7, flashing is BOOT held across a reset."]),
    ], 712, "status")
    sh.done(DOCS / "pad-s3-system.svg")


def sheet_pins():
    sh = Sheet(1560, 740, "XIAO ESP32S3: where each wire goes, and the pins that must stay empty",
               "Read from Seeed's XIAO ESP32S3 pin map (2026-10-13). The S3's strapping pins are GPIO0, 3, 45 and 46; D2 is GPIO3, "
               "so it stays empty. tools/check-pad-s3.py holds this table to firmware/pad's numbers.")
    sh.zone(20, 66, 1000, 440, "THE WIRES")
    y = 96
    sh.text(40, y, "XIAO pin", "ref"); sh.text(130, y, "GPIO", "ref"); sh.text(200, y, "net", "ref"); sh.text(330, y, "what", "ref")
    y += 20
    for pin, gpio, net, what in PINS:
        sh.text(40, y, pin, "pin")
        sh.text(130, y, "" if gpio is None else str(gpio), "pin")
        sh.text(200, y, net, "pin")
        sh.text(330, y, what, "pin")
        y += 18
    assert y <= 500, f"the pin table overflows by {y - 500} px"
    sh.note(40, 330, [
        "Two wires from the pad's five go nowhere on this table on purpose: the pad's VCC is the XIAO's 3V3 and its GND",
        "is GND, so J1 pins 5 and 1 land on the power pins, not on a GPIO. The three signals are D3, D4, D5, in a row.",
        "",
        "D2 (GPIO3) sits between D1 and D3 and is a strapping pin: leave it empty. D0 and D1 (GPIO1, GPIO2) are free",
        "and are where a second pad would go if gamepad mode ever made two pads worth it (a keyboard report has six",
        "key slots, so it does not: TM-NESB-003 rev B).",
    ])

    sh.zone(1040, 66, 500, 440, "THE BOARD, AS SEEED DRAWS IT")
    sh.chip(1150, 110, 270, "U1", "XIAO ESP32S3, top, socket up",
            [(None, "D0 GPIO1", ""), (None, "D1 GPIO2", ""), (None, "D2 GPIO3 strap", ""), (None, "D3 GPIO4", "PAD_LATCH"),
             (None, "D4 GPIO5", "PAD_CLK"), (None, "D5 GPIO6", "PAD_D0"), (None, "D6 GPIO43 TX", "LOG")],
            [(None, "5V", ""), (None, "GND", "GND"), (None, "3V3", "3V3"), (None, "D10 GPIO9", ""),
             (None, "D9 GPIO8", ""), (None, "D8 GPIO7", "MODE_SW"), (None, "D7 GPIO44 RX", "LOG")],
            extra="BAT pads on the underside; BAT- is the one nearest the socket")
    sh.note(1060, 372, [
        "Seven pins a side, the socket at the top. The order",
        "here is Seeed's drawing, left column top to bottom",
        "D0..D6, right column top to bottom 5V, GND, 3V3,",
        "D10, D9, D8, D7. AUTHORED from the wiki page, not",
        "from a board in hand: the first thing to do with a",
        "XIAO on the desk is read its silkscreen against this.",
    ])

    sh.zone(20, 522, 1520, 200, "THE ONE SOCKET")
    band(sh, 552, [
        ("FLASH", ["the ROM speaks USB itself (303a:1001), so flashing needs no bridge chip: hold BOOT, tap RESET, release BOOT, then",
                   "esptool or arduino-cli on the port that appears. No auto-reset circuit, so every flash is a hand on two buttons."]),
        ("RUN", ["TinyUSB takes the socket as the keyboard (303a:0002 on the P4 build) and the USB-Serial-JTAG is gone with it; the",
                 "sketch's log is UART0 on D6 and D7 at 115200, through any 3.3 V serial lead. On the P4 kit that was the second socket."]),
        ("CHARGE", ["the same socket charges the cell on the BAT pads whether or not a host is behind it; a charger is VBUS with no host,",
                    "which is the case the sink rule reads as BLE, so a pad on a charger talks to the phone."]),
        ("BATTERY", ["no GPIO reads the cell on the plain XIAO (Seeed: 'we do not have a GPIO configured for the battery pin'); the BLE",
                     "battery service says 100 until a divider to an ADC pin is wired and measured. The Plus variant has ADC_BAT on GPIO10."]),
    ], 712, "socket")
    sh.done(DOCS / "pad-s3-pins.svg")


def sheet_progress():
    sh = Sheet(1560, 740, "Progress: each row moves from authored to measured, and the revision says when",
               "TM-NESB-004 is the record of nes-bench#6. A row is MEASURED when a dated log or photo says so, and not before; "
               "'compiles' and 'authored' are what the desk can say on its own.")
    sh.zone(20, 66, 1520, 180, "THE PAD, BOTH PATHS")
    band(sh, 96, [
        ("MEASURED", ["2026-10-13  the sink rule, both report shapes, the pad poll at 3.3 V, USB typing and BLE typing: on the P4 kit, one binary."]),
        ("COMPILES", ["2026-10-12  firmware/pad for esp32s3 (USBMode=default); the desk test holds both descriptors to each other, mutant red."]),
        ("NEXT", ["a XIAO on the desk: its silkscreen against sheet 2; lsusb 303a:1001 on the native socket before any flash;",
                  "flash firmware/pad; a host sees 303a:0002 and gets eight keys; no host: the radio, a phone pairs, SC not legacy."]),
        ("OPEN", ["latency, press to key, either path (bench item 11); a case or a lead the XIAO lives in; the mode switch as a real part."]),
    ], 236, "pad")

    sh.zone(20, 262, 760, 460, "THE CELL AND THE CHARGER")
    band(sh, 292, [
        ("ON THE DESK", ["2026-10-13  a LiPo 3.7 V 2000 mAh (JST lead) and a strip of",
                         "USB-C TP4056 boards with the DW01 protection pair (photos)."]),
        ("DECIDE", ["option A, the cell on the BAT pads, or B, through a TP4056",
                    "board: with a meter, by whether the cell has its own",
                    "protection and whether 100 mA is a charge rate to live with."]),
        ("MEASURE", ["current in at the socket while charging; current out of",
                     "the cell while playing on BLE and on USB; hours per charge;",
                     "what the pad does while it charges (the P4 kit cannot say)."]),
        ("OPEN", ["a battery level for the BLE battery service: a divider to an",
                  "ADC pin, or the Plus variant's ADC_BAT on GPIO10."]),
    ], 712, "cell", text_x=160)

    sh.zone(800, 262, 740, 460, "THE THINGS THE P4 TAUGHT, CARRIED OVER")
    band(sh, 292, [
        ("HOSTED RADIO", ["the P4's radio is a C6 over SDIO; SC pairing failed at the DHKey",
                          "check and the P4 pairs legacy. The S3's radio is on the die, so",
                          "SC is expected to work and is what the sketch asks for there."]),
        ("THE PI", ["a bonded, trusted Pi reconnects to the pad on its own and holds",
                    "it; a phone sees nothing until the Pi is told block. Pairing from",
                    "a script needs tools/btpair.py (bluetoothctl's prompt eats pipes)."]),
        ("NO REPORT ID", ["on the air, ever: BlueZ 5.66 dropped the numbered report. keymap.h",
                          "serves both shapes from one body; USB keeps ID 1."]),
        ("ONE SOCKET", ["the keyboard takes it; the log moves to D6/D7; flash by hand."]),
    ], 712, "carried", label_x=820, text_x=940)
    sh.done(DOCS / "pad-s3-progress.svg")


def main():
    if "--check" in sys.argv:
        import filecmp
        import tempfile
        global DOCS
        with tempfile.TemporaryDirectory() as d:
            DOCS = Path(d)
            sheet_system(); sheet_pins(); sheet_progress()
            bad = 0
            for f in sorted(Path(d).glob("pad-s3-*.svg")):
                same = (ROOT / "docs" / f.name).exists() and filecmp.cmp(f, ROOT / "docs" / f.name, shallow=False)
                print(f"  {'ok  ' if same else 'DIFF'} docs/{f.name}")
                bad |= not same
            print("draw-pad-s3: the three sheets agree with the tool" if not bad else "draw-pad-s3: regenerate the sheets")
            return int(bad)
    sheet_system()
    sheet_pins()
    sheet_progress()
    print("wrote docs/pad-s3-system.svg, pad-s3-pins.svg, pad-s3-progress.svg")
    return 0


if __name__ == "__main__":
    sys.exit(main())
