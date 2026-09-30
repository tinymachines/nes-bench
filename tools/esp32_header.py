#!/usr/bin/env python3
"""A classic ESP32 devkit's two header rows, read off the board.

  python3 tools/esp32_header.py           # print the header and what is free
  python3 tools/esp32_header.py --check   # the self-checks, for check-all.sh

THE BOARD. An ESP32-WROOM-32 module on a 30-pin devkit (the DOIT
ESP32 DevKit V1 shape: CP2102 bridge, AMS1117 regulator, EN and BOOT
buttons beside a micro-USB socket). It reached the bench on 2026-09-30
as the stand-in for the ESP32-C6-DevKitC-1 that turned out dead, and
took firmware/pad-ble first try: esptool reads it as ESP32-D0WD-V3
(revision v3.1), 4 MB flash, MAC a4:f0:0f:75:3d:f0.

WHERE THIS CAME FROM. Read on 2026-09-30 off the owner's photograph
of the board seated on its breadboard, silkscreen legible at the
pin, both columns, with the breadboard's own row numbers in the same
frame. tools/p4_header.py argues at length that a pinout is read
from the drawing that defines it and not from a photograph, and that
argument stands for a 2x20 header whose silkscreen the bench eye
cannot resolve. This one is a single row of fifteen labels a side,
printed large, and the photograph shows every one; it is the same
kind of reading breadboard.py's C6_HEADER was made from. What the
photograph cannot say is which GPIO a label stands for, so LABEL_GPIO
below is the board family's own convention (D25 is GPIO25, RX0 and
TX0 are the UART0 pins GPIO3 and GPIO1, VP and VN are GPIO36 and
GPIO39) and the firmware is held to it by check-sheets.

THE ONE THING THAT MATTERS ON THIS PART AND ON NO OTHER HERE: the C6
map (GPIO2, 3, 6) cannot be used. GPIO6 to GPIO11 are the module's own
flash lines and never reach the header; GPIO3 is U0RXD, the receive
side of the CP2102 that is this board's only console. So pad-ble's
three signals move to D25, D26 and D27, adjacent on the EN side, and
firmware/pad-ble/pad-ble.ino carries a CONFIG_IDF_TARGET_ESP32 block
that says so.
"""
import sys

# The two rows, each read FROM THE USB END, which is the end the EN
# and BOOT buttons are on. With the board's antenna up and USB down,
# as it sits on the breadboard, the EN side is the left column and the
# D23 side the right; turned so USB is at the left, as breadboard.py
# draws a devkit, the EN side becomes the upper row.
EN_SIDE = ["VIN", "GND", "D13", "D12", "D14", "D27", "D26", "D25",
           "D33", "D32", "D35", "D34", "VN", "VP", "EN"]
D23_SIDE = ["3V3", "GND", "D15", "D2", "D4", "RX2", "TX2", "D5",
            "D18", "D19", "D21", "RX0", "TX0", "D22", "D23"]
SIDES = {"EN": EN_SIDE, "D23": D23_SIDE}

# Where the board sits in the photograph: its USB socket at the
# breadboard's row 1 end, its first pins in row 6, its last in row 20.
# Both columns share a row number, which is how a person finds a hole.
ROW0 = 6

# What each label stands for. D<n> is GPIO<n> on every board of this
# shape; the six that are not D-numbers are named for their other job.
LABEL_GPIO = {"RX0": "GPIO3", "TX0": "GPIO1", "RX2": "GPIO16", "TX2": "GPIO17",
              "VP": "GPIO36", "VN": "GPIO39"}
for _side in (EN_SIDE, D23_SIDE):
    for _l in _side:
        if _l.startswith("D"):
            LABEL_GPIO[_l] = "GPIO" + _l[1:]

# On the header and still not yours.
RESERVED = {
    "GPIO1": "U0TXD, the CP2102's transmit: the console, the log and the flash port.",
    "GPIO3": "U0RXD, the CP2102's receive: the console, the log and the flash port.",
    "GPIO12": "MTDI, a strapping pin: high at reset selects 1.8 V flash and the module does not boot.",
    "GPIO15": "MTDO, a strapping pin: low at reset silences the ROM log, and it drives high at boot.",
}
RESERVED_SHORT = {
    "GPIO1": "U0TXD, the console",
    "GPIO3": "U0RXD, the console",
    "GPIO12": "MTDI strap, 1.8 V flash",
    "GPIO15": "MTDO strap, ROM log",
}

# Reachable and usable, with a condition a builder has to know.
INPUT_ONLY = {"GPIO34", "GPIO35", "GPIO36", "GPIO39"}   # no output driver, no pullup
NOTES = {
    "GPIO2": "a strapping pin, and the devkit's own blue LED: pad-ble's pad-held light",
    "GPIO5": "a strapping pin; fine as an input after boot",
    "GPIO0": "the BOOT button; not on this header",
}

# Not on the header at all, recorded so nobody goes looking.
# Keys and reasons are kept short enough for the header page's table
# (11 and 24 characters), which check 8 below holds them to.
OFF_HEADER = {
    "GPIO6-11": "the module's SPI flash",
    "GPIO0": "the BOOT button",
    "9 more": "20,24,28-31,37,38 absent",
}

# What pad-ble takes. The three signals and the ground are all on the
# EN side, adjacent, so four of the five wires land in one row; only
# the supply crosses, to the first pin of the other side.
PAD_BLE = {
    "PAD_LATCH": ("D25", "GPIO25"),
    "PAD_CLK": ("D26", "GPIO26"),
    "PAD1_D0": ("D27", "GPIO27"),
    "3V3": ("3V3", "3V3"),
    "GND": ("GND", "GND"),
}
# The side each of the five is wired on. GND appears on both sides;
# the one taken is on the pad's own row.
PAD_SIDE = {"PAD_LATCH": "EN", "PAD_CLK": "EN", "PAD1_D0": "EN", "GND": "EN", "3V3": "D23"}
SPARE = {"MODE_SW": ("D4", "GPIO4"), "LED": ("D2", "GPIO2")}   # declared, not wired


def row_of(label, side):
    """The breadboard row a pin sits in, as the photograph shows it."""
    return ROW0 + SIDES[side].index(label)


def gpio_of(label):
    return LABEL_GPIO.get(label, label)


def gpios():
    return sorted({gpio_of(l) for s in SIDES.values() for l in s if l in LABEL_GPIO},
                  key=lambda s: int(s[4:]))


def free():
    """GPIOs on the header with no other job. Input-only pins are listed
    separately, because a wire that needs an output cannot go there."""
    return [g for g in gpios() if g not in RESERVED and g not in INPUT_ONLY]


def run_picture():
    """The EN side around the pad's pins, as the board prints it."""
    i = EN_SIDE.index("D27")
    return "   ".join(EN_SIDE[i - 1:i + 4])


# The pad's own facts (which wire is which colour, which 4021 pin each
# beeps to) are the pad's, not this board's, and live in one place.
def pad_facts():
    import p4_header as ph
    return ph


def checks():
    bad = []
    # 1. Fifteen a side, no label twice on a side, a ground on each.
    for name, side in SIDES.items():
        if len(side) != 15:
            bad.append(f"the {name} side has {len(side)} pins, not 15")
        if len(set(side)) != len(side):
            bad.append(f"the {name} side repeats a label")
        if "GND" not in side:
            bad.append(f"the {name} side has no GND")
    # 2. The count the 30-pin board is sold with, which nothing here
    #    could otherwise know: 25 GPIOs.
    if len(gpios()) != 25:
        bad.append(f"the header exposes {len(gpios())} GPIOs, not 25")
    # 3. The supplies where the photograph shows them: the first pin of
    #    each side at the USB end, GND second on both.
    if EN_SIDE[0] != "VIN" or D23_SIDE[0] != "3V3":
        bad.append("VIN and 3V3 are not the first pins at the USB end")
    if EN_SIDE[1] != "GND" or D23_SIDE[1] != "GND":
        bad.append("GND is not the second pin on both sides")
    # 4. Nothing reserved is off the header, nothing off the header is
    #    on it; the flash pins in particular never appear.
    for l in EN_SIDE + D23_SIDE:
        g = gpio_of(l)
        if g in ("GPIO6", "GPIO7", "GPIO8", "GPIO9", "GPIO10", "GPIO11", "GPIO0"):
            bad.append(f"{l} ({g}) is a flash or boot pin and should not be on the header")
    for g in RESERVED:
        if g not in gpios():
            bad.append(f"{g} is reserved but not on the header")
    # 5. pad-ble's five: real labels, the GPIO the label stands for,
    #    none reserved, outputs on pins that can drive, the four
    #    signals-and-ground in one row and adjacent.
    for net, (label, g) in PAD_BLE.items():
        side = PAD_SIDE[net]
        if label not in SIDES[side]:
            bad.append(f"{net}: the {side} side has no pin marked {label}")
            continue
        if gpio_of(label) != g:
            bad.append(f"{net}: {label} is {gpio_of(label)}, not {g}")
        if g in RESERVED:
            bad.append(f"{net}: {g} is reserved ({RESERVED[g]})")
        if net in ("PAD_LATCH", "PAD_CLK") and g in INPUT_ONLY:
            bad.append(f"{net}: {g} is input only and this is an output")
    sig = sorted(EN_SIDE.index(PAD_BLE[n][0]) for n in ("PAD_LATCH", "PAD_CLK", "PAD1_D0"))
    if sig != list(range(sig[0], sig[0] + 3)):
        bad.append("the three signal pins are not adjacent on the EN side")
    if [PAD_SIDE[n] for n in ("PAD_LATCH", "PAD_CLK", "PAD1_D0", "GND")] != ["EN"] * 4:
        bad.append("the signals and the ground are not all on the EN side")
    # 6. The spares are free and are the pins the firmware names.
    for k, (label, g) in SPARE.items():
        if gpio_of(label) != g or g in RESERVED:
            bad.append(f"{k}: {label} is {gpio_of(label)}, reserved {g in RESERVED}")
    # 7. The rows the build doc's table gives, so the doc and this
    #    module cannot say different numbers.
    want = {"GND": 7, "3V3": 6, "PAD_LATCH": 13, "PAD_CLK": 12, "PAD1_D0": 11}
    for net, r in want.items():
        got = row_of(PAD_BLE[net][0], PAD_SIDE[net])
        if got != r:
            bad.append(f"{net}: row {got} here, row {r} in the build doc")
    # 8. Short reasons fit their column.
    if set(RESERVED_SHORT) != set(RESERVED):
        bad.append("RESERVED and RESERVED_SHORT name different pins")
    for g, t in RESERVED_SHORT.items():
        if len(t) > 24:
            bad.append(f"{g}: the short reason is {len(t)} characters, over 24")
    for g, t in OFF_HEADER.items():
        if len(g) > 11 or len(t) > 24:
            bad.append(f"{g!r}: {len(g)} and {len(t)} characters, over the 11 and 24 the table holds")
    return bad


def main():
    if "--check" in sys.argv:
        bad = checks()
        for b in bad:
            print("  FAIL ", b)
        print("esp32-header: the header agrees with itself" if not bad
              else f"esp32-header: {len(bad)} disagreement(s)")
        return 1 if bad else 0
    print(f"ESP32-WROOM-32 devkit, 30 pins, rows {ROW0} to {ROW0 + 14} on the breadboard as photographed 2026-09-30")
    print(f"{'row':>4}  {'EN side':<8} {'':<8}  {'D23 side':<8}")
    for i in range(15):
        a, b = EN_SIDE[i], D23_SIDE[i]
        print(f"{ROW0 + i:>4}  {a:<8} {gpio_of(a) if a in LABEL_GPIO else '':<8}  {b:<8} {gpio_of(b) if b in LABEL_GPIO else ''}")
    print()
    print("pad-ble takes:", ", ".join(f"{n} on {l} ({g}, row {row_of(l, PAD_SIDE[n])})" for n, (l, g) in PAD_BLE.items()))
    print("reserved:", ", ".join(f"{g} ({RESERVED_SHORT[g]})" for g in RESERVED))
    print("input only:", ", ".join(sorted(INPUT_ONLY, key=lambda s: int(s[4:]))))
    print("free:", ", ".join(free()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
