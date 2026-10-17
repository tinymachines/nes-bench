#!/usr/bin/env python3
"""PLAN: a schedule for Super Mario Bros. searched on the model, then
played on the part (docs/bench-language.md, "Learning to play").

  python3 tools/plan.py rom.nes --out plan.txt [--seg 30] [--look 60] [--jobs 6] [--until 2600]

The bench answers a decision in about a second and a half, ninety
polls, so it cannot react to the game; it plays a schedule. This finds
one. The model (nes-console's `watch` example) plays a bench script
exactly as the head plays it on the part, and reports bytes of RAM at
every latch. The search commits the schedule a segment at a time: for
each segment of SEG latches it tries every move below, each followed
by LOOK latches of running right (so a move that only dies a moment
later loses), and keeps the one that ends furthest right with Mario
still alive. Every candidate replays from power-on, because the model
has no saved state; that costs about ten seconds each, run JOBS at a
time.

What it reads, each measured on the model against a known script on
2026-10-17 before it was trusted (run 20261017-201424's schedule):
$0770 the mode (1 playing), $006D and $0086 the position in the level
(page and x), $000E the player's state (8 normal), $00B5 the vertical
screen (1 on screen, more is a fall), $075A the lives, $0760 the area.
$000E 04 and 05 are the flagpole and the walk to the castle (measured
on the planned 1-1); any other state after play has begun, a fall off
the screen or a lost life counts as dead (the death codes themselves
are not yet measured).

The schedule it writes is a bench script: the start recipe, then AT
lines. The UNO holds 600 entries; this refuses to write more.
"""
import argparse
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WATCH = ["0770", "000e", "00b5", "006d", "0086", "075a", "0760", "001d"]
START = """POWER ON
WAIT 5 S
MODE INJECT
SET 00
RESET
WAIT 5 S
RESET
AT 200 08
AT 202 00
AT 330 08
AT 332 00
"""
# The moves for one segment: a list of (offset, byte) inside it. A jump
# is a fresh press of A (Right+B first, so A is released before it) at
# one of three points in the segment, held for j latches.
def moves(seg):
    m = {"run": [(0, 0x82)], "walk": [(0, 0x80)], "stop": [(0, 0x00)], "back": [(0, 0x42)]}
    for at in (0, seg // 3, 2 * seg // 3):
        for j in (6, 14, 24):
            m[f"jump{j}@{at}"] = [(0, 0x82), (at + 2, 0x83), (at + 2 + j, 0x82)]
    return m


class Model:
    def __init__(self, rom, nes):
        self.rom = rom
        self.exe = Path(nes) / "target" / "release" / "examples" / "watch"
        if not self.exe.exists():
            sys.exit(f"build it first: cargo build --release -p nes-console --example watch (in {nes})")

    def play(self, schedule, end):
        """Run the start recipe and the schedule [(latch, byte)] to latch
        `end`; return the rows {latch: [bytes in WATCH order]}."""
        text = START + "".join(f"AT {n} {b:02x}\n" for n, b in schedule)
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write(text)
            path = f.name
        try:
            last = max([n for n, _ in schedule] + [332])
            env = dict(os.environ, WATCH=",".join(WATCH))
            out = subprocess.run([str(self.exe), self.rom, path, str(max(0, end - last))],
                                 capture_output=True, text=True, env=env, check=True).stdout
        finally:
            os.unlink(path)
        rows = {}
        for line in out.splitlines():
            if line.startswith("W "):
                p = line.split()
                rows[int(p[1])] = [int(x, 16) for x in p[2:]]
        return rows


def judge(rows, since, lives0):
    """(alive, x, latch of death or None, area) over the rows from `since`."""
    x = area = 0
    playing = False   # the intro's "WORLD 1-1" screen holds $000E at 0 first
    for k in sorted(r for r in rows if r >= since):
        mode, state, vscreen, page, px, lives, ar, _air = rows[k]
        x, area = page * 256 + px, ar
        if mode != 1:
            continue
        if state == 0x08:
            playing = True
        if not playing:
            continue
        if lives < lives0 or vscreen > 1:
            return False, x, k, area
        if state in (0x04, 0x05):
            # MEASURED 2026-10-17 on the model, the planned 1-1: 04 is the
            # flagpole's slide (x 3161), 05 the walk to the castle, and the
            # area turns to 1-2 about 600 latches later. The level's end.
            return True, x, None, area + 1
        if state != 0x08:
            return False, x, k, area
    return True, x, None, area


def collapse(schedule):
    """Drop entries that repeat the byte already held."""
    out, held = [], None
    for n, b in sorted(schedule):
        if b != held:
            out.append((n, b))
            held = b
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom")
    ap.add_argument("--out", required=True)
    ap.add_argument("--nes", default=str(ROOT.parent / "nes"))
    ap.add_argument("--seg", type=int, default=30)
    ap.add_argument("--look", type=int, default=60)
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--first", type=int, default=480, help="the latch play begins from")
    ap.add_argument("--until", type=int, default=3000)
    ap.add_argument("--backtracks", type=int, default=40)
    a = ap.parse_args()
    model = Model(a.rom, a.nes)

    base = model.play([(a.first, 0x82)], a.first + 1)
    lives0 = base[max(base)][5]
    area0 = base[max(base)][6]
    mv = moves(a.seg)

    def ranked(schedule, t):
        """The moves at segment t, best first, dropping any that die inside
        the segment itself; one that dies only in the lookahead ranks
        below every one that lives through it."""
        cands = {n: schedule + [(t + o, b) for o, b in m] for n, m in mv.items()}
        tail = t + a.seg
        for n in cands:
            cands[n] = cands[n] + [(tail, 0x82)] if all(k < tail for k, _ in cands[n][len(schedule):]) else cands[n]
        with ThreadPoolExecutor(a.jobs) as ex:
            res = dict(zip(cands, ex.map(lambda s: judge(model.play(collapse(s), tail + a.look), a.first, lives0), cands.values())))
        keep = [n for n, r in res.items() if r[0] or r[2] > tail]
        keep.sort(key=lambda n: (res[n][3], res[n][0], res[n][1], n == "run"), reverse=True)
        return keep, res

    # depth-first: frames of (t, schedule before it, the moves still to try)
    stack = []
    schedule, t, backs, done = [], a.first, 0, False
    while t < a.until and not done:
        keep, res = ranked(schedule, t)
        line = ", ".join(f"{n} {r[1]}" + ("" if r[0] else f" dead@{r[2]}") for n, r in sorted(res.items(), key=lambda kv: -kv[1][1])[:6])
        while not keep:
            if not stack or backs >= a.backtracks:
                sys.exit(f"latch {t}: no move lives and nothing left to back up to ({backs} backtracks)")
            backs += 1
            t, schedule, keep, res = stack.pop()
            print(f"  back to latch {t} (backtrack {backs}), trying {keep[0] if keep else 'nothing'}", flush=True)
        best = keep[0]
        stack.append((t, schedule, keep[1:], res))
        r = res.get(best)
        print(f"latch {t}: {best} -> x {r[1]}" + ("" if r[0] else f" (dies at {r[2]} in the lookahead)") + f"   [{line}]", flush=True)
        schedule = schedule + [(t + o, b) for o, b in mv[best]]
        if r[3] != area0:
            print(f"the level is done at about latch {t}")
            done = True
        t += a.seg
    sched = collapse(schedule + [(t + a.seg, 0x00)])
    if len(sched) > 600:
        sys.exit(f"{len(sched)} entries: the UNO holds 600")
    last = max(n for n, _ in sched)
    body = START + "".join(f"AT {n} {b:02x}\n" for n, b in sched) + f"WAIT {last + 60}\nPOWER OFF\n"
    Path(a.out).write_text(f"# planned on the model by tools/plan.py, segments of {a.seg}, lookahead {a.look}\n" + body)
    print(f"wrote {a.out}: {len(sched)} entries, to latch {last}")


if __name__ == "__main__":
    main()
