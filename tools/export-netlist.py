#!/usr/bin/env python3
"""The netlist and the BOM, in formats an EDA tool will take.

  python3 tools/export-netlist.py                 # -> docs/fab/
  python3 tools/export-netlist.py --check         # every part has a footprint

Writes, per sheet:

  <sheet>.net         KiCad netlist (s-expression), for File > Import > Netlist
  <sheet>.protel.net  Protel/Tango netlist, which almost every other tool takes
  <sheet>-bom.csv     the bill of materials, grouped by value and footprint

The netlist itself is not authored: `tools/netlist.py` reads it out of
the schematic, and `tools/netlist.py --erc` has to be clean before any
of this means anything. What IS authored is the footprint each part
gets, and that is a real decision, not a lookup: a 100 nF capacitor can
be any of a dozen packages and only the person holding the drawer knows
which. FOOTPRINTS below is that decision, and `--check` fails on a part
that has not been given one, so a new part on a sheet cannot slip
through as an empty field.

**A1 is not a component.** It is an Arduino board, and a netlist that
lists it as a part with a footprint is describing a shield: a PCB that
plugs into the UNO's headers. If the board is meant to sit beside the
UNO and connect with a cable instead, A1 becomes a pin header and its
footprint changes. That decision has to be made before layout, not
during it, and the exporter says so in every file it writes.
"""
import argparse
import csv
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "fab"
sys.path.insert(0, str(ROOT / "tools"))
from loadmod import load  # noqa: E402

SHEETS = ["bench-v1b", "bench-v2b"]

# AUTHORED. Matched on a prefix of the part string, longest first. The
# comment on each is why that package and not another.
FOOTPRINTS = [
    ("74HCT04", "Package_DIP:DIP-14_W7.62mm", "DIP-14, socketed"),
    ("74HC165", "Package_DIP:DIP-16_W7.62mm", "DIP-16, socketed"),
    ("74HC595", "Package_DIP:DIP-16_W7.62mm", "DIP-16, socketed"),
    ("LM1881N", "Package_DIP:DIP-8_W7.62mm", "DIP-8, socketed"),
    ("100nF", "Capacitor_THT:C_Disc_D5.0mm_W2.5mm_P5.00mm", "5 mm disc, 0.2 inch pitch"),
    ("100R", "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal", "quarter watt axial, lying down"),
    ("680k", "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal", "quarter watt axial, lying down"),
    ("console controller port", "Connector_PinHeader_2.54mm:PinHeader_1x05_P2.54mm_Vertical",
     "the cut cable lands on a 5 way header; pins 6 and 7 are not carried"),
    ("original pad", "Connector_PinHeader_2.54mm:PinHeader_1x05_P2.54mm_Vertical",
     "the pad half of the cut cable, same 5 conductors"),
    ("Arduino UNO", "Connector_IDC:IDC-Header_2x10_P2.54mm_Vertical",
     "DECIDED 2026-09-09: cable, not shield. A 20 way IDC box header and a ribbon "
     "to the UNO, wired per A1_HEADER below"),
]

# AUTHORED, and the decision that makes the cable form buildable.
#
# A footprint's pads are numbered; a schematic's pins are named. A1's
# nodes say "D13" and "5V", and an IDC header's pads say 1 to 20, so
# something has to say which is which. This is that something, and it is
# the ribbon's pinout.
#
# Sixteen signals need sixteen pads, so a 2x8 header would fit exactly
# and would carry SCK and two clock lines at four megahertz with a
# single ground for the whole cable. A 20 way part costs the same and
# leaves four pads spare, so the spares are grounds and they sit beside
# the fastest edges: SCK, RCLK, MOSI and the two console clocks. In a
# ribbon the return current follows the nearest ground, and with one
# ground at the far end it has nowhere near to go.
A1_HEADER = {
    1: "5V", 2: "GND",
    3: "D13", 4: "GND",          # SCK, with a ground beside it
    5: "D11", 6: "D10",          # MOSI and RCLK
    7: "GND", 8: "D2",           # ground, then console 1 clock
    9: "D5", 10: "GND",          # console 1 latch, with a ground
    11: "D9", 12: "D4",          # console 2 clock and latch
    13: "D3", 14: "GND",         # CSYNC, with a ground
    15: "A0", 16: "A1",          # VSYNC and the trigger out
    17: "D6", 18: "D7",          # pad latch and clock
    19: "D8", 20: "A2",          # the two pads' data lines
}
UNRESOLVED = "Arduino UNO"


# Where KiCad keeps its footprints, if it is installed. A footprint name
# is a claim about a file, and until 2026-09-09 nothing here checked it:
# two of the names below were guesses and both were wrong (DIP-08 is
# spelled DIP-8, and the axial resistor needs its _Horizontal suffix).
# The export was perfectly happy to write them, because the check only
# asked whether a string was present. A check that cannot look at the
# thing it names is not a check.
FP_LIBS = [Path("/usr/share/kicad/footprints"), Path("/usr/share/kicad/modules")]


def footprint_file(fp):
    """The .kicad_mod a footprint name points at, or None if the library
    is not installed here. Returns False if the library IS installed and
    the footprint is not in it, which is the case worth failing on."""
    lib = next((p for p in FP_LIBS if p.is_dir()), None)
    if lib is None:
        return None
    libname, _, name = fp.partition(":")
    path = lib / f"{libname}.pretty" / f"{name}.kicad_mod"
    return path if path.is_file() else False


def footprint(part):
    for key, fp, why in sorted(FOOTPRINTS, key=lambda f: -len(f[0])):
        if part.startswith(key) or key in part:
            return fp, why
    return None, None


def net_pads(ns):
    """Every (ref, pad, function) a net lands on.

    Usually one pad per node. A1 is the exception and it has to be: the
    ribbon carries four spare grounds, deliberately, and if only the one
    pad the schematic draws were connected then the other four would be
    unconnected pins on a header and the whole reason for the 20 way
    part would be silently undone."""
    out = []
    for n in ns:
        if n["ref"] == "A1" and (n["pinname"] or "").split(" ")[0] == "GND":
            for pad, sig in sorted(A1_HEADER.items()):
                if sig == "GND":
                    out.append(("A1", str(pad), "GND"))
            continue
        pad, _warn = pad_name(n["ref"], n["pin"], n["pinname"])
        if pad is not None:
            out.append((n["ref"], pad, n["pinname"]))
    return out


def header_pad(pinname):
    """A1's pad number for a signal, from the authored ribbon pinout."""
    want = (pinname or "").split(" ")[0]
    for pad, sig in A1_HEADER.items():
        if sig == want:
            return pad
    return None


def pad_name(ref, pin, pinname):
    """The pad a node lands on. A schematic pin is a label for a human;
    a netlist node has to name a pad on a footprint.

    Numbered pins are already pads. A named pin gets its annotation
    stripped, so "D2 (INT0)" and "D13 SCK" become D2 and D13, which is
    what the pads are called. A pin that names MORE THAN ONE physical
    pin cannot become a node at all, and the exporter says so rather
    than inventing one: the UNO's serial is drawn as a single pin
    "D0, D1", which is two pads, and a board cannot be laid out from
    that until the schematic splits it."""
    if isinstance(pin, int):
        return str(pin), None
    name = (pinname or "").strip()
    if ref == "A1":
        pad = header_pad(name)
        if pad is None:
            return None, (f"A1 pin {name!r} has no pad in A1_HEADER. The ribbon's pinout has to "
                          "name every signal the schematic uses.")
        return str(pad), None
    if "," in name:
        return None, (f"{ref} draws {name!r} as one pin, which is {len(name.split(','))} pads. "
                      "Split it on the schematic before laying out a board.")
    return name.split(" ")[0], None


def components(nodes):
    out = {}
    for n in nodes:
        out.setdefault(n["ref"], n["part"])
    return out


def value_of(part):
    """The value a BOM wants: the part number, without the sheet's
    annotation about which rail it sits on or which bag it came from."""
    return part.split("  ")[0].split(" (")[0].strip()


def banner(sheet, kind):
    return (f"Generated by tools/export-netlist.py from {sheet}.svg on {date.today().isoformat()}. "
            f"The connections are read out of the schematic; the footprints are authored in that file. "
            f"A1 is an Arduino board, not a part: see the note in the tool before laying anything out.")


def routable(nets, offsheet):
    """Nets a board can actually have. A net with one node is a
    connector going off the board: real, but nothing to route."""
    keep, dropped = {}, []
    for net, ns in nets.items():
        if len(ns) >= 2:
            keep[net] = ns
        else:
            dropped.append(net)
    return keep, dropped


def kicad_net(sheet, nodes, nets):
    comps = components(nodes)
    L = ['(export (version "E")', '  (design',
         f'    (source "{sheet}.svg")', f'    (date "{date.today().isoformat()}")',
         '    (tool "nes-bench tools/export-netlist.py")',
         f'    (sheet (number "1") (name "/") (tstamps "/") (title_block (title "{sheet}")'
         f' (comment (number "1") (value "{banner(sheet, "kicad")}")))))',
         '  (components']
    for ref, part in sorted(comps.items()):
        fp, _why = footprint(part)
        L.append(f'    (comp (ref "{ref}") (value "{value_of(part)}")'
                 f'{f" (footprint " + chr(34) + fp + chr(34) + ")" if fp else ""}'
                 f' (tstamps "/{ref}"))')
    L.append("  )")
    L.append("  (nets")
    for i, (net, ns) in enumerate(sorted(nets.items()), 1):
        L.append(f'    (net (code "{i}") (name "{net}")')
        for ref, pad, fn in net_pads(ns):
            L.append(f'      (node (ref "{ref}") (pin "{pad}")'
                     f' (pinfunction "{fn}") (pintype "passive"))')
        L.append("    )")
    L.append("  ))")
    return "\n".join(L) + "\n"


def protel_net(sheet, nodes, nets):
    comps = components(nodes)
    L = [f"(* {banner(sheet, 'protel')} *)"]
    for ref, part in sorted(comps.items()):
        fp, _why = footprint(part)
        L += ["[", ref, fp or "UNRESOLVED", value_of(part), "]"]
    for net, ns in sorted(nets.items()):
        L += ["(", net]
        for ref, pad, _fn in net_pads(ns):
            L.append(f"{ref}-{pad}")
        L.append(")")
    return "\n".join(L) + "\n"


def bom_rows(nodes):
    comps = components(nodes)
    groups = defaultdict(list)
    for ref, part in comps.items():
        fp, why = footprint(part)
        groups[(value_of(part), fp or "", why or "")].append(ref)
    rows = []
    for (value, fp, why), refs in sorted(groups.items(), key=lambda kv: kv[0][0]):
        rows.append({"quantity": len(refs), "value": value,
                     "references": " ".join(sorted(refs)), "footprint": fp, "note": why})
    return rows


def parse_protel(text):
    """Read a Protel netlist back into {net: {"REF-PAD", ...}}. Used to
    check the exporter against itself: a writer that drops a node or
    invents one produces a file that looks perfectly well formed, and
    nothing downstream would ever notice."""
    nets, cur, name = {}, None, None
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("(*") or not line:
            continue
        if line == "(":
            cur, name = [], None
        elif line == ")" and cur is not None:
            nets[name] = set(cur)
            cur = None
        elif cur is not None:
            if name is None:
                name = line
            else:
                cur.append(line)
    return nets


def verify(sheet, keep):
    """What was written back against what was meant, node for node."""
    want = {net: {f"{r}-{p}" for r, p, _f in net_pads(ns)} for net, ns in keep.items()}
    got = parse_protel((OUT / f"{sheet}.protel.net").read_text())
    bad = []
    for net in sorted(set(want) | set(got)):
        if want.get(net) != got.get(net):
            a, b = want.get(net, set()), got.get(net, set())
            bad.append(f"{sheet} net {net!r}: written {sorted(b)}, meant {sorted(a)}")
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="exit 1 if a part has no footprint")
    a = ap.parse_args()

    nl = load(ROOT / "tools" / "netlist.py", "nl")
    sheets, offsheet = nl.collect()

    missing = []
    for sheet in SHEETS:
        for ref, part in components(sheets[sheet]).items():
            fp = footprint(part)[0]
            if fp is None:
                missing.append(f"{sheet}: {ref} ({part}) has no footprint. Add it to FOOTPRINTS.")
                continue
            found = footprint_file(fp)
            if found is False:
                missing.append(f"{sheet}: {ref} ({part}) names {fp!r}, which is not in the "
                               "footprint library. Check the spelling against what is installed.")
    for m in missing:
        print(f"  {m}")
    if a.check:
        if not missing:
            lib = next((p for p in FP_LIBS if p.is_dir()), None)
            where = "and every one is in the installed library" if lib else \
                "(no footprint library installed here, so the names are unverified)"
            print(f"export-netlist: every part on {len(SHEETS)} sheets has a footprint {where}")
        return 1 if missing else 0
    if missing:
        return 1

    OUT.mkdir(parents=True, exist_ok=True)
    problems = []
    for sheet in SHEETS:
        nodes = sheets[sheet]
        nets = nl.nets_of(nodes)
        errors, _notes = nl.erc(sheet, nodes, offsheet)
        if errors:
            print(f"  {sheet} does not pass its own rule check; not exporting it")
            return 1
        keep, dropped = routable(nets, offsheet)
        warns = []
        for ns in keep.values():
            for n in ns:
                _pad, warn = pad_name(n["ref"], n["pin"], n["pinname"])
                if warn and warn not in warns:
                    warns.append(warn)
        (OUT / f"{sheet}.net").write_text(kicad_net(sheet, nodes, keep))
        (OUT / f"{sheet}.protel.net").write_text(protel_net(sheet, nodes, keep))
        with (OUT / f"{sheet}-bom.csv").open("w", newline="") as f:
            w = csv.DictWriter(f, ["quantity", "value", "references", "footprint", "note"])
            w.writeheader()
            w.writerows(bom_rows(nodes))
        n_comp = len(components(nodes))
        print(f"  {sheet}: {n_comp} components, {len(keep)} routable nets "
              f"({len(dropped)} single-node net(s) left out: {', '.join(sorted(dropped)) or 'none'})")
        for wmsg in warns:
            print(f"    UNRESOLVED  {wmsg}")
        problems.extend(warns)
        wrong = verify(sheet, keep)
        for wmsg in wrong:
            print(f"    WRITER BUG  {wmsg}")
        if wrong:
            return 1
        n_nodes = sum(len(v) for v in keep.values())
        print(f"    read back: {len(keep)} nets and {n_nodes} nodes match the schematic")
    print(f"\nwrote {OUT.relative_to(ROOT)}/  ({len(SHEETS)} sheets)")
    n_gnd = sum(1 for v in A1_HEADER.values() if v == "GND")
    print(f"NOTE: A1 is a cable, not a shield: {dict((k, v) for k, v, _ in FOOTPRINTS)[UNRESOLVED]}, "
          f"wired per A1_HEADER, with {n_gnd} of its pads on GND so the ribbon's fast edges have a "
          "return path near them.")
    if problems:
        print(f"\n{len(problems)} thing(s) above must be settled on the schematic before a board. "
              "The netlists are written and are correct about everything else.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
