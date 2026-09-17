#!/usr/bin/env python3
"""B1: a run's triggered capture against the model's frame at the same
poll, through the roundtrip.

  python3 tools/b1-score.py runs/<stamp> rom.nes [capture-name] [--channel 3] [--nes ../nes]

Reads the run's `script.txt` for its `TRIG n` (the latch the capture
was triggered at) and the capture's `.toml` for the sample rate and the
trigger's sample, then runs nes-console's `capture-score` with
SCRIPT=script.txt, LATCH=n and TRIGGER_SAMPLE=i on the ROM: the model
plays the same SET and AT lines to the first frame after latch n, the
record is sliced from the trigger on so the recovery's first full frame
is that frame on the part, and the regions are scored (luma, hue,
saturation per flat region, the N6 tolerances). A capture armed on
several channels (the DS1054Z has no external trigger input, so the
bridge's TRIG rides on CH1 beside the video on CH3) names each as
`chN = "..."` in its `.toml`; the video is `--channel` (3, where the
bench's video probe sits), and a capture that has no such channel is
refused rather than scored on the trigger line, which is what the
first E2 run of 2026-09-18 would have done through the `file =` line. Real captures are
recorded, not held: the exit status is the scorer's own, and the first
region that misses is named in its table.

With no capture in the run (`--synthetic`), the scorer's SYNTH_TRIGGER
path runs instead: the tool's own green run, whose MUTATE_TRIGGER=1
must be red across the bars cartridge's luma-row step.
"""
import argparse
import os
import re
import subprocess
import sys
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("rom")
    ap.add_argument("capture", nargs="?", default=None, help="the capture's name (default: the run's only one)")
    ap.add_argument("--nes", default=str(Path(__file__).resolve().parent.parent.parent / "nes"))
    ap.add_argument("--channel", type=int, default=3, help="the video channel in a multi-channel capture")
    ap.add_argument("--frames", type=int, default=2000, help="a ceiling on the frames the model runs to reach the latch")
    ap.add_argument("--synthetic", action="store_true")
    a = ap.parse_args()
    # Absolute: the scorer runs in the model's checkout, and a run named
    # relative to this one vanished there (the first E2 run, 2026-09-18).
    run = Path(a.run).resolve()
    script = run / "script.txt"
    trig = None
    if script.exists():
        m = re.findall(r"^\s*TRIG\s+(\d+)", script.read_text(), re.M)
        trig = int(m[-1]) if m else None
    env = dict(os.environ)
    if script.exists():
        env["SCRIPT"] = str(script)
    if trig is not None:
        env["LATCH"] = str(trig)
    cmd = ["cargo", "run", "--release", "-p", "nes-console", "--example", "capture-score", "--", a.rom, str(a.frames)]
    if a.synthetic:
        env["SYNTH_TRIGGER"] = "1"
    else:
        tomls = sorted(run.glob("*.toml"))
        if a.capture:
            tomls = [run / f"{a.capture}.toml"]
        if len(tomls) != 1:
            print(f"{run}: {len(tomls)} captures; name one", file=sys.stderr)
            return 2
        meta = tomls[0].read_text()
        rate = float(re.search(r"rate_hz\s*=\s*([0-9.]+)", meta).group(1))
        ts = re.search(r"trigger_sample\s*=\s*(\d+)", meta)
        chans = dict(re.findall(r'^ch(\d+)\s*=\s*"([^"]+)"', meta, re.M))
        if chans:
            if str(a.channel) not in chans:
                print(f"{tomls[0].name}: channels {', '.join(sorted(chans))}; no CH{a.channel} (the video) to score", file=sys.stderr)
                return 2
            u8 = run / chans[str(a.channel)]
        else:
            u8 = run / re.search(r'file\s*=\s*"([^"]+)"', meta).group(1)
        cmd += [str(u8), f"{rate:.1f}"]
        if ts:
            env["TRIGGER_SAMPLE"] = ts.group(1)
        else:
            print("the capture's .toml has no trigger_sample: the recovery takes the record's first frame", file=sys.stderr)
    print("b1-score:", " ".join(f"{k}={env[k]}" for k in ("SCRIPT", "LATCH", "TRIGGER_SAMPLE", "SYNTH_TRIGGER") if k in env), " ".join(cmd[-3:]))
    return subprocess.call(cmd, cwd=a.nes, env=env)


if __name__ == "__main__":
    sys.exit(main())
