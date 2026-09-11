#!/usr/bin/env python3
"""The drawing package: one PDF, framed and paginated, from the sheets.

  python3 tools/make-package.py            # -> docs/package/nes-bench.pdf
  python3 tools/make-package.py --svg-only # the pages, no PDF

`docs/package.json` says what is in it and what goes in the title block.
`tools/sheetframe.py` draws the frame. Everything on a content sheet is
derived: the parts list from `tools/parts.py`, the wiring list from
`tools/netlist.py`, the build sequence from `tools/bringup.py`, the pin
map and the chip sheets from `tools/cheatsheet.py`. The only authored
text in the package is the intro paragraphs in the JSON, the schematics
themselves, and what each chip's pins do on the part, which is the
datasheet's and lives in one place in that tool.

The PDF is assembled by `rsvg-convert`, which takes several SVGs and
writes them as pages of one document at exactly 0.75 pt per unit, so an
ANSI B page is 17 by 11 inches in the PDF and prints as one.

Nothing here is committed. The SVG sheets are the artefact and are
checked against the wiring tables; a PDF is a rendering of them, made on
demand, for the same reason the PNGs are.
"""
import argparse
import importlib.util
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "package"
sys.path.insert(0, str(ROOT / "tools"))
import sheetframe as sf  # noqa: E402


from loadmod import load as _load  # noqa: E402


def load(name, path):
    return _load(ROOT / "tools" / path, name)


def git_rev():
    try:
        r = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True)
        return r.stdout.strip() or "no git"
    except OSError:
        return "no git"


def page_meta(cfg, title, n, total):
    return {"org": cfg["org"], "project": cfg["project"], "docno": cfg["docno"], "rev": cfg["rev"],
            "date": date.today().isoformat(), "drawn": cfg["drawn"], "title": title,
            "sheet": f"{n} of {total}", "source": f"git {git_rev()}", "scale": "NTS",
            "revisions": [tuple(r) for r in cfg.get("revisions", [])]}


def sheet_cover(p, cfg, spec):
    x, y, w, h = p.body_box(top_pad=44)
    p.header(cfg["project"], cfg["title"])
    p.text(x, y + 8, cfg["title"], "tmf-h1")
    cy = y + 44
    for para in cfg["intro"]:
        for line in sf.wrap(para, 104):
            p.text(x, cy, line, "tmf-body")
            cy += 18
        cy += 12
    cy += 10
    p.text(x, cy, "Sheets", "tmf-h2")
    paper = {"ansi-a": "letter", "ansi-b": "ANSI B", "a4": "A4", "a3": "A3"}
    # The index lists the sheets the package actually has, which is not
    # the same list as package.json when a build sequence needed a
    # second page of paper.
    sheets = cfg.get("_specs") or cfg["sheets"]
    rows = [[str(i + 1), s["title"] + (" (continued)" if s.get("from") else ""),
             paper.get(s.get("page", cfg.get("page", "ansi-b")), "?"),
             {"schematic": "schematic", "wiring": "derived from the schematic",
              "parts": "derived from the schematic", "steps": "derived from the bring-up tool",
              "pinmap": "derived from the schematic, the lab log and the bring-up tool",
              "chip": "pins from the schematic; purposes authored from the datasheet",
              "cover": "this sheet"}[s["kind"]]]
            for i, s in enumerate(sheets)]
    drawn = p.table((x, cy + 10, w * 0.86, h - (cy - y) - 24),
                    ["sheet", "title", "paper", "how it is made"],
                    rows, widths=[0.07, 0.50, 0.12, 0.31], mono=(0, 2))
    # The index of a document has to list all of it. `table` truncates
    # honestly and says so, which is right for a wiring list that runs
    # on: here there is no next sheet to run on to, so a truncated index
    # is a shorter intro, not a smaller font.
    assert drawn == len(rows), (
        f"the sheet index fits {drawn} of {len(rows)} rows on a {p.size} cover. "
        "Shorten the intro paragraphs in docs/package.json.")


def sheet_schematic(p, cfg, spec):
    top = p.header(cfg["project"], spec["title"])
    box = p.full_box(top_pad=52)
    scale = p.place_svg(ROOT / "docs" / spec["svg"], box, drop_heading=True)
    if p._dropped_sub:
        ix, iy, iw, _ih = p._inner
        p.text(ix + 8, top + 16, p._dropped_sub, "tmf-body")
    gen = {"breadboard": "breadboard.py", "wiring": "wiring-diagram.py"}.get(spec["svg"].split("-")[0], "draw-schematics.py")
    p.footer(f'{spec["svg"]}  {p.size}  placed at {scale*100:.0f}%  drawn by tools/{gen}')


def paginate(p, spec, rows, box, headers, widths, mono):
    """A table that carries on to another sheet when it has to. The
    driver reads `_left` and adds the paper; this only has to say how
    much it managed and where the next sheet should start."""
    skip = spec.get("from", 0)
    drawn = p.table(box, headers, rows[skip:], widths=widths, mono=mono)
    spec["_drawn_here"] = drawn
    spec["_left"] = len(rows) - skip - drawn
    return drawn


def sheet_wiring(p, cfg, spec):
    nl = load("netlist", "netlist.py")
    sheets, _offsheet = nl.collect()
    nodes = sheets[spec["sheet"]]
    nets = nl.nets_of(nodes)
    p.header(cfg["project"], spec["title"])
    x, y, w, h = p.body_box(top_pad=44)
    p.text(x, y + 6, "Every wire on the board, net by net", "tmf-h2")
    p.text(x, y + 26, "Connect everything on a row together. Read back out of the schematic, "
                      "so it cannot disagree with it."
                      + ("  Continued from the previous sheet." if spec.get("from") else ""),
           "tmf-body")
    rows = []
    for net, ns in sorted(nets.items(), key=lambda kv: (kv[0] not in nl.RAILS, kv[0])):
        pins = ", ".join(f"{n['ref']}-{n['pin']}" if n["pin"] is not None else f"{n['ref']} {n['pinname']}"
                         for n in ns)
        rows.append([net, str(len(ns)), pins])
    paginate(p, spec, rows, (x, y + 40, w, h - 46), ["net", "ends", "join these"],
             [0.14, 0.07, 0.79], (0, 2))


def sheet_parts(p, cfg, spec):
    pt = load("parts", "parts.py")
    found = pt.collect()
    p.header(cfg["project"], spec["title"])
    x, y, w, h = p.body_box(top_pad=44)
    p.text(x, y + 6, "Everything that has to be in a drawer", "tmf-h2")
    p.text(x, y + 26, "Parts from every sheet, deduplicated. The status column is the only "
                      "authored thing in this package's tables."
                      + ("  Continued from the previous sheet." if spec.get("from") else ""),
           "tmf-body")
    seen, rows = set(), []
    only = spec.get("only")
    for name, _fn, _b in pt.SHEETS:
        if only and name not in only:
            continue
        for _kind, ref, part, _extra in found[name]:
            key = part.split("  ")[0].strip()
            if key in seen:
                continue
            seen.add(key)
            st, note = pt.status_for(key)
            rows.append([key, st, note])
    paginate(p, spec, rows, (x, y + 40, w, h - 46), ["part", "status", "note"],
             [0.28, 0.12, 0.60], (0,))


def steps_items(cfg, spec):
    bu = load("bringup", "bringup.py")
    match = [s for s in bu.SESSIONS if s[0] == spec["session"]][0]
    _num, stitle, blurb, ids = match
    items = []
    for sid in ids:
        st = bu.BY_ID[sid]
        items.append(f"{sid}  {st['title']}")
        items += [f"      {d}" for d in st["do"]]
    return stitle, blurb, items


def sheet_steps(p, cfg, spec):
    stitle, blurb, items = steps_items(cfg, spec)
    skip = spec.get("from", 0)
    p.header(cfg["project"], spec["title"])
    x, y, w, h = p.body_box(top_pad=44)
    p.text(x, y + 6, stitle, "tmf-h2")
    p.text(x, y + 26, blurb if not skip else f"{blurb}  Continued from the previous sheet.",
           "tmf-body")
    drawn = p.steps((x, y + 42, w, h - 48), items[skip:], start=skip + 1)
    spec["_drawn_here"] = drawn
    spec["_left"] = len(items) - skip - drawn
    p.footer("generated from tools/bringup.py, which is also the tool that runs these steps")


def sheet_pinmap(p, cfg, spec):
    """The two breakouts pin by pin and the head's jumpers: the rows
    tools/cheatsheet.py writes as markdown, drawn as three tables. The
    controller port runs the width of the sheet; the two short ones sit
    side by side under it, which is what makes three fit on a letter."""
    cs = load("cheatsheet", "cheatsheet.py")
    p.header(cfg["project"], spec["title"])
    x, y, w, h = p.body_box(top_pad=44)
    tables = cs.pinmap(spec.get("sheet", "bench-v1b"))
    gap = 24
    boxes = [(x, w, 118)] + [(x, (w - gap) / 2, 56), (x + (w + gap) / 2, (w - gap) / 2, 56)]
    cy_row = y
    bottoms = []
    for k, ((title, note, headers, rows), (bx, bw, chars)) in enumerate(zip(tables, boxes)):
        cy = cy_row
        p.text(bx, cy + 6, title, "tmf-h2")
        cy += 14
        for line in sf.wrap(note, chars):
            cy += 15
            p.text(bx, cy, line, "tmf-body")
        cy += 10
        widths = {5: [0.06, 0.10, 0.14, 0.14, 0.56], 3: [0.20, 0.40, 0.40],
                  4: [0.14, 0.12, 0.37, 0.37]}[len(headers)]
        drawn = p.table((bx, cy, bw, y + h - cy), headers, rows, widths=widths, mono=(0, 1), strict=True)
        # Three short tables on one sheet: a row that does not fit is a
        # layout mistake, not a reason for a second sheet.
        assert drawn == len(rows), f"pinmap: {title!r} fits {drawn} of {len(rows)} rows"
        bottoms.append(cy + 21 + 19 * len(rows))
        if k == 0:
            cy_row = bottoms[0] + 22
    p.footer("generated from tools/cheatsheet.py: the schematic, the lab log and tools/bringup.py's lead table")


def sheet_chip(p, cfg, spec):
    """One chip, every pin of the package: the datasheet's purpose beside
    what the schematic wires it to."""
    cs = load("cheatsheet", "cheatsheet.py")
    ref, part, what, headers, rows = cs.chip_sheet(spec["ref"], spec.get("sheet", "bench-v1b"))
    p.header(cfg["project"], spec["title"])
    x, y, w, h = p.body_box(top_pad=44)
    p.text(x, y + 6, f"{ref}: {part}", "tmf-h2")
    cy = y + 12
    for line in sf.wrap(what, 118):
        cy += 15
        p.text(x, cy, line, "tmf-body")
    cy += 12
    drawn = p.table((x, cy, w, y + h - cy), headers, rows, widths=[0.05, 0.09, 0.44, 0.42], mono=(0, 1),
                    strict=True)
    assert drawn == len(rows), f"chip {ref}: fits {drawn} of {len(rows)} pins on a {p.size} sheet"
    p.footer("pin purposes authored from the datasheet in tools/cheatsheet.py; the bench column is read out of the schematic")


KINDS = {"cover": sheet_cover, "schematic": sheet_schematic, "wiring": sheet_wiring,
         "parts": sheet_parts, "steps": sheet_steps, "pinmap": sheet_pinmap, "chip": sheet_chip}


def render(cfg, specs, out):
    """Every sheet, at the page count `specs` currently implies."""
    files = []
    total = len(specs)
    cfg["_specs"] = specs
    for i, spec in enumerate(specs, 1):
        # A sheet may name its own paper. The package is landscape
        # letter; a drawing that will not print legibly at that size
        # says so here rather than being silently shrunk, which is the
        # same rule place_svg enforces from the other end.
        size = spec.get("page", cfg.get("page", "ansi-b"))
        p = sf.Page(page_meta(cfg, spec["title"], i, total), size=size)
        KINDS[spec["kind"]](p, cfg, spec)
        f = out / f"{i:02d}-{spec['kind']}.svg"
        p.done(f)
        files.append(str(f))
    return files


def build(cfg, out, svg_only):
    out.mkdir(parents=True, exist_ok=True)
    for f in out.glob("*.svg"):
        f.unlink()
    # A build sequence is as long as it is. Render, and if a steps sheet
    # ran out of paper, put another one after it and render the whole
    # package again, so the "sheet n of m" printed on every page is
    # still true. The loop is bounded by the item count, not by hope.
    specs = [dict(s) for s in cfg["sheets"]]
    files = []
    for _ in range(24):
        files = render(cfg, specs, out)
        grown = False
        for i, spec in enumerate(specs):
            if not spec.get("_left"):
                continue
            nxt = spec.get("from", 0) + spec["_drawn_here"]
            after = specs[i + 1] if i + 1 < len(specs) else None
            # A sheet that overflows keeps overflowing on every pass:
            # what decides whether to add paper is whether the sheet
            # that carries on from here is already there.
            if after and after["kind"] == spec["kind"] and after.get("from") == nxt:
                continue
            specs.insert(i + 1, {**{k: v for k, v in spec.items() if not k.startswith("_")},
                                 "from": nxt})
            grown = True
            break
        if not grown:
            break
    else:
        raise AssertionError("a sheet keeps overflowing: it fits nothing on a page")
    for f in out.glob("*.svg"):
        if str(f) not in files:
            f.unlink()
    for i, spec in enumerate(specs, 1):
        print(f"  sheet {i}/{len(specs)}  {spec['title']}")
    if svg_only:
        return 0
    pdf = out / f"{cfg['project']}-{cfg['docno']}-rev{cfg['rev']}.pdf"
    r = subprocess.run(["rsvg-convert", "-f", "pdf", "-o", str(pdf), *files],
                       capture_output=True, text=True)
    if r.returncode != 0 or not pdf.exists():
        print(f"rsvg-convert failed: {r.stderr.strip()[:300]}")
        return 1
    print(f"\n{pdf.relative_to(ROOT)}  {pdf.stat().st_size//1024} KB, {len(files)} pages\n")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--svg-only", action="store_true")
    ap.add_argument("--config", help="one manifest; the default is every docs/package*.json")
    a = ap.parse_args()
    # One drawing package per manifest. v1b and v2b are different
    # builds, they are numbered separately (TM-NESB-001 and -002), and
    # each gets its own directory so building one cannot quietly delete
    # the other's sheets.
    configs = [Path(a.config)] if a.config else sorted((ROOT / "docs").glob("package*.json"))
    if not configs:
        print("no package manifest found")
        return 1
    bad = 0
    for c in configs:
        cfg = json.loads(c.read_text())
        print(f"{c.name}  {cfg['docno']}  {cfg['title']}")
        bad |= build(cfg, OUT / cfg["docno"].lower(), a.svg_only)
    return bad


if __name__ == "__main__":
    sys.exit(main())
