#!/usr/bin/env python3
"""B1: a run's triggered capture against the model's frame at the same
poll, through the roundtrip.

  python3 tools/b1-score.py runs/<stamp> rom.nes [capture-name] [--channel N] [--nes ../nes]

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
first E2 run of 2026-09-18 would have done through the `file =` line.

The run's `knobs.toml` (tools/knobs.py) is written if the run has none
and handed to the scorer as KNOBS= (`--cold` hands it over without its
[warmth] table, so the model runs at the cold part's gain: how
tools/warmth-fit.py reads the drift it fits), so its report opens with the
model's alignment and its source; `--channel` defaults to the file's
`[capture] channel`. Real captures are
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
import knobs  # noqa: E402


def cold_copy(kpath):
    """The knobs file without its [warmth] table, beside the run in the
    system's temporary directory: the model at the cold part's gain."""
    import tempfile
    out, skip = [], False
    for line in kpath.read_text().splitlines():
        if line.strip().startswith("["):
            skip = line.strip() == "[warmth]"
        if not skip:
            out.append(line)
    f = tempfile.NamedTemporaryFile("w", suffix=".toml", prefix="knobs-cold-", delete=False)
    f.write("\n".join(out) + "\n")
    f.close()
    return Path(f.name)


def run_env(run, synthetic, channel, cold=False):
    """The environment a run hands the model's scorers: SCRIPT, LATCH
    (the script's last TRIG), KNOBS (written if the run has none), and
    the video channel resolved from the knobs file when none is named.
    Returns (env, channel)."""
    script = run / "script.txt"
    env = dict(os.environ)
    if script.exists():
        m = re.findall(r"^\s*TRIG\s+(\d+)", script.read_text(), re.M)
        if m:
            env["LATCH"] = m[-1]
        env["SCRIPT"] = str(script)
    if not synthetic:
        kpath = run / "knobs.toml"
        if not kpath.exists():
            print(f"{Path(sys.argv[0]).name}: wrote {knobs.init(run)}")
        env["KNOBS"] = str(cold_copy(kpath) if cold else kpath)
        if channel is None:
            m = re.search(r"^channel\s*=\s*(\d+)", kpath.read_text(), re.M)
            channel = int(m.group(1)) if m else knobs.VIDEO_CHANNEL
    elif channel is None:
        channel = knobs.VIDEO_CHANNEL
    return env, channel


def run_capture(run, capture, channel):
    """The run's one capture (or the named one): the video channel's
    .u8 file, its rate and its trigger's sample (None when the .toml
    has none). Refuses a capture without the video channel, and a run
    with several captures and no name. Raises SystemExit with the
    reason."""
    tomls = sorted(t for t in run.glob("*.toml") if t.name != "knobs.toml")
    if capture:
        tomls = [run / f"{capture}.toml"]
    if len(tomls) != 1:
        raise SystemExit(f"{run}: {len(tomls)} captures; name one")
    meta = tomls[0].read_text()
    rate = float(re.search(r"rate_hz\s*=\s*([0-9.]+)", meta).group(1))
    ts = re.search(r"trigger_sample\s*=\s*(\d+)", meta)
    chans = dict(re.findall(r'^ch(\d+)\s*=\s*"([^"]+)"', meta, re.M))
    if chans:
        if str(channel) not in chans:
            raise SystemExit(f"{tomls[0].name}: channels {', '.join(sorted(chans))}; no CH{channel} (the video) to score")
        u8 = run / chans[str(channel)]
    else:
        u8 = run / re.search(r'file\s*=\s*"([^"]+)"', meta).group(1)
    return u8, rate, (int(ts.group(1)) if ts else None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("rom")
    ap.add_argument("capture", nargs="?", default=None, help="the capture's name (default: the run's only one)")
    ap.add_argument("--nes", default=str(Path(__file__).resolve().parent.parent.parent / "nes"))
    ap.add_argument("--channel", type=int, default=None, help="the video channel in a multi-channel capture (default: the knobs file's)")
    ap.add_argument("--frames", type=int, default=2000, help="a ceiling on the frames the model runs to reach the latch")
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--cold", action="store_true", help="score against the model at the cold part's gain (the knobs file without [warmth])")
    a = ap.parse_args()
    # Absolute: the scorer runs in the model's checkout, and a run named
    # relative to this one vanished there (the first E2 run, 2026-09-18).
    run = Path(a.run).resolve()
    env, a.channel = run_env(run, a.synthetic, a.channel, a.cold)
    cmd = ["cargo", "run", "--release", "-p", "nes-console", "--example", "capture-score", "--", a.rom, str(a.frames)]
    if a.synthetic:
        env["SYNTH_TRIGGER"] = "1"
    else:
        try:
            u8, rate, ts = run_capture(run, a.capture, a.channel)
        except SystemExit as e:
            print(e, file=sys.stderr)
            return 2
        cmd += [str(u8), f"{rate:.1f}"]
        if ts is not None:
            env["TRIGGER_SAMPLE"] = str(ts)
        else:
            print("the capture's .toml has no trigger_sample: the recovery takes the record's first frame", file=sys.stderr)
    print("b1-score:", " ".join(f"{k}={env[k]}" for k in ("SCRIPT", "LATCH", "TRIGGER_SAMPLE", "SYNTH_TRIGGER") if k in env), " ".join(cmd[-3:]))
    return subprocess.call(cmd, cwd=a.nes, env=env)


if __name__ == "__main__":
    sys.exit(main())
