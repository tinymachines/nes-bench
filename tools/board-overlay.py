#!/usr/bin/env python3
"""The wiring drawn on the photograph: every chip pin's landing on the
breadboard ringed and named with its net, coloured by the build's state,
over the eye's frame of the board, and every check called out by number
with the sheet's note set below the photograph.

  python3 tools/board-overlay.py [frame.jpg] [--out docs/lab/board-junctions-v1b.png]
                                 [--status docs/build-status-v1b.json] [--map docs/board-map.json]
  python3 tools/board-overlay.py --read captures/frame.jpg    # the map off a fresh rig frame,
                                                              # the views re-aimed; then draw

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
right. A map may name a `frame_rotate` (degrees, PIL's sense) applied
to the frame before anything else: the rig's camera is turned 90
degrees so the whole board fits one frame, and the map is read in the
frame turned back. Only the chips are placed on the map so far; the console lead,
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
PINK = (215, 20, 20)  # the check colour: red, heavy, seen at arm's length
PLAN = (20, 140, 40)  # a placement asked for and not built yet: green
PALETTE = [(122, 63, 191), (15, 143, 158), (181, 101, 29), (141, 31, 94), (63, 111, 42), (91, 91, 214), (194, 24, 91),
           (0, 121, 107), (230, 81, 0), (69, 39, 160), (46, 125, 50), (109, 76, 65), (2, 119, 189), (173, 20, 87),
           (85, 139, 47), (239, 108, 0), (40, 83, 147), (0, 131, 143), (158, 157, 36), (216, 67, 21), (21, 101, 192)]
RAIL_COLOUR = {"+5V": (208, 43, 43), "GND": (27, 100, 200)}


class Board:
    """Hole positions in the frame for one breadboard of the map."""

    def __init__(self, m):
        a = np.array(m["column_y"]["anchors"], dtype=float)
        self.anchors = a[np.argsort(-a[:, 0])]
        self.poly = np.polyfit(a[:, 0], a[:, 1], 2)
        self.rows = m["rows"]
        self.rail = m["rail_x"]
        self.crop = m["crop"]

    def y(self, col):
        # With anchors at every fifth column the map interpolates between
        # them (the lens shrinks the pitch toward the frame's edge in a way a
        # quadratic through three anchors cannot follow); a sparse map keeps
        # the quadratic.
        if len(self.anchors) >= 6:
            cols, ys = self.anchors[::-1, 0], self.anchors[::-1, 1]
            if col > cols[-1]:
                # past the last anchor (a wire hid the holes the walk
                # needed): carry the last pitch on
                return float(ys[-1] + (col - cols[-1]) * (ys[-1] - ys[-2]) / (cols[-1] - cols[-2]))
            return float(np.interp(col, cols, ys))
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


def part_hole(board, part, pin):
    """A single-row part's pin: the column counted from the pin-1 end
    along one side, and the outermost hole of that column's strip."""
    if "holes" in part:
        # a part whose pins sit on named holes (a capacitor across a chip's
        # end, a resistor between two strips): [[column, side, row], ...]
        col, side, i = part["holes"][pin - 1]
        y = board.y(col)
        return col, side, (board.x(side, i, y), y)
    lo, hi = part["columns"]
    col = hi - (pin - 1) if part.get("pin1", "hi") == "hi" else lo + (pin - 1)
    side = part["side"]
    y = board.y(col)
    # `row`: which hole of the strip the part sits in, 0 next to the other
    # board to 4 next to the rails; a part not saying sits in the outermost
    i = part.get("row", 0 if side == "middle" else 4)
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


def find_holes(L):
    """Every hole centre in a frame: normalised correlation with a dark
    7x7 square in a 15x15 patch of board, local maxima above 0.5."""
    from scipy.signal import fftconvolve
    from scipy.ndimage import maximum_filter
    t = np.full((15, 15), 1.0)
    t[4:11, 4:11] = -1.0
    t -= t.mean()
    t /= np.linalg.norm(t)
    num = fftconvolve(L, t[::-1, ::-1], mode="same")
    ones = np.ones_like(t)
    m = fftconvolve(L, ones, mode="same") / t.size
    m2 = fftconvolve(L * L, ones, mode="same")
    sd = np.sqrt(np.maximum(m2 - t.size * m * m, 1e-6))
    ncc = num / sd
    pk = (ncc == maximum_filter(ncc, size=9)) & (ncc > 0.5)
    ys, xs = np.nonzero(pk)
    return xs, ys


def even_rows(v, lo, hi, n, pitches=np.arange(22.5, 25.5, 0.05)):
    """n evenly spaced rows fitted to a set of coordinates: the origin
    and pitch that put the most holes within 3 px of a row."""
    best = None
    for p in pitches:
        for y0 in np.arange(lo, hi, 0.5):
            rows = y0 + p * np.arange(n)
            c = sum(int((abs(v - r) <= 3).sum()) for r in rows)
            if best is None or c > best[0]:
                best = (c, y0, p)
    c, y0, p = best
    return [int(round(y0 + p * i)) for i in range(n)], p, c


def read_board(m, name, xs, ys, L):
    """One board's rows, rail pair and columns off the hole cloud, inside
    the camera-y band the map names for it (`band`). The rail pair is
    looked for beyond both five-row groups and the one with more holes
    wins; the group next to it is the rails side (rows a to e)."""
    b = m["boards"][name]
    lo_y, hi_y = b.get("band", [0, 1080])
    sel = (xs > 40) & (xs < 1600) & (ys > lo_y) & (ys < hi_y)
    Y = ys[sel]
    g1, p1, c1 = even_rows(Y, lo_y + 5, hi_y - 100, 5)
    cands = []
    if g1[-1] + 95 < hi_y:
        cands.append(even_rows(Y, g1[-1] + 45, g1[-1] + 95, 5))
    top = g1[0] - 45 - 4 * p1
    if top - 50 > lo_y:
        cands.append(even_rows(Y, max(lo_y + 2, top - 50), top, 5))
    g2, p2, c2 = max(cands, key=lambda g: g[2])
    (ga, pa, ca), (gb, pb, cb) = sorted([(g1, p1, c1), (g2, p2, c2)], key=lambda g: g[0][0])
    rails = []
    if ga[0] - 30 > lo_y + 2:
        rails.append((even_rows(Y, max(lo_y + 2, ga[0] - 160), ga[0] - 30, 2), "above"))
    if gb[-1] + 30 < hi_y - 2:
        rails.append((even_rows(Y, gb[-1] + 30, min(hi_y - 2, gb[-1] + 160), 2), "below"))
    (rl, pr, cr), where = max(rails, key=lambda r: r[0][2])
    if where == "above":
        ae, fj, outer, inner = ga, gb, rl[0], rl[1]
    else:
        ae, fj, outer, inner = gb, ga, rl[1], rl[0]
    print(f"  {name}: rows a-e {ae} ({ca if ae is ga else cb} holes), f-j {fj} ({cb if ae is ga else ca} holes), rails {where} at {rl} ({cr} holes)")
    band = (ys > min(ae[0], fj[0]) - 15) & (ys < max(ae[-1], fj[-1]) + 15) & sel
    h = np.convolve(np.bincount(xs[band], minlength=2000).astype(float), np.ones(5), "same")
    px = np.array([i for i in range(40, 1600) if h[i] >= 4 and h[i] == h[i - 14:i + 15].max()], float)
    # the pitch to start the walk with is the peaks' own commonest spacing
    # (24 px at the first rig height, 31 on a zoom-250 frame at the second)
    gaps = np.diff(np.sort(px))
    gaps = gaps[(gaps > 8) & (gaps < 60)]
    pitch = float(np.median(gaps)) if len(gaps) else 24.4
    # column 1 is the rightmost peak that has the next column beside it:
    # a stray peak past the board's end (the rail strip, a wire's edge)
    # must not be numbered 1
    starts = [x for x in sorted(px, reverse=True) if np.any(abs(px - (x - pitch)) < 6)]
    x, col, pos = (starts[0] if starts else px.max()), 1, {}
    pos[1] = x
    missed = 0
    while col < 70 and x > 50 and missed < 5:
        exp = x - pitch
        near = px[abs(px - exp) < 5]
        if len(near):
            nx = near[np.argmin(abs(near - exp))]
            pitch = 0.7 * pitch + 0.3 * (x - nx)
            missed = 0
        else:
            nx = exp
            missed += 1
        col += 1
        x = nx
        pos[col] = x
    # the walk ends at the last column a hole was seen in, not the run of
    # interpolated ones past the board's edge or under a cable
    while missed:
        del pos[max(pos)]
        missed -= 1
    last = max(pos)
    anchors = [[c, int(round(pos[c]))] for c in sorted({1, 5, *range(10, last + 1, 5), last}, reverse=True) if c in pos]
    print(f"  {name}: columns 1 at x {pos[1]:.0f} to {last} at {pos[last]:.0f}; pitch {pos[1] - pos[2]:.1f} px at column 1")
    b["column_y"]["anchors"] = anchors
    # Row order is by distance from the rail pair, farthest first, so
    # index 4 of the rails side is the hole next to the rails and index 0
    # of the middle side is the hole next to the other board on either
    # board, whichever way up it lies.
    rail_x = 1080 - inner
    mid = sorted((1080 - y for y in fj), key=lambda x: -abs(x - rail_x))
    rails_x = sorted((1080 - y for y in ae), key=lambda x: -abs(x - rail_x))
    yt, yb = anchors[0][1], anchors[-1][1]
    letters = {s: b.get("rows", {}).get(s, {}).get("letters", "") for s in ("middle", "rails")}
    b["rows"] = {"middle": {"y_top": yt, "x_top": mid, "y_bottom": yb, "x_bottom": mid, "letters": letters["middle"]},
                 "rails": {"y_top": yt, "x_top": rails_x, "y_bottom": yb, "x_bottom": rails_x, "letters": letters["rails"]}}
    # the inner rail row (next to the board's blue line) is GND, the outer +5V
    b["rail_x"] = {"GND": {"y_top": yt, "x_top": 1080 - inner, "y_bottom": yb, "x_bottom": 1080 - inner},
                   "+5V": {"y_top": yt, "x_top": 1080 - outer, "y_bottom": yb, "x_bottom": 1080 - outer}}
    xs_all = mid + rails_x + [1080 - inner, 1080 - outer]
    b["crop"] = [min(xs_all) - 30, yt - 30, max(xs_all) + 30, yb + 40]
    return f"{name}: rows a-e {ae}, f-j {fj}, rails {where} at {rl}, columns 1 to {last} ({pos[1] - pos[2]:.1f} px a column at 1)"


def unzoom(m, b, zoomed):
    """A map read off a zoomed frame, put into zoom-100 coordinates: the
    crop of zoom Z is centred at (960 + pan/36000*960*(1-100/Z),
    540 - tilt/36000*540*(1-100/Z)) and Z/100 wide (docs/eye-views.json).
    The map's own frame is the camera's turned by frame_rotate, so the
    turn is undone, the zoom taken out, and the turn put back."""
    Z, pan, tilt = zoomed
    f = 1 - 100 / Z
    cx, cy = 960 + pan / 36000 * 960 * f, 540 - tilt / 36000 * 540 * f
    s = Z / 100

    def fix(mx, my):
        # map -> camera (zoomed) -> camera (zoom 100) -> map
        camx, camy = my, 1080 - mx
        camx, camy = cx + (camx - 960) / s, cy + (camy - 540) / s
        return 1080 - camy, camx

    b["column_y"]["anchors"] = [[c, int(round(fix(0, y)[1]))] for c, y in b["column_y"]["anchors"]]
    for side in b["rows"].values():
        side["x_top"] = [int(round(fix(x, 0)[0])) for x in side["x_top"]]
        side["x_bottom"] = list(side["x_top"])
        side["y_top"], side["y_bottom"] = b["column_y"]["anchors"][0][1], b["column_y"]["anchors"][-1][1]
    for r in b["rail_x"].values():
        r["x_top"] = r["x_bottom"] = int(round(fix(r["x_top"], 0)[0]))
        r["y_top"], r["y_bottom"] = b["column_y"]["anchors"][0][1], b["column_y"]["anchors"][-1][1]
    x0, y0, x1, y1 = b["crop"]
    (X0, Y0), (X1, Y1) = fix(x0, y0), fix(x1, y1)
    b["crop"] = [int(min(X0, X1)), int(min(Y0, Y1)), int(max(X0, X1)), int(max(Y0, Y1))]


def read_map(m, frame: Path, out: Path, views: Path, zoomed=None):
    """The map read off a frame of the rig (the camera straight down and
    turned, `frame_rotate` set): every hole found, the ten hole rows and
    the two rail rows fitted as even progressions, the columns walked
    leftward from the board's last hole (column 1) with an adaptive
    pitch. The old map stays as the prior for one thing only: the bands
    the rows are looked for in. The named views' aims are carried through
    the similarity between the old map and the new one."""
    img = Image.open(frame).convert("L")
    L = np.asarray(img, dtype=float)
    xs, ys = find_holes(L)
    b = m["boards"]["right"]
    old = Board(b)
    reads = [read_board(m, name, xs, ys, L) for name in m["boards"]]
    if zoomed:
        # The raised camera puts about 10 px on a hole at zoom 100, under
        # what the hole finder resolves; the map is read off a zoomed frame
        # (the board's band given in that frame) and put into zoom-100
        # coordinates, which is what every view and overlay uses.
        for name in m["boards"]:
            unzoom(m, m["boards"][name], zoomed)
    new = Board(b)
    stamp = __import__("time").strftime("%Y-%m-%d %H:%M %Z")
    m["frame"] = f"{frame} (read {stamp} by board-overlay.py --read)"
    m["_about"].append(f"READ {stamp} off {frame.name} by --read: {len(xs)} hole centres by template correlation; per board, in the camera-y band it names, the two five-row groups and the rail pair as even progressions and the columns walked from the board's last hole with an adaptive pitch, anchors every fifth column. " + "; ".join(reads) + ".")
    out.write_text(json.dumps(m, indent=1) + "\n")
    print(f"wrote {out}")
    reaim_views(old, new, views, stamp, f"by board-overlay.py --read off {frame.name}")


def reaim_views(old, new, views: Path, stamp, how):
    """Carry the named views' aims through the similarity between the old
    map and the new one (camera frame coordinates): a view that looked at
    a hole keeps looking at that hole after the camera or the board
    moved. Returns (scale, degrees, shift, worst residual)."""
    A, B = [], []
    for col in range(1, 36):
        for side in ("middle", "rails"):
            for i in (0, 4):
                y = old.y(col); A.append((y, 1080 - old.x(side, i, y)))
                y = new.y(col); B.append((y, 1080 - new.x(side, i, y)))
    A, B = np.array(A), np.array(B)
    ma, mb = A.mean(0), B.mean(0)
    Ac, Bc = A - ma, B - mb
    U, D, Vt = np.linalg.svd(Ac.T @ Bc / len(A))
    R = (U @ Vt).T
    if np.linalg.det(R) < 0:
        Vt[-1] *= -1
        R = (U @ Vt).T
    s = D.sum() / (Ac ** 2).sum() * len(A)
    t = mb - s * R @ ma
    res = np.abs(B - (s * (R @ A.T).T + t)).max()
    v = json.loads(views.read_text())
    q = lambda x: max(-36000, min(36000, int(round(x / 3600)) * 3600))
    for w in v["views"].values():
        ax, ay = s * R @ np.array(w["at"], float) + t
        w["at"] = [int(round(ax)), int(round(ay))]
        f = 1 - 100 / w["zoom"]
        w["pan"], w["tilt"] = q((ax - 960) / (960 * f) * 36000), q((540 - ay) / (540 * f) * 36000)
    deg = np.degrees(np.arctan2(R[1, 0], R[0, 0]))
    v["_about"].append(f"RE-AIMED {stamp} {how}: scale {s:.3f}, {deg:.1f} degrees, shift {t.round(0).tolist()}, worst residual {res:.0f} px.")
    views.write_text(json.dumps(v, indent=1) + "\n")
    print(f"re-aimed {len(v['views'])} views (scale {s:.3f}, shift {t.round(0).tolist()}, worst residual {res:.0f} px)")
    return s, deg, t, res


def read_boards(m, out: Path, views: Path, frames=None, bands=None, write=True, aims=None, only=None):
    """Each board read off its own zoomed frame, the one the map names in
    `zoomed_frame` (frame, zoom_pan_tilt, band) or the one given in
    `frames`, in the band it sits in there, and put into zoom-100
    coordinates. This is the read the locked rig uses: at 11 px a hole
    the zoom-100 frame is under what the hole finder resolves, and one
    zoom-250 frame holds one board. Returns the per-board summaries; with
    write=False nothing is written and the map in memory is the read."""
    old = Board(m["boards"]["right"])
    reads = []
    for name, b in m["boards"].items():
        if only and name not in only:
            continue
        z = dict(b["zoomed_frame"])
        if frames and name in frames:
            z["frame"] = frames[name]
        if bands and name in bands:
            z["band"] = list(bands[name])
        if aims and name in aims:
            z["zoom_pan_tilt"] = list(aims[name])
        L = np.asarray(Image.open(ROOT / z["frame"] if not Path(z["frame"]).is_absolute() else z["frame"]).convert("L"), dtype=float)
        xs, ys = find_holes(L)
        band100 = b.get("band")
        b["band"] = z["band"]
        reads.append(read_board(m, name, xs, ys, L))
        unzoom(m, b, z["zoom_pan_tilt"])
        b["band"] = band100
        b["zoomed_frame"] = z
    if not write:
        return reads
    new = Board(m["boards"]["right"])
    stamp = __import__("time").strftime("%Y-%m-%d %H:%M %Z")
    m["frame"] = f"per board off zoomed frames (read {stamp} by board-overlay.py --read-boards)"
    m["_about"].append(f"READ {stamp} by --read-boards, each board off its zoomed frame (" + "; ".join(
        f"{n}: {b['zoomed_frame']['frame']} at zoom,pan,tilt {b['zoomed_frame']['zoom_pan_tilt']}, band {b['zoomed_frame']['band']}" for n, b in m["boards"].items())
        + ") and put into zoom-100 coordinates. " + "; ".join(reads) + ".")
    out.write_text(json.dumps(m, indent=1) + "\n")
    print(f"wrote {out}")
    reaim_views(old, new, views, stamp, "by board-overlay.py --read-boards")
    return reads


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--read", action="store_true", help="read the map afresh off FRAME (the rig: straight down, frame_rotate set), re-aim the views, and stop")
    ap.add_argument("--views", default=str(ROOT / "docs" / "eye-views.json"))
    ap.add_argument("--read-boards", action="store_true", help="read each board off its own zoomed frame (the map's zoomed_frame: frame, zoom_pan_tilt, band), re-aim the views, and stop")
    ap.add_argument("--frames", metavar="BOARD=PATH,...", help="--read-boards: fresh zoomed frames per board, taken at the map's aims")
    ap.add_argument("--bands", metavar="BOARD=LO,HI,...", help="--read-boards: the band (frame y) a board sits in, as BOARD=LO:HI, when it changed")
    ap.add_argument("--aims", metavar="BOARD=Z:PAN:TILT,...", help="--read-boards: the zoom, pan and tilt the board's fresh frame was taken at, when it changed")
    ap.add_argument("--zoomed", metavar="Z,PAN,TILT", help="--read off a zoomed frame taken at this zoom, pan and tilt (the bands in that frame); the map comes out in zoom-100 coordinates")
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
    if a.read_boards:
        frames = dict(kv.split("=", 1) for kv in a.frames.split(",")) if a.frames else None
        bands = {kv.split("=")[0]: [int(x) for x in kv.split("=")[1].split(":")] for kv in a.bands.split(",")} if a.bands else None
        aims = {kv.split("=")[0]: [int(x) for x in kv.split("=")[1].split(":")] for kv in a.aims.split(",")} if a.aims else None
        read_boards(m, Path(a.map), Path(a.views), frames, bands, aims=aims)
        return
    if a.read:
        read_map(m, Path(a.frame), Path(a.map), Path(a.views), zoomed=[int(v) for v in a.zoomed.split(",")] if a.zoomed else None)
        return
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

    img = Image.open(a.frame).convert("RGB")
    if m.get("frame_rotate"):
        # The rig's camera is turned so the columns run along the frame's
        # long side; the map is read in the frame turned back, so the
        # conventions below (columns along y) hold for both mounts.
        img = img.rotate(m["frame_rotate"], expand=True)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", 19)
        small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 15)
        title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 26)
    except OSError:
        font = small = title = ImageFont.load_default()
    W = int(1080 * a.scale)
    # The callouts: every pin the sheet marks as a check gets a number,
    # one number per distinct note (a note that names two pins is one
    # callout on both), and the notes are set below the photograph in
    # that order, so the picture reads like the right-angle sheet.
    notes, callout = [], {}
    on_map = {f"{ref}.{p}" for ref, chip in m["chips"].items() for p in range(1, chip["pins"] + 1)}
    on_map |= {f"{ref}.{p}" for ref, part in m.get("parts", {}).items() for p in range(1, part["pins"] + 1)}
    checks = [(k, v) for k, v in status["pins"].items() if v.get("state") in ("check", "plan")]
    # the pins the picture rings first, so the badges count up from 1 on
    # the board; a check on a pin the map does not place (the UNO, the
    # console lead) is listed after them with a hollow badge
    for key, v in sorted(checks, key=lambda kv: kv[0] not in on_map):
        text = v.get("note", "")
        if text not in notes:
            notes.append(text)
        callout[key] = notes.index(text) + 1
    hollow = {n for n in range(1, len(notes) + 1) if not any(k in on_map for k, m_ in callout.items() if m_ == n)}
    plans = {n for k, n in callout.items() if status["pins"][k].get("state") == "plan"}
    try:
        note_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 19)
        badge_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
    except OSError:
        note_font = badge_font = ImageFont.load_default()

    def wrap(text, width):
        probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
        lines, line = [], ""
        for word in text.split():
            trial = (line + " " + word).strip()
            if probe.textlength(trial, font=note_font) > width and line:
                lines.append(line)
                line = word
            else:
                line = trial
        if line:
            lines.append(line)
        return lines

    def note_panel(W):
        note_lines = []
        for i, text in enumerate(notes, 1):
            pins_of = ", ".join(k.replace(".", "-") for k, n in callout.items() if n == i)
            note_lines.append((i, wrap(f"{pins_of}: {text}", W - 90)))
        return note_lines, (40 + sum(27 * len(ls) + 14 for _, ls in note_lines) if note_lines else 0)
    boards = {n: Board(b) for n, b in m["boards"].items() if b.get("rows")}
    placed = 0
    areas = {}
    panels = []

    def state_of(ref, pin):
        v = status["pins"].get(f"{ref}.{pin}")
        return v["state"] if v else None

    # One canvas per board, its label bands its own, stacked below the
    # title in the order the boards lie in the frame (the map's x).
    order = sorted(boards, key=lambda n: boards[n].crop[0])
    for board_name in order:
        board = boards[board_name]
        zf = m["boards"][board_name].get("zoomed_frame")
        if zf:
            # The board read off a zoomed frame is drawn on that frame: at
            # the raised camera the zoom-100 frame puts 11 px on a hole, the
            # zoom-250 frame 28. Every map coordinate is carried into the
            # zoomed frame by the inverse of `unzoom`.
            Z, pan, tilt = zf["zoom_pan_tilt"]
            f_ = 1 - 100 / Z
            zcx, zcy = 960 + pan / 36000 * 960 * f_, 540 - tilt / 36000 * 540 * f_
            zs = Z / 100

            def tf(mx, my, zcx=zcx, zcy=zcy, zs=zs):
                camx, camy = my, 1080 - mx
                camx, camy = 960 + (camx - zcx) * zs, 540 + (camy - zcy) * zs
                return 1080 - camy, camx
            bimg = Image.open(ROOT / zf["frame"]).convert("RGB")
            if m.get("frame_rotate"):
                bimg = bimg.rotate(m["frame_rotate"], expand=True)
            (ax, ay), (bx_, by_) = tf(*board.crop[:2]), tf(*board.crop[2:])
            x0, y0, x1, y1 = int(min(ax, bx_)), int(min(ay, by_)), int(max(ax, bx_)), int(max(ay, by_))
            S = a.scale / zs
        else:
            tf = lambda mx, my: (mx, my)  # noqa: E731
            bimg = img
            x0, y0, x1, y1 = board.crop
            S = a.scale
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(bimg.width, x1), min(bimg.height, y1)
        crop = bimg.crop((x0, y0, x1, y1))
        W, H = int((y1 - y0) * S), int((x1 - x0) * S)
        top_pad = 110
        canvas = Image.new("RGB", (W, H + top_pad + 110), (250, 248, 240))
        rot = crop.rotate(-90, expand=True).resize((W, H), Image.LANCZOS)
        canvas.paste(rot, (0, top_pad))
        d = ImageDraw.Draw(canvas)

        def to_canvas(px, py):
            px, py = tf(px, py)
            cx, cy = px - x0, py - y0
            return ((y1 - y0 - cy) * S, cx * S + top_pad)

        labels = []
        items = [(ref, c, pin_hole) for ref, c in m["chips"].items() if c["board"] == board_name]
        items += [(ref, c, part_hole) for ref, c in m.get("parts", {}).items() if c["board"] == board_name]
        for ref, c, hole in items:
            pins = {n["pin"]: n for n in nodes if n["ref"] == ref and n["pin"] is not None}
            lo, hi = c["columns"]
            if hole is pin_hole:
                (bx0, by0) = to_canvas(board.x("middle", 4, board.y(hi)) + 8, board.y(hi) - 9)
                (bx1, by1) = to_canvas(board.x("rails", 0, board.y(lo)) - 8, board.y(lo) + 9)
            else:
                side = c["side"]
                i0, i1 = (0, 1) if side == "middle" else (3, 4)
                (bx0, by0) = to_canvas(board.x(side, i0, board.y(hi)) - 8, board.y(hi) - 9)
                (bx1, by1) = to_canvas(board.x(side, i1, board.y(lo)) + 8, board.y(lo) + 9)
            d.rectangle([min(bx0, bx1), min(by0, by1), max(bx0, bx1), max(by0, by1)], outline=(40, 40, 40), width=2)
            d.text(((bx0 + bx1) / 2 - 12, (by0 + by1) / 2 - 9), ref, fill=(255, 255, 255), font=font)
            for pin, n in sorted(pins.items()):
                net = n["net"]
                if net in nl.NC or pin > c["pins"]:
                    continue
                col, side, (px, py) = hole(board, c, pin)
                cx, cy = to_canvas(px, py)
                st = state_of(ref, pin)
                col_ = GREY if st == "done" else PINK if st == "check" else PLAN if st == "plan" else colour.get(net, (60, 60, 60))
                r = 13 if st in ("check", "plan") else 10
                d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=col_, width=5 if st in ("check", "plan") else 3)
                if st == "plan":
                    d.ellipse([cx - r - 6, cy - r - 6, cx + r + 6, cy + r + 6], outline=col_, width=2)
                if net in nl.RAILS:
                    rx, ry = to_canvas(board.rail_x(net, py), py)
                    d.line([cx, cy, rx, ry], fill=col_, width=3)
                    d.ellipse([rx - 6, ry - 6, rx + 6, ry + 6], fill=col_)
                labels.append((cx, cy, f"{pin} {net}", col_, side == "middle"))
                k = callout.get(f"{ref}.{pin}")
                if k:
                    areas.setdefault(k, []).append((cx, cy, side, board_name))
                placed += 1
        for key, v in status["pins"].items():
            k, at = callout.get(key), v.get("at")
            if k and at and key not in on_map and at.get("board", "right") == board_name:
                y = board.y(at["col"])
                if at["side"] == "rail":
                    pts = [(*to_canvas(board.rail_x(r, y), y), "rails", board_name) for r in ("GND", "+5V")]
                else:
                    pts = [(*to_canvas(board.x(at["side"], 0 if at["side"] == "middle" else 4, y), y), at["side"], board_name)]
                areas.setdefault(k, []).extend(pts)
                hollow.discard(k)
        for k, pts in areas.items():
            pts = [p for p in pts if p[3] == board_name]
            if not pts:
                continue
            kc = PLAN if k in plans else PINK
            mx, my = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
            rr = max(((p[0] - mx) ** 2 + (p[1] - my) ** 2) ** 0.5 for p in pts) + 42
            d.ellipse([mx - rr, my - rr, mx + rr, my + rr], outline=kc, width=6)
            up = pts[0][2] == "middle"
            bx, by = mx + rr * 0.7, my - rr * 0.7 if up else my + rr * 0.7
            d.ellipse([bx - 20, by - 20, bx + 20, by + 20], fill=kc)
            w = d.textlength(str(k), font=badge_font)
            d.text((bx - w / 2, by - 13), str(k), fill=(255, 255, 255), font=badge_font)
        for name in ("GND", "+5V"):
            ya, yb = board.y(1), board.y(int(board.anchors[0, 0]))
            xa, xb = to_canvas(board.rail_x(name, ya), ya), to_canvas(board.rail_x(name, yb), yb)
            d.line([xa, xb], fill=RAIL_COLOUR[name], width=2)
            d.text((xa[0] + 6, xa[1] - 8), name, fill=RAIL_COLOUR[name], font=font)
        for above in (True, False):
            side_l = sorted([t_ for t_ in labels if t_[4] == above], key=lambda t_: t_[0])
            for kk, (cx, cy, text, c_, _) in enumerate(side_l):
                w = d.textlength(text, font=font)
                row = kk % 3
                if above:
                    ty = top_pad - 30 - row * 24
                    d.line([cx, cy - 10, cx, ty + 22], fill=c_, width=2)
                else:
                    ty = top_pad + H + 12 + row * 24
                    d.line([cx, cy + 10, cx, ty - 2], fill=c_, width=2)
                d.text((cx - w / 2, ty), text, fill=c_, font=font)
        letters = {s: m["boards"][board_name]["rows"][s].get("letters", "") for s in ("middle", "rails")}
        d.text((12, 6), f"the {board_name} board (rows {letters['middle']} toward the other board, {letters['rails']} toward its rails)", fill=(90, 90, 90), font=small)
        panels.append(canvas)

    W = max(c.width for c in panels)
    H_all = sum(c.height for c in panels)
    note_lines, panel = note_panel(W)  # wrapped to the width the boards came out at
    canvas = Image.new("RGB", (W, H_all + 80 + panel), (250, 248, 240))
    d = ImageDraw.Draw(canvas)
    y = 80
    for c in panels:
        canvas.paste(c, (0, y))
        y += c.height
    d.text((12, 10), f"Bridge v1b on the boards: the eye's frame with every chip and part pin's landing ringed and named. {status['read']}.", fill=(30, 30, 30), font=title)
    d.text((12, 44), "Grey: seen in its hole. Red: needs a check. Green: a placement asked for, not built yet (the note says where). Colour: not built yet. A ring is the outermost hole of the pin's strip; a rail pin points at its rail. "
                     f"Frame {m['frame']}.", fill=(70, 70, 70), font=small)
    top_pad, H = 0, H_all
    if note_lines:
        y = H_all + 80 + 30
        d.line([12, y - 12, W - 12, y - 12], fill=(200, 200, 200), width=2)
        d.text((12, y - 6), "The checks (red) and the placements to make (green), as the as-built sheet notes them; a hollow badge is a pin the map does not place:", fill=(30, 30, 30), font=badge_font)
        y += 26
        for i, ls in note_lines:
            kc = PLAN if i in plans else PINK
            if i in hollow:
                d.ellipse([14, y, 46, y + 32], outline=kc, width=3)
                d.text((30 - d.textlength(str(i), font=badge_font) / 2, y + 4), str(i), fill=kc, font=badge_font)
            else:
                d.ellipse([14, y, 46, y + 32], fill=kc)
                d.text((30 - d.textlength(str(i), font=badge_font) / 2, y + 4), str(i), fill=(255, 255, 255), font=badge_font)
            for line in ls:
                d.text((60, y + 4), line, fill=(40, 40, 40), font=note_font)
                y += 27
            y += 14
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    canvas.save(a.out, optimize=True)
    print(f"wrote {a.out}: {placed} pins over {len(m['chips'])} chips and {len(m.get('parts', {}))} parts on {len(panels)} boards, {len(notes)} callouts, {canvas.width}x{canvas.height}")


if __name__ == "__main__":
    main()
