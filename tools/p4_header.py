#!/usr/bin/env python3
"""The Waveshare ESP32-P4-Module-DEV-KIT's 2x20 header, P6, measured.

  python3 tools/p4_header.py           # print the header and what is free
  python3 tools/p4_header.py --check   # the self-checks, for check-all.sh

WHERE THIS CAME FROM, AND WHY IT IS NOT A PHOTOGRAPH. Read on
2026-09-24 out of Waveshare's own schematic for this board,
ESP32-P4-Module-DEV-KIT.pdf, connector P6, by rendering the page at
900 dpi and reading the connector at a zoom where the wire leaving
each pin is unmistakable. The bench eye can SEE the silkscreen on this
header and the temptation to read it off a photograph was real. That
is precisely how TM-NESB-003 shipped with the C6's two header rows
swapped through four revisions, so: a pinout is read from the drawing
that defines it, or it is a guess.

THE TWO CHECKS THAT CAUGHT THE READING. The labels in an Altium
schematic sit ABOVE the wire they name, so a whole column can be read
one row out, which is the same failure by another route. Two
independent counts settle it and both are asserted below:

  1. Both columns must come out at exactly 20 pins with nothing left
     over. The one-row-out reading leaves three pins unexplained.
  2. The header must expose exactly 28 distinct GPIOs, which is the
     number Waveshare advertises for this board and which nothing in
     this repository could otherwise know.

PIN 1 IS NOT WHERE A RASPBERRY PI PUTS IT. The header is physically
Pi-shaped and the rows are numbered the other way round: 5V is on
pins 1 and 3 where a Pi has it on 2 and 4, and 3V3 is on 2 and 18
where a Pi has 1 and 17. Every ground sits one away from where a Pi
user expects it. A Pi HAT will fit and will not work.
"""
import sys

# Connector P6, exactly as the schematic draws it. Even pins are the
# left column, odd pins the right.
P6 = {
    2: "3V3",   1: "5V",
    4: "GPIO7", 3: "5V",
    6: "GPIO8", 5: "GND",
    8: "GPIO23", 7: "GPIO37",
    10: "GND", 9: "GPIO38",
    12: "GPIO21", 11: "GPIO22",
    14: "GPIO20", 13: "GND",
    16: "GPIO6", 15: "GPIO5",
    18: "3V3", 17: "GPIO4",
    20: "GPIO3", 19: "GND",
    22: "GPIO2", 21: "GPIO1",
    24: "GPIO0", 23: "GPIO36",
    26: "GND", 25: "GPIO32",
    28: "GPIO24", 27: "GPIO25",
    30: "GPIO33", 29: "GND",
    32: "GPIO26", 31: "GPIO54",
    34: "GPIO48", 33: "GND",
    36: "GPIO53", 35: "GPIO46",
    38: "GPIO47", 37: "GPIO27",
    40: "GND", 39: "GPIO45",
}

# A pin that is on the header and still must not be taken. Every one of
# these is wired to something on the board itself, so driving it fights
# hardware rather than simply not working.
RESERVED = {
    "GPIO54": "the onboard ESP32-C6's RESET. Take this and the radio dies.",
    "GPIO45": "the MicroSD card's power switch (Q1's gate).",
    "GPIO53": "the speaker amplifier's CTRL.",
    "GPIO36": "BOOT_MODE2, a strapping pin, pulled up.",
    "GPIO24": "USB1P1_N, half of the high-speed USB pair.",
    "GPIO25": "USB1P1_P, the other half.",
    "GPIO7": "ESP_I2C_SDA to the audio codec, with a 2.2k pullup on the board.",
    "GPIO8": "ESP_I2C_SCL to the audio codec, with a 2.2k pullup on the board.",
}

# The same eight in a few words, for a table cell. The sentences above
# are for a person reading; these are for a column 184 px wide. Kept
# beside each other and checked against each other, because two lists
# of the same thing drift the moment they are apart.
RESERVED_SHORT = {
    "GPIO54": "the C6's RESET",
    "GPIO45": "MicroSD power switch",
    "GPIO53": "speaker amp CTRL",
    "GPIO36": "BOOT_MODE2 strap",
    "GPIO24": "USB1P1_N",
    "GPIO25": "USB1P1_P",
    "GPIO7": "codec SDA, 2.2k pullup",
    "GPIO8": "codec SCL, 2.2k pullup",
}

# Not on the header at all, recorded so nobody goes looking. The SDIO
# group is the link to the radio and is the reason the P4 can do BLE.
OFF_HEADER = {
    "GPIO9 to GPIO13": "I2S to the audio codec",
    "GPIO14 to GPIO19": "SDIO to the onboard C6",
    "GPIO28 to GPIO31": "Ethernet PHY",
    "GPIO34, GPIO35": "Ethernet PHY; 35 is BOOT_MODE",
    "GPIO39 to GPIO44": "MicroSD card",
    "GPIO49 to GPIO52": "Ethernet PHY",
}

# What pad-ble takes, and the whole point of the choice: every one of
# these is an EVEN pin, so all five wires land in one row and none
# crosses the header. The three signals are GPIO2, 3 and 6, which is
# the same map firmware/bridge/bridge.ino already polls a pad on, so
# poll_pad runs unedited on this part too.
PAD_BLE = {
    "PAD_LATCH": (22, "GPIO2"),
    "PAD_CLK": (20, "GPIO3"),
    "PAD1_D0": (16, "GPIO6"),
    "3V3": (18, "3V3"),
    "GND": (26, "GND"),
}

# Which pin of the pad's own connector each net is, so the lead colour
# can be LOOKED UP instead of typed.
PAD_J1_PIN = {"GND": 1, "PAD_CLK": 2, "PAD_LATCH": 3, "PAD1_D0": 4, "3V3": 5}


def pad_colour():
    """The cut cable's lead colours, from the one place that measured them.

    TYPED BY HAND ONCE, 2026-09-24, AND THREE OF THE FIVE WERE WRONG.
    The owner had said "same five colours as the bridge, Black, Yellow,
    Blue, Green, Red", which is a set and not an order, and I assigned
    them to nets by guess: GND black, CLK yellow, LATCH blue. The cable
    was rung out on 2026-09-09 and the answer has been in
    tools/bringup.py's LEADS ever since: GND is YELLOW, CLK is BLUE and
    OUT0 is BLACK. Only D0 green and +5V red were right, and those two
    were luck.

    It reached rev E and went live before anyone read it against the
    measurement. So this no longer holds a copy: it reads LEADS, and a
    pin that is not there raises rather than guesses."""
    import bringup
    by_pin = {p: c for p, _n, c in bringup.LEADS}
    return {net: by_pin[pin].capitalize() for net, pin in PAD_J1_PIN.items()}


PAD_COLOUR = pad_colour()


def gpios():
    """Every distinct GPIO the header brings out."""
    return sorted({v for v in P6.values() if v.startswith("GPIO")},
                  key=lambda s: int(s[4:]))


def free():
    """GPIOs on the header with nothing else already on them."""
    return [g for g in gpios() if g not in RESERVED]


def checks():
    bad = []
    # 1. The connector is whole: 40 pins, 20 a side, none missing.
    if sorted(P6) != list(range(1, 41)):
        bad.append("P6 does not name pins 1 to 40 exactly once")
    if len([p for p in P6 if p % 2 == 0]) != 20:
        bad.append("the even column is not 20 pins")
    if len([p for p in P6 if p % 2 == 1]) != 20:
        bad.append("the odd column is not 20 pins")
    # 2. Waveshare's own count, which this repository cannot derive.
    if len(gpios()) != 28:
        bad.append(f"the header exposes {len(gpios())} GPIOs, not the 28 Waveshare states")
    # 3. The supplies sit where the schematic puts them, NOT where a Pi does.
    if [p for p, n in P6.items() if n == "5V"] != [1, 3]:
        bad.append("5V is not on pins 1 and 3")
    if sorted(p for p, n in P6.items() if n == "3V3") != [2, 18]:
        bad.append("3V3 is not on pins 2 and 18")
    if sorted(p for p, n in P6.items() if n == "GND") != [5, 10, 13, 19, 26, 29, 33, 40]:
        bad.append("the grounds are not where the schematic puts them")
    # 4. pad-ble's five wires: real pins, right nets, none reserved, one row.
    for net, (pin, name) in PAD_BLE.items():
        if P6.get(pin) != name:
            bad.append(f"{net}: pin {pin} is {P6.get(pin)}, not {name}")
        if name in RESERVED:
            bad.append(f"{net}: {name} is reserved ({RESERVED[name]})")
        if pin % 2:
            bad.append(f"{net}: pin {pin} is on the odd row, so a wire crosses")
    # 5. Every wire has a colour and every colour a wire, and every
    #    colour is the one the cable was rung out as, not a guess.
    if set(PAD_COLOUR) != set(PAD_BLE):
        bad.append("the colour table and the pin table name different wires")
    if set(PAD_J1_PIN) != set(PAD_BLE):
        bad.append("PAD_J1_PIN and PAD_BLE name different wires")
    import bringup
    for pin, name, colour in bringup.LEADS:
        net = [n for n, p in PAD_J1_PIN.items() if p == pin]
        if not net:
            bad.append(f"J1 pin {pin} ({name}) is not claimed by any net here")
        elif PAD_COLOUR[net[0]].lower() != colour:
            bad.append(f"{net[0]}: {PAD_COLOUR[net[0]]} against the rung-out {colour}")
    # 6. The long and short reasons name the same eight pins, and the
    #    short ones stay short enough for the column they are drawn in.
    if set(RESERVED_SHORT) != set(RESERVED):
        bad.append("RESERVED and RESERVED_SHORT name different pins")
    for g, t in RESERVED_SHORT.items():
        if len(t) > 24:
            bad.append(f"{g}: the short reason is {len(t)} characters, over the 24 a cell holds")
    return bad


def main():
    if "--check" in sys.argv:
        bad = checks()
        for b in bad:
            print("  FAIL ", b)
        print("p4-header: the header agrees with itself" if not bad
              else f"p4-header: {len(bad)} disagreement(s)")
        return 1 if bad else 0
    print("Waveshare ESP32-P4-Module-DEV-KIT, connector P6\n")
    print("  odd                        even")
    for i in range(1, 41, 2):
        star_o = " *" if P6[i] in RESERVED else "  "
        star_e = " *" if P6[i + 1] in RESERVED else "  "
        print(f"  {i:>2} {P6[i]:<8}{star_o}   {P6[i+1]:>8} {i+1:<2}{star_e}")
    print("\n  * on the header and already spoken for:")
    for g, why in RESERVED.items():
        print(f"      {g:<8} {why}")
    print("\n  free:", ", ".join(free()))
    print("\n  pad-ble takes, all on the even row so nothing crosses:")
    for net, (pin, name) in PAD_BLE.items():
        print(f"      {PAD_COLOUR[net]:<7} {net:<10} P6 pin {pin:<3} {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
