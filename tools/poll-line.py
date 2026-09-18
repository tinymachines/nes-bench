#!/usr/bin/env python3
"""The poll's scanline on the part: a capture with the controller's
latch on one channel and the video on another, every latch pulse
placed against the vertical sync before it, in lines.

  python3 tools/poll-line.py runs/<stamp> [--latch-ch 2] [--video-ch 3] [--vsync-onset 244.821]

For each rising edge on the latch channel: the lines from the start of
the last vertical sync (the first long sync pulse of the serration) to
the edge, and that as a PPU line, the onset placed in the PPU's frame
by --vsync-onset. The default is the switch-level 2C02's: the sync-tip
leg asserted from row 244 dot 280 (2c02's `vsync-probe`, 2026-09-18),
244 + 280/341 lines; this record shows the same shape (the broad pulse
one line after the preceding horizontal sync). Until that measurement
the tool assumed the encoder's line-granular 245.0, which put every
part-side line 0.18 high. The line period is measured off the record's
horizontal sync pulses, not assumed. What the model says for the same
game is where its own latch strobe rose in the PPU's frame
(`POSITIONS=1 pad-log`, the `P` lines: rise line and dot), not a line
derived from a dot count (tools/dissect.py's line_of, which numbers
the pre-render line 0 and drifts a dot per skipped dot; see the
dissection's part-side section). Neither side is told the other's
answer.
"""
import argparse
import re
from pathlib import Path

import numpy as np


def edges_rising(x, thresh, min_gap):
    hi = x > thresh
    r = np.flatnonzero(~hi[:-1] & hi[1:]) + 1
    keep = [int(r[0])] if len(r) else []
    for i in r[1:]:
        if i - keep[-1] >= min_gap:
            keep.append(int(i))
    return keep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--latch-ch", type=int, default=2)
    ap.add_argument("--video-ch", type=int, default=3)
    ap.add_argument("--vsync-onset", type=float, default=244 + 280 / 341, help="where in the PPU's frame the vertical sync begins, in lines (the die's row 244 dot 280)")
    a = ap.parse_args()
    run = Path(a.run)
    toml = next(t for t in run.glob("*.toml") if t.name != "knobs.toml").read_text()
    rate = float(re.search(r"rate_hz\s*=\s*([0-9.]+)", toml).group(1))
    trig = int(re.search(r"trigger_sample\s*=\s*(\d+)", toml).group(1))
    chans = dict(re.findall(r'^ch(\d+)\s*=\s*"([^"]+)"', toml, re.M))
    latch = np.fromfile(run / chans[str(a.latch_ch)], dtype=np.uint8)
    video = np.fromfile(run / chans[str(a.video_ch)], dtype=np.uint8).astype(np.int16)
    us = rate / 1e6
    # The latch: logic, the rise; pulses at least 100 us apart.
    lt = (int(latch.min()) + int(latch.max())) / 2
    rises = edges_rising(latch.astype(np.int16), lt, int(100 * us))
    # The video: sync tip and blanking off the record, sync = below the midpoint.
    tip = float(np.percentile(video, 0.2))
    blank = float(np.percentile(video, 40))
    low = video < (tip + 0.4 * (blank - tip))
    # Runs of low: start and length.
    d = np.diff(low.astype(np.int8))
    starts = np.flatnonzero(d == 1) + 1
    ends = np.flatnonzero(d == -1) + 1
    if low[0]:
        starts = np.r_[0, starts]
    if low[-1]:
        ends = np.r_[ends, len(low)]
    lengths = ends - starts
    hsync = starts[(lengths > 2 * us) & (lengths < 10 * us)]
    long = starts[lengths > 15 * us]
    # Vertical sync start: a long pulse not preceded by another within 100 us.
    vstarts = [int(s) for i, s in enumerate(long) if i == 0 or s - long[i - 1] > 100 * us]
    # The line period off the horizontal syncs (median spacing, half-lines excluded).
    sp = np.diff(hsync)
    sp = sp[(sp > 50 * us) & (sp < 80 * us)]
    line = float(np.median(sp))
    print(f"{run.name}: {len(rises)} latch pulses, {len(vstarts)} vertical syncs, line period {line / us:.3f} us ({line:.1f} samples), sync tip {tip:.0f} blank {blank:.0f} (levels), trigger at {trig}")
    rows = []
    for r in rises:
        prev = [v for v in vstarts if v < r]
        if not prev:
            continue
        v = prev[-1]
        lines = (r - v) / line
        rows.append((r, v, lines))
    from collections import Counter
    c = Counter()
    for r, v, lines in rows:
        ppu = (a.vsync_onset + lines) % 262
        c[int(ppu)] += 1
        print(f"  latch rise at sample {r:>9} ({(r - trig) / rate * 1000:+8.3f} ms from the trigger): {lines:7.3f} lines after the vertical sync = PPU line {ppu:7.3f}")
    frac = sorted(((a.vsync_onset + l) % 262) for _, _, l in rows)
    print(f"  PPU line of the rise, median {frac[len(frac) // 2]:.3f}, spread {frac[-1] - frac[0]:.3f} (the strobe falls 24 dots later)")
    print("  PPU line histogram (the rise; the strobe falls 24 dots later): " + ", ".join(f"{k}: {n}" for k, n in sorted(c.items())))


if __name__ == "__main__":
    main()
