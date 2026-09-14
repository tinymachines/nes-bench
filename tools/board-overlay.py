#!/usr/bin/env python3
"""The wiring drawn on the photograph: every chip pin's landing on the
breadboard ringed and named with its net, coloured by the build's state,
over the eye's frame of the board.

  python3 tools/board-overlay.py [frame.jpg] [--out docs/lab/board-junctions-v1b.png]
                                 [--status docs/build-status-v1b.json] [--map docs/board-map.json]

The photograph's hole grid comes from docs/board-map.json, read off one
camera pose under pixel rulers (MEASURED, dated there); the nets come
from the schematic through tools/netlist.py; which pin sits in which
hole comes from the as-built chip placement in the same map; the state
of each pin comes from the build-status file the as-built wiring sheet
is drawn from. So the picture says the same thing as the right-angle
sheet, on the board itself: grey where a wire was seen in its hole,
pink where it needs a check, the net's own colour where it is not built
yet. Nothing here is typed twice: a hole position, a net, a state each
live in one file.

The frame is cropped to the board the map describes and turned so the
columns run left to right as they do on the sheets, pin 1 ends at the
right. Only the chips are placed on the map so far; the console lead,
the UNO strip and the rails' feeds are named on the sheet, not here.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from loadmod import load  # noqa: E402

GREY = (150, 150, 150)
PINK = (212, 0, 111)
PALETTE = [(122, 63, 191), (15, 143, 158), (181, 101, 29), (141, 31, 94), (63, 111, 42), (91, 91, 214), (194, 24, 91),
           (0, 121, 107), (230, 81, 0), (69, 39, 160), (46, 125, 50), (109, 76, 65), (2, 119, 189), (173, 20, 87),
           (85, 139, 47), (239, 108, 0), (40, 83, 147), (0, 131, 143), (158, 157, 36), (216, 67, 21), (21, 101, 192)]
RAIL_COLOUR = {"+5V": (208, 43, 43), "GND": (27, 100, 200)}


class Board:
    """Hole positions in the frame for one breadboard of the map."""

    def __init__(self, m):
        a = np.array(m["column_y"]["anchors"], dtype=float)
        self.poly = np.polyfit(a[:, 0], a[:, 1], 2)
        self.rows = m["rows"]
        self.rail = m["rail_x"]
        self.crop = m["crop"]

    def y(self, col):
        return float(np.polyval(self.poly, col))

    def x(self, side, i, y):
        r = self.rows[side]
        t = (y - r["y_top"]) / (r["y_bottom"] - r["y_top"])
        return r["x_top"][i] + t * (r["x_bottom"][i] - r["x_top"][i])

    def rail_x(self, name, y):
        r = self.rail[name]
        t = (y - r["y_top"]) / (r["y_bottom"] - r["y_top"])
        return r["x_top"] + t * (r["x_bottom"] - r["x_top"])


def pin_hole(board, chip, pin):
    """The column and side of a DIP pin as built, and the outermost hole
    of its strip (where a wire is most likely to land)."""
    lo, hi = chip["columns"]
    n = chip["pins"]
    half = n // 2
    if pin <= half:
        col, side, i = hi - (pin - 1), "middle", 0
    else:
        col, side, i = lo + (pin - half - 1), "rails", 4
    y = board.y(col)
    return col, side, (board.x(side, i, y), y)


def dips(profile, minsep=10, depth=10):
    """Local minima of a luma profile: the holes along a line."""
    from scipy.ndimage import minimum_filter1d, uniform_filter1d
    sm = uniform_filter1d(profile, 41)
    mn = minimum_filter1d(profile, minsep)
    idx = np.where((profile == mn) & (profile < sm - depth))[0]
    out = []
    for i in idx:
        if out and i - out[-1] < minsep // 2:
            continue
        out.append(int(i))
    return out


def snap_progression(found, prior, tol):
    """Five holes of one row as an even progression: each prior snaps to
    the nearest dip, a dip taken twice (a hole hidden under a wire) is
    dropped, and the progression is fitted through what is left, so the
    hidden hole is placed by its neighbours' pitch. Returns the fitted
    positions and the worst residual of a kept reading."""
    prior = np.asarray(prior, dtype=float)
    near = np.array([min(found, key=lambda f: abs(f - x)) for x in prior], dtype=float)
    keep = np.ones(len(prior), bool)
    for i in range(len(prior)):
        dup = [j for j in range(len(prior)) if near[j] == near[i]]
        if len(dup) > 1:
            best = min(dup, key=lambda j: abs(near[j] - prior[j]))
            for j in dup:
                keep[j] = j == best
    keep &= np.abs(near - prior) <= tol
    if keep.sum() < 3:
        raise SystemExit(f"REFUSED: only {keep.sum()} of {len(prior)} holes of a row read within {tol} px of the prior")
    i = np.arange(len(prior))
    a, b = np.polyfit(i[keep], near[keep], 1)
    fit = a * i + b
    return [int(round(v)) for v in fit], float(np.abs(near[keep] - prior[keep]).max()), int(keep.sum())


def recalibrate(m, frame: Path, board_name: str, shift, out: Path, tol=8, columns_from_prior=False):
    """The map re-read for a moved camera: the old map plus a shift is
    the prior. Each hole row's five holes are found as luma dips in a
    band and fitted as an even progression (a hole under a wire is
    interpolated); the column anchors are found where the dips of all
    ten hole rows agree (a wire across the board dents one row's
    profile, a hole dents them all). A reading further than `tol` from
    its prior is dropped; a row with fewer than three kept is refused."""
    L = np.asarray(Image.open(frame).convert("L"), dtype=float)
    b = m["boards"][board_name]
    dx, dy = shift
    worst = 0.0
    for side in ("middle", "rails"):
        r = b["rows"][side]
        for key, ykey in (("x_top", "y_top"), ("x_bottom", "y_bottom")):
            y = r[ykey] + dy
            band = L[y - 30:y + 30, :].mean(axis=0)
            found = dips(band, minsep=12, depth=8)
            fit, w, kept = snap_progression(found, [x + dx for x in r[key]], tol)
            print(f"  {side} {key} at y {y}: {fit} ({kept} of 5 read, worst {w:.0f} px)")
            worst = max(worst, w)
            r[key], r[ykey] = fit, int(y)
    for name, r in b["rail_x"].items():
        for key, ykey in (("x_top", "y_top"), ("x_bottom", "y_bottom")):
            y = r[ykey] + dy
            band = L[y - 30:y + 30, :].mean(axis=0)
            found = dips(band, minsep=8, depth=6)
            near = min(found, key=lambda f: abs(f - (r[key] + dx)))
            if abs(near - (r[key] + dx)) > tol:
                print(f"  rail {name} {key}: no dip within {tol} px, prior kept")
                near = r[key] + dx
            r[key], r[ykey] = int(near), int(y)
    if columns_from_prior:
        # The column anchors moved by the measured shift alone: a wire's
        # edge dents a row's profile at half a pitch and the vote below has
        # numbered those as columns before now; the rulers' anchors plus
        # the shift the chip crop measured are the better reading.
        b["column_y"]["anchors"] = [[col, y + dy] for col, y in b["column_y"]["anchors"]]
        print(f"  columns: the prior anchors shifted by {dy} px, not re-read")
        merged = None
    votes = np.zeros(L.shape[0])
    for side in ("middle", "rails"):
        r = b["rows"][side]
        for i in range(5):
            x = int(round((r["x_top"][i] + r["x_bottom"][i]) / 2))
            prof = L[:, x - 3:x + 4].mean(axis=1)
            # the board sits a little turned in the frame, so one column's
            # holes fall a few pixels apart across the ten rows: a wide window
            for yy in dips(prof, minsep=9, depth=8):
                votes[max(0, yy - 5):yy + 6] += 1
    cols = [yy for yy in range(6, len(votes) - 6) if votes[yy] >= 5 and votes[yy] == votes[yy - 6:yy + 7].max()]
    if merged is None:
        merged = []
        b["crop"] = [b["crop"][0] + dx, b["crop"][1], b["crop"][2] + dx, b["crop"][3]]
        stamp = __import__("time").strftime("%Y-%m-%d %H:%M %Z")
        m["frame"] = f"{frame} (re-read {stamp}, shift {dx},{dy} from the prior; rows re-read, worst {worst:.0f} px; columns shifted)"
        m["_about"].append(f"RE-READ {stamp} off {frame.name}: the previous map shifted by ({dx},{dy}) as the prior; each row's holes found as dips and fitted as an even progression (worst residual {worst:.0f} px); the column anchors shifted by the measured {dy} px, not re-read.")
        out.write_text(json.dumps(m, indent=1) + "\n")
        print(f"wrote {out}: re-read off {frame.name}")
        return
    merged = []
    for yy in cols:
        if merged and yy - merged[-1] < 8:
            continue
        merged.append(yy)
    # Number the voted columns by walking from the prior anchor that
    # agrees best, one column per hole, a gap of about two pitches
    # counting as a missed hole. The anchors become every column found,
    # not the handful the rulers were read at, and a column the prior
    # placed near the frame's edge cannot drag the fit.
    priors = {col: y + dy for col, y in b["column_y"]["anchors"]}
    best_col = min(priors, key=lambda c: min(abs(f - priors[c]) for f in merged))
    start = min(merged, key=lambda f: abs(f - priors[best_col]))
    print(f"  columns: walking from column {best_col} at y {start} ({int(votes[start])} rows agree)")
    numbered = {start: best_col}
    for direction in (1, -1):
        y, col = start, best_col
        pitch = None
        while True:
            nxt = [f for f in merged if (f - y) * direction > 0]
            if not nxt:
                break
            f = min(nxt, key=lambda v: abs(v - y))
            gap = abs(f - y)
            if pitch is None:
                pitch = gap
            steps = max(1, int(round(gap / pitch)))
            if steps > 2:
                break
            col -= direction * steps  # y grows downward as the column number falls
            pitch = gap / steps
            numbered[f] = col
            y = f
    new = sorted(([c, int(y)] for y, c in numbered.items() if c >= 1), reverse=True)
    for col, y in new:
        if col in priors:
            worst = max(worst, abs(y - priors[col]))
    print(f"  columns found: {new[0][0]} to {new[-1][0]} ({len(new)}); against the priors, worst {worst:.0f} px")
    b["column_y"]["anchors"] = new
    b["crop"] = [b["crop"][0] + dx, b["crop"][1], b["crop"][2] + dx, b["crop"][3]]
    stamp = __import__("time").strftime("%Y-%m-%d %H:%M %Z")
    m["frame"] = f"{frame} (re-read {stamp}, shift {dx},{dy} from the prior, worst residual {worst:.0f} px)"
    m["_about"].append(f"RE-READ {stamp} off {frame.name}: the previous map shifted by ({dx},{dy}) as the prior; each row's holes found as dips and fitted as an even progression, the column anchors where the dips of all ten hole rows agree (worst residual {worst:.0f} px).")
    out.write_text(json.dumps(m, indent=1) + "\n")
    print(f"wrote {out}: re-read off {frame.name}, worst residual {worst:.0f} px")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--recalibrate", nargs=2, type=int, metavar=("DX", "DY"), help="re-read the map off FRAME with this shift from the current map as the prior, and stop")
    ap.add_argument("--tolerance", type=int, default=8, help="how far a re-read anchor may land from its shifted prior, in pixels")
    ap.add_argument("--columns-from-prior", action="store_true", help="shift the column anchors by DY instead of re-reading them (the rows are always re-read)")
    ap.add_argument("frame", nargs="?", default=str(ROOT / "captures" / "b0-all.jpg"))
    ap.add_argument("--out", default=str(ROOT / "docs" / "lab" / "board-junctions-v1b.png"))
    ap.add_argument("--status", default=str(ROOT / "docs" / "build-status-v1b.json"))
    ap.add_argument("--map", default=str(ROOT / "docs" / "board-map.json"))
    ap.add_argument("--scale", type=float, default=2.6)
    a = ap.parse_args()
    m = json.loads(Path(a.map).read_text())
    if a.recalibrate:
        recalibrate(m, Path(a.frame), "right", a.recalibrate, Path(a.map), tol=a.tolerance, columns_from_prior=a.columns_from_prior)
        return
    status = json.loads(Path(a.status).read_text())
    nl = load(ROOT / "tools" / "netlist.py", "nl")
    sheets, _ = nl.collect()
    nodes = sheets["bench-v1b"]
    nets = sorted({n["net"] for n in nodes if n["net"] not in nl.NC and n["net"] not in nl.RAILS})
    colour = {net: PALETTE[i % len(PALETTE)] for i, net in enumerate(nets)}
    colour.update(RAIL_COLOUR)

    board_name = "right"
    board = Board(m["boards"][board_name])
    img = Image.open(a.frame).convert("RGB")
    x0, y0, x1, y1 = board.crop
    crop = img.crop((x0, y0, x1, y1))
    # Columns left to right like the sheets: the frame's y runs down as the
    # column number falls, so a rotation of 90 degrees clockwise (PIL's
    # negative angle) puts column 1 at the left and the high columns (pin
    # 1 ends) at the right, the middle-board side on top. The first build
    # rotated the other way and mapped the rings for this one: every ring
    # sat on a mirrored column, which the photograph made obvious at once.
    S = a.scale
    W, H = int((y1 - y0) * S), int((x1 - x0) * S)
    canvas = Image.new("RGB", (W, H + 270), (250, 248, 240))
    rot = crop.rotate(-90, expand=True).resize((W, H), Image.LANCZOS)
    top_pad = 130
    canvas.paste(rot, (0, top_pad))
    d = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", 14)
        small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 13)
        title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
    except OSError:
        font = small = title = ImageFont.load_default()

    def to_canvas(px, py):
        # rotate 90 clockwise about the crop: (x, y) -> (H_crop - y, x) in crop terms
        cx, cy = px - x0, py - y0
        return ((y1 - y0 - cy) * S, cx * S + top_pad)

    def state_of(ref, pin):
        v = status["pins"].get(f"{ref}.{pin}")
        return v["state"] if v else None

    placed = 0
    labels = []  # (x, y, text, colour, above)
    for ref, chip in m["chips"].items():
        if chip["board"] != board_name:
            continue
        pins = {n["pin"]: n for n in nodes if n["ref"] == ref and n["pin"] is not None}
        # the chip body: a faint outline over its columns
        lo, hi = chip["columns"]
        (bx0, by0) = to_canvas(board.x("middle", 4, board.y(hi)) + 8, board.y(hi) - 9)
        (bx1, by1) = to_canvas(board.x("rails", 0, board.y(lo)) - 8, board.y(lo) + 9)
        d.rectangle([min(bx0, bx1), min(by0, by1), max(bx0, bx1), max(by0, by1)], outline=(40, 40, 40), width=2)
        d.text(((bx0 + bx1) / 2 - 12, (by0 + by1) / 2 - 9), ref, fill=(255, 255, 255), font=font)
        for pin, n in sorted(pins.items()):
            net = n["net"]
            if net in nl.NC:
                continue
            col, side, (px, py) = pin_hole(board, chip, pin)
            cx, cy = to_canvas(px, py)
            st = state_of(ref, pin)
            c = GREY if st == "done" else PINK if st == "check" else colour.get(net, (60, 60, 60))
            r = 11 if st == "check" else 9
            d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=c, width=3 if st == "check" else 2)
            # the wire's other end: a rail pin points to its rail
            if net in nl.RAILS:
                rx, ry = to_canvas(board.rail_x(net, py), py)
                d.line([cx, cy, rx, ry], fill=c, width=2)
                d.ellipse([rx - 5, ry - 5, rx + 5, ry + 5], fill=c)
            labels.append((cx, cy, f"{pin} {net}", c, side == "middle"))
            placed += 1
    # rails
    for name in ("GND", "+5V"):
        ya, yb = board.y(1), board.y(35)
        xa, xb = to_canvas(board.rail_x(name, ya), ya), to_canvas(board.rail_x(name, yb), yb)
        d.line([xa, xb], fill=RAIL_COLOUR[name], width=2)
        d.text((xb[0] + 6, xb[1] - 8), name, fill=RAIL_COLOUR[name], font=font)
    # labels: above the board for the middle side, below for the rails
    # side, staggered in two rows so neighbours do not collide
    for above in (True, False):
        side = sorted([t for t in labels if t[4] == above], key=lambda t: t[0])
        for k, (cx, cy, text, c, _) in enumerate(side):
            w = d.textlength(text, font=font)
            row = k % 3
            if above:
                ty = top_pad - 26 - row * 20
                d.line([cx, cy - 9, cx, ty + 16], fill=c, width=1)
            else:
                ty = top_pad + H + 10 + row * 20
                d.line([cx, cy + 9, cx, ty - 2], fill=c, width=1)
            d.text((cx - w / 2, ty), text, fill=c, font=font)
    d.text((12, 8), f"Bridge v1b on the board: the eye's frame with every chip pin's landing ringed and named. {status['read']}.", fill=(30, 30, 30), font=title)
    d.text((12, 36), "Grey: seen in its hole. Pink: needs a check (the as-built sheet's note says what). Colour: not built yet. A ring is the outermost hole of the pin's strip; a rail pin points at its rail. "
                     f"Frame {m['frame']}; the grid read off it under rulers, one camera pose.", fill=(70, 70, 70), font=small)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    canvas.save(a.out, optimize=True)
    print(f"wrote {a.out}: {placed} pins over {len(m['chips'])} chips on the {board_name} board, {W}x{H + 270}")


if __name__ == "__main__":
    main()
