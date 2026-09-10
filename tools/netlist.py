#!/usr/bin/env python3
"""The netlist, read back out of the schematics, and its rule check.

  python3 tools/netlist.py [sheet]        # print the nets and the ERC
  python3 tools/netlist.py --erc          # ERC only; exit 1 on an error

`tools/draw-schematics.py` draws every pin as `(number, name, net)`, so
the sheets have carried a full netlist since the day they were written
and nothing had ever read it back. This does, by importing that file and
recording what each sheet asks to be drawn, exactly as `tools/parts.py`
does for the bill of materials.

Two things come out of it that a picture cannot give you: a from/to
wiring list a person can follow hole by hole, and an electrical rule
check. The rule check is the point. A schematic drawn by hand is a
drawing: nothing in it objects to a net with one end, a supply pin left
off a rail, or the same reference used twice. All three are mistakes
that survive every visual review and then cost an afternoon at the
bench.
"""
import argparse
import importlib.util
import io
import sys
from collections import defaultdict
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SHEETS = ["bench-v1b", "bench-v2b", "bench-v1", "bench-v2", "pad-adapter"]
FN = {"bench-v1b": "sheet_v1b", "bench-v2b": "sheet_v2b", "bench-v1": "sheet_v1",
      "bench-v2": "sheet_v2", "pad-adapter": "sheet_pad"}

# A net named this is a deliberate no-connect, not a wire.
NC = {"NC", "", None}
# Rails: a net every board has, which may legitimately have many nodes
# and which it is worth naming separately in the report.
RAILS = {"+5V", "GND", "3V3", "PI_5V", "PI_3V3", "VBAT", "VBUS"}


def collect():
    spec = importlib.util.spec_from_file_location("draw", ROOT / "tools" / "draw-schematics.py")
    m = importlib.util.module_from_spec(spec)
    argv, sys.argv = sys.argv, [sys.argv[0], str(ROOT / "docs")]
    try:
        spec.loader.exec_module(m)
    finally:
        sys.argv = argv

    sheets = {}
    cur = {"name": None}
    real_chip, real_twopin, real_done = m.Sheet.chip, m.Sheet.twopin, m.Sheet.done

    def add(ref, part, pin, pinname, net):
        sheets[cur["name"]].append({"ref": ref, "part": part, "pin": pin, "pinname": pinname, "net": net})

    def chip(self, x, y, w, ref, part, left, right, conn=False, extra=None):
        for no, nm, net in list(left) + list(right):
            add(ref, part, no, nm, net)
        return real_chip(self, x, y, w, ref, part, left, right, conn=conn, extra=extra)

    def twopin(self, x, y, ref, part, net_a, net_b, horizontal=True):
        add(ref, part, 1, "1", net_a)
        add(ref, part, 2, "2", net_b)
        return real_twopin(self, x, y, ref, part, net_a, net_b, horizontal=horizontal)

    m.Sheet.chip, m.Sheet.twopin, m.Sheet.done = chip, twopin, lambda self, path: None
    try:
        for name in SHEETS:
            cur["name"] = name
            sheets[name] = []
            with redirect_stdout(io.StringIO()):
                getattr(m, FN[name])()
    finally:
        m.Sheet.chip, m.Sheet.twopin, m.Sheet.done = real_chip, real_twopin, real_done
    return sheets


def nets_of(nodes):
    nets = defaultdict(list)
    for n in nodes:
        if n["net"] not in NC:
            nets[n["net"]].append(n)
    return nets


def erc(name, nodes):
    """Errors are things that cannot be right. Notes are things worth a
    human's eye that may be perfectly intended."""
    errors, notes = [], []
    nets = nets_of(nodes)

    for net, ns in sorted(nets.items()):
        if len(ns) == 1:
            n = ns[0]
            errors.append(f"net {net!r} has one end only: {n['ref']} pin {n['pin']} ({n['pinname']}). "
                          "A net with one end is a wire to nowhere, or a name typed two ways.")

    # Every device that is not a connector wants a supply and a ground.
    by_ref = defaultdict(list)
    for n in nodes:
        by_ref[n["ref"]].append(n)
    for ref, ns in sorted(by_ref.items()):
        part = ns[0]["part"]
        names = {(n["pinname"] or "").upper() for n in ns}
        if not any(k in names for k in ("VCC", "VDD", "VBAT", "5V", "3V3")):
            continue
        on = {n["pinname"].upper(): n["net"] for n in ns if n["pinname"]}
        for supply in ("VCC", "VDD"):
            if supply in on and on[supply] in NC:
                errors.append(f"{ref} ({part}) has {supply} on no net")
        if "GND" not in names and "VSS" not in names:
            notes.append(f"{ref} ({part}) has a supply pin but no GND or VSS pin drawn")

    # One reference, one part. A ref used twice on a sheet is two devices
    # sharing a name, and the wiring list would merge them silently.
    for ref, ns in sorted(by_ref.items()):
        parts = {n["part"] for n in ns}
        if len(parts) > 1:
            errors.append(f"reference {ref} names {len(parts)} different parts: {', '.join(sorted(parts))}")
        seen = defaultdict(int)
        for n in ns:
            if n["pin"] is not None:
                seen[n["pin"]] += 1
        dupes = [p for p, c in seen.items() if c > 1]
        if dupes:
            errors.append(f"{ref} draws pin(s) {', '.join(str(d) for d in sorted(dupes))} more than once")

    singles = [net for net, ns in nets.items() if net in RAILS and len(ns) < 2]
    for net in sorted(singles):
        notes.append(f"rail {net} has fewer than two nodes on this sheet")
    return errors, notes


def report(sheets, only=None):
    L = []
    bad = 0
    for name in SHEETS:
        if only and name != only:
            continue
        nodes = sheets[name]
        nets = nets_of(nodes)
        errors, notes = erc(name, nodes)
        bad += len(errors)
        refs = len({n["ref"] for n in nodes})
        L.append(f"\n=== {name}: {refs} references, {len(nodes)} pins, {len(nets)} nets")
        for e in errors:
            L.append(f"  ERROR  {e}")
        for n in notes:
            L.append(f"  note   {n}")
        if not errors:
            L.append("  ERC clean")
    return "\n".join(L), bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sheet", nargs="?", help="one sheet only")
    ap.add_argument("--erc", action="store_true", help="rule check only; exit 1 on an error")
    a = ap.parse_args()
    sheets = collect()
    text, bad = report(sheets, a.sheet)
    print(text.strip())
    print(f"\n{bad} ERC error(s)")
    return 1 if (bad and a.erc) else 0


if __name__ == "__main__":
    sys.exit(main())
