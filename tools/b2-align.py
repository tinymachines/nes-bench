#!/usr/bin/env python3
"""B2: the console's CPU-to-PPU alignment read off the scope, and the
histogram over power-ons.

  python3 tools/b2-align.py classify runs/<stamp> [--roles 2=m2,4=ale,1=master]
  python3 tools/b2-align.py selftest              # every class synthesised and read back; the mutation red
  python3 tools/b2-align.py sweep <head> script.txt N [--roles ...]   # N runs, a histogram

The console's `Alignment` (nes-console) is a pair of master
half-steps: cpu_phase, where a phi1 begins, 0 to 23 over a CPU cycle,
and ppu_phase, where a dot begins, 0 to 7. What the pins show, measured
on the dies before this was written: the 2A03's M2 falls on the very
half-step its core's clk0 falls, which is a phi1's start
(`v2a03-sim`'s m2-phase: M2 high 15 of 24 half-steps, the part's 62.5
percent duty), and the 2C02's ALE rises on the very half-step pclk0
rises, a dot's start, every other dot while rendering (`v2c02-sim`'s
ale-phase, 2,508 of 2,508 rises). So the offset from an ALE rise to the
next M2 fall, in half-steps, is cpu_phase minus ppu_phase, and its value
mod 8 is the alignment class (a dot is 8 half-steps; the pair (4, 3)
the model runs in is class 1). The value mod 24 is printed too: ALE
rises every 16 half-steps, so over many edges it takes three values
apart by 8, and whether the part prefers one is data.

The ruler is the console's own master clock when a channel carries it
(the half-step is measured as half its mean period over the record);
without one the nominal 21.477272 MHz is used. Edges are threshold
crossings at each channel's own mid-level, interpolated between
samples. A record where the offsets do not agree to within a quarter
half-step is refused as not a clean capture, not classified.

The self-test synthesises the three channels for every class at the
scope's rate with the measured pin offsets, reads each back, and then
shifts the synthesised ALE by one half-step (MUTATE) and requires the
class to move. That is the tool's own gate before the relays exist.
"""
import argparse
import collections
import json
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

MASTER_HZ = 21_477_272.0
HALF_STEP_S = 1.0 / (2 * MASTER_HZ)


def read_u8(path):
    return np.fromfile(path, dtype=np.uint8).astype(np.float32)


def edges(sig, rising):
    """Times (in samples, interpolated) of the threshold crossings."""
    lo, hi = np.percentile(sig, 2), np.percentile(sig, 98)
    if hi - lo < 20:
        raise SystemExit(f"a channel is flat (range {lo:.0f}..{hi:.0f} of 255): is the probe on?")
    thr = (lo + hi) / 2
    above = sig > thr
    if rising:
        idx = np.flatnonzero(~above[:-1] & above[1:])
    else:
        idx = np.flatnonzero(above[:-1] & ~above[1:])
    # Linear interpolation of the crossing between idx and idx+1.
    a, b = sig[idx], sig[idx + 1]
    frac = (thr - a) / np.where(b != a, b - a, 1.0)
    return idx + frac


def classify(m2, ale, rate, master=None):
    """The class and its diagnostics from three records at one rate."""
    if master is not None:
        r = edges(master, True)
        period = (r[-1] - r[0]) / (len(r) - 1) / rate
        half = period / 2
        ruler = f"the master clock channel: {1 / period / 1e6:.6f} MHz over {len(r)} periods"
    else:
        half = HALF_STEP_S
        ruler = "the nominal master clock"
    m2_falls = edges(m2, False) / rate
    ale_rises = edges(ale, True) / rate
    if len(m2_falls) < 50 or len(ale_rises) < 50:
        raise SystemExit(f"too few edges: {len(m2_falls)} M2 falls, {len(ale_rises)} ALE rises")
    # For each M2 fall, the previous ALE rise.
    j = np.searchsorted(ale_rises, m2_falls) - 1
    ok = j >= 0
    off = (m2_falls[ok] - ale_rises[j[ok]]) / half
    # ALE only rises while the PPU fetches: an M2 fall long after the
    # last rise (blanking, or the pre-render idle) is not an offset.
    near = off < 48
    off = off[near]
    if len(off) < 50:
        raise SystemExit("too few M2 falls within three CPU cycles of an ALE rise: is the PPU rendering?")
    q = np.round(off)
    resid = off - q
    spread = float(np.percentile(np.abs(resid), 95))
    if spread > 0.25:
        raise SystemExit(f"the offsets do not sit on half-steps: 95th percentile residual {spread:.2f} half-steps; not a clean capture")
    mod8 = collections.Counter((int(v) % 8) for v in q)
    mod24 = collections.Counter((int(v) % 24) for v in q)
    cls, n = mod8.most_common(1)[0]
    purity = n / len(q)
    if purity < 0.98:
        raise SystemExit(f"the class is not clean: {cls} on {purity:.1%} of {len(q)} M2 falls; mod 8 histogram {dict(sorted(mod8.items()))}")
    return dict(cls=cls, n=len(q), purity=purity, resid95=spread, mod8=dict(sorted(mod8.items())), mod24=dict(sorted(mod24.items())), ruler=ruler, half_step_ns=half * 1e9)


def synthesise(cpu_phase, ppu_phase, rate, seconds=0.004, noise=3.0, ale_shift=0.0, seed=1):
    """Three records as the scope would see them, from the model's
    alignment and the measured pin offsets: M2 low from a phi1's start
    (cpu_phase mod 24) for 9 half-steps then high for 15; ALE rising on
    dot starts (ppu_phase mod 8) every 16 half-steps, high for 4; the
    master clock a square at MASTER_HZ. Levels 5 V logic into the head's
    1 V/div, -2 V offset window, roughly 50..230 of 255, edges one
    sample wide, Gaussian noise on top."""
    rng = np.random.default_rng(seed)
    n = int(seconds * rate)
    t = np.arange(n) / rate
    hs = t / HALF_STEP_S  # time in half-steps
    master = ((np.floor(hs) % 2) == 0).astype(np.float32)
    m2_phase = (hs - cpu_phase) % 24
    m2 = (m2_phase >= 9).astype(np.float32)  # low for the phi1's 9, high 15
    ale_phase = (hs - ppu_phase - ale_shift) % 16
    ale = (ale_phase < 4).astype(np.float32)
    out = []
    for sig in (master, m2, ale):
        v = 50 + 180 * sig + rng.normal(0, noise, n)
        out.append(np.clip(v, 0, 255).astype(np.uint8))
    return out  # master, m2, ale


def selftest(args):
    rate = 250e6
    bad = 0
    print(f"synthesis at {rate / 1e6:.0f} MSa/s, the head's three-channel rate")
    for ppu in (3, 0, 5):
        for cpu in range(24):
            master, m2, ale = synthesise(cpu, ppu, rate)
            r = classify(m2.astype(np.float32), ale.astype(np.float32), rate, master.astype(np.float32))
            want = (cpu - ppu) % 8
            mark = "" if r["cls"] == want else "  WRONG"
            bad += r["cls"] != want
            if cpu < 8 or mark:
                print(f"  cpu_phase {cpu:2d} ppu_phase {ppu}: class {r['cls']} (want {want}), mod 24 {r['mod24']}, residual95 {r['resid95']:.3f}, ruler {r['ruler'].split(':')[0]}{mark}")
    # The mutation: the synthesised ALE one half-step late; the class
    # must move on every alignment, or the classifier is not looking.
    moved = 0
    for cpu in range(24):
        master, m2, ale = synthesise(cpu, 3, rate, ale_shift=1.0)
        r = classify(m2.astype(np.float32), ale.astype(np.float32), rate, master.astype(np.float32))
        moved += r["cls"] == (cpu - 4) % 8
    print(f"{72 - bad} of 72 alignments read back as their class; MUTATE (ALE one half-step late) moved the class on {moved} of 24")
    if bad or moved != 24:
        print("selftest FAILED")
        return 1
    print("selftest passed")
    return 0


def load_run(run, roles):
    run = Path(run)
    tomls = sorted(run.glob("*.toml"))
    if not tomls:
        raise SystemExit(f"{run}: no capture")
    meta = tomls[0].read_text()
    rate = float(re.search(r"rate_hz\s*=\s*([0-9.]+)", meta).group(1))
    files = dict(re.findall(r'ch(\d+)\s*=\s*"([^"]+)"', meta))
    if not files:
        # A single-channel capture: file = "...".
        raise SystemExit(f"{tomls[0]}: no per-channel files (the head's ARM with a channel list writes chN = ...)")
    sig = {}
    for ch, role in roles.items():
        if ch not in files:
            raise SystemExit(f"channel {ch} ({role}) is not in the capture: {sorted(files)}")
        sig[role] = read_u8(run / files[ch])
    return sig, rate


def parse_roles(s):
    roles = {}
    for part in s.split(","):
        ch, role = part.split("=")
        roles[ch.strip()] = role.strip()
    if "m2" not in roles.values() or "ale" not in roles.values():
        raise SystemExit("--roles must name m2 and ale channels")
    return roles


def cmd_classify(args):
    sig, rate = load_run(args.run, parse_roles(args.roles))
    r = classify(sig["m2"], sig["ale"], rate, sig.get("master"))
    print(json.dumps(dict(run=str(args.run), rate=rate, **r)))
    return 0


def ask(host, port, req):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(5)
    s.sendto(json.dumps(req).encode(), (host, port))
    return json.loads(s.recvfrom(65535)[0].decode())


def cmd_sweep(args):
    host, _, port = args.head.partition(":")
    port = int(port) if port else 6530
    script = Path(args.script).read_text()
    hist = collections.Counter()
    results = []
    for i in range(args.n):
        rep = ask(host, port, {"op": "run", "script": script})
        if not rep.get("ok"):
            print(rep)
            return 1
        stamp = rep["stamp"]
        while ask(host, port, {"op": "status"}).get("run"):
            time.sleep(0.5)
        subprocess.check_call([sys.executable, str(Path(__file__).parent / "bench.py"), args.head, "fetch", stamp, "--into", args.into], stdout=subprocess.DEVNULL)
        try:
            sig, rate = load_run(Path(args.into) / stamp, parse_roles(args.roles))
            r = classify(sig["m2"], sig["ale"], rate, sig.get("master"))
            hist[r["cls"]] += 1
            results.append((stamp, r["cls"], r["mod24"]))
            print(f"{i + 1:3d} {stamp}: class {r['cls']} mod 24 {r['mod24']}")
        except SystemExit as e:
            hist["unreadable"] += 1
            print(f"{i + 1:3d} {stamp}: {e}")
    print(f"histogram over {args.n} power-ons: {dict(sorted(hist.items(), key=str))}")
    Path(args.into, "b2-sweep.json").write_text(json.dumps(dict(histogram=dict(hist), runs=results), indent=2, default=str))
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("classify")
    c.add_argument("run")
    c.add_argument("--roles", default="2=m2,4=ale,1=master")
    sub.add_parser("selftest")
    s = sub.add_parser("sweep")
    s.add_argument("head")
    s.add_argument("script")
    s.add_argument("n", type=int)
    s.add_argument("--roles", default="2=m2,4=ale,1=master")
    s.add_argument("--into", default="runs")
    a = ap.parse_args()
    return {"classify": cmd_classify, "selftest": lambda _: selftest(a), "sweep": cmd_sweep}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
