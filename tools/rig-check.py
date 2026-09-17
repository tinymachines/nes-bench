#!/usr/bin/env python3
"""The rig's regression check: run it after every change to the bench.

  python3 tools/rig-check.py                        # the sequence; exit 1 on any FAIL
  python3 tools/rig-check.py --baseline             # accept what the cameras see now as the reference
  python3 tools/rig-check.py --no-side              # the BRIO only

The Pi comes from --pi, or PI in the bench's .env (gitignored).

What it checks, in order, each a PASS or a FAIL with the number that decided it:

  1. light     the BRIO's whole-board frame is lit: its mean level near the
               baseline's and the exposure under the camera's cap (312 at
               1080p, where a dark room pins it: 2026-09-15).
  2. still     the frame differs from the baseline frame by sensor noise
               only: the worst 40 px block of |difference| under 60 (noise
               measures about 20; a moved board or camera 120 to 180).
               A FAIL names the region that moved, in map coordinates.
  3. boards    each board, off a zoom-250 frame taken at the aim the map
               records for it, still reads where the map says: the rows,
               the rail pair and the columns found, and the read's anchors
               within 6 px (half a hole at zoom 100) of the map's. A FAIL
               means the map is stale: `board-overlay.py --read-boards
               --frames ...` on the frames this check just took, then the
               overlay, then this check again with --baseline.
  4. side      each side eye is lit and still aimed where it was: its frame
               correlates with its baseline frame at 0.85 or better.

--baseline takes the same frames and, instead of comparing, keeps them as
captures/rig/baseline-*.jpg and writes their measurements (levels, hole
counts, the boards' read) into docs/rig-baseline.json, dated. Take a
baseline only after the map has been read against the same frames and
the overlay looked at; a baseline of a wrong rig makes every later check
agree with the wrong rig.

The frames go to captures/rig/ (gitignored, like every capture). The
result also goes to captures/rig/last-check.json.
"""
import argparse
import copy
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from loadmod import load  # noqa: E402

CAPS = ROOT / "captures"
RIG = CAPS / "rig"
BASE = ROOT / "docs" / "rig-baseline.json"
MAP = ROOT / "docs" / "board-map.json"

# The side eyes, by their stable names on the Pi (docs/rig.md).
SIDE = {
    "side-9000": ("usb-046d_0990_08DF0A45-video-index0", "1600x1200"),
    "side-communicate": ("usb-046d_09a2_ABAD8310-video-index0", "1280x960"),
}
EXPOSURE_CAP = 312       # the BRIO's longest exposure at 1080p, units of 100 us
BLOCK = 40               # px, the block the frame difference is scored in
MOVED = 60.0             # a block's mean |difference| above this is a move, not noise
ANCHOR_TOL = 6           # px at zoom 100: half a hole
SIDE_NCC = 0.85


def level(path):
    return float(np.asarray(Image.open(path).convert("L"), dtype=float).mean())


def exposure(toml):
    m = re.search(r"exposure_time_absolute = (\d+)", Path(toml).read_text())
    return int(m.group(1)) if m else None


def grab_brio(pi, name, zoom=100, pan=0, tilt=0, settle=30):
    """One BRIO frame through tools/eye.py, into captures/rig/NAME.jpg."""
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "eye.py"), "grab", f"rig/{name}", "--pi", pi,
                        "--preset", "board", "--zoom", str(zoom), "--pan", str(pan), "--tilt", str(tilt),
                        "--settle", str(settle)], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"eye.py grab {name}: {r.stderr.strip()[:300] or r.stdout.strip()[:300]}")
    return RIG / f"{name}.jpg", RIG / f"{name}.toml"


def grab_side(pi, name, byid, size, frames=40):
    """One side-eye frame through ffmpeg on the Pi, after `frames` frames of
    settling (the Communicate blows out white before it settles)."""
    dev = f"/dev/v4l/by-id/{byid}"
    script = (f"rm -f /tmp/{name}-*.jpg; ffmpeg -loglevel error -y -f v4l2 -input_format mjpeg -video_size {size} "
              f"-i {dev} -frames:v {frames} /tmp/{name}-%02d.jpg && cp /tmp/{name}-{frames:02d}.jpg /tmp/{name}.jpg")
    r = subprocess.run(["ssh", "-o", "ConnectTimeout=8", "-o", "BatchMode=yes", pi, script], capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(f"{name}: {r.stderr.strip()[:300]}")
    out = RIG / f"{name}.jpg"
    subprocess.run(["scp", "-q", "-o", "ConnectTimeout=8", f"{pi}:/tmp/{name}.jpg", str(out)], check=True)
    return out


def moved_blocks(a_path, b_path):
    """The worst BLOCK px block of |a - b| and the blocks over MOVED."""
    a = np.asarray(Image.open(a_path).convert("L"), dtype=float)
    b = np.asarray(Image.open(b_path).convert("L"), dtype=float)
    if a.shape != b.shape:
        return None, None, None
    H, W = a.shape
    d = np.abs(a - b)[:H // BLOCK * BLOCK, :W // BLOCK * BLOCK]
    bl = d.reshape(H // BLOCK, BLOCK, W // BLOCK, BLOCK).mean(axis=(1, 3))
    ys, xs = np.nonzero(bl > MOVED)
    region = None
    if len(xs):
        # camera -> map coordinates (frame_rotate -90: map x = 1080 - cam y, map y = cam x)
        cx0, cx1 = xs.min() * BLOCK, xs.max() * BLOCK + BLOCK
        cy0, cy1 = ys.min() * BLOCK, ys.max() * BLOCK + BLOCK
        region = {"map_x": [int(1080 - cy1), int(1080 - cy0)], "map_y": [int(cx0), int(cx1)]}
    return float(bl.max()), int((bl > MOVED).sum()), region


def ncc(a_path, b_path, size=(160, 120)):
    a = np.asarray(Image.open(a_path).convert("L").resize(size), dtype=float).ravel()
    b = np.asarray(Image.open(b_path).convert("L").resize(size), dtype=float).ravel()
    a -= a.mean(); b -= b.mean()
    return float((a @ b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


def anchors_of(b):
    return {c: y for c, y in b["column_y"]["anchors"]}


def compare_board(m_ref, m_new, name):
    """The read's anchors, rows and rails against the map's: the worst
    difference in px at zoom 100, and how many columns the read found."""
    a, b = m_ref["boards"][name], m_new["boards"][name]
    ra, rb = anchors_of(a), anchors_of(b)
    common = sorted(set(ra) & set(rb))
    worst = 0.0
    for c in common:
        worst = max(worst, abs(ra[c] - rb[c]))
    for side in ("middle", "rails"):
        for x, y in zip(a["rows"][side]["x_top"], b["rows"][side]["x_top"]):
            worst = max(worst, abs(x - y))
    for r in ("GND", "+5V"):
        worst = max(worst, abs(a["rail_x"][r]["x_top"] - b["rail_x"][r]["x_top"]))
    return worst, max(rb), len(common)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pi", help="user@host of the Pi the cameras are on; the default is PI in .env")
    ap.add_argument("--baseline", action="store_true", help="keep these frames as the reference instead of comparing")
    ap.add_argument("--no-side", action="store_true", help="skip the side eyes")
    ap.add_argument("--settle", type=int, default=30, help="BRIO frames to stream before keeping one")
    a = ap.parse_args()
    bo = load(ROOT / "tools" / "board-overlay.py", "bo")
    a.pi = a.pi or load(ROOT / "tools" / "bench-check.py", "bench_check").dotenv(ROOT).get("PI")
    if not a.pi:
        sys.exit("no Pi: pass --pi user@host, or put PI= in .env (.env.example is the shape)")
    RIG.mkdir(parents=True, exist_ok=True)
    m = json.loads(MAP.read_text())
    base = json.loads(BASE.read_text()) if BASE.exists() else None
    if not a.baseline and base is None:
        sys.exit("no baseline yet: run with --baseline once the rig is right (docs/rig.md, the routine)")
    rows, result = [], {"at": time.strftime("%Y-%m-%d %H:%M %Z"), "checks": []}

    def check(name, ok, detail):
        rows.append((name, "PASS" if ok else "FAIL", detail))
        result["checks"].append({"check": name, "ok": bool(ok), "detail": detail})

    # 1. light, 2. still
    frame, toml = grab_brio(a.pi, "all", settle=a.settle)
    lv, ex = level(frame), exposure(toml)
    result["all"] = {"level": round(lv, 1), "exposure": ex}
    if a.baseline:
        check("light", lv > 80 and (ex is None or ex < EXPOSURE_CAP), f"level {lv:.0f}, exposure {ex}")
    else:
        ref = base["all"]["level"]
        check("light", abs(lv - ref) < 0.3 * ref and (ex is None or ex < EXPOSURE_CAP),
              f"level {lv:.0f} (baseline {ref:.0f}), exposure {ex} (cap {EXPOSURE_CAP})")
        worst, n, region = moved_blocks(frame, RIG / "baseline-all.jpg")
        if worst is None:
            check("still", False, "baseline frame missing or a different size")
        else:
            check("still", worst < MOVED, f"worst {BLOCK} px block {worst:.0f} (noise about 20, a move 120 and up), {n} blocks over {MOVED:.0f}"
                  + (f", region map x {region['map_x']}, y {region['map_y']}" if region else ""))

    # 3. the boards, each off its own zoomed frame at the map's aim
    frames = {}
    for name, b in m["boards"].items():
        Z, pan, tilt = b["zoomed_frame"]["zoom_pan_tilt"]
        f, t = grab_brio(a.pi, name, Z, pan, tilt, settle=max(a.settle, 30))
        frames[name] = f
        lv2, ex2 = level(f), exposure(t)
        result[name] = {"level": round(lv2, 1), "exposure": ex2, "aim": [Z, pan, tilt]}
        if lv2 < 80 or (ex2 is not None and ex2 >= EXPOSURE_CAP):
            check(f"board {name}", False, f"frame dark: level {lv2:.0f}, exposure {ex2}")
            continue
        trial = copy.deepcopy(m)
        try:
            summary = bo.read_boards(trial, MAP, ROOT / "docs" / "eye-views.json",
                                     frames={name: str(f.relative_to(ROOT))}, write=False, only=[name])
        except Exception as e:  # a board not in its frame leaves nothing to fit
            check(f"board {name}", False, f"read failed: {str(e)[:120]}")
            continue
        worst, last, n = compare_board(m, trial, name)
        result[name]["read"] = {"worst_px": round(worst, 1), "columns": last, "anchors_compared": n}
        if a.baseline:
            check(f"board {name}", worst <= ANCHOR_TOL and last >= 40,
                  f"read against the map: worst {worst:.0f} px over {n} anchors (tolerance {ANCHOR_TOL}), columns 1 to {last}")

    # 4. the side eyes
    if not a.no_side:
        for name, (byid, size) in SIDE.items():
            try:
                f = grab_side(a.pi, name, byid, size)
            except Exception as e:
                check(name, False, f"grab failed: {str(e)[:120]}")
                continue
            lv3 = level(f)
            result[name] = {"level": round(lv3, 1)}
            if a.baseline:
                check(name, lv3 > 40, f"level {lv3:.0f}")
            else:
                ref = RIG / f"baseline-{name}.jpg"
                c = ncc(f, ref) if ref.exists() else None
                result[name]["ncc"] = None if c is None else round(c, 3)
                check(name, c is not None and c >= SIDE_NCC and lv3 > 40,
                      f"level {lv3:.0f}, correlation with the baseline {c:.2f} (floor {SIDE_NCC})" if c is not None else "no baseline frame")

    # the verdict
    w = max(len(r[0]) for r in rows)
    print()
    for name, state, detail in rows:
        print(f"  {name:<{w}}  {state}  {detail}")
    bad = [r for r in rows if r[1] == "FAIL"]
    if a.baseline:
        if bad:
            print(f"\nnot taking a baseline: {len(bad)} check(s) failed on the frames it would be made of")
            (RIG / "last-check.json").write_text(json.dumps(result, indent=1) + "\n")
            return 1
        for name in ["all", *m["boards"], *([] if a.no_side else SIDE)]:
            shutil.copy(RIG / f"{name}.jpg", RIG / f"baseline-{name}.jpg")
        result["frames"] = {name: f"captures/rig/baseline-{name}.jpg" for name in ["all", *m["boards"], *([] if a.no_side else SIDE)]}
        BASE.write_text(json.dumps(result, indent=1) + "\n")
        print(f"\nbaseline taken {result['at']}: frames in captures/rig/baseline-*.jpg, measurements in {BASE.relative_to(ROOT)}")
    else:
        print(f"\n{'no regression' if not bad else str(len(bad)) + ' regression(s)'} against the baseline of {base['at']}")
    (RIG / "last-check.json").write_text(json.dumps(result, indent=1) + "\n")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
