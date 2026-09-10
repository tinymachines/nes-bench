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


# ---------------------------------------------------------- measure_port
# A synthetic poll in the same shape the console makes: the latch high
# for 4.44 us once every 16.639 ms, eight clock lows of 0.62 us at
# 15.64 us spacing after it. The point of the numbers is the SHAPE: the
# latch is high for 0.027 percent of the record. Both bugs found on the
# first real capture were invisible to anything with a balanced duty
# cycle, and there was no test here at all before that capture.
POLL_HZ, LATCH_US, CLOCK_LOW_US, CLOCK_PERIOD_US, CLOCKS = 60.0997, 4.44, 0.62, 15.64, 8


def synth_poll(rate=5_000_000.0, frames=6):
    import numpy as np
    period = int(round(rate / POLL_HZ))
    n = period * frames
    latch = np.zeros(n, dtype=np.float32) + 20.0
    clock = np.zeros(n, dtype=np.float32) + 200.0
    lw = int(round(LATCH_US * 1e-6 * rate))
    cw = max(1, int(round(CLOCK_LOW_US * 1e-6 * rate)))
    cp = int(round(CLOCK_PERIOD_US * 1e-6 * rate))
    for f in range(frames):
        t = f * period + 1000
        latch[t:t + lw] = 220.0
        for k in range(CLOCKS):
            c = t + lw + 200 + k * cp
            clock[c:c + cw] = 20.0
    return latch, clock, rate


def check_measure_port(b):
    """The four numbers, off a synthetic record whose duty cycle is a
    needle. Both of these assertions went red on the code that shipped
    this morning: the level test called the latch flat, and the clock
    period came back in samples with a microsecond label."""
    import numpy as np
    bad = 0
    latch, clock, rate = synth_poll()
    m = b.measure_port(latch, clock, rate)
    if "error" in m:
        print(f"FAIL a needle duty cycle must not read as flat: {m['error']}")
        return 1
    want = [("latch_high_us", LATCH_US, 0.25), ("clock_low_us", CLOCK_LOW_US, 0.25),
            ("clock_period_us", CLOCK_PERIOD_US, 0.5), ("polls_per_s", POLL_HZ, 0.5)]
    for key, target, tol in want:
        got = m.get(key)
        ok = got is not None and abs(got - target) <= tol
        print(f"{'ok  ' if ok else 'FAIL'} measure_port {key}: {got} (want {target} +- {tol})")
        if not ok:
            bad += 1
    ok = m.get("clocks_per_latch_mode") == CLOCKS
    print(f"{'ok  ' if ok else 'FAIL'} measure_port clocks per latch: {m.get('clocks_per_latch_mode')} (want {CLOCKS})")
    bad += 0 if ok else 1

    # A dead probe still has to be caught, or the fix above would have
    # traded one wrong answer for another.
    flat = np.zeros(100_000, dtype=np.float32) + 77.0
    m = b.measure_port(flat, clock, rate)
    ok = "error" in m and "flat" in m["error"]
    print(f"{'ok  ' if ok else 'FAIL'} a genuinely flat channel is still refused: {m.get('error')}")
    bad += 0 if ok else 1

    # And a lone spike is a glitch, not a level.
    spike = np.zeros(100_000, dtype=np.float32) + 77.0
    spike[500:504] = 220.0
    m = b.measure_port(spike, clock, rate)
    ok = "error" in m and "glitch" in m["error"]
    print(f"{'ok  ' if ok else 'FAIL'} a four sample spike is refused as a glitch: {m.get('error')}")
    bad += 0 if ok else 1
    return bad


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

    bad += check_measure_port(b)

    print(f"\n{len(CASES) + 9} checks, {bad} failing")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
