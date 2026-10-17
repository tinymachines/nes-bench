#!/usr/bin/env python3
"""Route the v2b board, once, and record the result.

  python3 tools/route-pcb.py               # -> docs/routing/bench-v2b.ses
  python3 tools/route-pcb.py --passes 60
  python3 tools/route-pcb.py --sheet bench-v1c   # -> docs/routing/bench-v1c.ses

Routing is the one step here that is expensive and not deterministic, so
it is not on the path of a build. This tool runs it and **records the
answer**; `tools/make-pcb.py` applies the recording every time and needs
neither Java nor a router. A fresh clone gets a routed board.

The recording is `docs/routing/bench-v2b.ses`, a Specctra session file,
and it is committed for the same reason the pin golden is committed in
the 6502 repository: it is the output of a long search, it is checkable
against the thing it describes, and re-deriving it on every build would
buy nothing and cost minutes.

What keeps it honest is `tools/session.py`: the session file carries
every part's position, so it can be held to the board it is applied to
and it fails loudly when a part has moved in `ROWS` since the routing
was made.

The router is freerouting, run headless. It is not vendored: point
FREEROUTING_JAR at a jar, or drop one in ~/.cache/freerouting/. Version
2.1.0 is what this was made with; 2.4.1 needs a Java newer than this box
has. The jar is not a dependency of anything else here.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "routing"
sys.path.insert(0, str(ROOT / "tools"))
from loadmod import load  # noqa: E402

import pcbnew  # noqa: E402


def jar():
    env = os.environ.get("FREEROUTING_JAR")
    if env:
        return Path(env)
    found = sorted(Path.home().glob(".cache/freerouting/freerouting-*.jar"))
    return found[-1] if found else None


def check_rules(dsn, mk):
    """The design rules KiCad put in the file, against the ones this
    project authored. The netclass accessors are broken in KiCad 6's
    Python bindings, so the authored numbers cannot be pushed into the
    board; the next best thing is to read back what the exporter wrote
    and refuse to route on rules nobody chose."""
    text = Path(dsn).read_text()
    got = {}
    m = re.search(r"\(rule\s+\(width\s+([\d.]+)\)\s+\(clearance\s+([\d.]+)\)", text)
    if m:
        got["width_um"], got["clearance_um"] = float(m.group(1)), float(m.group(2))
    bad = []
    for key, want in (("width_um", mk.TRACK_UM), ("clearance_um", mk.CLEARANCE_UM)):
        if key not in got:
            bad.append(f"the exported design has no {key}")
        elif abs(got[key] - want) > 1.0:
            bad.append(f"{key} is {got[key]} in the exported design, {want} in tools/make-pcb.py")
    return got, bad


def widen(dsn, widths, clearance_um):
    """Give the nets in `widths` their own router class, at their own
    track width. KiCad 6's bindings cannot reach a netclass, so the board
    cannot carry the width into the export; the exported design is
    edited instead, the nets taken out of the default class and put in
    one of their own, and the router then lays them at that width. The
    session file records each wire's width, so the board gets it too."""
    if not widths:
        return
    text = Path(dsn).read_text()
    m = re.search(r'\(class kicad_default(?: "")?([^()]*)', text)
    if not m:
        raise RuntimeError("the exported design has no kicad_default class")
    # KiCad 6 lists no nets in its default class (every net not named
    # elsewhere falls into it); if a later version lists them, the wide
    # ones come out, so no net is in two classes.
    names = m.group(1).split()
    if names:
        kept = " ".join(n for n in names if n not in widths)
        text = text[:m.start(1)] + " " + kept + "\n" + text[m.end(1):]
    for net in widths:
        if f"(net {net}" not in text and f'(net "{net}"' not in text:
            raise RuntimeError(f"{net} is not a net in the exported design")
    groups = {}
    for net, w in widths.items():
        groups.setdefault(w, []).append(net)
    via = re.search(r'\(use_via ([^)]+)\)', text).group(1)
    extra = "".join(f'    (class wide_{w:.0f} {" ".join(sorted(nets))}\n'
                    f'      (circuit (use_via {via}))\n'
                    f'      (rule (width {w:.0f}) (clearance {clearance_um:.0f}))\n    )\n'
                    for w, nets in sorted(groups.items()))
    i = text.index("(class kicad_default")
    text = text[:i] + extra.lstrip() + "    " + text[i:]
    Path(dsn).write_text(text)


def run(jarfile, dsn, ses, passes, workdir):
    (workdir / "freerouting.json").write_text(json.dumps({
        "gui": {"enabled": False},
        "usage_and_diagnostic_data": {"analytics_enabled": False, "disable_analytics": True},
    }, indent=2))
    r = subprocess.run(["java", "-jar", str(jarfile), "-de", str(dsn), "-do", str(ses),
                        "-mp", str(passes)],
                       cwd=str(workdir), capture_output=True, text=True, timeout=3600)
    stats = {}
    blocks = re.findall(r"\{.*\}", r.stdout, re.S)
    for b in reversed(blocks):
        try:
            stats = json.loads(b)
            break
        except ValueError:
            continue
    return r, stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--passes", type=int, default=40)
    ap.add_argument("--jar", help="the freerouting jar; else $FREEROUTING_JAR, else ~/.cache")
    ap.add_argument("--sheet", default="bench-v2b", choices=["bench-v2b", "bench-v1c"])
    a = ap.parse_args()

    jarfile = Path(a.jar) if a.jar else jar()
    if not jarfile or not jarfile.exists():
        print("route-pcb: no freerouting jar. Set FREEROUTING_JAR, or:\n"
              "  mkdir -p ~/.cache/freerouting && cd ~/.cache/freerouting\n"
              "  curl -LO https://github.com/freerouting/freerouting/releases/download/"
              "v2.1.0/freerouting-2.1.0.jar\n"
              "The recorded routing in docs/routing/ is what builds use; this tool only "
              "makes a new one.")
        return 1
    if not shutil.which("java"):
        print("route-pcb: no java on PATH")
        return 1

    mk = load(ROOT / "tools" / "make-pcb.py", "makepcb")
    mk.select(a.sheet)
    board, placed, keep, applied, unset = mk.build()
    if unset:
        for m in unset:
            print(f"  {m}")
        return 1

    # The pours come off before the router sees the board. Left on, they
    # are declared as planes, the router treats every pad on those nets
    # as already connected, and then its own signal traces cut the plane
    # into islands: the first run came back "0 incomplete" and left
    # three pads with no copper path to their net and the ground plane
    # in four pieces. Routed as ordinary nets they are traces, and the
    # pours go back on afterwards over the top of them.
    # The keepouts are zones too and must stay: they are what tells the
    # router where the UNO's jacks stand.
    for z in list(board.Zones()):
        if not z.GetIsRuleArea():
            board.Remove(z)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        dsn, ses = tmp / f"{a.sheet}.dsn", tmp / f"{a.sheet}.ses"
        if not pcbnew.ExportSpecctraDSN(board, str(dsn)):
            print("  the Specctra export failed")
            return 1
        rules, bad = check_rules(dsn, mk)
        widen(dsn, mk.NET_WIDTHS, mk.CLEARANCE_UM)
        if mk.NET_WIDTHS:
            rules["wide"] = dict(mk.NET_WIDTHS)
        for m in bad:
            print(f"  {m}")
        if bad:
            return 1
        print(f"  {len(placed)} parts, {len(keep)} nets, {applied} pads; "
              f"{rules['width_um']:.0f} um track, {rules['clearance_um']:.0f} um clearance")
        print(f"  routing with {jarfile.name}, {a.passes} passes...")
        r, stats = run(jarfile, dsn, ses, a.passes, tmp)
        if not ses.exists():
            print(f"  the router wrote no session file (exit {r.returncode})")
            print("\n".join(r.stdout.splitlines()[-15:]))
            return 1
        conn = stats.get("connections", {})
        viol = stats.get("clearance_violations", {}).get("total_count")
        left = conn.get("incomplete_count")
        print(f"  {conn.get('maximum_count')} connections, {left} incomplete, "
              f"{stats.get('traces', {}).get('total_segment_count')} segments, "
              f"{stats.get('vias', {}).get('total_count')} vias, "
              f"{viol} clearance violations by the router's own count")
        if left:
            print(f"  REFUSED: {left} connection(s) unrouted. More passes, or move something in ROWS.")
            return 1
        OUT.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ses, OUT / f"{a.sheet}.ses")
        (OUT / f"{a.sheet}.json").write_text(json.dumps(
            {"router": jarfile.name, "passes": a.passes, "rules": rules, "stats": stats},
            indent=2) + "\n")
    print(f"  wrote {(OUT / f'{a.sheet}.ses').relative_to(ROOT)}")
    print(f"  now run: python3 tools/make-pcb.py --sheet {a.sheet} --plot")
    return 0


if __name__ == "__main__":
    sys.exit(main())
