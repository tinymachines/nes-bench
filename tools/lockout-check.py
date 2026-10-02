#!/usr/bin/env python3
"""Is the console's lockout chip still resetting the console?

  python3 tools/lockout-check.py --cart keyless --channel 1            # watch, then the button
  python3 tools/lockout-check.py --cart keyless --channel 1 --pin4 2   # and the cut leg's level
  python3 tools/lockout-check.py --score captures/NAME.toml            # a record again, cold
  python3 tools/lockout-check.py --selftest                            # the desk test; MUTATE=1 must go red

WHAT IT MEASURES. A front-loading NES holds a lock (the 3193A) whose
pin 9 drives the reset line of the CPU and the PPU. When no key answers
it, the lock pulls that line low "with a 1Hz square wave" (nesdev, CIC
lockout chip, read 2026-10-02). The modification that stops it takes
the lock's pin 4 off the board, which makes the chip a key, and a key
never drives reset. So the question "is it defeated" has a waveform for
an answer: with NO KEY in the slot, the reset line either sits high or
it is a square wave of about a second.

One scope channel on the reset line (the lock's pin 9, the CPU's pin 3
and the PPU's pin 22 are one net), twelve seconds at a time:

  watch    hands off. Steady high, or pulsing.
  button   press and release Reset once while it records. The line has
           to go low and come back.

WHY THE BUTTON. A probe on the +5 V rail sits high for twelve seconds
too, and "steady high" from a rail would be reported as a defeated
lock. A check that can pass on nothing has to be made to see something:
the button record is what shows the probe is on a line that resets. It
does not show WHICH reset line. The front panel's button feeds the
lock's own reset input (pin 7), which also falls with the button and
never carries the square wave, so a probe there passes with the lock
alive. That one is settled with a meter, unpowered: the probe point
rings through to the CPU's pin 3. The tool says so every time and
cannot check it.

WHY --cart. With a licensed game in the slot a working lock is
satisfied and holds the line high, exactly as a defeated one does. The
measurement only means something with no key present: an empty slot, or
a cartridge whose lockout position is empty (the calibration cart).
`--cart licensed` is refused for that reason.

WHAT IT CANNOT SEE. Whether pin 4 was cut cleanly, whether the leg is
grounded or floating, and whether the stub touches its pad when the
board flexes. --pin4 reads the leg's level on a second channel, which
answers the first two while the probe is on it.

The classifier is plain Python on purpose: it runs in check-all.sh on a
desk with nothing installed, and a twelve-second record at this depth
is 120,000 points.
"""
import argparse
import importlib.util
import json
import os
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent

# A 5 V logic line through a 1X probe. Hysteresis, so a slow edge or a
# ringing one is one transition and not twenty.
LOW_V, HIGH_V = 1.2, 3.0
DWELL_S = 0.020          # a level shorter than this is a glitch, not a state
WATCH_S = 10.0           # steady high for at least this long, or it is not a verdict
PRESS_S = 0.050          # the button's low has to last at least this long
PERIOD_S = (0.6, 1.6)    # "1Hz" with room: nobody has measured this lock's rate here
SECONDS = 12.0
DEPTH = 120_000


def states(volts, rate):
    """The record as runs of (level, samples): level True for high.
    Samples between the two thresholds keep the level before them; a
    record that never reaches either threshold has no runs."""
    lo = float("-inf") if os.environ.get("MUTATE") else LOW_V
    level = None
    runs = []
    for v in volts:
        if v >= HIGH_V:
            now = True
        elif v <= lo:
            now = False
        else:
            now = level
        if now is None:
            continue
        if runs and runs[-1][0] == now:
            runs[-1][1] += 1
        else:
            runs.append([now, 1])
        level = now
    # Merge glitches into what surrounds them, shortest first, until
    # every run that is left is a state.
    dwell = max(1, int(DWELL_S * rate))
    while len(runs) > 1:
        i = min(range(len(runs)), key=lambda k: runs[k][1])
        if runs[i][1] >= dwell:
            break
        n = runs.pop(i)[1]
        if i < len(runs) and i > 0:      # between two runs of the other level: they join
            runs[i - 1][1] += n + runs.pop(i)[1]
        elif i > 0:
            runs[i - 1][1] += n
        else:
            runs[0][1] += n
    return [(lv, n) for lv, n in runs]


def median(xs):
    xs = sorted(xs)
    return xs[len(xs) // 2] if xs else None


def classify(volts, rate):
    """What the line did, in facts, and one word for it:
      none      it never reached a logic level (probe off, or a 10X probe)
      low       it never went high
      steady    high from end to end
      pulsing   a square wave of about a second: the lock, resetting
      moved     it changed, and not as a square wave of about a second"""
    runs = states(volts, rate)
    seen = sum(n for _lv, n in runs)
    out = {"seconds": round(len(volts) / rate, 2), "rate_hz": rate}
    if not runs:
        out.update(kind="none", max_v=round(max(volts), 2), min_v=round(min(volts), 2))
        return out
    highs = sorted(v for v in volts if v >= HIGH_V)
    lows = sorted(v for v in volts if v <= LOW_V)
    out["high_v"] = round(highs[len(highs) // 2], 2) if highs else None
    out["low_v"] = round(lows[len(lows) // 2], 2) if lows else None
    falls = sum(1 for a, b in zip(runs, runs[1:]) if a[0] and not b[0])
    rises = sum(1 for a, b in zip(runs, runs[1:]) if not a[0] and b[0])
    out.update(falls=falls, rises=rises,
               high_fraction=round(sum(n for lv, n in runs if lv) / seen, 3),
               longest_low_s=round(max((n for lv, n in runs if not lv), default=0) / rate, 3),
               longest_high_s=round(max((n for lv, n in runs if lv), default=0) / rate, 3))
    if not any(lv for lv, _n in runs):
        out["kind"] = "low"
    elif len(runs) == 1:
        out["kind"] = "steady"
    else:
        # A square wave: whole periods (a low run and the high run after
        # it) of about a second, the two halves comparable. The first
        # and last runs are cut by the record's ends and are left out.
        inner = runs[1:-1]
        periods = [(a[1] + b[1]) / rate for a, b in zip(inner, inner[1:]) if not a[0] and b[0]]
        duty = [b[1] / (a[1] + b[1]) for a, b in zip(inner, inner[1:]) if not a[0] and b[0]]
        mp, md = median(periods), median(duty)
        if len(periods) >= 3 and PERIOD_S[0] <= mp <= PERIOD_S[1] and 0.25 <= md <= 0.75:
            out.update(kind="pulsing", period_s=round(mp, 3), duty=round(md, 2))
        else:
            out["kind"] = "moved"
            if mp is not None:
                out.update(period_s=round(mp, 3), duty=round(md, 2))
    return out


def verdict(watch, button=None, pin4=None):
    """(exit status, one line). 0 defeated, 1 the lock is alive, 2 not shown either way."""
    for name, r in (("watch", watch), ("button", button)):
        if r and r["kind"] == "pulsing":
            return 1, (f"NOT DEFEATED: in the {name} record the reset line is a square wave, period "
                       f"{r['period_s']} s. That is the lock refusing a slot with no key in it.")
    if pin4 and pin4.get("level") == "high":
        return 1, (f"NOT DEFEATED: pin 4's leg reads {pin4['volts']} V. It is still tied to +5 V, "
                   "so the chip is still a lock, whatever the reset line did in twelve seconds.")
    if watch["kind"] == "none":
        return 2, (f"NOT SHOWN: the line never reached a logic level (it read {watch['min_v']} to "
                   f"{watch['max_v']} V). A probe that is off the board reads this, and so does a 10X "
                   "probe on a channel set for 1X.")
    if watch["kind"] == "low":
        # A real logic low is a few tens of millivolts. Half a volt that
        # never moves is what 5 V looks like through a 10X probe on a
        # channel set for 1X, and calling that "low" would send the
        # reader to the console instead of to the probe's switch.
        if watch["low_v"] >= 0.3:
            return 2, (f"NOT SHOWN: the line sat at {watch['low_v']} V for the whole record, which is not "
                       "a logic low. It is what 5 V reads through a 10X probe on a channel set for 1X: "
                       "check the probe's switch.")
        return 2, ("NOT SHOWN: the line sat low for the whole record. The console is off, or held in "
                   "reset, or the probe is on something that is not the reset line.")
    if watch["kind"] != "steady" or watch["seconds"] < WATCH_S:
        return 2, (f"NOT SHOWN: the watch record is '{watch['kind']}' over {watch['seconds']} s "
                   f"({watch.get('falls', 0)} falls). It has to be steady high for {WATCH_S:g} s with "
                   "nobody touching the console.")
    if button is None:
        return 2, ("NOT SHOWN: the line sat high, which is also what the +5 V rail does. Run the button "
                   "record: the line has to fall when Reset is pressed.")
    pressed = (button["kind"] in ("moved", "low") and button.get("longest_low_s", 0) >= PRESS_S
               and button.get("longest_high_s", 0) >= 1.0)
    if not pressed:
        return 2, (f"NOT SHOWN: the line sat high in the watch record, and the button record is "
                   f"'{button['kind']}' (longest low {button.get('longest_low_s', 0)} s). Nothing shows "
                   "this is a line that resets; a supply rail reads the same.")
    tail = f" Pin 4's leg reads {pin4['volts']} V." if pin4 else ""
    return 0, (f"DEFEATED, on this line: steady at {watch['high_v']} V for {watch['seconds']} s with no "
               f"key in the slot, and low for {button['longest_low_s']} s under the Reset button.{tail} "
               "It holds only if the probe is on the CPU's reset net and not the button's own line: "
               "ring it through to the CPU's pin 3 with a meter, unpowered.")


def pin4_level(volts):
    v = median(volts)
    return {"volts": round(v, 2), "level": "high" if v >= HIGH_V else "low" if v <= LOW_V else "between"}


# ---------------------------------------------------------------- the scope

def scope_class():
    spec = importlib.util.spec_from_file_location("headd", ROOT / "head" / "headd.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.Scope


def scope_address(explicit):
    spec = importlib.util.spec_from_file_location("bringup", ROOT / "tools" / "bringup.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.scope_address(explicit)


def to_volts(sc, ch, raw):
    """Codes to volts by the instrument's own preamble for that channel,
    not by what the arm asked for."""
    sc.cmd(f":WAVeform:SOURce CHANnel{ch}")
    pre = sc.ask(":WAVeform:PREamble?").split(",")
    yinc, yorig, yref = float(pre[7]), float(pre[8]), float(pre[9])
    return [(c - yorig - yref) * yinc for c in raw]


def record(sc, chs, name, note, seconds):
    """One single-shot record of `seconds`, forced: nothing here waits
    for an edge, because the line this is for may never have one."""
    out = ROOT / "captures"
    out.mkdir(exist_ok=True)
    tb = seconds / 12.0
    sc.arm(chs=chs, scale=1.0, offset=-2.0, source=f"CH{chs[0]}", tb=tb, depth=DEPTH)
    # The trigger sits 3.5 divisions in (headd.Scope.arm, MEASURED
    # 2026-09-07) and the instrument will not take one until that much
    # of the record is behind it.
    time.sleep(tb * 4 + 1.0)
    if not sc.triggered():
        sc.cmd(":TFORce")
    deadline = time.time() + seconds + 15
    while not sc.triggered():
        if time.time() > deadline:
            raise RuntimeError("the scope did not finish the record")
        time.sleep(0.5)
    info = sc.read_record(chs, out, name, note)
    volts = {ch: to_volts(sc, ch, (out / info["files"][ch]).read_bytes()) for ch in chs}
    return info, volts


def live(a):
    if a.cart == "licensed":
        print("lockout-check: refused. With a licensed game in the slot a working lock holds the line "
              "high too, so the record could not tell the two apart. Empty the slot, or use a cartridge "
              "with no lockout chip on it.")
        return 2
    addr = scope_address(a.scope)
    if not addr:
        print("lockout-check: no scope address: pass --scope, set $SCOPE, or put it in bench.local.md")
        return 2
    chs = [a.channel] + ([a.pin4] if a.pin4 else [])
    stamp = time.strftime("%Y%m%dT%H%M%S")
    sc = scope_class()(addr, tries=3)
    res = {"cart": a.cart, "channel": a.channel, "stamp": stamp}
    try:
        print(f"watch: {a.seconds:g} s, hands off the console...", flush=True)
        _info, v = record(sc, chs, f"lockout-{stamp}-watch", f"lockout watch, slot: {a.cart}", a.seconds)
        res["watch"] = classify(v[a.channel], DEPTH / a.seconds)
        print("  " + json.dumps(res["watch"]))
        if a.pin4:
            res["pin4"] = pin4_level(v[a.pin4])
            print("  pin 4: " + json.dumps(res["pin4"]))
        if not a.no_button and res["watch"]["kind"] == "steady":
            print(f"button: {a.seconds:g} s. Wait five seconds, then press Reset for about a second and "
                  "let go...", flush=True)
            _info, v = record(sc, chs, f"lockout-{stamp}-button", f"lockout button, slot: {a.cart}", a.seconds)
            res["button"] = classify(v[a.channel], DEPTH / a.seconds)
            print("  " + json.dumps(res["button"]))
    finally:
        try:
            sc.restore_setup()
        except Exception:  # noqa: BLE001
            pass
    code, line = verdict(res["watch"], res.get("button"), res.get("pin4"))
    res.update(exit=code, verdict=line)
    (ROOT / "captures" / f"lockout-{stamp}.json").write_text(json.dumps(res, indent=1) + "\n")
    print(line)
    print(f"lockout-check: records and this result are in captures/lockout-{stamp}*")
    return code


def score(path):
    """A record again, cold, from its .toml: the same classifier, and no
    volts but the arm's own (1 V a division about +2 V), since the
    preamble was the instrument's and is not kept."""
    p = pathlib.Path(path)
    meta = dict(line.split(" = ", 1) for line in p.read_text().splitlines() if " = " in line and not line.startswith("#"))
    raw = (p.parent / meta["file"].strip('"')).read_bytes()
    volts = [(c - 127) * 0.04 + 2.0 for c in raw]
    r = classify(volts, float(meta["rate_hz"]))
    print(json.dumps(r))
    return 0


# ---------------------------------------------------------------- the desk test

def synth(spec, rate=1000.0, high=4.9, low=0.1):
    """A record from (level, seconds) pairs. Level may be a number of volts."""
    out = []
    for lv, s in spec:
        v = high if lv is True else low if lv is False else lv
        out += [v] * int(s * rate)
    return out, rate


def selftest():
    square = [(False, 3.5)] + [(True, 0.5), (False, 0.5)] * 8 + [(True, 0.5)]
    press = [(True, 5.0), (False, 1.1), (True, 5.9)]
    bounce = [(True, 5.0), (False, 0.004), (True, 0.004), (False, 1.1), (True, 0.003), (False, 0.003), (True, 5.9)]
    cases = [
        # name, watch, button, pin4 volts, exit wanted, the word that has to be in the line
        ("a defeated lock", [(True, 12)], press, None, 0, "DEFEATED"),
        ("a defeated lock, bouncing button", [(True, 12)], bounce, None, 0, "DEFEATED"),
        ("a defeated lock, leg grounded", [(True, 12)], press, 0.02, 0, "DEFEATED"),
        ("a live lock, no key", square, None, None, 1, "NOT DEFEATED"),
        ("a live lock seen only in the button record", [(True, 12)], square, None, 1, "NOT DEFEATED"),
        ("a leg still on +5 V", [(True, 12)], press, 4.95, 1, "NOT DEFEATED"),
        ("the supply rail", [(True, 12)], [(True, 12)], None, 2, "NOT SHOWN"),
        ("no button record", [(True, 12)], None, None, 2, "NOT SHOWN"),
        ("held in reset", [(False, 12)], None, None, 2, "sat low"),
        ("a 10X probe on a 1X channel", [(0.49, 12)], None, None, 2, "10X probe"),
        ("a probe on nothing", [(2.1, 12)], None, None, 2, "logic level"),
        ("too short to say", [(True, 6)], press, None, 2, "NOT SHOWN"),
        ("somebody pressed Reset during the watch", press, press, None, 2, "NOT SHOWN"),
    ]
    bad = 0
    for name, w, b, p4, want, word in cases:
        watch = classify(*synth(w))
        button = classify(*synth(b)) if b else None
        pin4 = pin4_level([p4] * 100) if p4 is not None else None
        code, line = verdict(watch, button, pin4)
        ok = code == want and word in line
        bad += not ok
        print(f"  {'ok  ' if ok else 'FAIL'} {name}: exit {code}" + ("" if ok else f", wanted {want} with '{word}': {line}"))
    # The square wave has to be read as one, by its numbers.
    r = classify(*synth(square))
    ok = r["kind"] == "pulsing" and abs(r["period_s"] - 1.0) < 0.01 and r["falls"] >= 8
    bad += not ok
    print(f"  {'ok  ' if ok else 'FAIL'} the square wave's own numbers: {json.dumps(r)}")
    print("lockout-check selftest: " + ("every case agrees" if not bad else f"{bad} case(s) disagree"))
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--score", metavar="TOML")
    ap.add_argument("--cart", choices=["none", "keyless", "licensed"],
                    help="what is in the slot: nothing, a cartridge with no lockout chip, or a licensed game")
    ap.add_argument("--channel", type=int, default=1, help="the scope channel on the reset line")
    ap.add_argument("--pin4", type=int, help="a second channel, on the lockout chip's cut pin 4 leg")
    ap.add_argument("--seconds", type=float, default=SECONDS)
    ap.add_argument("--no-button", action="store_true", help="the watch record only (never a verdict of defeated)")
    ap.add_argument("--scope")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if a.score:
        return score(a.score)
    if not a.cart:
        ap.error("--cart is required: the record means nothing without knowing what is in the slot")
    return live(a)


if __name__ == "__main__":
    sys.exit(main())
