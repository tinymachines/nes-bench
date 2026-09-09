#!/usr/bin/env python3
"""The bring-up tool's own guards, exercised without a bench.

  python3 tools/check-bringup.py

`tools/bringup.py` is interactive, so its checks are the part of this
repository least likely to be run twice before somebody depends on them.
This drives `check_harness_map` through scripted answers and asserts the
outcome of each, including the ones that must FAIL: a guard that has
never been seen to refuse is not a guard.

The case that matters is a breakout with two leads the same colour. The
bench's own controller breakout has GND and CLK both yellow, which are
exactly the two leads a probe's ground clip and its tip land on, and a
clip on a driven line grounds it. Colours cannot separate them and the
housing's moulded numbers say nothing about a breakout, so the step
refuses that map unless a meter was used.
"""
import builtins
import importlib.util
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HARNESS = ["brown", "red", "orange", "yellow", "white", "blue", "purple"]


def bringup():
    spec = importlib.util.spec_from_file_location("bringup", ROOT / "tools" / "bringup.py")
    m = importlib.util.module_from_spec(spec)
    argv, sys.argv = sys.argv, [sys.argv[0]]
    try:
        spec.loader.exec_module(m)
    finally:
        sys.argv = argv
    return m


def run(b, method, breakout, harness=None):
    """One scripted pass through the step. `breakout` is None for a
    harness with nothing spliced onto it."""
    answers = [method] + (harness or HARNESS) + (["y"] + breakout if breakout else ["n"])
    it = iter(answers)
    real_input, builtins.input = builtins.input, lambda p="": next(it)
    out, real_out = io.StringIO(), sys.stdout
    sys.stdout = out
    try:
        return b.check_harness_map(None, None)
    finally:
        sys.stdout = real_out
        builtins.input = real_input


# (label, method, breakout leads pin 1..7, expected state, a word the
#  summary has to contain). "nc" means the pin is not brought out.
CASES = [
    ("the bench's own map, rung out", "both",
     ["yellow", "yellow", "black", "green", "red", "nc", "nc"], "pass", "told apart with the meter"),
    ("the same map read off the housing", "moulded",
     ["yellow", "yellow", "black", "green", "red", "nc", "nc"], "fail", "ring those leads out"),
    ("a breakout that drops D0", "meter",
     ["yellow", "grey", "black", "nc", "red", "nc", "nc"], "fail", "D0 is not on the breakout"),
    ("distinct colours, +5V brought out", "meter",
     ["black", "white", "green", "blue", "red", "nc", "purple"], "pass", "rung out with a meter"),
    ("no breakout at all", "moulded", None, "pass", "the numbering is the housing's own"),
    ("a method that is not one of the three", "brown", None, "fail", "is not one of"),
]


def main():
    b = bringup()
    bad = 0
    for label, method, breakout, want, needle in CASES:
        state, data, summary = run(b, method, breakout)
        ok = state == want and needle in summary
        print(f"{'ok  ' if ok else 'FAIL'} {label}: {state}: {summary}")
        if not ok:
            bad += 1
            print(f"       wanted {want} with {needle!r}")

    # The supply flag is what step 1.2's reading is redirected by, so it
    # is asserted rather than left to the wording.
    _, d, _ = run(b, "meter", ["yellow", "grey", "black", "green", "red", "nc", "nc"])
    if d.get("supply_out") is not False:
        print("FAIL a breakout without +5V must record supply_out false"); bad += 1
    _, d, _ = run(b, "meter", ["black", "white", "green", "blue", "red", "nc", "purple"])
    if d.get("supply_out") is not True:
        print("FAIL a breakout carrying +5V must record supply_out true"); bad += 1
    if not bad:
        print(f"ok   supply_out follows pin 7 both ways")

    print(f"\n{len(CASES) + 1} checks, {bad} failing")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
