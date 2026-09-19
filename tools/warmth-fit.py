#!/usr/bin/env python3
"""The warmth curve: the part's picture gain against the seconds it has
been on, fitted to a warm-up series (tools/warmup.sh: one capture from
a cold console, then one every few minutes with the power left on).

  python3 tools/warmth-fit.py rom.nes runs/<stamp> runs/<stamp> ...          # fit
  python3 tools/warmth-fit.py rom.nes runs/<stamp> ... --check               # score with the curve in the files

Fit: each run is scored with `b1-score.py --cold` (the model at gain
one), its seconds on read off the head's logs (knobs.py), and every
flat region's captured luma and saturation are fitted together to
v0 * (1 - depth * (1 - exp(-t / tau))), one v0 per series and one
(depth, tau) for all of them, by a grid over tau and depth with the
v0s solved exactly at each point. Prints the curve, its rms and worst
residual, and each series' own best depth, so a curve the series do
not share shows. The constants go into knobs.py by hand.

Check: each run is scored as it stands (its knobs.toml carrying the
warmth, knobs.py warmth adds it), and the table of dY per run is
printed with each region's spread across the series: with the curve
right the spread is the scorer's own noise, without it the drift.

The first series (2026-09-18, 20260918-194516..203018, ten captures
over 45 minutes at 200 mV a division, Super Mario Bros.' title): depth
0.0214, tau 1050 s, rms 0.00098 over forty numbers; luma alone wants
0.024, saturation alone 0.018, both inside the scorer's tolerance of
the shared curve.
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import knobs  # noqa: E402

ROW = re.compile(r"^\$([0-9a-f]{2})\s+(\d)\s+(\d+)\.\.(\d+)\s+(\d+)\.\.(\d+)\s+\|\s*\+?([-\d.]+)\s+([\d.]+)\s+\S+\s*\|\s*\+?([-\d.]+)\s+([\d.]+)\s+\S+\s*\|\s*([-+\d.]+)\s+([-+\d.]+)")


def score(run, rom, cold):
    cmd = [sys.executable, str(HERE / "b1-score.py"), str(run), rom] + (["--cold"] if cold else [])
    out = subprocess.run(cmd, capture_output=True, text=True).stdout
    rows = {}
    for line in out.splitlines():
        m = ROW.match(line)
        if m:
            key = f"${m.group(1)}/{m.group(2)}"
            rows[key] = dict(y_syn=float(m.group(7)), y=float(m.group(9)), sat=float(m.group(10)), dy=float(m.group(11)), dsat=float(m.group(12)))
    if not rows:
        raise SystemExit(f"{run}: the scorer printed no regions\n{out}")
    return rows


def fit(T, series):
    """(rms, tau, depth, worst) over a grid; each series' v0 exact."""
    best = None
    for tau in np.arange(60, 4000, 10):
        w = 1 - np.exp(-T / tau)
        for depth in np.arange(0, 0.08, 0.0002):
            f = 1 - depth * w
            res = np.concatenate([s - (s @ f / (f @ f)) * f for s in series])
            r = float(np.sqrt(np.mean(res ** 2)))
            if best is None or r < best[0]:
                best = (r, float(tau), float(depth), float(np.max(np.abs(res))))
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom")
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    runs = [Path(r) for r in a.runs]
    T = []
    for r in runs:
        s = knobs.seconds_on(r)
        if s is None:
            raise SystemExit(f"{r}: the head's logs do not say how long the console had been on")
        T.append(s)
    T = np.array(T)
    scored = [score(r, a.rom, cold=not a.check) for r in runs]
    keys = sorted(set.intersection(*(set(s) for s in scored)))
    if a.check:
        print(f"{'run':<18} {'s on':>6}  " + "  ".join(f"{k + ' dY':>11}" for k in keys))
        for r, t, s in zip(runs, T, scored):
            print(f"{r.name:<18} {t:>6.0f}  " + "  ".join(f"{s[k]['dy']:>+11.4f}" for k in keys))
        for k in keys:
            d = np.array([s[k]["dy"] for s in scored])
            print(f"{k}: dY spread {d.max() - d.min():.4f} across the series (mean {d.mean():+.4f})")
        return 0
    series = {f"{k} Y": np.array([s[k]["y"] for s in scored]) for k in keys}
    series.update({f"{k} sat": np.array([s[k]["sat"] for s in scored]) for k in keys})
    rms, tau, depth, worst = fit(T, list(series.values()))
    print(f"{len(runs)} captures, {T.min():.0f}..{T.max():.0f} s on, {len(series)} series ({', '.join(series)})")
    print(f"shared curve: depth {depth:.4f}, tau {tau:.0f} s, rms {rms:.5f}, worst {worst:.4f}")
    for name, s in series.items():
        r1, t1, d1, _ = fit(T, [s])
        print(f"  {name} alone: depth {d1:.4f}, tau {t1:.0f} s, rms {r1:.5f}")
    print(f"knobs.py carries depth {knobs.WARMTH_DEPTH}, tau {knobs.WARMTH_TAU_S} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
