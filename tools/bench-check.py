#!/usr/bin/env python3
"""The signal paths' regression check: the bridge, the console and the scope.

  python3 tools/bench-check.py                     # every path; exit 1 on any FAIL
  python3 tools/bench-check.py --no-walk           # skip the register walk (the slow one)
  python3 tools/bench-check.py --bridge HOST:6545 --scope HOST

tools/rig-check.py asks whether the cameras still see what they saw.
This asks whether the electrons still go where they went, and it runs
the same measurements the bring-up and the register walk of 2026-09-15
held, so a wire that fell out between two sittings shows here and not
in the next experiment's result.

  bridge    the UNO answers STATUS with its banner over the Pi's socket.
  scope     the DS1054Z answers *IDN?.
  polls     MODE PASS for 20 s: the console polls about 60 times a
            second and every poll is eight clocks (bring-up 5.1, B0's
            gate 1). No polls at all is a SKIP, not a FAIL: the console
            is off or no game is running, and the checks that need it
            are skipped with that reason rather than failed.
  trigger   TRIG 20 stops the scope armed on CH1, 2.5 V rising
            (bring-up 6.1).
  walk      MODE INJECT, fifteen bytes set into the register one at a
            time, the scope stopped on the latch's fall (CH2) and D0
            (CH4) read at the middle of each of the eight bit slots off
            the screen; pressed is LOW; every byte must read back as
            set (the walk of 2026-09-15 23:00, 15 of 15).
  reset     with --hands: the console resets. The poll stream is the
            instrument: the game stops polling while the CPU is held and
            restarts, a pause of a second or more in a stream that
            otherwise never goes quiet, then polls again. Manual: you
            hold the front panel's button for two seconds when asked.
            Head: the Pi holds GPIO17 high for two seconds through OK1,
            which sits in parallel with that button. Both pins are set
            with pinctrl, which leaves a level in place after it exits
            (the boot config makes them outputs, GPIO27 high, GPIO17 low).
  power     with --hands: the console goes off and comes back. Manual:
            you throw the front panel's switch off, count three, and on,
            with the relay resting open. Head: the front switch stays
            OFF; the Pi powers the console before the run (GPIO27 high,
            MEASURED 2026-09-17), drops it for three seconds and brings
            it back. K1 is in parallel with the front switch (J3 brown and
            red), so either one powers the console. The stream stops and
            resumes, a gap of at least a second and a half. The pin is
            put back as it was found at the end.

  --hands manual and --hands head are the same two measurements with a
  different hand on the button, so a wiring that works by hand and not
  from the head shows as exactly that.

The scope's settings the walk changes are read first and put back after,
the trigger slope and sweep and the channels with them, and the bridge
is left in MODE PASS after a RESET. The walk's screenshots are kept in
captures/bench/walk-XX.png so a difference can be looked at. The result
also goes to captures/bench/last-check.json.

Addresses: the scope's as tools/bringup.py finds it (--scope, $SCOPE,
bench.local.md); the bridge's from --bridge, $BRIDGE, or the first
address with :6545 on it in bench.local.md. Neither lives in a commit.
"""
import argparse
import io
import json
import os
import re
import socket
import struct
import subprocess
import sys
import time
import zlib
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "captures" / "bench"
sys.path.insert(0, str(ROOT / "tools"))
from loadmod import load  # noqa: E402

# 55 and aa first: their bits alternate, so their own transitions give the
# clock period and the first slot boundary for the rest of the run.
WALK = ("55", "aa", "00", "ff", "01", "02", "04", "08", "10", "20", "40", "80", "06", "7f", "1b")
# The screen's geometry at 20 us/div with the trigger 80 us from the left
# edge: the graticule runs x 84..684 for 200 us, so 3 px a microsecond.
# The bit slots after the latch's fall: the first clock about 7 us after
# it and one every 13 us; the first bit is read at 3.5 us, the others
# 6.5 us into their slot. MEASURED 2026-09-15 on the walk's screenshots.
PX_PER_US = 3.0
# The authored fallback, from the walk of 2026-09-15: the first clock about
# 7 us after the latch's fall and one every 13 us. The game does not clock
# every poll alike, and a different game state clocks faster (MEASURED
# 2026-09-17: byte 00 read as if two bits past the eighth clock), so the
# timing is taken from each capture's own transitions where it can be.
FIRST_US, PERIOD_US = 7.0, 13.0
TRACE_LOW_Y = 230        # a trace centre below this screen row is the high level


def bridge_address(explicit=None):
    if explicit:
        return explicit
    if os.environ.get("BRIDGE"):
        return os.environ["BRIDGE"]
    local = ROOT / "bench.local.md"
    if local.exists():
        m = re.search(r"\b(\d{1,3}(?:\.\d{1,3}){3}:6545)\b", local.read_text())
        if m:
            return m.group(1)
    return None


class Bridge:
    """The UNO through the Pi's serial bridge: the board resets on
    connect, so the first 2.5 s are its boot, and reads are bounded
    because it streams a line per poll forever."""

    def __init__(self, addr):
        host, port = addr.rsplit(":", 1)
        self.s = socket.create_connection((host, int(port)), timeout=8)
        self.s.settimeout(0.3)
        time.sleep(2.5)

    def send(self, line):
        self.s.sendall((line + "\n").encode())
        time.sleep(0.2)

    def read(self, window=0.4):
        out, end = b"", time.time() + window
        while time.time() < end:
            try:
                out += self.s.recv(65536)
            except (socket.timeout, OSError):
                pass
        return out.decode(errors="replace").splitlines()

    def close(self):
        try:
            self.s.close()
        except OSError:
            pass


class Scope:
    def __init__(self, host):
        self.s = socket.create_connection((host, 5555), timeout=6)
        self.saved = {}

    def cmd(self, c):
        self.s.sendall((c + "\n").encode())
        time.sleep(0.06)

    def ask(self, c):
        self.drain()
        self.s.sendall((c + "\n").encode())
        out = b""
        self.s.settimeout(3)
        try:
            while not out.endswith(b"\n"):
                out += self.s.recv(65536)
        except (socket.timeout, OSError):
            pass
        return out.decode(errors="replace").strip()

    def drain(self):
        """Whatever the instrument still had to say. A query whose answer
        arrived late leaves a line in the socket, and the next read takes
        it for the head of its own answer: a screenshot read came back as
        b'OP\\n#90000...', the tail of an earlier :TRIGger:STATus?."""
        self.s.settimeout(0.05)
        out = b""
        try:
            while True:
                c = self.s.recv(1 << 16)
                if not c:
                    break
                out += c
        except (socket.timeout, OSError):
            pass
        return out

    def shot(self, path):
        """A screenshot as the scope sends it (its PNG chunk CRCs are wrong;
        load() rewrites them). The TMC block is found in the stream rather
        than assumed to start it."""
        for _ in range(3):
            self.drain()
            self.s.sendall(b":DISPlay:DATA? ON,OFF,PNG\n")
            buf, t1 = b"", time.time()
            self.s.settimeout(4)
            while time.time() - t1 < 10:
                try:
                    c = self.s.recv(1 << 16)
                except (socket.timeout, OSError):
                    break
                if not c:
                    break
                buf += c
                i = buf.find(b"#9")
                if i >= 0 and len(buf) >= i + 11 and buf[i + 2:i + 11].isdigit() and len(buf) >= i + 11 + int(buf[i + 2:i + 11]):
                    break
            i = buf.find(b"#9")
            if i >= 0 and len(buf) >= i + 11 and buf[i + 2:i + 11].isdigit():
                n = int(buf[i + 2:i + 11])
                Path(path).write_bytes(buf[i + 11:i + 11 + n])
                return n
            time.sleep(0.5)
        return 0

    def save(self, keys):
        self.saved = {k: self.ask(k + "?") for k in keys}

    def restore(self):
        for k, v in self.saved.items():
            if v:
                self.cmd(f"{k} {v}")


def load_png(path):
    d = Path(path).read_bytes()
    out, i = d[:8], 8
    while i < len(d):
        n = struct.unpack(">I", d[i:i + 4])[0]
        typ, body = d[i + 4:i + 8], d[i + 8:i + 8 + n]
        out += d[i:i + 8] + body + struct.pack(">I", zlib.crc32(typ + body) & 0xffffffff)
        i += 12 + n
    return Image.open(io.BytesIO(out)).convert("RGB")


def trace(im, want):
    """The screen row of a channel's trace at every column, by its colour
    (CH4 blue, CH2 cyan), NaN where the trace is not drawn."""
    a = np.asarray(im).astype(int)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    m = (b > 150) & (r < 120) & (g < 150) if want == "blue" else (g > 150) & (b > 150) & (r < 120)
    m[:47, :] = False
    m[430:, :] = False
    m[:, :84] = False
    m[:, 684:] = False
    return np.array([np.flatnonzero(m[:, x]).mean() if m[:, x].any() else np.nan for x in range(a.shape[1])])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bridge", help="host:port of the Pi's serial bridge")
    ap.add_argument("--scope", help="the scope's address")
    ap.add_argument("--no-walk", action="store_true")
    ap.add_argument("--no-scope", action="store_true")
    ap.add_argument("--poll-seconds", type=float, default=20.0)
    ap.add_argument("--hands", choices=["manual", "head"], help="also check reset and power, by your hand or the Pi's")
    ap.add_argument("--pi", help="user@host of the Pi, for --hands head (default: the bridge's host)")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    bu = load(ROOT / "tools" / "bringup.py", "bringup")
    rows, result = [], {"at": time.strftime("%Y-%m-%d %H:%M %Z"), "checks": []}

    def check(name, state, detail):
        rows.append((name, state, detail))
        result["checks"].append({"check": name, "state": state, "detail": detail})

    # bridge
    baddr = bridge_address(a.bridge)
    if not baddr:
        sys.exit("no bridge address: pass --bridge HOST:6545, set $BRIDGE, or put it in bench.local.md")
    try:
        br = Bridge(baddr)
    except OSError as e:
        check("bridge", "FAIL", f"cannot connect: {e}")
        return finish(rows, result)
    br.send("STATUS")
    lines = br.read(1.0)
    banner = [l for l in lines if l.startswith("#")]
    check("bridge", "PASS" if banner else "FAIL", banner[0] if banner else f"no banner in {len(lines)} lines")

    # scope
    sc = None
    if not a.no_scope:
        saddr = bu.scope_address(a.scope)
        if not saddr:
            check("scope", "SKIP", "no address (pass --scope, set $SCOPE, or bench.local.md)")
        else:
            try:
                sc = Scope(saddr)
                idn = sc.ask("*IDN?")
                check("scope", "PASS" if "DS1" in idn else "FAIL", idn or "no answer to *IDN?")
            except OSError as e:
                check("scope", "FAIL", f"cannot connect: {e}")
                sc = None

    # the head's power: with the front switch off the console is dark until
    # K1 closes, so --hands head closes it first and puts it back after
    pi = a.pi or baddr.rsplit(":", 1)[0]
    k1_was = None
    if a.hands == "head":
        r = subprocess.run(["ssh", "-o", "ConnectTimeout=8", "-o", "BatchMode=yes", pi,
                            # 12 s, not 6: two polls of 1199 carried nine clocks when the
                            # window opened 6 s after the relay powered the console
                            # (MEASURED 2026-09-17; four later windows, 4886 polls, all
                            # eight). The gate stays strict and the game gets to boot.
                            "pinctrl get 27; pinctrl set 27 op dh; sleep 12"], capture_output=True, text=True, timeout=60)
        k1_was = "hi" if "| hi" in r.stdout else "lo" if "| lo" in r.stdout else None
        result["k1_found"] = k1_was
        print(f"  console powered from the Pi, GPIO27 high (it was {k1_was}); waiting for the game")

    # polls: MODE PASS, the console's own polling through the bridge
    br.send("MODE PASS")
    br.send("RESET")
    br.read(0.5)
    lines = br.read(a.poll_seconds)
    polls = [int(l.split()[3]) for l in lines if l.startswith("L ") and len(l.split()) == 4]
    console = bool(polls)
    if not polls:
        check("polls", "SKIP", f"no polls in {a.poll_seconds:.0f} s: the console is off or no game is polling")
    else:
        hist = Counter(polls)
        eights = hist.get(8, 0)
        ok = eights == len(polls) and len(polls) >= 50 * a.poll_seconds
        check("polls", "PASS" if ok else "FAIL",
              f"{len(polls)} polls in {a.poll_seconds:.0f} s ({len(polls) / a.poll_seconds:.1f}/s), clocks per poll {dict(sorted(hist.items()))}")
        result["polls"] = {"n": len(polls), "hist": {int(k): int(v) for k, v in sorted(hist.items())}}

    keys = (":TRIGger:EDGe:SOURce", ":TRIGger:EDGe:SLOPe", ":TRIGger:EDGe:LEVel", ":TRIGger:SWEep", ":TIMebase:MAIN:SCALe",
            ":TIMebase:MAIN:OFFSet", ":CHANnel1:DISPlay", ":CHANnel2:DISPlay", ":CHANnel3:DISPlay", ":CHANnel4:DISPlay",
            ":CHANnel1:SCALe", ":CHANnel1:OFFSet", ":CHANnel2:SCALe", ":CHANnel2:OFFSet", ":CHANnel4:SCALe", ":CHANnel4:OFFSet")
    if sc is not None:
        sc.save(keys)
    try:
        # trigger: TRIG n stops the scope on CH1
        if sc is None:
            check("trigger", "SKIP", "no scope")
        elif not console:
            check("trigger", "SKIP", "no polls, so no latch for TRIG to land on")
        else:
            for c in (":STOP", ":CHANnel1:DISPlay ON", ":CHANnel1:PROBe 1", ":CHANnel1:COUPling DC", ":CHANnel1:SCALe 1",
                      ":CHANnel1:OFFSet -2", ":TRIGger:MODE EDGE", ":TRIGger:EDGe:SOURce CHANnel1", ":TRIGger:EDGe:SLOPe POSitive",
                      ":TRIGger:EDGe:LEVel 2.5", ":TRIGger:SWEep SINGle", ":TIMebase:MAIN:SCALe 0.005", ":TIMebase:MAIN:OFFSet 0.02",
                      ":RUN"):
                sc.cmd(c)
            time.sleep(0.5)
            sc.cmd(":SINGle")
            time.sleep(0.5)
            br.send("RESET")
            br.send("TRIG 20")
            fired = False
            for _ in range(20):
                if sc.ask(":TRIGger:STATus?") == "STOP":
                    fired = True
                    break
                time.sleep(0.5)
            check("trigger", "PASS" if fired else "FAIL", "TRIG 20 stopped the scope on CH1" if fired else "the scope did not stop: R1, the lead to CH1, or the level (2.5 V rising)")

        # the walk
        if a.no_walk:
            check("walk", "SKIP", "--no-walk")
        elif sc is None:
            check("walk", "SKIP", "no scope")
        elif not console:
            check("walk", "SKIP", "no polls: the console clocks the register")
        else:
            sc.cmd(":CHANnel3:DISPlay OFF")
            sc.cmd(":CHANnel1:DISPlay OFF")
            for ch in (2, 4):
                for c in (f":CHANnel{ch}:DISPlay ON", f":CHANnel{ch}:PROBe 1", f":CHANnel{ch}:SCALe 1", f":CHANnel{ch}:OFFSet -2", f":CHANnel{ch}:COUPling DC"):
                    sc.cmd(c)
            for c in (":TRIGger:MODE EDGE", ":TRIGger:EDGe:SOURce CHAN2", ":TRIGger:EDGe:SLOPe NEGative", ":TRIGger:EDGe:LEVel 2.5",
                      ":TRIGger:SWEep SINGle", ":TIMebase:MAIN:SCALe 0.00002", ":TIMebase:MAIN:OFFSet 0.00008"):
                sc.cmd(c)
            br.send("MODE INJECT")
            br.read(0.3)
            res, wrong, missing, retaken = {}, [], [], []

            timing = {"first": FIRST_US, "period": PERIOD_US, "from": "authored 2026-09-15"}

            def read_byte(byte, path):
                """One poll: the scope stopped on the latch's fall, D0 read
                at the middle of each of the eight bit slots. Returns the
                pressed bits, or None when the scope did not stop.

                The slots come from the capture's own D0 transitions when
                it has enough of them (55 and aa alternate every bit, so
                they always do): every transition sits on a clock edge, so
                the median gap is the clock period and the first one is the
                first slot boundary. A byte with few transitions uses the
                last timing measured in this run."""
                sc.cmd(":SINGle")
                time.sleep(0.9)
                if sc.ask(":TRIGger:STATus?") != "STOP":
                    return None
                sc.shot(path)
                im = load_png(path)
                d0, latch = trace(im, "blue"), trace(im, "cyan")
                low = [x for x in range(84, 684) if not np.isnan(latch[x]) and latch[x] < TRACE_LOW_Y]
                fall = max(low) if low else 144
                lvl = np.where(np.isnan(d0), np.nan, (d0 < TRACE_LOW_Y).astype(float))
                valid = ~np.isnan(lvl)

                # every transition after the latch's fall, in us from it
                edges = [(x - fall) / PX_PER_US for x in range(fall + 2, 684)
                         if valid[x] and valid[x - 1] and lvl[x] != lvl[x - 1]]
                inside = [e for e in edges if 2.0 < e < 160.0]
                # Every transition sits on a clock edge, so the clock is the
                # (first, period) that explains all of them: a search over
                # both, scored by how close each transition lands to a clock.
                # A median of the gaps is not enough (on a byte whose bits do
                # not alternate a gap is several clocks, and even on 55 a
                # median put the last two samples on a slot boundary,
                # 2026-09-17). Five transitions is the floor; a byte with
                # fewer keeps the last clock measured in this run.
                if len(inside) >= 5:
                    best = None
                    for per in np.arange(8.0, 16.01, 0.05):
                        for fst in np.arange(3.0, 26.01, 0.25):
                            clocks = fst + per * np.arange(8)
                            err = sum(min(abs(e - c) for c in clocks) for e in inside)
                            if best is None or err < best[0]:
                                best = (err, fst, per)
                    err, fst, per = best
                    if err / len(inside) < 1.5:      # us of slop per transition
                        timing.update(first=float(fst), period=float(per),
                                      **{"from": f"fitted on {byte}, {err / len(inside):.2f} us per edge"})
                first, period = timing["first"], timing["period"]
                mids = [first / 2.0] + [first + (k + 0.5) * period for k in range(7)]

                def level_at(us):
                    x = int(round(fall + us * PX_PER_US))
                    v = [lvl[i] for i in range(x - 1, x + 2) if 0 <= i < len(lvl) and valid[i]]
                    return int(round(np.mean(v))) if v else None
                bits = [level_at(m) for m in mids]
                return [i for i, v in enumerate(bits) if v == 0]

            for byte in WALK:
                br.send(f"SET {byte}")
                br.read(0.3)
                want = [i for i in range(8) if int(byte, 16) >> i & 1]
                # The game does not clock every poll alike: one poll in a
                # walk of fifteen came with its eight clocks in 68 us
                # against the usual 98 (MEASURED 2026-09-15 23:40, ten
                # captures of the same bytes all at 98), which lands the
                # last mid-slot samples past the eighth clock. A byte that
                # differs is taken again; the register is judged on a
                # second poll, and the retake is reported.
                pressed = None
                for attempt in range(3):
                    got = read_byte(byte, OUT / f"walk-{byte}.png")
                    if got is None:
                        continue
                    if attempt:
                        retaken.append(byte)
                    pressed = got
                    if pressed == want:
                        break
                if pressed is None:
                    missing.append(byte)
                    continue
                res[byte] = {"pressed": pressed, "want": want}
                if pressed != want:
                    wrong.append(f"{byte}: read {pressed}, set {want}")
            result["walk"] = res
            result["walk_retaken"] = retaken
            result["walk_timing"] = dict(timing)
            n_ok = sum(1 for v in res.values() if v["pressed"] == v["want"])
            note = (f", slots {timing['period']:.1f} us from {timing['first']:.1f} us ({timing['from']})"
                    + (f", retaken: {', '.join(retaken)}" if retaken else ""))
            if not wrong and not missing:
                check("walk", "PASS", f"{n_ok} of {len(WALK)} bytes read back as set, D0 at the eight mid-slots off the screen{note}")
            else:
                check("walk", "FAIL", f"{n_ok} of {len(WALK)} right" + (f"; no trigger for {missing}" if missing else "") + (f"; {'; '.join(wrong)}" if wrong else "") + note)
        # the hands
        if not a.hands:
            check("reset", "SKIP", "not asked: --hands manual or --hands head")
            check("power", "SKIP", "not asked: --hands manual or --hands head")
        elif not console:
            check("reset", "SKIP", "no polls: a reset shows as a gap in them")
            check("power", "SKIP", "no polls: a power cycle shows as a gap in them")
        else:
            br.send("MODE PASS")
            br.read(0.5)
            for name, lo, hi, manual, head, wait in (
                    ("reset", 1.0, 12.0, "press the console's RESET button and HOLD it for two full seconds",
                     "sleep 3; pinctrl set 17 op dh; sleep 2; pinctrl set 17 op dl", 15.0),
                    ("power", 1.5, 20.0, "throw the console's POWER switch off, count three, and back on",
                     "sleep 3; pinctrl set 27 op dl; sleep 3; pinctrl set 27 op dh", 30.0)):
                if a.hands == "manual":
                    print(f"\n  {name}: {manual}, any time in the next {wait:.0f} s (listening now)")
                    gap, resumed, n = poll_gap(br, wait)
                    how = "by hand"
                else:
                    proc = subprocess.Popen(["ssh", "-o", "ConnectTimeout=8", "-o", "BatchMode=yes", pi, head],
                                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    gap, resumed, n = poll_gap(br, wait)
                    _out, err = proc.communicate(timeout=30)
                    how = f"from the Pi's GPIO{'17' if name == 'reset' else '27'}"
                    if proc.returncode != 0:
                        check(name, "FAIL", f"the Pi could not drive the pin: {err.strip()[:160]}")
                        continue
                if gap is None:
                    check(name, "FAIL", f"no pause in the polls in {wait:.0f} s ({n} polls): nothing happened {how}")
                elif not (lo <= gap <= hi):
                    check(name, "FAIL", f"polls paused {gap:.2f} s {how}, expected {lo:g} to {hi:g} s")
                elif not resumed:
                    check(name, "FAIL", f"polls stopped after {gap:.2f} s {how} and did not resume in {wait:.0f} s")
                else:
                    check(name, "PASS", f"polls paused {gap:.2f} s {how} and resumed ({n} polls in {wait:.0f} s)")
    finally:
        if k1_was is not None:
            subprocess.run(["ssh", "-o", "ConnectTimeout=8", "-o", "BatchMode=yes", pi,
                            f"pinctrl set 27 op d{'h' if k1_was == 'hi' else 'l'}"], capture_output=True, text=True, timeout=30)
            print(f"  GPIO27 put back {k1_was} (the console {'on' if k1_was == 'hi' else 'off'})")
        br.send("MODE PASS")
        br.send("RESET")
        br.read(0.3)
        br.close()
        if sc is not None:
            sc.restore()
            for c in (":CHANnel1:DISPlay ON", ":CHANnel2:DISPlay ON", ":CHANnel3:DISPlay ON", ":CHANnel4:DISPlay ON", ":RUN"):
                sc.cmd(c)
    return finish(rows, result)


def poll_gap(br, seconds, bin_s=0.25, quiet=3):
    """Listen to the bridge for `seconds` and return (the longest pause
    in the polls, whether polls came after it, the poll count). The Pi's
    bridge hands lines over in batches about every 100 ms, so arrival
    times cannot see the 17 ms cadence (MEASURED 2026-09-16 00:10: a
    0.1 s "gap" every batch, and one of 0.4 s); the polls are counted per
    quarter second instead, fifteen a bin when the game runs, and a run
    of bins with fewer than `quiet` is the pause. A running game never
    goes quiet that long; a held reset or a power cycle does."""
    n_bins = int(seconds / bin_s) + 1
    bins = [0] * n_bins
    t0, end, count = time.time(), time.time() + seconds, 0
    while time.time() < end:
        for l in br.read(0.1):
            if l.startswith("L ") and len(l.split()) == 4:
                k = min(int((time.time() - t0) / bin_s), n_bins - 1)
                bins[k] += 1
                count += 1
    # the longest run of quiet bins, with polls before and after it
    best, run, start, best_start = 0, 0, 0, None
    for k, c in enumerate(bins):
        if c < quiet:
            if run == 0:
                start = k
            run += 1
            if run > best:
                best, best_start = run, start
        else:
            run = 0
    if best < 2:         # one quiet bin is a late batch from the bridge, not the console
        return None, True, count
    after = sum(bins[best_start + best:])
    before = sum(bins[:best_start])
    if before == 0:      # quiet from the start is not a pause, the console was off
        return None, after > 0, count
    return best * bin_s, after > 0, count


def finish(rows, result):
    w = max(len(r[0]) for r in rows)
    print()
    for name, state, detail in rows:
        print(f"  {name:<{w}}  {state}  {detail}")
    bad = [r for r in rows if r[1] == "FAIL"]
    skipped = [r for r in rows if r[1] == "SKIP"]
    print(f"\n{'no regression' if not bad else str(len(bad)) + ' regression(s)'}"
          + (f", {len(skipped)} skipped ({'; '.join(r[0] for r in skipped)})" if skipped else ""))
    (OUT / "last-check.json").write_text(json.dumps(result, indent=1) + "\n")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
