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
Nothing here has met the part: it has run against tools/fake-bridge.py
and tools/fake-scope.py --video, which serves the model's own
synthesis with an optional divergence planted at a latch, and finds it.
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
    while ask(host, port, {"op": "status"}).get("run"):
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
    for line in log.read_text().splitlines():
        f = line.split()
        if len(f) == 4 and f[0] == "L":
            polls.append((int(f[1]), int(f[2], 16)))
    if not polls:
        raise SystemExit(f"{log}: no polls")
    lines = ["# recorded from " + str(a.run), "MODE INJECT", f"SET {polls[0][1]:02x}", "RESET"]
    last = polls[0][1]
    changes = 0
    for n, b in polls:
        if b != last:
            lines.append(f"AT {n} {b:02x}")
            last = b
            changes += 1
    lines.append(f"# {len(polls)} polls, {changes} changes, last latch {polls[-1][0]}")
    Path(a.out).write_text("\n".join(lines) + "\n")
    print(f"wrote {a.out}: {len(polls)} polls, {changes} changes, latches {polls[0][0]}..{polls[-1][0]}")
    # The bridge holds the schedule in RAM and the two builds differ by
    # a factor of sixteen. A record that does not fit is replayed with
    # its tail missing, which looks like a finding about the part, so it
    # is named here rather than discovered later.
    if changes > a.schedule_max:
        print(f"  REFUSED: {changes} changes will not fit the {a.bridge} bridge's {a.schedule_max}-entry schedule.")
        print(f"  Record a shorter run, or use the C6 build (--bridge c6, {SCHEDULE_MAX['c6']} entries).")
        return 1
    if changes > a.schedule_max * 0.8:
        print(f"  note: {changes} of the {a.bridge} bridge's {a.schedule_max} schedule entries used")
    return 0


# ------------------------------------------------------------------ replay
def replay_script(record, triggers, name_prefix="t", tail=20):
    """The record's lines with a capture at each trigger latch."""
    body = [l for l in record.splitlines() if l.split("#")[0].strip()]
    out = list(body)
    # ARM before TRIG: arming is seconds of SCPI, and a trigger set
    # first can fire before the scope is listening.
    for t in triggers:
        out += [f"ARM {name_prefix}{t}", f"TRIG {t}", f"WAIT {t + tail}", "CAPTURE"]
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


def cmd_replay(a):
    record = Path(a.script).read_text()
    triggers = [int(t) for t in a.at.split(",")]
    manifest = {}
    bad = 0
    for t in triggers:
        run = run_script(a.head, replay_script(record, [t]), a.into)
        manifest[str(t)] = run.name
        held, rows, summary = score(run, a.rom, f"t{t}", a.nes)
        misses = [k for k, v in rows.items() if v["miss"]]
        print(f"  latch {t} ({run.name}): {'agrees' if held else 'DISAGREES'}: {summary}" + (f"; first miss ${misses[0][0]} emphasis {misses[0][1]} rows {misses[0][2]}..{misses[0][3]}" if misses else ""))
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
    held, rows, summary = score(run, a.rom, f"t{hi}", a.nes)
    if held:
        print(f"latch {hi} agrees with the model: no divergence in {lo}..{hi} ({summary})")
        return 0
    steps = 1
    first_miss = next((k for k, v in rows.items() if v["miss"]), None)
    while hi - lo > 1:
        mid = (lo + hi) // 2
        run = run_script(a.head, replay_script(record, [mid]), a.into)
        held, rows, _ = score(run, a.rom, f"t{mid}", a.nes)
        steps += 1
        if held:
            lo = mid
        else:
            hi = mid
            first_miss = next((k for k, v in rows.items() if v["miss"]), first_miss)
        print(f"  step {steps}: latch {mid} {'agrees' if held else 'disagrees'}; bracket {lo}..{hi}")
    print(f"first divergent latch: {hi} (latch {lo} agrees), {steps} replays" + (f"; region ${first_miss[0]} rows {first_miss[2]}..{first_miss[3]}" if first_miss else ""))
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    nes_default = str(HERE.parent.parent / "nes")
    r = sub.add_parser("record")
    r.add_argument("run")
    r.add_argument("-o", "--out", required=True)
    r.add_argument("--bridge", choices=sorted(SCHEDULE_MAX), default="uno",
                   help="which bridge will replay this: uno (v1b, the one built first) or c6 (v1)")
    p = sub.add_parser("replay")
    p.add_argument("head")
    p.add_argument("script")
    p.add_argument("rom")
    p.add_argument("--at", required=True)
    p.add_argument("--into", default="runs")
    p.add_argument("--nes", default=nes_default)
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
    a = ap.parse_args()
    if getattr(a, "bridge", None):
        a.schedule_max = SCHEDULE_MAX[a.bridge]
    return {"record": cmd_record, "replay": cmd_replay, "agree": cmd_agree, "bisect": cmd_bisect}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
