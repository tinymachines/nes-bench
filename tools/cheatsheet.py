#!/usr/bin/env python3
"""The cheat sheet: the two breakouts pin by pin, and one page per chip.

  python3 tools/cheatsheet.py            # write docs/cheat-sheet.md
  python3 tools/cheatsheet.py --check    # exit 1 if it is not current
  python3 tools/cheatsheet.py --sheet bench-v1b-head   # -> docs/cheat-sheet-head.md, the head's hands
  MUTATE=1 python3 tools/cheatsheet.py   # must exit 0 having CAUGHT a
                                         # pinout that disagrees with the
                                         # schematic (see bottom)

Three tables the bench keeps needing at once, joined from where each
fact already lives, so nothing here is a second copy:

- The controller port: pin number and signal from the schematic's
  connector symbol (`tools/draw-schematics.py`, held to `docs/wiring.md`
  by `tools/check-sheets.py`); the NES harness colour from the lab log
  (step 1.1); the breakout lead from `tools/bringup.py`'s LEADS table,
  which is also what the build steps print.
- The power and reset breakout, from the same table's neighbour.
- The head's four jumpers: the Pi pins the wiring names, with their
  header positions, which are the Pi's own numbering and authored here.

Then one page per chip on the sheet: every pin of the package with what
the datasheet says it does (AUTHORED here, one place) and what it is
wired to on this bench (read out of the schematic). The two are joined
by pin number, and a pin the schematic names differently from the
datasheet table is refused rather than printed, so the authored table
and the drawing cannot disagree in silence.

`tools/make-package.py` draws the same rows as sheets of the drawing
package; this file writes them as markdown for reading on GitHub at the
bench.
"""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "docs" / "lab-log.jsonl"
OUTS = {"bench-v1b": ROOT / "docs" / "cheat-sheet.md",
        "bench-v1b-head": ROOT / "docs" / "cheat-sheet-head.md"}
sys.path.insert(0, str(ROOT / "tools"))
from loadmod import load  # noqa: E402

# ------------------------------------------------------------ AUTHORED
# Datasheet pinouts, by package pin number. Names are the schematic's
# (the join below insists on it). Purposes are one line each and say
# what the pin does on the part, not on this bench; the bench column is
# derived. Sources: TI SN74HCT04 (SCLS228), TI/Nexperia 74HC165,
# TI SN74HC595 (SCLS041).
CHIPS = {
    "74HCT04": {
        "what": ("Hex inverter, six independent gates. HCT inputs switch at TTL levels "
                 "(high from 2.0 V), which is why it sits on the console's NMOS OUT0 line: "
                 "OUT0 high loads the register, so its inversion is the 165's active-low load. "
                 "One gate is used. The other five inputs are CMOS and must not float: tie "
                 "each spare A input to GND and leave its Y open."),
        "pins": {
            1: ("1A", "gate 1 input"), 2: ("1Y", "gate 1 output, the inverse of 1A"),
            3: ("2A", "gate 2 input"), 4: ("2Y", "gate 2 output"),
            5: ("3A", "gate 3 input"), 6: ("3Y", "gate 3 output"),
            7: ("GND", "ground"),
            8: ("4Y", "gate 4 output"), 9: ("4A", "gate 4 input"),
            10: ("5Y", "gate 5 output"), 11: ("5A", "gate 5 input"),
            12: ("6Y", "gate 6 output"), 13: ("6A", "gate 6 input"),
            14: ("VCC", "supply, 4.5 to 5.5 V; 100 nF to GND at the pin"),
        },
    },
    "74HC165": {
        "what": ("8-bit parallel-in, serial-out shift register: the pad's 4021 in a 74 package. "
                 "While /PL is low the eight inputs A to H are copied into the stages as they "
                 "are (it is transparent, so the byte must be settled before the load). With /PL "
                 "high, each rising edge of CP shifts one place toward QH and pulls DS in at A. "
                 "QH shows stage H, so H is the first bit out and A the eighth, which is why the "
                 "pad's order A, B, Select, Start, Up, Down, Left, Right is wired H down to A. "
                 "/CE high holds the clock off."),
        "pins": {
            1: ("/PL", "parallel load, active low: inputs copied in while low"),
            2: ("CP", "shift clock, rising edge, when /CE is low"),
            3: ("E", "parallel input E, the fourth bit out"),
            4: ("F", "parallel input F, the third bit out"),
            5: ("G", "parallel input G, the second bit out"),
            6: ("H", "parallel input H, the first bit out (QH after a load)"),
            7: ("/QH", "inverted serial output"),
            8: ("GND", "ground"),
            9: ("QH", "serial output: stage H"),
            10: ("DS", "serial in: shifts into A after the eighth clock"),
            11: ("A", "parallel input A, the eighth bit out"),
            12: ("B", "parallel input B, the seventh bit out"),
            13: ("C", "parallel input C, the sixth bit out"),
            14: ("D", "parallel input D, the fifth bit out"),
            15: ("/CE", "clock enable, active low: high inhibits CP"),
            16: ("VCC", "supply, 2 to 6 V; 100 nF to GND at the pin"),
        },
    },
    "74HC595": {
        "what": ("8-bit serial-in, parallel-out shift register with an output latch. Each rising "
                 "edge of SRCLK shifts SER in at QA's stage; the stages are invisible until a "
                 "rising edge of RCLK copies all eight into the output latch at once, which is "
                 "what makes a byte atomic to the console: the 165 never sees a half-written "
                 "byte. /OE low turns the outputs on; /SRCLR low clears the shift stages (not "
                 "the latch). QH' is the eighth stage, for chaining a second 595."),
        "pins": {
            1: ("QB", "latched output B"), 2: ("QC", "latched output C"),
            3: ("QD", "latched output D"), 4: ("QE", "latched output E"),
            5: ("QF", "latched output F"), 6: ("QG", "latched output G"),
            7: ("QH", "latched output H"),
            8: ("GND", "ground"),
            9: ("QH'", "stage H unlatched: serial out for a chained 595"),
            10: ("/SRCLR", "shift register clear, active low: tie high to run"),
            11: ("SRCLK", "shift clock, rising edge: SER into A, A into B, and on"),
            12: ("RCLK", "latch clock, rising edge: all eight stages to the outputs"),
            13: ("/OE", "output enable, active low: low drives QA to QH"),
            14: ("SER", "serial data in, sampled on SRCLK's rising edge"),
            15: ("QA", "latched output A"),
            16: ("VCC", "supply, 2 to 6 V; 100 nF to GND at the pin"),
        },
    },
}

# The Raspberry Pi 4's 40-pin header, the four positions this bench
# uses. BCM numbers are the ones the head daemon and docs/wiring.md
# name; the header position is the Pi's own numbering, odd pins on the
# inside row, and is what a jumper actually lands on.
PI_HEADER = [
    ("GPIO17", 11, "PC817 module INPUT +", "reset, 100 ms high"),
    ("GPIO27", 13, "relay module IN", "power: high is on"),
    ("5V", 2, "relay module VCC", "the coil's supply"),
    ("GND", 6, "PC817 IN-, relay GND", "the one ground lent"),
]

# The two modules on the head sheet. Their pins are named, not
# numbered, so the join below is by name: a pin the schematic draws
# under another name is refused, and so is a table pin the schematic
# does not draw. Sources: the PC817 datasheet (Sharp) and the module's
# own silkscreen; the Songle SRD-05VDC-SL-C relay and the one-channel
# opto-isolated module's silkscreen.
MODULES = {
    "PC817 module": {
        "what": ("One optocoupler on a carrier: an LED behind a series resistor on the input "
                 "side, a phototransistor on the output side, nothing joining the two but light. "
                 "The carrier adds a pull-up from OUT to VCC; with VCC left open OUT is the bare "
                 "collector and GND the emitter, so the output side is a switch to its own GND "
                 "and nothing more: the reset button, closed by the head. INPUT + high (3.3 V "
                 "from a Pi pin is enough) lights the LED and closes the switch."),
        "pins": [
            ("input", "INPUT +", "LED anode via the series resistor: high turns it on"),
            ("input", "INPUT -", "LED cathode, the input side's return"),
            ("output", "OUT", "collector: pulled to GND while the LED is lit"),
            ("output", "GND", "emitter, the output side's own ground"),
            ("output", "VCC", "pull-up supply for OUT; open, so OUT is open collector"),
        ],
    },
    "relay module, 5 V coil": {
        "what": ("A 5 V coil relay on a carrier with an opto-isolated input, driving the coil's "
                 "transistor. The coil takes about 80 mA from VCC, which is why it is on the Pi's "
                 "5 V pin and not a GPIO. The contact is a changeover, COM to NO or NC. MEASURED "
                 "2026-09-17 at the console rather than read off the module: GPIO27 HIGH powers "
                 "the console and LOW turns it off, which is why the boot config rests it low."),
        "pins": [
            ("coil", "VCC", "coil and carrier supply, 5 V"),
            ("coil", "GND", "coil and carrier return"),
            ("coil", "IN", "control: GPIO27 high is the console on (measured)"),
            ("contact", "COM", "the contact's common"),
            ("contact", "NO", "normally open: meets COM while the coil is on"),
            ("contact", "NC", "normally closed: meets COM while the coil is off"),
        ],
    },
}


def module_of(part):
    for key in MODULES:
        if part.startswith(key):
            return key
    return None


# ------------------------------------------------------------- DERIVED
def _read_log():
    if not LOG.exists():
        return []
    out = []
    for line in LOG.read_text().splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def harness_colours():
    """Pin number to the NES harness's own wire colour, from the latest
    real pass of step 1.1. Only the colours are taken: the signal names
    in that record are the published ones the housing was read against
    on 2026-09-08, and the schematic carries the measured ones."""
    passes = [e for e in _read_log()
              if e.get("step") == "1.1" and e.get("state") == "pass" and not e.get("rehearsal")]
    if not passes:
        return {}, None
    e = sorted(passes, key=lambda e: e["at"])[-1]
    return {int(k[3:]): v["colour"] for k, v in e["data"]["map"].items()}, e["at"][:10]


def collect(sheet="bench-v1b"):
    nl = load(ROOT / "tools" / "netlist.py", "netlist")
    bu = load(ROOT / "tools" / "bringup.py", "bringup")
    sheets, off = nl.collect()
    nodes = sheets[sheet]
    nets = nl.nets_of(nodes)
    nl.OFFSHEET = off
    return nl, bu, nodes, nets


def other_ends(nl, nets, net, ref):
    """The other pins on a net, by designator. A rail is named, not
    listed: the wiring list already lists it, and eleven designators in
    one cell say less than 'the GND rail' does."""
    if net in nl.NC:
        return ""
    if net in nl.RAILS:
        return f"the {net} rail"
    ends = [n for n in nets.get(net, []) if n["ref"] != ref]
    return ", ".join(end_name(n) if n["ref"] == "PI" else
                     f"{n['ref']}-{n['pin']}" if n["pin"] is not None else f"{n['ref']} {n['pinname']}"
                     for n in ends)


def end_name(n):
    """One end of a net as a builder reads it: the designator and the pin
    name, with the pin number where the sheet has one (on the head sheet
    the Pi's numbers are header positions)."""
    if n["ref"] == "PI" and n["pin"] is not None:
        return f"{n['ref']} {n['pinname']} (position {n['pin']})"
    if n["pin"] is not None:
        return f"{n['ref']}-{n['pin']} {n['pinname']}"
    return f"{n['ref']} {n['pinname']}"


def head_pinmap(sheet="bench-v1b-head"):
    """The head sheet's tables: the Pi's jumpers read off the sheet, the
    power and reset breakout, and every net as a wiring list."""
    nl, bu, nodes, nets = collect(sheet)
    role = {bcm: (pos, r) for bcm, pos, _to, r in PI_HEADER}
    hrows = []
    for n in sorted([n for n in nodes if n["ref"] == "PI" and n["pin"] is not None], key=lambda n: n["pin"]):
        pos, r = role[n["pinname"]]
        assert pos == n["pin"], f"PI {n['pinname']}: the sheet says position {n['pin']}, PI_HEADER says {pos}"
        hrows.append([n["pinname"], str(n["pin"]), other_ends(nl, nets, n["net"], "PI"), r])
    assert len(hrows) >= 4, "the head sheet draws fewer than four Pi jumpers"
    head = ("The head's four jumpers",
            "Four Dupont leads off the Pi's header, no breakout (2026-09-10). Positions are the Pi's "
            "own numbering, odd on the inside row; the far end is read off sheet 3. No wire from "
            "here to the console: the Pi's ground reaches it through the UNO's USB cable only.",
            ["Pi pin", "pos.", "to", "role"], hrows)
    prows = [[str(p), c, c, bu.POWER_RESET_ROLES[p]] for p, c in bu.POWER_RESET_LEADS]
    pwr = ("The power and reset breakout, J3",
           "Five ways straight through, colour for colour with the front panel's harness, pin 1 at "
           "the back, tapped in parallel with the panel. What each way is was metered 2026-09-17; "
           "no way is ground. Orange sits 4.40 V above yellow with the console on and the button "
           "released (2026-09-17), so OK1's OUT goes on orange and its GND on yellow.",
           ["pin", "NES harness", "breakout lead", "what it is"], prows)
    wrows = []
    for net in sorted(nets, key=lambda k: (k in nl.RAILS, k)):
        ends = [end_name(n) for n in nets[net]]
        if len(ends) == 1:
            ends.append(nl.OFFSHEET[net])     # a cable off the sheet, named by where it goes
        wrows.append([net, ends[0], "; ".join(ends[1:])])
    wiring = ("Every wire on sheet 3",
              "One row per net, read off the schematic. RST_HI is 3 orange and RST_LO is 4 yellow, the "
              "reset button, orange the higher of the two. PWR_BROWN and PWR_RED put the relay "
              "across the front panel's power switch, which stays off while the head runs the power.",
              ["net", "from", "to"], wrows)
    return [wiring, head, pwr]


def pinmap(sheet="bench-v1b"):
    """Three tables: (title, note, headers, rows)."""
    if sheet == "bench-v1b-head":
        return head_pinmap(sheet)
    nl, bu, nodes, nets = collect(sheet)
    colours, when = harness_colours()
    leads = {p: c for p, _n, c in bu.LEADS}
    ports = sorted({n["ref"] for n in nodes if n["part"] == "console controller port"})
    assert ports, f"{sheet} draws no console controller port"
    j = ports[0]
    rows = []
    for n in sorted([n for n in nodes if n["ref"] == j], key=lambda n: n["pin"]):
        p = n["pin"]
        on = other_ends(nl, nets, n["net"], j) or ("" if n["net"] in nl.NC else n["net"])
        if n["net"] in nl.NC and n["pinname"] == "+5V":
            on = "not used: the bridge runs from the UNO's 5 V"
        rows.append([str(p), n["pinname"], colours.get(p, "?"), leads.get(p, "not carried"), on])
    con = ("The controller port: pin, NES harness, breakout",
           f"Pin numbers are the ones moulded into this console's port housing and the signals "
           f"are the schematic's, MEASURED 2026-09-09 (the supply is on 5, not 7). Harness colours "
           f"from the lab log, step 1.1 ({when}). Breakout leads rung out 2026-09-09 with the cable "
           f"out of the console; the pad half of the cut carries the same five colours. "
           f"Use the lead, not the colour rule.",
           ["pin", "signal", "NES harness", "breakout lead", "on the bridge"], rows)
    prows = [[str(p), c, c, bu.POWER_RESET_ROLES[p]] for p, c in bu.POWER_RESET_LEADS]
    pwr = ("The power and reset breakout",
           "Five ways straight through, colour for colour with the front panel's harness "
           "(docs/lab/06-breakout-map-power-reset.jpg), metered 2026-09-17. No way is ground: "
           "the front panel is grounded by its pad and housing.",
           ["pin", "NES harness", "breakout lead", "what it is"], prows)
    # The UNO ribbon: colour per pin from the bring-up tool's table, the
    # net and its far end from the schematic.
    uno = {n["pinname"].split()[0]: n for n in nodes if n["ref"] == "A1"}
    rrows = []
    for pin, colour in bu.RIBBON:
        n = uno.get(pin)
        rrows.append([pin, colour, n["net"] if n else "?", other_ends(nl, nets, n["net"], "A1") if n else "not on the schematic"])
    rib = ("The UNO ribbon",
           "Nine Dupont wires from the UNO's digital header, colour per pin as read off the header "
           "(2026-09-11). The net and the far end come from the schematic.",
           ["UNO pin", "colour", "net", "to"], rrows)
    hrows = [[bcm, str(pos), to, role] for bcm, pos, to, role in PI_HEADER]
    head = ("The head's four jumpers",
            "Four Dupont leads off the Pi's header, no breakout (2026-09-10). Header positions "
            "are the Pi's own numbering. No wire from here to the console: the Pi's ground "
            "reaches it through the UNO's USB cable only.",
            ["Pi pin", "pos.", "to", "role"], hrows)
    return [con, pwr, head, rib]


# The scope's four channels, as wired 2026-09-15 (the user), and the
# trigger. MEASURED 2026-09-15: the DS1054Z has no external trigger
# input (the SCPI trigger source EXT is refused and stays where it was),
# so the design's "rear EXT TRIG" cannot be built on this scope and the
# bridge's TRIG line takes a channel. CH1 is the one channel free: it
# was held for the console's master clock, which is not probed yet;
# when it is, TRIG and the clock share CH1 by turns. CH3 is where the
# video probe has sat since 2026-09-07 (1,512 sync pulses counted there).
SCOPE = [
    ("CH1", "TRIG", "R1 on the middle board: the resistor in row a from column 9 (the green D3 lead's housing) to column 6 (the red lead to the scope)", "the trigger: 2.5 V rising at latch T, 5.4 V for 874 us (MEASURED 2026-09-15); the master clock's channel later, by turns"),
    ("CH2", "CON_OUT0 (latch)", "U1 pin 1: right board column 34, the side toward U2 (rows f to j)", "one pulse per poll, 3.6 us wide, 60.06 a second; a new lead 2026-09-15 evening"),
    ("CH3", "composite video", "the console's video out, through the splitter", "the picture the poll lands in"),
    ("CH4", "CON_D0", "U2 pin 9: right board column 18, the rails side (rows a to e)", "the byte the console reads back, pressed LOW: high through the eight bits for 00, low for ff (MEASURED 2026-09-15 23:00, which is how the two probes were told apart)"),
    ("EXT TRIG", "none", "not on this scope", "the DS1054Z has no external trigger input (MEASURED 2026-09-15: source EXT refused; the rear BNC is Trig Out)"),
]
# Every probe's ground on the right board's GND rail, and the probes on
# 10x: a 1x probe hangs 100 pF on the line it reads, which on D0 is
# part of the ground-bounce story of 2026-09-15.


def scope_table():
    return ("The scope: channels and the trigger",
            "As wired 2026-09-15, each probe's landing given as a board column so it can be put back. Probe grounds on the "
            "right board's GND rail, which is the console's ground; probes on 10x. "
            "The DS1054Z has no external trigger input (MEASURED 2026-09-15), so the bridge's TRIG takes "
            "CH1, the channel held for the master clock until the mainboard is probed. Step 6.1 of the "
            "bring-up arms the scope on CH1 and fires TRIG at a latch.",
            ["input", "signal", "probe on", "why"], [list(r) for r in SCOPE])


def module_sheet(ref, sheet, drawn, nl, nets):
    """A module's pins are named, so the join is by name, both ways:
    a drawn pin the table lacks and a table pin the sheet lacks are
    both refused. MUTATE renames one table pin and must be caught."""
    part = drawn[0]["part"]
    key = module_of(part)
    spec = MODULES[key]
    pins = list(spec["pins"])
    if os.environ.get("MUTATE"):
        side, name, purpose = pins[0]
        pins[0] = (side, name + "X", purpose)
    names = [name for _s, name, _p in pins]
    on = {n["pinname"]: n for n in drawn}
    for name in on:
        assert name in names, f"{ref} ({key}): the schematic draws pin {name!r}, which the module table does not have"
    for name in names:
        assert name in on, f"{ref} ({key}): the module table has pin {name!r}, which the schematic does not draw"
    rows = []
    for side, name, purpose in pins:
        net = on[name]["net"]
        if net in nl.NC:
            here = "no connection: left open on purpose"
        elif net in nl.RAILS:
            here = other_ends(nl, nets, net, ref)
        else:
            ends = other_ends(nl, nets, net, ref)
            here = f"{net}" + (f": {ends}" if ends else "")
        rows.append([side, name, purpose, here])
    return ref, part, spec["what"], ["side", "pin", "on the part", "on this bench"], rows


def chip_sheet(ref, sheet="bench-v1b"):
    """(ref, part, description, headers, rows) for one chip on a sheet.
    Refuses a pin the schematic names differently from CHIPS."""
    nl, _bu, nodes, nets = collect(sheet)
    drawn = [n for n in nodes if n["ref"] == ref]
    assert drawn, f"{ref} is not on {sheet}"
    part = drawn[0]["part"]
    if module_of(part):
        return module_sheet(ref, sheet, drawn, nl, nets)
    key = part.split()[0]
    if os.environ.get("MUTATE"):
        # The proof this join can refuse: swap the datasheet's names for
        # pins 1 and 2 and the schematic must be caught disagreeing.
        d = {k: dict(v) for k, v in CHIPS.items()}
        d[key]["pins"] = dict(d[key]["pins"])
        d[key]["pins"][1], d[key]["pins"][2] = d[key]["pins"][2], d[key]["pins"][1]
        spec = d[key]
    else:
        spec = CHIPS.get(key)
    assert spec, f"{ref} is a {key}, which tools/cheatsheet.py has no pinout for"
    by_pin = {n["pin"]: n for n in drawn if n["pin"] is not None}
    for p, n in by_pin.items():
        assert p in spec["pins"], f"{ref} ({key}) pin {p} is on the schematic and not in the {key} pinout"
        want = spec["pins"][p][0]
        assert n["pinname"] == want, (
            f"{ref} ({key}) pin {p}: the schematic calls it {n['pinname']!r}, the datasheet table {want!r}. "
            f"One of them is wrong; fix it before printing a cheat sheet that says both.")
    rows = []
    for p in sorted(spec["pins"]):
        name, purpose = spec["pins"][p]
        if p in by_pin:
            net = by_pin[p]["net"]
            if net in nl.NC:
                here = "no connection"
            elif net in nl.RAILS:
                here = other_ends(nl, nets, net, ref)
            else:
                ends = other_ends(nl, nets, net, ref)
                here = f"{net}" + (f": {ends}" if ends else "")
        else:
            here = "not on the schematic"
            if name.endswith("A") and key == "74HCT04":
                here = "not on the schematic: tie to GND"
            elif name.endswith("Y") and key == "74HCT04":
                here = "not on the schematic: leave open"
        rows.append([str(p), name, purpose, here])
    return ref, part, spec["what"], ["pin", "name", "on the part", "on this bench"], rows


def chip_refs(sheet="bench-v1b"):
    """The chips on a sheet that have a pinout here, in designator order."""
    _nl, _bu, nodes, _nets = collect(sheet)
    seen = []
    for n in nodes:
        if n["ref"] not in seen and (n["part"].split()[0] in CHIPS or module_of(n["part"])):
            seen.append(n["ref"])
    if sheet == "bench-v1b-head":
        return seen     # the sheet's own order: OK1 (6.2) before K1 (6.3)
    return sorted(seen, key=lambda r: (r[0], int(r[1:]) if r[1:].isdigit() else 0))


def md_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(out)


def steps_section():
    """Bring-up 6.2 and 6.3 as the tool runs them, from its own table."""
    bu = load(ROOT / "tools" / "bringup.py", "bringup")
    L = ["## The two steps, as the bring-up tool runs them", "",
         "From `tools/bringup.py`, the same table `docs/build-guide.md` is written from. On the Pi:",
         "", "```", "cd ~/nes-bench && yes '' | python3 tools/bringup.py --step 6.2 --bridge /dev/ttyACM0 --scope SCOPE --operator NAME",
         "```", ""]
    for sid in ("6.2", "6.3"):
        st = bu.BY_ID[sid]
        L += [f"**{sid} {st['title']}**", ""]
        L += [f"- {d}" for d in st["do"]]
        L += [""]
    return L


def render(sheet="bench-v1b"):
    if sheet == "bench-v1b-head":
        L = ["# Cheat sheet, sheet 3: the head's hands", "",
             "Generated by `tools/cheatsheet.py --sheet bench-v1b-head`. The jumpers, the wiring",
             "list and each module's bench column are read out of the schematic's third sheet",
             "(`bench-v1b-3.svg`); the breakout leads come from the bring-up tool's own table; the",
             "only authored text is what each module pin does on the part, kept in one place in",
             "that tool and refused if the schematic names a pin differently. Which two ways of",
             "the breakout are the reset pair is step 6.2's measurement and is not written here.",
             "The same wiring at right angles: `wiring-v1b-head.svg`.", "",
             f"Sheet: `{sheet}`.", ""]
        for title, note, headers, rows in pinmap(sheet):
            L += [f"## {title}", "", note, "", md_table(headers, rows), ""]
        for ref in chip_refs(sheet):
            r, part, what, headers, rows = chip_sheet(ref, sheet)
            L += [f"## {r}: {part}", "", what, "", md_table(headers, rows), ""]
        L += steps_section()
        return "\n".join(L).rstrip() + "\n"
    L = ["# Cheat sheet: the breakouts pin by pin, and every pin of every chip", "",
         "Generated by `tools/cheatsheet.py`. The pin numbers and signals are read out of",
         "the schematic, the harness colours out of the lab log, the breakout leads out of",
         "the bring-up tool's own table, and each chip's wiring out of the netlist. The only",
         "authored text is what each pin does on the part, which is the datasheet's, kept",
         "in one place in that tool and refused if the schematic names a pin differently.",
         "The same rows are sheets of the drawing package (`tools/make-package.py`).",
         "The head's hands (the Pi's jumpers, the PC817 and the relay) have their own:",
         "`cheat-sheet-head.md`.", "",
         f"Sheet: `{sheet}`.", ""]
    for title, note, headers, rows in pinmap(sheet) + [scope_table()]:
        L += [f"## {title}", "", note, "", md_table(headers, rows), ""]
    for ref in chip_refs(sheet):
        r, part, what, headers, rows = chip_sheet(ref, sheet)
        L += [f"## {r}: {part}", "", what, "", md_table(headers, rows), ""]
    return "\n".join(L).rstrip() + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--sheet", default="bench-v1b")
    a = ap.parse_args()
    if os.environ.get("MUTATE"):
        try:
            for ref in chip_refs(a.sheet):
                chip_sheet(ref, a.sheet)
        except AssertionError as e:
            print(f"MUTATE: caught it: {e}")
            return 0
        print("MUTATE: a swapped pinout was NOT caught")
        return 1
    OUT = OUTS[a.sheet]
    text = render(a.sheet)
    if a.check:
        if OUT.exists() and OUT.read_text() == text:
            print(f"{OUT.relative_to(ROOT)} is current")
            return 0
        print(f"{OUT.relative_to(ROOT)} is stale: run python3 tools/cheatsheet.py --sheet {a.sheet}")
        return 1
    OUT.write_text(text)
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
