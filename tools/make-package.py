#!/usr/bin/env python3
"""The drawing package: one PDF, framed and paginated, from the sheets.

  python3 tools/make-package.py            # -> docs/package/nes-bench.pdf
  python3 tools/make-package.py --svg-only # the pages, no PDF

`docs/package.json` says what is in it and what goes in the title block.
`tools/sheetframe.py` draws the frame. Everything on a content sheet is
derived: the parts list from `tools/parts.py`, the wiring list from
`tools/netlist.py`, the build sequence from `tools/bringup.py`. The only
authored text in the package is the intro paragraphs in the JSON and the
schematics themselves.

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
    p.footer(f'{spec["svg"]}  {p.size}  placed at {scale*100:.0f}%  '
             f'drawn by tools/draw-schematics.py')


def sheet_wiring(p, cfg, spec):
    nl = load("netlist", "netlist.py")
    sheets, _offsheet = nl.collect()
    nodes = sheets[spec["sheet"]]
    nets = nl.nets_of(nodes)
    p.header(cfg["project"], spec["title"])
    x, y, w, h = p.body_box(top_pad=44)
    p.text(x, y + 6, "Every wire on the board, net by net", "tmf-h2")
    p.text(x, y + 26, "Connect everything on a row together. Read back out of the schematic, "
                      "so it cannot disagree with it.", "tmf-body")
    rows = []
    for net, ns in sorted(nets.items(), key=lambda kv: (kv[0] not in nl.RAILS, kv[0])):
        pins = ", ".join(f"{n['ref']}-{n['pin']}" if n["pin"] is not None else f"{n['ref']} {n['pinname']}"
                         for n in ns)
        rows.append([net, str(len(ns)), pins])
    p.table((x, y + 40, w, h - 46), ["net", "ends", "join these"], rows,
            widths=[0.14, 0.07, 0.79], mono=(0, 2))


def sheet_parts(p, cfg, spec):
    pt = load("parts", "parts.py")
    found = pt.collect()
    p.header(cfg["project"], spec["title"])
    x, y, w, h = p.body_box(top_pad=44)
    p.text(x, y + 6, "Everything that has to be in a drawer", "tmf-h2")
    p.text(x, y + 26, "Parts from every sheet, deduplicated. The status column is the only "
                      "authored thing in this package's tables.", "tmf-body")
    seen, rows = set(), []
    for name, _fn, _b in pt.SHEETS:
        for _kind, ref, part, _extra in found[name]:
            key = part.split("  ")[0].strip()
            if key in seen:
                continue
            seen.add(key)
            st, note = pt.status_for(key)
            rows.append([key, st, note])
    p.table((x, y + 40, w, h - 46), ["part", "status", "note"], rows,
            widths=[0.28, 0.12, 0.60], mono=(0,))


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


KINDS = {"cover": sheet_cover, "schematic": sheet_schematic, "wiring": sheet_wiring,
         "parts": sheet_parts, "steps": sheet_steps}


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--svg-only", action="store_true")
    ap.add_argument("--config", default=str(ROOT / "docs" / "package.json"))
    a = ap.parse_args()
    cfg = json.loads(Path(a.config).read_text())
    OUT.mkdir(parents=True, exist_ok=True)
    for f in OUT.glob("*.svg"):
        f.unlink()
    # A build sequence is as long as it is. Render, and if a steps sheet
    # ran out of paper, put another one after it and render the whole
    # package again, so the "sheet n of m" printed on every page is
    # still true. The loop is bounded by the item count, not by hope.
    specs = [dict(s) for s in cfg["sheets"]]
    files = []
    for _ in range(24):
        files = render(cfg, specs, OUT)
        grown = False
        for i, spec in enumerate(specs):
            if not spec.get("_left"):
                continue
            nxt = spec.get("from", 0) + spec["_drawn_here"]
            after = specs[i + 1] if i + 1 < len(specs) else None
            # A sheet that overflows keeps overflowing on every pass:
            # what decides whether to add paper is whether the sheet
            # that carries on from here is already there.
            if after and after["kind"] == "steps" and after.get("from") == nxt:
                continue
            specs.insert(i + 1, {**{k: v for k, v in spec.items() if not k.startswith("_")},
                                 "from": nxt})
            grown = True
            break
        if not grown:
            break
    else:
        raise AssertionError("a steps sheet keeps overflowing: it fits nothing on a page")
    for f in OUT.glob("*.svg"):
        if str(f) not in files:
            f.unlink()
    for i, spec in enumerate(specs, 1):
        print(f"  sheet {i}/{len(specs)}  {spec['title']}")
    if a.svg_only:
        return 0
    pdf = OUT / f"{cfg['project']}-{cfg['docno']}-rev{cfg['rev']}.pdf"
    r = subprocess.run(["rsvg-convert", "-f", "pdf", "-o", str(pdf), *files],
                       capture_output=True, text=True)
    if r.returncode != 0 or not pdf.exists():
        print(f"rsvg-convert failed: {r.stderr.strip()[:300]}")
        return 1
    print(f"\n{pdf.relative_to(ROOT)}  {pdf.stat().st_size//1024} KB, {len(files)} pages")
    return 0


if __name__ == "__main__":
    sys.exit(main())
