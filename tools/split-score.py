#!/usr/bin/env python3
"""The split on the part: a run's triggered capture and the model, each
asked where down the picture the rows begin to move, and which of the
model's frames the part's triggered frame is.

  python3 tools/split-score.py runs/<stamp> rom.nes [capture-name] [--channel N] [--gap 2] [--nes ../nes]
  python3 tools/split-score.py --synthetic runs/<stamp> rom.nes      # the tool's own green run

Reads the run as b1-score.py does (its script's TRIG for the latch, its
capture's .toml for the rate and the trigger's sample, its knobs file)
and runs nes-console's `split-score`: the model to the first frame after
the latch, the record sliced from the trigger, and on each side the
horizontal shift of every picture row between two frames GAP apart, in
dots, from decoded luma. The still rows are the status bar, the moving
rows the level, the split between the last of one and the first of the
other, as tight as the picture's content lets it be; then the part's
frame against the model's F-1..F+2, the status rows giving the constant
offset and the level rows the scroll beyond it, to name the model
frame the part drew. A real capture is recorded, not held. With
--synthetic the part is the model's own frames through the card model
and the run is held (the model's example says how, and its
MUTATE_FRAME=1 and MUTATE_STILL=1 must be red).

First run 2026-09-18 on Super Mario Bros. at latch 600 with Right held
from 520 (exercise/split.txt, run 20260918-135721): part and model both
still through row 32 and moving from row 47, the sky between flat; the
part advanced 1.94 dots to the model's 1.89 over two frames; and the
part's triggered frame was the model's F+1, because this game polls
after the encoder's sync rows and the recovery anchors on the next
sync (docs/mario-dissection.md).
"""
import argparse
import importlib.util
import subprocess
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location("b1_score", Path(__file__).resolve().parent / "b1-score.py")
b1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(b1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("rom")
    ap.add_argument("capture", nargs="?", default=None, help="the capture's name (default: the run's only one)")
    ap.add_argument("--nes", default=str(Path(__file__).resolve().parent.parent.parent / "nes"))
    ap.add_argument("--channel", type=int, default=None, help="the video channel in a multi-channel capture (default: the knobs file's)")
    ap.add_argument("--frames", type=int, default=2000, help="a ceiling on the frames the model runs to reach the latch")
    ap.add_argument("--gap", type=int, default=2, help="frames between the two compared on each side")
    ap.add_argument("--synthetic", action="store_true")
    a = ap.parse_args()
    run = Path(a.run).resolve()
    env, a.channel = b1.run_env(run, a.synthetic, a.channel)
    if "LATCH" not in env:
        print(f"{run}: the script has no TRIG line, so there is no latch to place the frame at", file=sys.stderr)
        return 2
    env["GAP"] = str(a.gap)
    cmd = ["cargo", "run", "--release", "-p", "nes-console", "--example", "split-score", "--", a.rom, str(a.frames)]
    if not a.synthetic:
        try:
            u8, rate, ts = b1.run_capture(run, a.capture, a.channel)
        except SystemExit as e:
            print(e, file=sys.stderr)
            return 2
        if ts is None:
            print("the capture's .toml has no trigger_sample: the model's frame cannot be placed against the record", file=sys.stderr)
            return 2
        cmd += [str(u8), f"{rate:.1f}"]
        env["TRIGGER_SAMPLE"] = str(ts)
    print("split-score:", " ".join(f"{k}={env[k]}" for k in ("SCRIPT", "LATCH", "TRIGGER_SAMPLE", "GAP") if k in env), " ".join(cmd[-3:]))
    return subprocess.call(cmd, cwd=a.nes, env=env)


if __name__ == "__main__":
    sys.exit(main())
