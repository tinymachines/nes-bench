#!/usr/bin/env python3
"""The schematic sheets as PNGs, for reading offline on a phone.

  python3 tools/render-png.py [outdir] [--scale N]

The SVGs are the artefact: `tools/draw-schematics.py` writes them, they
are committed, and `tools/check-sheets.py` holds them to the wiring
tables. A PNG is a photograph of one, so it is generated on demand and
never committed: a committed PNG has no check that can tell whether it
still matches the drawing beside it, and PNG output is not reproducible
across renderer versions, so there is no honest way to add one.

Renderers, in the order they are tried, with the reason:

- `rsvg-convert` (librsvg), which is what the SVGs were drawn against.
- `inkscape`, which is thorough and slow.
- headless `chromium`, which is a browser and therefore right by
  definition, but has to be told a window size and screenshots it.

ImageMagick's `convert` is NOT in that list. Without a librsvg delegate
it falls back to its own MSVG renderer, which drops text styling and
produces a plausible-looking sheet with the wrong fonts and missing pin
labels. A bad render of a schematic is worse than no render.
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHEETS = ["bench-v1b-1", "bench-v1b-2", "bench-v2b-1", "bench-v2b-2", "bench-v2b-3", "bench-v2b-4", "bench-v1", "bench-v2", "logical-timing", "pad-adapter", "breadboard-v1b"]


def renderer():
    for name in ("rsvg-convert", "inkscape", "chromium"):
        if shutil.which(name):
            return name
    return None


def render(tool, src, dst, scale):
    if tool == "rsvg-convert":
        cmd = [tool, "-z", str(scale), "-o", str(dst), str(src)]
    elif tool == "inkscape":
        cmd = [tool, f"--export-filename={dst}", f"--export-dpi={96 * scale}", str(src)]
    else:
        cmd = [tool, "--headless", "--no-sandbox", "--disable-gpu",
               f"--screenshot={dst}", "--default-background-color=FFFFFFFF", str(src)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode == 0 and dst.exists(), (r.stderr or r.stdout).strip()[:200]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir", nargs="?", default=str(ROOT / "docs"), help="where to write the PNGs")
    ap.add_argument("--scale", type=float, default=2.0, help="pixels per SVG unit (default 2, for zooming on a phone)")
    a = ap.parse_args()

    tool = renderer()
    if not tool:
        print("no SVG renderer found. Install librsvg2-bin (rsvg-convert), inkscape, or chromium.")
        return 1
    out = Path(a.outdir)
    out.mkdir(parents=True, exist_ok=True)

    bad = 0
    for name in SHEETS:
        src = ROOT / "docs" / f"{name}.svg"
        if not src.exists():
            print(f"missing {src.relative_to(ROOT)}: run python3 tools/draw-schematics.py docs")
            bad += 1
            continue
        dst = out / f"{name}.png"
        ok, err = render(tool, src, dst, a.scale)
        if ok:
            print(f"{dst}  {dst.stat().st_size // 1024} KB")
        else:
            print(f"FAILED {name}: {err}")
            bad += 1
    print(f"{len(SHEETS) - bad} of {len(SHEETS)} sheets rendered with {tool} at {a.scale}x")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
