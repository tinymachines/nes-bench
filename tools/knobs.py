#!/usr/bin/env python3
"""The knobs file: one per run, `runs/<stamp>/knobs.toml`, the numbers
the model carries that it could not measure on a die, each with where
it came from (docs/exercise.md, Programme 1).

  python3 tools/knobs.py init runs/<stamp>            # write it from the measured defaults and the run's ARM line
  python3 tools/knobs.py show runs/<stamp>            # print it
  python3 tools/knobs.py check runs/<stamp> [--nes ../nes]   # the model reads it back, or refuses by name

`init` refuses to overwrite: a knob that changed is a new line in the
file with its source, not a rewrite. The model's reader
(nes-console/src/knobs.rs) is the one place the schema lives; `check`
runs it, so a file this writer got wrong is refused there, not
explained here. `b1-score.py` writes the file for a run that has none
and hands it to the scorer as KNOBS=.

Tables today: [alignment] (the console's power-on alignment, measured
off the two dies' clock recipes until E4's histogram sets it from the
part) and [capture] (the scope's window on the video, from the run's
ARM line: the channel the video sits on, the scale, the offset).
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

VIDEO_CHANNEL = 3   # docs/wiring.md: the video probe on CH3


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
    ap.add_argument("op", choices=["init", "show", "check"])
    ap.add_argument("run")
    ap.add_argument("--nes", default=str(Path(__file__).resolve().parent.parent.parent / "nes"))
    ap.add_argument("--force", action="store_true", help="init: overwrite (the bench's rehearsals only)")
    a = ap.parse_args()
    if a.op == "init":
        print(init(a.run, a.force))
    elif a.op == "show":
        print((Path(a.run) / "knobs.toml").read_text(), end="")
    else:
        return check(a.run, a.nes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
