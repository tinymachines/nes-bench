#!/usr/bin/env python3
"""PLAN: a schedule for Super Mario Bros. searched on the model, then
played on the part (docs/bench-language.md, "Learning to play").

  python3 tools/plan.py rom.nes --out plan.txt [--prefix script.txt] --first N
                        [--seg 30] [--look 60] [--jobs 6] [--until N] [--backtracks 60]

The bench answers a decision in about a second and a half, ninety
polls, so it cannot react to the game; it plays a schedule. This finds
one on the model and writes it as a bench script.

The model is nes-console's `branch` example: a console kept running in
a process, saved and loaded through `Console::save_state`. The search
commits the schedule a segment at a time. For each segment of SEG
latches it loads the segment's saved state, tries every move below,
each followed by LOOK latches of running right (so a move that only
dies a moment later ranks low), and keeps the one that ends furthest on
with Mario alive; the state after the chosen move is saved as the next
segment's start. When every move at a segment dies, it backs up to the
previous segment and takes that one's next best (depth first). A
candidate costs its own latches, about 0.6 s, where a replay from
power-on cost ten (the first version of this, 2026-10-17, which
cleared 1-1 in about seventy-five minutes).

--prefix is a bench script played before the search (the start recipe
and any schedule already planned, e.g. 1-1's for planning 1-2); its
WAIT n and POWER OFF lines are ignored. --first is the latch the search
starts at.

What it reads, each measured on the model on 2026-10-17: $0770 the mode
(1 playing), $006D and $0086 the position in the area (page and x),
$0760 the area within the level (1-2's intro is 1, its underground 2),
$000E the player's state, $00B5 the vertical screen, $075A the lives.
The states, measured: 08 under control; 0B hit (Mario's first goomba,
latch 628), then off the screen (vertical screen 2 to 4), then 06, then
the life is gone; 07 the game walking him in (1-2's intro); 04 the
flagpole's slide and 05 the walk to the castle (the planned 1-1). Dead
is 0B or 06, the vertical screen past 1, or a life lost; 04 or 05 is the
level done, and so is $075C or $075F (the level, the world) changing,
which is how a castle ends ($0770 turning 2 at the axe, measured on 1-4,
is the first sign of it); anything else is the game moving him and is
waited through.

Moves stay inside their segment, because the console's schedule and the
UNO's must both be in increasing latch order: a jump's release that
would fall past the segment's end is left to the next segment's first
byte. `hold` keeps A held across the boundary, so a jump can be longer
than a segment.

Two things the first save-state run taught (1-1, 2026-10-17): running
right alone is too narrow a lookahead (near a gap every move "dies" in
it), so the lookahead is the best of three continuations; and standing
still always lives, so a branch that gains under STALL_PX in STALL
segments of one area while he is under control (state 08: the walk
into 1-2's exit pipe, state 02, holds him still and is not a stall) is
a dead end and is backed out of. Rising out of 1-2's pipe, state 07,
holds him about 96 latches, and a segment that saw any such state is
not counted.

And from 1-2 the same day: a group of enemies is passed by timing, so a
jump can start every five latches, and a latch backed out of four times
gives up the segment before it too (depth first alone spent eleven
backtracks on one latch whose cause was earlier). The UNO holds 600 entries; this refuses to write more.
"""
import argparse
import os
import queue
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WATCH = ["0770", "000e", "00b5", "006d", "0086", "075a", "0760", "001d", "075c", "075f", "00ce"]
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
DEAD = (0x0B, 0x06)
STALL, STALL_PX = 8, 16   # 8 segments: room to wait for a lift (3-3)
ESCALATE = 4
EXTEND = 150
DONE = (0x04, 0x05)


def taps(seg, every, held, press):
    """A pressed every `every` latches for two, `held` between: a swim."""
    e = []
    for o in range(0, seg, every):
        e += [(o, press), (o + 2, held)] if o + 2 < seg else [(o, press)]
    return e


def moves(seg, swim=False):
    """The moves for one segment: name -> [(offset, byte)], every offset
    inside the segment. With swim, the water's moves too (2-2, measured
    2026-10-18: steady taps hold Mario near the surface, every 6 latches
    level and every 16 sinking slowly, Right moving him about 45 dots in
    30 latches at any rate, no taps sinking him to the floor). Each tap is
    two schedule entries, so the rates are the economical ones."""
    m = {"run": [(0, 0x82)], "walk": [(0, 0x80)], "stop": [(0, 0x00)], "back": [(0, 0x42)], "hold": [(0, 0x83)]}
    for at in range(0, seg, 5):
        for j in (4, 10, 18):
            e = [(0, 0x82), (at + 2, 0x83)]
            if at + 2 + j < seg:
                e.append((at + 2 + j, 0x82))
            name = f"jump{j}@{at}" if at + 2 + j < seg else f"jump@{at}"
            m.setdefault(name, e)
    if swim:
        m.update({
            "swim10": taps(seg, 10, 0x80, 0x81),
            "swim16": taps(seg, 16, 0x80, 0x81),
            "float10": taps(seg, 10, 0x00, 0x01),
            "swimback": taps(seg, 16, 0x40, 0x41),
            "drift": [(0, 0x80)],
        })
    return m


class Worker:
    def __init__(self, exe, rom):
        env = dict(os.environ, WATCH=",".join(WATCH))
        self.p = subprocess.Popen([str(exe), rom], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, env=env, bufsize=1)

    def ask(self, *lines):
        rows = {}
        for line in lines:
            self.p.stdin.write(line + "\n")
            self.p.stdin.flush()
            while True:
                r = self.p.stdout.readline()
                if not r:
                    raise RuntimeError(f"the model stopped on {line!r}")
                if r.startswith("W "):
                    f = r.split()
                    rows[int(f[1])] = [int(x, 16) for x in f[2:]]
                elif r.startswith("OK"):
                    break
                elif r.startswith("ERR"):
                    raise RuntimeError(f"{line!r}: {r.strip()}")
        return rows

    def close(self):
        self.p.stdin.write("QUIT\n")
        self.p.stdin.flush()
        self.p.wait(timeout=10)


def judge(rows, lives0):
    """(alive, done, area, x, latch of death or None, held): held is the
    first state that was not 08 while the game ran, or 08 if Mario was
    his own throughout (the stall rule counts only those)."""
    x = area = 0
    held = 0x08
    piped = 0   # a pipe taken counts above x: past 2-2's exit pipe Mario
                # lands at a smaller x in the same area (measured 2026-10-18)
    level0 = tuple(rows[min(rows)][8:10]) if rows else None
    for k in sorted(rows):
        mode, state, vscreen, page, px, lives, ar, _air, level, world = rows[k][:10]
        if (level, world) != level0:
            # the level or the world moved on: a castle ends with no
            # flagpole (the axe, then the next world), so this is done too
            return True, True, area, x, None, state
        x, area = page * 256 + px, ar
        if mode == 2:
            # MEASURED 2026-10-18 on 1-4: the axe turns $0770 to 2 (the
            # bridge falls, Toad), and back to 1 at the next world
            return True, True, area, x, None, state
        if mode != 1:
            continue
        if state in DEAD or vscreen > 1 or lives < lives0:
            return False, False, area, x, k, state
        if state in DONE:
            return True, True, area, x, None, state
        if state != 0x08 and held == 0x08:
            held = state
        if state in (0x02, 0x03):
            piped = 0.5
    return True, False, area + piped, x, None, held


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom")
    ap.add_argument("--out", required=True)
    ap.add_argument("--prefix", help="a bench script played first (WAIT n and POWER OFF ignored)")
    ap.add_argument("--first", type=int, required=True, help="the latch the search starts at")
    ap.add_argument("--nes", default=str(ROOT.parent / "nes"))
    ap.add_argument("--seg", type=int, default=30)
    ap.add_argument("--look", type=int, default=60)
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--until", type=int, default=99999)
    ap.add_argument("--backtracks", type=int, default=60)
    ap.add_argument("--swim", action="store_true", help="add the water's moves (2-2)")
    ap.add_argument("--beam", type=int, default=0, help="keep this many distinct positions a segment instead of searching depth first (3-3)")
    a = ap.parse_args()
    exe = Path(a.nes) / "target" / "release" / "examples" / "branch"
    if not exe.exists():
        sys.exit(f"build it first: cargo build --release -p nes-console --example branch (in {a.nes})")

    tmp = Path(tempfile.mkdtemp(prefix="plan-"))
    prefix_lines = []
    if a.prefix:
        for line in Path(a.prefix).read_text().splitlines():
            w = line.split("#")[0].split()
            if w and not (w[0] == "WAIT" and len(w) == 2) and w[:2] != ["POWER", "OFF"]:
                prefix_lines.append(line)
    else:
        prefix_lines = START.splitlines()
    pre_ats = [(int(l.split()[1]), int(l.split()[2], 16)) for l in prefix_lines if l.startswith("AT ")]
    (tmp / "prefix.txt").write_text("\n".join(prefix_lines) + "\n")

    workers = [Worker(exe, a.rom) for _ in range(a.jobs)]
    pool = queue.Queue()
    for w in workers:
        pool.put(w)

    def on_worker(fn):
        w = pool.get()
        try:
            return fn(w)
        finally:
            pool.put(w)

    s0 = tmp / f"s{a.first}.state"
    on_worker(lambda w: w.ask(f"SCRIPT {tmp / 'prefix.txt'} {a.first - 1}", f"SAVE {s0}"))
    lives0 = on_worker(lambda w: w.ask(f"LOAD {s0}", f"RUN {a.first}"))[a.first][5]
    mv = moves(a.seg, a.swim)

    # The lookahead: after a move, the best of four ways on (running, a
    # jump at once, a jump a little later, and waiting then jumping), so a
    # move is called deadly only when none of them lives.
    def continuations(t0):
        return [[(t0, 0x82)], [(t0, 0x82), (t0 + 2, 0x83), (t0 + 26, 0x82)], [(t0, 0x82), (t0 + 20, 0x83), (t0 + 44, 0x82)],
                # wait, then go: a lift has to come before the jump to it
                # lives (3-3's mushroom lifts, 2026-10-18)
                [(t0, 0x00), (t0 + 40, 0x82), (t0 + 42, 0x83), (t0 + 66, 0x82)]]

    def better(r):
        return (r[1], r[2], r[0], r[3] if r[0] else r[4] or 0, r[3])

    def evaluate(state, t, entries):
        end = t + a.seg + a.look
        outs = []
        for cont in continuations(t + a.seg):
            cmds = [f"LOAD {state}"] + [f"AT {n} {b:02x}" for n, b in entries + cont] + [f"RUN {end}"]
            # a lookahead that ends with the game holding Mario (a pipe,
            # a cut scene) is run on until he is his own again, so what
            # lies past it counts: 1-2's exit pipe holds him about 75
            # latches, longer than LOOK (measured 2026-10-17)
            cmds += [f"RUN {end + k}" for k in range(30, EXTEND + 1, 30)]
            def run(w):
                rows = w.ask(*cmds[:-(EXTEND // 30)])
                for c in cmds[-(EXTEND // 30):]:
                    last = rows[max(rows)]
                    if last[1] in (0x08,) + DEAD or last[1] in DONE:
                        break
                    rows.update(w.ask(c))
                return rows
            outs.append(judge(on_worker(run), lives0) + (cont,))
        return max(outs, key=better)

    def ranked(state, t):
        cands = {n: [(t + o, b) for o, b in m] for n, m in mv.items()}
        with ThreadPoolExecutor(a.jobs) as ex:
            res = dict(zip(cands, ex.map(lambda e: evaluate(state, t, e), cands.values())))
        # a stall is a dead end: standing still always lives, so a branch
        # that has not gained STALL_PX in STALL segments is given up
        # (only while Mario is his own: in a pipe or a cut scene the game
        # holds him still, and that is not a stall)
        recent = path_x[-STALL:]
        if len(recent) == STALL and recent[-1][0] == recent[0][0] and recent[-1][1] - recent[0][1] < STALL_PX and all(p[2] == 0x08 for p in recent):
            return [], res
        # kept: a move one of whose continuations lives. (Before the
        # lookahead had three continuations, a move that died only in it
        # was kept too; on 1-3 that committed Mario to a gap he was
        # already falling into, 2026-10-17.)
        keep = [n for n, r in res.items() if r[0]]
        # ties go to the move with the fewest schedule entries (the UNO
        # holds 600), then to running
        keep.sort(key=lambda n: (res[n][1], res[n][2], res[n][0], res[n][3], -len(mv[n]), n == "run"), reverse=True)
        return keep, res

    if a.beam > 1:
        # BEAM (3-3, 2026-10-18). Depth first commits to one route a
        # segment at a time, and on 3-3 the low mushroom is a dead end
        # whose way out (up to the middle platform, then the tall column)
        # gains no x, so it never ranked first and was gone by the time
        # every forward move died. Here the BEAM best positions, distinct
        # by area, x and height, are all kept and all expanded.
        beam = [dict(state=s0, chosen=[])]
        t, backs, done, chosen = a.first, 0, False, []
        while t < a.until and not done:
            jobs = [(i, n) for i in range(len(beam)) for n in mv]
            with ThreadPoolExecutor(a.jobs) as ex:
                results = list(ex.map(lambda j: evaluate(beam[j[0]]["state"], t, [(t + o, b) for o, b in mv[j[1]]]), jobs))
            scored = [(j, r) for j, r in zip(jobs, results) if r[0]]
            if not scored:
                sys.exit(f"latch {t}: the beam of {len(beam)} has no move that lives")
            won = [(j, r) for j, r in scored if r[1]]
            if won:
                (i, n), r = max(won, key=lambda jr: -len(mv[jr[0][1]]))
                chosen = beam[i]["chosen"] + [(t + o, b) for o, b in mv[n]] + r[6]
                print(f"latch {t}: {n} (beam {i}) -> area {r[2]} x {r[3]} DONE", flush=True)
                done = True
                break
            scored.sort(key=lambda jr: (jr[1][2], jr[1][3], -len(mv[jr[0][1]])), reverse=True)
            new, seen = [], set()
            for (i, n), r in scored[:a.beam * 6]:
                entries = [(t + o, b) for o, b in mv[n]]
                nxt = tmp / f"b{t + a.seg}-{len(new)}.state"
                rows = on_worker(lambda w: w.ask(f"LOAD {beam[i]['state']}", *[f"AT {k} {b:02x}" for k, b in entries], f"RUN {t + a.seg - 1}", f"SAVE {nxt}"))
                last = rows[max(rows)]
                key = (last[6], (last[3] * 256 + last[4]) // 8, last[10] // 16)
                if key in seen:
                    continue
                seen.add(key)
                new.append(dict(state=nxt, chosen=beam[i]["chosen"] + entries))
                if len(new) == a.beam:
                    break
            (i0, n0), r0 = scored[0]
            print(f"latch {t}: beam {len(new)} kept of {len(scored)} alive; best {n0} -> area {r0[2]} x {r0[3]}", flush=True)
            beam = new
            t += a.seg
    else:
        stack = []
        chosen = []
        path_x = []   # (area, x) after each committed segment, on the current branch
        fails = {}    # latch -> backtracks out of it
        t, state, backs, done = a.first, s0, 0, False
        while t < a.until and not done:
            keep, res = ranked(state, t)
            top = ", ".join(f"{n} {r[3]}" + ("" if r[0] else f" dead@{r[4]}") for n, r in sorted(res.items(), key=lambda kv: -kv[1][3])[:5])
            while not keep:
                if not stack or backs >= a.backtracks:
                    sys.exit(f"latch {t}: no move lives and nothing left to back up to ({backs} backtracks)")
                backs += 1
                fails[t] = fails.get(t, 0) + 1
                t, state, keep, res, chosen, path_x = stack.pop()
                # four failures at one latch: the cause is further back, so
                # give up the segment before as well
                if fails.get(t + a.seg, 0) >= ESCALATE and stack:
                    fails[t + a.seg] = 0
                    t, state, keep, res, chosen, path_x = stack.pop()
                print(f"  back to latch {t} (backtrack {backs}), next {keep[0] if keep else 'nothing'}", flush=True)
            best = keep[0]
            stack.append((t, state, keep[1:], res, chosen, path_x))
            r = res[best]
            entries = [(t + o, b) for o, b in mv[best]]
            chosen = chosen + entries
            path_x = path_x + [(r[2], r[3], r[5])]
            print(f"latch {t}: {best} -> area {r[2]} x {r[3]}" + (" DONE" if r[1] else "") + ("" if r[0] else f" (dies at {r[4]} in the lookahead)") + f"   [{top}]", flush=True)
            if r[1]:
                # the flagpole was reached in the lookahead, so the way there
                # is the continuation that found it: without it the schedule
                # stops short (1-3, 2026-10-17: Mario stood at the end alive)
                chosen = chosen + r[6]
                done = True
                break
            nxt = tmp / f"s{t + a.seg}-{backs}.state"
            on_worker(lambda w: w.ask(f"LOAD {state}", *[f"AT {n} {b:02x}" for n, b in entries], f"RUN {t + a.seg - 1}", f"SAVE {nxt}"))
            state = nxt
            t += a.seg

    for w in workers:
        w.close()
    sched, held = [], None
    release = t + a.seg + a.look + (EXTEND if done else 40)
    for n, b in sorted(pre_ats + chosen + [(release, 0x00)]):
        if b != held:
            sched.append((n, b))
            held = b
    if len(sched) > 600:
        # the UNO holds 600 at once; the head streams the rest (2026-10-18)
        print(f"note: {len(sched)} entries, more than the UNO's 600: the head streams the rest during the run")
    last = max(n for n, _ in sched)
    body = START + "".join(f"AT {n} {b:02x}\n" for n, b in sched if n > 332) + f"WAIT {last + 60}\nPOWER OFF\n"
    Path(a.out).write_text(f"# planned on the model by tools/plan.py, segments of {a.seg}, lookahead {a.look}, {backs} backtracks\n" + body)
    print(f"wrote {a.out}: {len(sched)} entries, to latch {last}" + ("" if done else " (NOT done)"))


if __name__ == "__main__":
    main()
