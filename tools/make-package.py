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
            "sheet": f"{n} of {total}", "source": f"git {git_rev()}", "scale": "NTS"}


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
    rows = [[str(i + 1), s["title"], {"schematic": "schematic", "wiring": "derived from the schematic",
                                      "parts": "derived from the schematic", "steps": "derived from the bring-up tool",
                                      "cover": "this sheet"}[s["kind"]]]
            for i, s in enumerate(cfg["sheets"])]
    p.table((x, cy + 10, w * 0.72, h - (cy - y) - 24), ["sheet", "title", "how it is made"],
            rows, widths=[0.09, 0.55, 0.36], mono=(0,))


def sheet_schematic(p, cfg, spec):
    top = p.header(cfg["project"], spec["title"])
    box = p.full_box(top_pad=46)
    scale = p.place_svg(ROOT / "docs" / spec["svg"], box)
    p.footer(f'{spec["svg"]}  placed at {scale*100:.0f}%  drawn by tools/draw-schematics.py')
    if scale < 0.5:
        print(f"    NOTE {spec['svg']} placed at {scale*100:.0f}%: it may want its own page size or a split")


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


def sheet_steps(p, cfg, spec):
    bu = load("bringup", "bringup.py")
    n = spec["session"]
    match = [s for s in bu.SESSIONS if s[0] == n][0]
    _num, stitle, blurb, ids = match
    p.header(cfg["project"], spec["title"])
    x, y, w, h = p.body_box(top_pad=44)
    p.text(x, y + 6, stitle, "tmf-h2")
    p.text(x, y + 26, blurb, "tmf-body")
    items = []
    for sid in ids:
        st = bu.BY_ID[sid]
        items.append(f"{sid}  {st['title']}")
        items += [f"      {d}" for d in st["do"]]
    p.steps((x, y + 42, w, h - 48), items)
    p.footer("generated from tools/bringup.py, which is also the tool that runs these steps")


KINDS = {"cover": sheet_cover, "schematic": sheet_schematic, "wiring": sheet_wiring,
         "parts": sheet_parts, "steps": sheet_steps}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--svg-only", action="store_true")
    ap.add_argument("--config", default=str(ROOT / "docs" / "package.json"))
    a = ap.parse_args()
    cfg = json.loads(Path(a.config).read_text())
    OUT.mkdir(parents=True, exist_ok=True)
    total = len(cfg["sheets"])
    files = []
    for i, spec in enumerate(cfg["sheets"], 1):
        p = sf.Page(page_meta(cfg, spec["title"], i, total), size=cfg.get("page", "ansi-b"))
        KINDS[spec["kind"]](p, cfg, spec)
        f = OUT / f"{i:02d}-{spec['kind']}.svg"
        p.done(f)
        files.append(str(f))
        print(f"  sheet {i}/{total}  {spec['title']}")
    if a.svg_only:
        return 0
    pdf = OUT / f"{cfg['project']}-{cfg['docno']}-rev{cfg['rev']}.pdf"
    r = subprocess.run(["rsvg-convert", "-f", "pdf", "-o", str(pdf), *files],
                       capture_output=True, text=True)
    if r.returncode != 0 or not pdf.exists():
        print(f"rsvg-convert failed: {r.stderr.strip()[:300]}")
        return 1
    print(f"\n{pdf.relative_to(ROOT)}  {pdf.stat().st_size//1024} KB, {total} pages")
    return 0


if __name__ == "__main__":
    sys.exit(main())
