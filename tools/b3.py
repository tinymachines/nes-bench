#!/usr/bin/env python3
"""B3: record and replay. A human's run on the original pad, logged by
the bridge, becomes a script; the script replays on the part and on the
model; captures at chosen latches are scored; the first latch where the
model and the part disagree is found by bisection.

  python3 tools/b3.py record runs/<stamp> -o replay.txt
      The run's bridge.log (MODE PASS, a hand on the pad) as a script:
      MODE INJECT, SET the first byte, an AT at every change, and the
      run's length. Nothing else: RESET, ARM and TRIG are the replay's.

  python3 tools/b3.py replay <head> replay.txt rom.nes --at 300,900,1800 --into runs/replay-a
      The script replayed on the part once per latch named, each replay
      from RESET with one capture triggered at its latch (one per run,
      because reading a record takes seconds while the console runs on
      and a second trigger set late fires late), fetched, and every
      capture scored against the model's frame at that latch
      (b1-score). Prints a row per latch; writes replay.json into the
      directory naming the run of each latch.

  python3 tools/b3.py agree runs/replay-a runs/replay-b rom.nes
      Two replays' captures at the same latches against each other: the
      part against itself. Each is scored against the model to get its
      regions' luma, hue and saturation, and the two readings are
      differenced region for region under B1's tolerances. A game whose
      two replays differ is nondeterministic on the part, and is named.

  python3 tools/b3.py bisect <head> replay.txt rom.nes --lo 0 --hi 3600 [--into runs/]
      The first latch at which a capture disagrees with the model,
      assuming divergence is monotone (a game that has diverged stays
      diverged): a replay with a trigger at the midpoint each step,
      scored; agree moves lo up, disagree moves hi down. About
      log2(hi - lo) replays. Prints the bracket at every step and the
      first divergent latch, with the region that named it.

The replay's script per trigger: the record's lines (RESET among
them), then ARM <name>, TRIG t, WAIT t+20, CAPTURE, the arm first
because it takes seconds of SCPI and a trigger set before it can fire
unheard. The head
plays them; the model plays the same file through capture-score.
It was written against tools/fake-bridge.py and tools/fake-scope.py
--video (the model's own synthesis with a divergence planted at a
latch, found). It met the part on 2026-09-18 with a typed record
(exercise/e3-scripted.txt: the menu, the title, Mario walking and
jumping) and three things changed there: the arm names the bench's
channels and trigger (ARM_ARGS; a bare ARM fell back to EXT, which the
head refuses), the status poll rides out the minute the head is silent
reading a record, and a capture is called the model's by the picture's
correlation (--by picture, below) rather than by B1's region
tolerances, which every real capture misses by its calibration. Two
replays agreed with each other at 400, 800 and 1150, each agreed with
the model, and the bisection over 0..1150 found no divergence in one
replay; the same capture scored against a record with Right dropped
disagrees. A hand's record (MODE PASS, exercise/e3-hand.txt) is the
step still to play.
"""
import argparse
import json
import re
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent

# What each bridge build can hold, from its own firmware's SCHEDULE_MAX
# (firmware/bridge-uno on the ATmega328P's 2 KB, firmware/bridge on the
# C6). Read out of the sources so the two cannot drift.
def _schedule_max():
    out = {}
    for key, rel, pat in (("uno", "firmware/bridge-uno/bridge-uno.ino", r"SCHEDULE_MAX\s*=\s*(\d+)"),
                          ("c6", "firmware/bridge/bridge.ino", r"schedule\[(\d+)\]")):
        m = re.search(pat, (HERE.parent / rel).read_text())
        if m:
            out[key] = int(m.group(1))
    return out


SCHEDULE_MAX = _schedule_max()


def entries_for(bridge, gap):
    """The schedule entries one AT costs, `gap` latches after the one
    before it (or after latch 0). The UNO packs each entry as a one-byte
    gap and the byte, with a filler per 255 latches of a longer gap
    (firmware/bridge-uno/schedule.h, Schedule::cost); the C6 keeps
    absolute latches, one entry an AT."""
    return gap // 255 + 1 if bridge == "uno" else 1

# The capture every replay arms: E2's (exercise/e2-title.txt), the
# bridge's TRIG on CH1 beside the video on CH3 at 200 mV a division. A
# bare `ARM name` falls back to the head's old defaults, whose trigger
# source EXT the DS1054Z does not have and the head refuses by name;
# this tool was written against the fakes before that was known.
ARM_ARGS = "1,3 0.2 -0.5 CH1"

# A replay's frame is the model's on two readings of split-score's
# fourth section (Pearson's r of the decoded luma, blind to the part's
# constant gain and offset). The SCREEN: the coarse shape (30 by 32
# blocks of the frame) against the model's F at least C_MIN. The FRAME:
# at full resolution F no worse than F-1, F+1 or F+2 by more than
# R_TIE, which a still screen passes (its frames are all alike) and a
# scrolling one passes only at the right frame. AUTHORED from the first
# records, 2026-09-18: every true match 0.9968 to 0.9992 coarse (the
# title, the split, the game's black world card, Mario walking), the
# same game thirty frames on 0.72 to 0.78, the replay scored against a
# record with Right dropped 0.66. Full resolution alone could not do the
# screen: the black card, which is small text, reads 0.71 against every
# frame, below the mutant's 0.47 by less than the title's 0.91 is above
# it. B1's region tolerances (--by regions) are the other rule, and
# every real capture misses them by its calibration (E2: hue 3 and 9
# degrees, luma 0.04), so under them the part disagrees at every latch.
C_MIN = 0.99
R_TIE = 0.01


def ask(host, port, req, timeout=5.0):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    s.sendto(json.dumps(req).encode(), (host, port))
    return json.loads(s.recvfrom(65535)[0].decode())


def head_addr(head):
    host, _, port = head.partition(":")
    return host, int(port) if port else 6530


def run_script(head, script, into):
    """Play a script on the head, wait, fetch: the run's directory."""
    host, port = head_addr(head)
    rep = ask(host, port, {"op": "run", "script": script})
    if not rep.get("ok"):
        raise SystemExit(f"the head refused the run: {rep}")
    stamp = rep["stamp"]
    # The head answers no request while it reads a record off the scope
    # (about a minute for 12 M points), so a status that times out is a
    # run still playing, not a dead head; bench.py waits the same way.
    # Found on the part (2026-09-18): the first replay died here and
    # left its run playing, and every call after it was refused.
    while True:
        try:
            if not ask(host, port, {"op": "status"}).get("run"):
                break
        except TimeoutError:
            pass
        time.sleep(0.3)
    subprocess.check_call([sys.executable, str(HERE / "bench.py"), head, "fetch", stamp, "--into", into], stdout=subprocess.DEVNULL)
    out = Path(into) / stamp
    log = (out / "head.log").read_text().strip().splitlines()
    if not log or not log[-1].endswith(" done"):
        raise SystemExit(f"run {stamp} did not finish: {log[-1] if log else '(no head.log)'}")
    return out


# ------------------------------------------------------------------ record
def cmd_record(a):
    log = Path(a.run) / "bridge.log"
    polls = []
    lines = log.read_text().splitlines()
    # The bridge's log carries the session before its RESET (the head
    # drains everything it printed); the record starts at the bridge's
    # acknowledgement, where its latch count is zero. Found on the first
    # hand's record (2026-09-18): latches 364290..1502, the first byte
    # the pad's state from before the run.
    resets = [i for i, l in enumerate(lines) if l.strip() == "# reset"]
    if resets:
        lines = lines[resets[-1] + 1:]
    for line in lines:
        f = line.split()
        if len(f) == 4 and f[0] == "L":
            polls.append((int(f[1]), int(f[2], 16)))
    if a.until is not None:
        # A hand's minute can carry more changes than the bridge holds
        # (the first one, 2026-09-18: 247 over 3603 latches against the
        # UNO's 128): the replay is then of its first part, cut here, and
        # the record says so.
        polls = [(n, b) for n, b in polls if n <= a.until]
    if not polls:
        raise SystemExit(f"{log}: no polls")
    # The record's own way in: the power words before its RESET, so a
    # replay starts from the state the hand's run did. A replay from a
    # bare RESET started from whatever the last run left, which for the
    # multicart is its game's bank: the first hand's replays (2026-09-18)
    # came back up in Super Mario Bros. with no menu, took the menu's
    # presses as the game's, and matched the model's screens a frame off.
    pre = []
    script = Path(a.run) / "script.txt"
    for l in (script.read_text().splitlines() if script.exists() else []):
        w = l.split("#")[0].split()
        if not w:
            continue
        if w[0].upper() == "RESET":
            break
        if w[0].upper() == "POWER" or (w[0].upper() == "WAIT" and len(w) == 3 and w[2].upper() == "S"):
            pre.append(" ".join(w))
    lines = ["# recorded from " + str(a.run)] + pre + ["MODE INJECT", f"SET {polls[0][1]:02x}", "RESET"]
    last = polls[0][1]
    changes = 0
    entries = 0      # what the bridge's RAM holds: see entries_for
    prev_n = 0
    for n, b in polls:
        if b != last:
            lines.append(f"AT {n} {b:02x}")
            entries += entries_for(a.bridge, n - prev_n)
            prev_n = n
            last = b
            changes += 1
    lines.append(f"# {len(polls)} polls, {changes} changes, last latch {polls[-1][0]}")
    Path(a.out).write_text("\n".join(lines) + "\n")
    print(f"wrote {a.out}: {len(polls)} polls, {changes} changes, latches {polls[0][0]}..{polls[-1][0]}")
    # The bridge holds the schedule in RAM and the two builds differ by
    # a factor of sixteen. A record that does not fit is replayed with
    # its tail missing, which looks like a finding about the part, so it
    # is named here rather than discovered later.
    if entries > a.schedule_max:
        print(f"  REFUSED: {changes} changes are {entries} entries, which will not fit the {a.bridge} bridge's {a.schedule_max}-entry schedule.")
        print(f"  Record a shorter run, cut it (--until), or use the C6 build (--bridge c6, {SCHEDULE_MAX['c6']} entries).")
        return 1
    if entries > a.schedule_max * 0.8:
        print(f"  note: {entries} of the {a.bridge} bridge's {a.schedule_max} schedule entries used")
    return 0


# ------------------------------------------------------------------ replay
def replay_script(record, triggers, name_prefix="t", tail=20):
    """The record's lines with a capture at each trigger latch."""
    body = [l for l in record.splitlines() if l.split("#")[0].strip()]
    out = list(body)
    # ARM before TRIG: arming is seconds of SCPI, and a trigger set
    # first can fire before the scope is listening.
    for t in triggers:
        out += [f"ARM {name_prefix}{t} {ARM_ARGS}", f"TRIG {t}", f"WAIT {t + tail}", "CAPTURE"]
    return "\n".join(out) + "\n"


def score(run, rom, capture, nes):
    """b1-score on one capture of a run: (held, rows, summary line)."""
    r = subprocess.run([sys.executable, str(HERE / "b1-score.py"), str(run), rom, capture, "--nes", nes], capture_output=True, text=True)
    rows = {}
    for line in r.stdout.splitlines():
        m = re.match(r"^\$([0-9a-f]{2})\s+(\d)\s+(\d+)\.\.(\d+)\s+(\d+)\.\.(\d+)\s+\|\s+(\S+)\s+(\S+)\s+(\S+)\s+\|\s+(\S+)\s+(\S+)\s+(\S+)\s+\|\s+(\S+)\s+(\S+)\s+(\S+)(\s+MISS)?", line)
        if m:
            key = (m.group(1), m.group(2), m.group(3), m.group(4))
            rows[key] = dict(y=float(m.group(10)), sat=float(m.group(11)), hue=m.group(12), dy=float(m.group(13)), dsat=float(m.group(14)), dhue=float(m.group(15)), miss=bool(m.group(16)))
    summary = next((l for l in r.stdout.splitlines() if "regions within" in l), r.stdout[-300:] + r.stderr[-300:])
    held = bool(rows) and not any(v["miss"] for v in rows.values())
    return held, rows, summary


def picture(run, rom, capture, nes):
    """split-score on one capture of a run: (held, {j: (coarse r, r)}, summary line)."""
    r = subprocess.run([sys.executable, str(HERE / "split-score.py"), str(run), rom, capture, "--nes", nes], capture_output=True, text=True)

    def read(tag):
        line = next((l for l in r.stdout.splitlines() if tag in l), None)
        return {int(j): float(v) for j, v in re.findall(r"F([+-]\d+) (-?[\d.]+|NaN)", line.split("(Pearson r):", 1)[1])} if line else {}
    coarse, full = read("coarse shape"), read("whole picture's luma")
    if 0 not in coarse or 0 not in full:
        return False, {}, (r.stdout[-300:] + r.stderr[-300:]).strip()
    near = max(full.get(j, -1.0) for j in (-1, 1, 2))
    held = coarse[0] >= C_MIN and full[0] >= near - R_TIE
    far = max(full)
    summary = f"screen {coarse[0]:.4f} (F+{far} {coarse.get(far, float('nan')):.4f}); frame r {full[0]:.3f}, best neighbour {near:.3f}"
    return held, {j: (coarse.get(j), full.get(j)) for j in full}, summary


def judge(a, run, capture):
    """(held, summary, first miss or None) under the chosen rule."""
    if a.by == "picture":
        held, _, summary = picture(run, a.rom, capture, a.nes)
        return held, summary, None
    held, rows, summary = score(run, a.rom, capture, a.nes)
    return held, summary, next((k for k, v in rows.items() if v["miss"]), None)


def cmd_replay(a):
    record = Path(a.script).read_text()
    triggers = [int(t) for t in a.at.split(",")]
    manifest = {}
    bad = 0
    for t in triggers:
        run = run_script(a.head, replay_script(record, [t]), a.into)
        manifest[str(t)] = run.name
        held, summary, miss = judge(a, run, f"t{t}")
        print(f"  latch {t} ({run.name}): {'agrees' if held else 'DISAGREES'}: {summary}" + (f"; first miss ${miss[0]} emphasis {miss[1]} rows {miss[2]}..{miss[3]}" if miss else ""))
        bad += not held
    Path(a.into, "replay.json").write_text(json.dumps(dict(script=str(a.script), rom=a.rom, runs=manifest), indent=2))
    return 1 if bad else 0


# ------------------------------------------------------------------- agree
def cmd_agree(a):
    ma = json.loads(Path(a.replay_a, "replay.json").read_text())["runs"]
    mb = json.loads(Path(a.replay_b, "replay.json").read_text())["runs"]
    triggers = sorted(set(map(int, ma)) & set(map(int, mb)))
    if not triggers:
        raise SystemExit("the two replays share no trigger latch")
    tol_y, tol_hue, tol_sat_rel, tol_sat_abs = 0.01, 1.0, 0.05, 0.005
    bad = 0
    for t in triggers:
        _, ra, _ = score(Path(a.replay_a) / ma[str(t)], a.rom, f"t{t}", a.nes)
        _, rb, _ = score(Path(a.replay_b) / mb[str(t)], a.rom, f"t{t}", a.nes)
        keys = sorted(set(ra) & set(rb))
        if not keys:
            print(f"  latch {t}: no region scored on both replays")
            bad += 1
            continue
        worst = None
        for k in keys:
            dy = abs(ra[k]["y"] - rb[k]["y"])
            dsat = abs(ra[k]["sat"] - rb[k]["sat"])
            dhue = 0.0
            if ra[k]["hue"] != "grey" and rb[k]["hue"] != "grey":
                d = (float(ra[k]["hue"]) - float(rb[k]["hue"]) + 180) % 360 - 180
                dhue = abs(d)
            miss = dy > tol_y or dhue > tol_hue or dsat > max(tol_sat_abs, tol_sat_rel * ra[k]["sat"])
            if miss and worst is None:
                worst = (k, dy, dsat, dhue)
        if worst:
            k, dy, dsat, dhue = worst
            print(f"  latch {t}: the two replays DIFFER at ${k[0]} rows {k[2]}..{k[3]}: luma {dy:.4f}, saturation {dsat:.4f}, hue {dhue:.1f} deg")
            bad += 1
        else:
            print(f"  latch {t}: the two replays agree on {len(keys)} regions")
    return 1 if bad else 0


# ------------------------------------------------------------------ bisect
def cmd_bisect(a):
    record = Path(a.script).read_text()
    lo, hi = a.lo, a.hi  # lo agrees (assumed), hi disagrees (checked first)
    print(f"bisecting the first divergent latch in {lo}..{hi}")
    run = run_script(a.head, replay_script(record, [hi]), a.into)
    held, summary, first_miss = judge(a, run, f"t{hi}")
    if held:
        print(f"latch {hi} agrees with the model: no divergence in {lo}..{hi} ({summary})")
        return 0
    steps = 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        run = run_script(a.head, replay_script(record, [mid]), a.into)
        held, summary, miss = judge(a, run, f"t{mid}")
        steps += 1
        if held:
            lo = mid
        else:
            hi = mid
            first_miss = miss or first_miss
        print(f"  step {steps}: latch {mid} {'agrees' if held else 'disagrees'} ({summary}); bracket {lo}..{hi}")
    print(f"first divergent latch: {hi} (latch {lo} agrees), {steps} replays" + (f"; region ${first_miss[0]} rows {first_miss[2]}..{first_miss[3]}" if first_miss else ""))
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    nes_default = str(HERE.parent.parent / "nes")
    r = sub.add_parser("record")
    r.add_argument("run")
    r.add_argument("-o", "--out", required=True)
    r.add_argument("--until", type=int, default=None, help="the record's last latch: a prefix of the run, when all of it will not fit the bridge's schedule")
    r.add_argument("--bridge", choices=sorted(SCHEDULE_MAX), default="uno",
                   help="which bridge will replay this: uno (v1b, the one built first) or c6 (v1)")
    p = sub.add_parser("replay")
    p.add_argument("head")
    p.add_argument("script")
    p.add_argument("rom")
    p.add_argument("--at", required=True)
    p.add_argument("--into", default="runs")
    p.add_argument("--nes", default=nes_default)
    p.add_argument("--by", choices=("picture", "regions"), default="picture",
                   help="how a capture is called the model's: the whole picture's correlation (split-score) or B1's region tolerances")
    g = sub.add_parser("agree")
    g.add_argument("replay_a")
    g.add_argument("replay_b")
    g.add_argument("rom")
    g.add_argument("--nes", default=nes_default)
    b = sub.add_parser("bisect")
    b.add_argument("head")
    b.add_argument("script")
    b.add_argument("rom")
    b.add_argument("--lo", type=int, default=0)
    b.add_argument("--hi", type=int, required=True)
    b.add_argument("--into", default="runs")
    b.add_argument("--nes", default=nes_default)
    b.add_argument("--by", choices=("picture", "regions"), default="picture",
                   help="how a capture is called the model's: the whole picture's correlation (split-score) or B1's region tolerances")
    a = ap.parse_args()
    if getattr(a, "bridge", None):
        a.schedule_max = SCHEDULE_MAX[a.bridge]
    return {"record": cmd_record, "replay": cmd_replay, "agree": cmd_agree, "bisect": cmd_bisect}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
