#!/usr/bin/env python3
"""The calibration cartridge's reader: one tool for every eye
(calibration-plan.md, C1). Every frame of the cartridge names itself in
a strip of blocks; this reads the strip off whatever picture it is
given, by the manifest's rectangles, and scores the screen's regions
against the model's own picture of the same screen and variant through
the same decode.

  python3 tools/cal.py model    roms/cal.nes [--frames 40]
        the model's frame offset: how many frames from power-on the
        console runs before the strip's counter reads c (so a record
        whose strip says c is the model at frame c + offset)
  python3 tools/cal.py grab     roms/cal.nes captures/pi/.../x_screen.jpg [...]
        grabber frames: find the console's pixel grid in the 720 x 480
        picture from the strip's own structure, read the strip, refuse a
        frame that does not read, and score every flat region of the
        screen against the model (luma, hue, saturation on the grid)
  python3 tools/cal.py scope    roms/cal.nes record.u8 <rate_hz>
        a scope record: decode it (ntsc-crt's recover-real --nes), read
        the strip off the decoded picture, run the model to the same
        frame, and score the regions through nes-console's capture-score
        at that frame (the N6 path and tolerances)
  python3 tools/cal.py selftest roms/cal.nes
        the tool on synthetic input: the model's decoded pictures read by
        the same reader that will read the part's, and the same pictures
        re-sampled to the grabber's geometry with an unknown offset and
        JPEG-compressed, found and read again. MUTATE=1 reads half a
        block off and must go red.

The manifest (`cal.json` beside the ROM) is the only source of where
anything is: a rectangle typed here would drift from the cartridge. The
grabber's sample geometry and the colour figures are `eyes.py`'s, loaded
from it, for the same reason. Siblings: `../nes` (built with --release:
run-rom, cal-screens, capture-score) and `../ntsc-crt` (recover-real).
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
CAPS = ROOT / "captures"
sys.path.insert(0, str(ROOT / "tools"))
from loadmod import load  # noqa: E402

eyes = load(ROOT / "tools" / "eyes.py", "eyes")
GRAB_W, GRAB_H, NES_W, NES_H, STEP = eyes.GRAB_W, eyes.GRAB_H, eyes.NES_W, eyes.NES_H, eyes.GRAB_SAMPLES_PER_NES_PX


# ------------------------------------------------------------ manifest
def manifest_for(rom: Path) -> dict:
    m = rom.with_suffix(".json")
    if not m.exists():
        sys.exit(f"{m} is not beside the ROM: export-testrom writes it (cargo run --release -p nes-console --example export-testrom -- {rom} cal)")
    return json.loads(m.read_text())


# --------------------------------------------------------------- strip
class Unreadable(Exception):
    pass


def block_lumas(grid, strip, dx=0.0, dy=0):
    """The mean luma of every block's middle 8 x 8 dots on the 256 x 240
    grid; dx, dy shift the sampling (the mutation, and the alignment
    search)."""
    L = eyes.luma(grid)
    b = strip["block"]
    out = np.zeros((strip["rows"], strip["cols"]))
    for r in range(strip["rows"]):
        for c in range(strip["cols"]):
            x0 = int(round(strip["x0"] + c * b + b // 4 + dx))
            y0 = strip["y0"] + r * b + b // 4 + dy
            if y0 < 0 or y0 + b // 2 > NES_H or x0 < 0 or x0 + b // 2 > NES_W:
                out[r, c] = np.nan
            else:
                out[r, c] = L[y0:y0 + b // 2, x0:x0 + b // 2].mean()
    return out


def sync_refs(strip):
    """(row, col, bit) for every block whose value the manifest fixes."""
    refs = []
    for f in strip["fields"]:
        if "value" in f:
            for i in range(f["bits"]):
                refs.append((f["row"], f["col"] + i, (f["value"] >> (f["bits"] - 1 - i)) & 1))
    return refs


def read_strip(grid, strip, dx=0.0, dy=0):
    """The strip's fields off a picture on the console grid. The
    threshold is the middle of the fixed blocks' own white and black,
    so a dim or a bright picture reads alike; a block nearer the
    threshold than a third of the swing, or a fixed block that reads
    wrong, or a parity that fails, is a refusal."""
    lum = block_lumas(grid, strip, dx, dy)
    if np.isnan(lum).any():
        raise Unreadable("the strip runs off the picture")
    refs = sync_refs(strip)
    whites = [lum[r, c] for r, c, bit in refs if bit]
    blacks = [lum[r, c] for r, c, bit in refs if not bit]
    w, k = float(np.mean(whites)), float(np.mean(blacks))
    swing = w - k
    if swing < 20:
        raise Unreadable(f"no strip: the fixed blocks' white and black are {w:.0f} and {k:.0f}")
    thr = (w + k) / 2
    bits = lum > thr
    margin = np.abs(lum - thr).min() / swing
    if margin < 1 / 3:
        r, c = np.unravel_index(np.argmin(np.abs(lum - thr)), lum.shape)
        raise Unreadable(f"block ({r},{c}) reads {lum[r, c]:.0f} against a threshold of {thr:.0f} (swing {swing:.0f}): not a clean bit")
    for r, c, bit in refs:
        if bool(bits[r, c]) != bool(bit):
            raise Unreadable(f"fixed block ({r},{c}) reads {int(bits[r, c])}, the manifest says {bit}")
    v = {}
    for f in strip["fields"]:
        x = 0
        for i in range(f["bits"]):
            x = x << 1 | int(bits[f["row"], f["col"] + i])
        v[f["name"]] = x
    frame = v["frame_15_12"] << 12 | v["frame_11_8"] << 8 | v["frame_7_0"]
    p = v["screen"] ^ v["variant"] ^ v["hold"] ^ (frame & 0xff) ^ (frame >> 8) ^ v["pad"]
    p ^= p >> 4
    p ^= p >> 2
    p ^= p >> 1
    if (p & 1) != v["parity"]:
        raise Unreadable(f"parity: the strip says {v['parity']}, the fields fold to {p & 1}")
    return {"screen": v["screen"], "variant": v["variant"], "hold": bool(v["hold"]), "frame": frame, "pad": v["pad"],
            "white": round(w, 1), "black": round(k, 1), "margin": round(float(margin), 3), "bits": bits.astype(int).tolist()}


# ---------------------------------------------------------- pictures
def grid_from_decoded(ppm: Path):
    """ntsc-crt's decoded picture (2048 x 240, eight samples a dot) on
    the console grid."""
    img = np.asarray(Image.open(ppm).convert("RGB")).astype(np.float64)
    return img.reshape(NES_H, NES_W, img.shape[1] // NES_W, 3).mean(axis=2)


def grabber_rows(path: Path):
    """A grabber frame as 240 rows of 720 samples: the 480 lines are the
    240 picture lines doubled, so pairs are averaged."""
    img = np.asarray(Image.open(path).convert("RGB")).astype(np.float64)
    if img.shape[:2] != (GRAB_H, GRAB_W):
        raise Unreadable(f"{path.name} is {img.shape[1]}x{img.shape[0]}, not the grabber's {GRAB_W}x{GRAB_H}")
    return img.reshape(NES_H, 2, GRAB_W, 3).mean(axis=1)


def resample(rows, x0):
    """eyes.py's resample_columns, vectorised: 256 columns from x0 at the
    grabber's step, each the mean of the samples it covers (the same
    floor and ceil bounds; selftest holds the two equal)."""
    cs = np.concatenate([np.zeros((rows.shape[0], 1, 3)), np.cumsum(rows, axis=1)], axis=1)
    i = np.arange(NES_W)
    ia = np.clip(np.floor(x0 + i * STEP).astype(int), 0, rows.shape[1])
    ib = np.clip(np.ceil(x0 + (i + 1) * STEP).astype(int), 0, rows.shape[1])
    n = np.maximum(ib - ia, 1)
    return (cs[:, ib] - cs[:, ia]) / n[None, :, None]


def template_fit(grid, strip, bits):
    """How well the strip band of the picture matches the ideal strip
    drawn from the bits it read: the correlation of luma with a picture
    of white and black blocks at the manifest's places. The decoder's
    filters smear every edge over a few dots and the comb over three
    rows, so a step's energy ties across offsets; the correlation peaks
    at the smear's centre, which is where the grid is."""
    L = eyes.luma(grid)
    b, x0, y0 = strip["block"], strip["x0"], strip["y0"]
    band = L[y0:y0 + strip["rows"] * b, x0:x0 + strip["cols"] * b]
    ideal = np.kron(np.asarray(bits, dtype=float), np.ones((b, b)))
    return eyes.corr(band, ideal)


def find_grid(rows, strip):
    """Where the console's 256 dots start in the grabber's line (x0, in
    samples) and how its rows sit (dy). First every offset at which a
    strip reads at all, coarse over the whole line; the strip they agree
    on is the frame's; then, among the offsets that read that strip, the
    one whose strip band best matches the ideal strip drawn from those
    bits, to a quarter sample. Refuses if no offset reads."""
    reads = []
    for dy in range(-10, 11):
        for x0 in np.arange(0.0, GRAB_W - NES_W * STEP + 0.01, 2.0):
            g = np.roll(resample(rows, x0), -dy, axis=0)
            try:
                s = read_strip(g, strip)
            except Unreadable:
                continue
            reads.append((x0, dy, (s["screen"], s["variant"], s["frame"], s["pad"])))
    if not reads:
        raise Unreadable("no offset of the grabber's line and rows reads a strip")
    keys = [k for _, _, k in reads]
    key = max(set(keys), key=keys.count)
    plateau = [(x0, dy) for x0, dy, k in reads if k == key]
    xs = [x for x, _ in plateau]
    dys = [d for _, d in plateau]
    best = None
    for dy in range(min(dys), max(dys) + 1):
        for x0 in np.arange(min(xs) - 2.0, max(xs) + 2.01, 0.25):
            g = np.roll(resample(rows, x0), -dy, axis=0)
            try:
                s = read_strip(g, strip)
            except Unreadable:
                continue
            if (s["screen"], s["variant"], s["frame"], s["pad"]) != key:
                continue
            e = template_fit(g, strip, s["bits"])
            if best is None or e > best[0]:
                best = (e, x0, dy, s["margin"])
    _, x0, dy, margin = best
    grid = np.roll(resample(rows, x0), -dy, axis=0)
    return grid, {"x0_samples": round(float(x0), 2), "dy_rows": int(dy), "margin": round(float(margin), 3),
                  "fit": round(float(best[0]), 4), "offsets_that_read": len(plateau)}


# --------------------------------------------------------------- model
NES = (ROOT.parent / "nes").resolve()


def nes_example(name):
    p = NES / "target" / "release" / "examples" / name
    if not p.exists():
        sys.exit(f"{p} is not built: cargo build --release -p nes-console --examples (in {NES})")
    return p


def model_screens(rom: Path, variant: int) -> Path:
    """The model's eight screens at `variant` (palette and bars; the
    others have one), decoded, cached under captures/cal-model/."""
    out = CAPS / "cal-model" / f"v{variant}"
    if not (out / "cal-7-geometry.ppm").exists():
        out.mkdir(parents=True, exist_ok=True)
        r = subprocess.run([str(nes_example("cal-screens")), str(out)], env={**os.environ, "VARIANT": str(variant)}, capture_output=True, text=True, cwd=NES)
        if r.returncode != 0:
            sys.exit(f"cal-screens failed:\n{r.stdout}{r.stderr}")
        (out / "strips.txt").write_text(r.stdout)
    return out


def model_grid(rom: Path, manifest: dict, screen: int, variant: int):
    d = model_screens(rom, variant if screen in (1, 2) else 0)
    name = manifest["screens"][screen]["name"]
    return grid_from_decoded(d / f"cal-{screen}-{name}.ppm")


def model_offset(rom: Path, manifest: dict, frames: int):
    """Frames from power-on to the frame whose strip reads c, minus c."""
    out = CAPS / "cal-model" / f"offset-{frames}.ppm"
    out.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run([str(nes_example("run-rom")), str(rom), str(frames), str(out.with_suffix(".pal.ppm"))],
                       env={**os.environ, "DECODED": str(out)}, capture_output=True, text=True, cwd=NES)
    if r.returncode != 0:
        sys.exit(f"run-rom failed:\n{r.stdout}{r.stderr}")
    s = read_strip(grid_from_decoded(out), manifest["strip"])
    return frames - 1 - s["frame"], s


# --------------------------------------------------------------- score
def region_figures(grid, r, inset=8):
    """Luma (0..1 of the picture's white), saturation and hue of a flat
    region's interior, the grabber's or the model's, on the grid. The
    inset keeps the decoder's settling out of the mean."""
    x0, y0, x1, y1 = r["x"] + inset, r["y"] + inset, r["x"] + r["w"] - inset, r["y"] + r["h"] - inset
    if x1 <= x0 or y1 <= y0:
        return None
    patch = grid[y0:y1, x0:x1]
    mean = patch.reshape(-1, 3).mean(axis=0)
    h, s = eyes.hue_sat(mean[None, None, :])
    return {"Y": float(eyes.luma(mean[None, None, :])[0, 0]) / 255.0, "sat": float(s[0, 0]), "hue": float(h[0, 0]),
            "rgb": [round(float(v), 1) for v in mean], "std": float(eyes.luma(patch).std())}


def score_regions(manifest, strip_read, grid, model):
    """Every flat region of the screen the strip names, on both grids."""
    sc = manifest["screens"][strip_read["screen"]]
    rows = []
    for r in sc["regions"]:
        if "entries" not in r:
            continue
        entry = r["entries"][strip_read["variant"]]
        a, b = region_figures(model, r), region_figures(grid, r)
        if a is None or b is None:
            continue
        dhue = (b["hue"] - a["hue"] + 180) % 360 - 180 if a["sat"] > 0.08 and b["sat"] > 0.08 else None
        rows.append({"region": r["name"], "entry": entry, "model": a, "picture": b,
                     "dY": round(b["Y"] - a["Y"], 4), "dsat": round(b["sat"] - a["sat"], 4), "dhue": None if dhue is None else round(dhue, 1)})
    return rows


def print_scores(rows):
    print(f"{'region':<9} {'entry':<6} | {'Y mod':<7} {'sat mod':<8} {'hue mod':<8} | {'Y pic':<7} {'sat pic':<8} {'hue pic':<8} | {'dY':<8} {'dsat':<8} dhue")
    for r in rows:
        a, b = r["model"], r["picture"]
        e = "back" if r["entry"] is None else f"${r['entry']:02x}"
        hm = f"{a['hue']:+.1f}" if a["sat"] > 0.08 else "grey"
        hp = f"{b['hue']:+.1f}" if b["sat"] > 0.08 else "grey"
        dh = "" if r["dhue"] is None else f"{r['dhue']:+.1f}"
        print(f"{r['region']:<9} {e:<6} | {a['Y']:<7.3f} {a['sat']:<8.3f} {hm:<8} | {b['Y']:<7.3f} {b['sat']:<8.3f} {hp:<8} | {r['dY']:<+8.4f} {r['dsat']:<+8.4f} {dh}")


def save_grid_png(grid, strip, path: Path, scale=3):
    im = Image.fromarray(np.clip(grid, 0, 255).astype(np.uint8)).resize((NES_W * scale, NES_H * scale), Image.NEAREST)
    d = ImageDraw.Draw(im)
    b = strip["block"]
    for r in range(strip["rows"]):
        for c in range(strip["cols"]):
            x, y = (strip["x0"] + c * b) * scale, (strip["y0"] + r * b) * scale
            d.rectangle([x, y, x + b * scale - 1, y + b * scale - 1], outline=(255, 0, 128))
    im.save(path)


# ----------------------------------------------------------- commands
def cmd_model(a):
    rom = Path(a.rom).resolve()
    m = manifest_for(rom)
    offset, s = model_offset(rom, m, a.frames)
    print(f"model: after {a.frames} frames from power-on the last frame's strip reads screen {s['screen']} variant {s['variant']} frame {s['frame']} pad {s['pad']:02x}")
    print(f"model: offset {offset}: a strip that reads c is the model's frame {'c + ' if offset >= 0 else 'c - '}{abs(offset)} (frames from power-on, counting from 0)")
    return 0


def cmd_grab(a):
    rom = Path(a.rom).resolve()
    m = manifest_for(rom)
    bad = 0
    for f in a.frames:
        f = Path(f)
        try:
            rows = grabber_rows(f)
            grid, geo = find_grid(rows, m["strip"])
            s = read_strip(grid, m["strip"], dx=8 if os.environ.get("MUTATE") else 0)
        except Unreadable as e:
            print(f"{f.name}: REFUSED: {e}")
            bad += 1
            continue
        name = m["screens"][s["screen"]]["name"]
        print(f"{f.name}: grid at x0 {geo['x0_samples']} samples, dy {geo['dy_rows']} rows, margin {geo['margin']}; strip: screen {s['screen']} ({name}) variant {s['variant']} frame {s['frame']} pad {s['pad']:02x} hold {int(s['hold'])}; white {s['white']} black {s['black']}")
        save_grid_png(grid, m["strip"], CAPS / f"{f.stem}-cal-grid.png")
        model = model_grid(rom, m, s["screen"], s["variant"])
        rows_ = score_regions(m, s, grid, model)
        if rows_:
            print_scores(rows_)
        (CAPS / f"{f.stem}-cal.json").write_text(json.dumps({"frame": str(f), "grid": geo, "strip": {k: v for k, v in s.items() if k != "bits"}, "regions": rows_}, indent=1))
    return 1 if bad else 0


def cmd_scope(a):
    rom = Path(a.rom).resolve()
    m = manifest_for(rom)
    crt = (ROOT.parent / "ntsc-crt").resolve()
    r = subprocess.run(["cargo", "run", "--release", "-q", "-p", "ntsc-source-cap", "--example", "recover-real", "--", str(Path(a.record).resolve()), "u8", str(a.rate), "--nes"],
                       cwd=crt, capture_output=True, text=True)
    print(r.stdout.strip())
    if r.returncode != 0:
        sys.exit(f"recover-real failed:\n{r.stderr[-1200:]}")
    dec = crt / "goldens" / "real-capture.ppm"
    img = np.asarray(Image.open(dec).convert("RGB")).astype(np.float64)
    if img.shape[0] != NES_H:
        sys.exit(f"the decoded picture is {img.shape[1]}x{img.shape[0]}; expected {NES_H} rows")
    grid = img.reshape(NES_H, NES_W, img.shape[1] // NES_W, 3).mean(axis=2) if img.shape[1] % NES_W == 0 else img
    try:
        s = read_strip(grid, m["strip"])
    except Unreadable as e:
        sys.exit(f"REFUSED: the decoded record's strip does not read: {e}")
    print(f"record: strip reads screen {s['screen']} variant {s['variant']} frame {s['frame']} pad {s['pad']:02x}")
    offset, _ = model_offset(rom, m, a.offset_frames)
    frames = s["frame"] + offset + 1
    print(f"model: frame offset {offset}; running capture-score to {frames} frames so its last frame is the record's")
    cs = subprocess.run([str(nes_example("capture-score")), str(rom), str(frames), str(Path(a.record).resolve()), str(a.rate)], capture_output=True, text=True, cwd=NES)
    print(cs.stdout)
    return cs.returncode


def synth_grabber(grid, x0, dy, path: Path, quality=90):
    """The console grid as the grabber would deliver it: 256 dots spread
    over 643.6 of 720 samples from x0, rows shifted by dy and doubled,
    JPEG-compressed."""
    rows = np.zeros((NES_H, GRAB_W, 3))
    xs = np.arange(GRAB_W)
    src = (xs - x0) / STEP
    inside = (src >= 0) & (src < NES_W)
    idx = np.clip(np.floor(src).astype(int), 0, NES_W - 1)
    shifted = np.roll(grid, dy, axis=0)
    rows[:, inside] = shifted[:, idx[inside]]
    rows[:, ~inside] = 16.0
    img = np.repeat(rows, 2, axis=0)
    Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).save(path, quality=quality)


def cmd_selftest(a):
    rom = Path(a.rom).resolve()
    m = manifest_for(rom)
    strip = m["strip"]
    mutate = bool(os.environ.get("MUTATE"))
    dx = 8 if mutate else 0
    if mutate:
        print("MUTATE=1: the reader samples half a block to the right of the manifest's blocks")
    fails = 0
    # 0. the vectorised resampler is eyes.py's, sample for sample
    probe = np.random.default_rng(1).random((4, GRAB_W, 3)) * 255
    for x0 in (0.0, 17.25, 60.5):
        if not np.allclose(resample(probe, x0), eyes.resample_columns(probe, x0, STEP, NES_W)):
            print(f"  resample at x0 {x0} differs from eyes.resample_columns")
            fails += 1
    # 1. the model's decoded pictures, read by this reader, against what cal-screens read off the frame itself
    d = model_screens(rom, 0)
    said = {}
    for line in (d / "strips.txt").read_text().splitlines():
        if ": screen " in line:
            path, rest = line.split(": ", 1)
            w = rest.split()
            said[Path(path).name] = {"screen": int(w[1]), "variant": int(w[3]), "frame": int(w[7]), "pad": int(w[9], 16)}
    for name, want in sorted(said.items()):
        try:
            got = read_strip(grid_from_decoded(d / name), strip, dx=dx)
        except Unreadable as e:
            print(f"  {name}: REFUSED: {e}")
            fails += 1
            continue
        ok = all(got[k] == want[k] for k in want)
        fails += not ok
        print(f"  {name}: {'ok ' if ok else 'BAD'} screen {got['screen']} variant {got['variant']} frame {got['frame']} pad {got['pad']:02x} (margin {got['margin']})")
    # 2. the same pictures as grabber frames with an offset this tool is not told.
    # The decoded picture's own strip sits a little off the manifest (the
    # comb filter delays the picture by a line): measured here on the
    # picture itself, and the finder is expected to follow the picture.
    g0 = grid_from_decoded(d / "cal-0-strip.ppm")
    bits0 = read_strip(g0, strip)["bits"]
    shift = max(range(-3, 4), key=lambda k: template_fit(np.roll(g0, -k, axis=0), strip, bits0))
    print(f"  the decoded picture's strip sits {shift:+d} row(s) from the manifest (the decode path's line delay); the finder follows the picture")
    synth = CAPS / "cal-model" / "synth"
    synth.mkdir(parents=True, exist_ok=True)
    for i, (name, want) in enumerate(sorted(said.items())):
        x0, dy = 30.0 + 3.7 * i, (i % 5) - 2
        out = synth / (Path(name).stem + ".jpg")
        synth_grabber(grid_from_decoded(d / name), x0, dy, out)
        try:
            rows = grabber_rows(out)
            grid, geo = find_grid(rows, strip)
            got = read_strip(grid, strip, dx=dx)
        except Unreadable as e:
            print(f"  {out.name}: REFUSED: {e}")
            fails += 1
            continue
        ok = all(got[k] == want[k] for k in want) and abs(geo["x0_samples"] - x0) <= 1.0 and geo["dy_rows"] == dy + shift
        fails += not ok
        print(f"  {out.name}: {'ok ' if ok else 'BAD'} found x0 {geo['x0_samples']} (made {x0}), dy {geo['dy_rows']} (made {dy}{shift:+d}); strip screen {got['screen']} frame {got['frame']}; fit {geo['fit']}")
        if ok and want["screen"] == 1:
            rows_ = score_regions(m, got, grid, grid_from_decoded(d / name))
            worst = max((abs(r["dY"]) for r in rows_), default=0)
            print(f"    palette regions through the synthetic grabber: {len(rows_)} scored, worst dY {worst:.4f}")
    print("selftest:", "FAIL" if fails else "PASS", f"({fails} failures)")
    return 1 if fails else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("model"); p.add_argument("rom"); p.add_argument("--frames", type=int, default=40); p.set_defaults(fn=cmd_model)
    p = sub.add_parser("grab"); p.add_argument("rom"); p.add_argument("frames", nargs="+"); p.set_defaults(fn=cmd_grab)
    p = sub.add_parser("scope"); p.add_argument("rom"); p.add_argument("record"); p.add_argument("rate", type=float); p.add_argument("--offset-frames", type=int, default=40); p.set_defaults(fn=cmd_scope)
    p = sub.add_parser("selftest"); p.add_argument("rom"); p.set_defaults(fn=cmd_selftest)
    a = ap.parse_args()
    sys.exit(a.fn(a))


if __name__ == "__main__":
    main()
