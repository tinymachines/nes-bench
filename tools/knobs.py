#!/usr/bin/env python3
"""The knobs file: one per run, `runs/<stamp>/knobs.toml`, the numbers
the model carries that it could not measure on a die, each with where
it came from (docs/exercise.md, Programme 1).

  python3 tools/knobs.py init runs/<stamp>            # write it from the measured defaults and the run's ARM line
  python3 tools/knobs.py show runs/<stamp>            # print it
  python3 tools/knobs.py check runs/<stamp> [--nes ../nes]   # the model reads it back, or refuses by name
  python3 tools/knobs.py warmth runs/<stamp>          # append [warmth] + [warmth_curve] to a file written before them

`init` refuses to overwrite: a knob that changed is a new line in the
file with its source, not a rewrite. The model's reader
(nes-console/src/knobs.rs) is the one place the schema lives; `check`
runs it, so a file this writer got wrong is refused there, not
explained here. `b1-score.py` writes the file for a run that has none
and hands it to the scorer as KNOBS=.

Tables today: [alignment] (the console's power-on alignment, measured
off the two dies' clock recipes until E4's histogram sets it from the
part), [capture] (the scope's window on the video, from the run's
ARM line: the channel the video sits on, the scale, the offset), and
[warmth] with [warmth_curve]: the seconds the console had been on when
the record was triggered, read off the head's logs (the last `power on`
across every run up to this one, with no `power off` after it), and
the picture-gain curve tools/warmth-fit.py fitted to the warm-up
series. A run whose power the head never switched (the front switch by
hand, before the relay) gets no [warmth]: the seconds are not known,
and the model runs cold.
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

VIDEO_CHANNEL = 3   # docs/wiring.md: the video probe on CH3

# The part's picture gain against the seconds it has been on:
# 1 - DEPTH * (1 - exp(-t / TAU_S)). Fitted by tools/warmth-fit.py to the
# warm-up series of 2026-09-18 (ten captures over 45 minutes from a cold
# console, luma and saturation of two regions sharing one curve); the
# residual is the fit's rms over those forty numbers. Refit, then change
# these four together.
WARMTH_DEPTH = 0.0214
WARMTH_TAU_S = 1050
WARMTH_RESIDUAL = 0.001
WARMTH_BY = "warm-up series 20260918-194516..203018, tools/warmth-fit.py"


def head_events(runs_dir):
    """Every run's head.log power switching, in time order: (unix
    seconds, 'on' | 'off')."""
    ev = []
    for log in sorted(Path(runs_dir).glob("*/head.log")):
        for line in log.read_text(errors="replace").splitlines():
            w = line.split()
            if len(w) >= 3 and w[1] == "power" and w[2] in ("on", "off"):
                ev.append((float(w[0]), w[2]))
    return sorted(ev)


def trigger_time(run):
    """When the run's record was triggered: the head's first line after
    it began waiting for the latch past the trigger (within half a
    second of the trigger itself), else the TRIG line. None without
    either."""
    log = Path(run) / "head.log"
    if not log.exists():
        return None
    lines = log.read_text(errors="replace").splitlines()
    for i, line in enumerate(lines):
        if "wait for latch" in line and i + 1 < len(lines):
            return float(lines[i + 1].split()[0])
    for line in lines:
        if "<- TRIG" in line:
            return float(line.split()[0])
    return None


def seconds_on(run):
    """(seconds, the power-on's run) the console had been on at the
    run's trigger, or None when the head's logs cannot say."""
    run = Path(run)
    t = trigger_time(run)
    if t is None:
        return None
    last = None
    for when, what in head_events(run.parent):
        if when > t:
            break
        last = (when, what)
    if last is None or last[1] != "on":
        return None
    return t - last[0]


def warmth_lines(run):
    s = seconds_on(run)
    if s is None:
        return []
    return ["[warmth]",
            f"seconds_on = {round(s)}",
            'source = "measured"',
            f'by = "{Path(run).name} head.log trigger against the last power on in runs/*/head.log"',
            "",
            "[warmth_curve]",
            f"depth = {WARMTH_DEPTH}",
            f"tau_s = {WARMTH_TAU_S}",
            'source = "fitted"',
            f'by = "{WARMTH_BY}"',
            f"residual = {WARMTH_RESIDUAL}",
            ""]


def capture_from_script(script_text):
    """The last ARM line's channels, scale and offset; the head's own
    defaults where the line leaves them out (head/headd.py)."""
    arm = None
    for line in script_text.splitlines():
        w = line.split("#")[0].split()
        if w and w[0].upper() == "ARM":
            arm = w
    if arm is None:
        return None
    chs = [int(c) for c in (arm[2] if len(arm) > 2 else "3").split(",")]
    scale = float(arm[3]) if len(arm) > 3 else 0.5
    offset = float(arm[4]) if len(arm) > 4 else -1.3
    if VIDEO_CHANNEL in chs:
        ch = VIDEO_CHANNEL
    elif len(chs) == 1:
        ch = chs[0]
    else:
        raise SystemExit(f"the ARM line captures CH{','.join(map(str, chs))} and none is the video's CH{VIDEO_CHANNEL}")
    return ch, scale, offset


def render(run, capture):
    stamp = run.name
    out = [f"# {stamp}: the knobs this run's model side ran with, each with its",
           "# source. Read by nes-console's runners (KNOBS=); a key they do not",
           "# know is refused by name. docs/exercise.md, Programme 1.",
           "",
           "[alignment]",
           "cpu_phase = 4",
           "ppu_phase = 3",
           'source = "measured"',
           'by = "v2a03-sim clk-phase, v2c02-sim clk-phase"   # the dies\' own power-on recipes; E4 sets it from the part',
           ""]
    if capture:
        ch, scale, offset = capture
        out += ["[capture]",
                f"scale_v_per_div = {scale}",
                f"offset_v = {offset}",
                f"channel = {ch}",
                'source = "authored"',
                f'by = "{stamp} script.txt ARM"   # 200 mV/div uses 100 of the scope\'s levels on the video; 500 used 43 (E2)',
                ""]
    out += warmth_lines(run)
    return "\n".join(out)


def init(run, force=False):
    run = Path(run)
    path = run / "knobs.toml"
    if path.exists() and not force:
        raise SystemExit(f"{path} exists: a knob that changed is a new line with its source, not a rewrite")
    script = run / "script.txt"
    capture = capture_from_script(script.read_text()) if script.exists() else None
    path.write_text(render(run, capture))
    return path


def add_warmth(run):
    """Append the warmth tables to a file written before they existed
    (appended, not rewritten: the file's other lines stand)."""
    path = Path(run) / "knobs.toml"
    if not path.exists():
        raise SystemExit(f"{path}: no knobs file (knobs.py init)")
    text = path.read_text()
    if "[warmth]" in text:
        raise SystemExit(f"{path} already carries [warmth]")
    lines = warmth_lines(run)
    if not lines:
        raise SystemExit(f"{run}: the head's logs do not say how long the console had been on")
    path.write_text(text.rstrip("\n") + "\n\n" + "\n".join(lines))
    return path


def check(run, nes):
    path = Path(run) / "knobs.toml"
    if not path.exists():
        raise SystemExit(f"{path}: no knobs file (knobs.py init)")
    r = subprocess.run(["cargo", "run", "--release", "-q", "-p", "nes-console", "--example", "knobs", "--", str(path.resolve())],
                       cwd=nes, capture_output=True, text=True)
    sys.stdout.write(r.stdout)
    sys.stderr.write("\n".join(l for l in r.stderr.splitlines() if not l.startswith("warning")) + ("\n" if r.stderr else ""))
    return r.returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("op", choices=["init", "show", "check", "warmth"])
    ap.add_argument("run")
    ap.add_argument("--nes", default=str(Path(__file__).resolve().parent.parent.parent / "nes"))
    ap.add_argument("--force", action="store_true", help="init: overwrite (the bench's rehearsals only)")
    a = ap.parse_args()
    if a.op == "init":
        print(init(a.run, a.force))
    elif a.op == "warmth":
        print(add_warmth(a.run))
    elif a.op == "show":
        print((Path(a.run) / "knobs.toml").read_text(), end="")
    else:
        return check(a.run, a.nes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
