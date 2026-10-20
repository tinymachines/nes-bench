#!/usr/bin/env python3
"""A short-hold beam from one of plan.py's saved states, for a detour the
level planner's thirty-poll segments never string together: climbing onto a
raised pipe. plan.py's beam ranks by progress to the right, and a climb is
three moves that make none (8-4, 2026-10-20: hit the hidden coin block at
X 2400 from below, stand on it, jump onto the pipe at X 2432 and press
Down). This one ranks by height instead, six polls at a time, and stops at
the pipe's entry; the path it finds is spliced into the planner's .json
sidecar and plan.py resumes from the state it saved.

  python3 tools/plan-climb.py ROM STATE T0 STEPS PHASE [--nes ../nes]

  PHASE reveal  rank standing positions by |x - XB| (under the hidden
                block) and stop when the block's metatile in the block
                buffer (BLK, an address) is no longer HIDDEN and Mario
                stands: the block is now solid
  PHASE climb   rank by height (y, a position in the air penalised two
                tiles so a stand beats the top of a jump) then |x - XP|;
                stop at a pipe entry (state 02 or 03) whose EntrancePage
                is ENTR

Environment: SEG polls a step (6), K positions kept (12), XB, XP, XMAX
(positions past it are dropped), LOOP (a screen-left at or past it is
dropped: a maze check about to fire), BLK (hex), HIDDEN (hex, 5f), ENTR.
Dropped too: a life lost, Mario hurt (his size changed), a fall past the
screen. Writes found.json (the entries as (latch, byte) and the saved
state) in its temporary directory, which it names first.

Used on 8-4 twice: the raised pipe at X 2432 (BLK=0646, XB=2396, XP=2440,
XMAX=2470, LOOP=2432, ENTR=12) and the water pipe at X 3648 (XP=3656,
XMAX=3700, LOOP=3712, ENTR=0), each in under four minutes.
"""
import json, os, subprocess, sys, tempfile, threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

#    0 mode 1 state 2 page 3 px 4 y 5 lives 6 air 7 screen page 8 screen left 9 EntrancePage 10 vscreen 11 size 12 block
W = ["0770", "000e", "006d", "0086", "00ce", "075a", "001d", "071a", "071c", "0751", "00b5", "0756"]
SEG = int(os.environ.get("SEG", "6"))
K = int(os.environ.get("K", "12"))
XB, XP = int(os.environ.get("XB", "0")), int(os.environ.get("XP", "0"))
XMAX, LOOP = int(os.environ.get("XMAX", "99999")), int(os.environ.get("LOOP", "99999"))
BLK = os.environ.get("BLK", "0000")
HIDDEN = int(os.environ.get("HIDDEN", "5f"), 16)
ENTR = int(os.environ.get("ENTR", "0"))
MOVES = {"stop": [0x00], "walk": [0x80], "run": [0x82], "hold": [0x83], "runA2": [0x83, 0x83, 0x82], "walkA": [0x81],
         "left": [0x40], "runleft": [0x42], "leftA": [0x43], "A": [0x01], "down": [0x20], "A2": [0x01, 0x01, 0x00],
         "holdleft": [0x43, 0x43, 0x42], "runA1": [0x83, 0x82, 0x82], "walkA1": [0x81, 0x80, 0x80]}


class Worker:
    def __init__(self, exe, rom):
        self.p = subprocess.Popen([str(exe), rom], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1,
                                  env=dict(os.environ, WATCH=",".join(W + [BLK])))

    def ask(self, *lines):
        last = None
        for line in lines:
            self.p.stdin.write(line + "\n")
            self.p.stdin.flush()
            while True:
                r = self.p.stdout.readline()
                if not r:
                    raise RuntimeError("model stopped")
                if r.startswith("W "):
                    last = [int(x, 16) for x in r.split()[2:]]
                elif r.startswith("OK"):
                    break
                elif r.startswith("ERR"):
                    raise RuntimeError(r)
        return last

    def quit(self):
        self.p.stdin.write("QUIT\n")
        self.p.stdin.flush()


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--nes")]
    nes = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--nes=")), str(Path(__file__).resolve().parent.parent.parent / "nes"))
    rom, state, t0, steps, phase = args[0], args[1], int(args[2]), int(args[3]), args[4]
    exe = Path(nes) / "target" / "release" / "examples" / "branch"
    if not exe.exists():
        sys.exit(f"build it first: cargo build --release -p nes-console --example branch (in {nes})")
    tmp = tempfile.mkdtemp(prefix="plan-climb-")
    print("tmp", tmp)
    workers = [Worker(exe, rom) for _ in range(6)]
    free = list(range(6))
    lock = threading.Lock()

    def on_worker(fn):
        with lock:
            i = free.pop()
        try:
            return fn(workers[i])
        finally:
            with lock:
                free.append(i)

    def stop(found):
        json.dump(found, open(f"{tmp}/found.json", "w"))
        print("FOUND", f"{tmp}/found.json", flush=True)
        for w in workers:
            w.quit()

    v0 = on_worker(lambda w: w.ask(f"LOAD {state}", f"RUN {t0}"))
    lives0, size0 = v0[5], v0[11]
    print(f"start x {v0[2] * 256 + v0[3]} y {v0[4]:02x} lives {lives0} size {size0} block {v0[12]:02x}")
    beam = [dict(state=state, path=[])]
    t = t0
    for step in range(steps):
        jobs = [(i, n) for i in range(len(beam)) for n in MOVES]

        def run(job):
            i, n = job
            bs = MOVES[n]
            ents = [(t + k * (SEG // len(bs)), b) for k, b in enumerate(bs)]
            nxt = f"{tmp}/s{step}-{i}-{n}.state"
            last = on_worker(lambda w: w.ask(f"LOAD {beam[i]['state']}", *[f"AT {a} {b:02x}" for a, b in ents], f"RUN {t + SEG - 1}", f"SAVE {nxt}"))
            return i, n, ents, nxt, last

        with ThreadPoolExecutor(6) as ex:
            res = list(ex.map(run, jobs))
        cands = []
        for i, n, ents, nxt, v in res:
            mode, st, pg, px, y, lives, air, sp, sl, entr, vs, size, blk = v
            x = pg * 256 + px
            scrl = sp * 256 + sl
            path = beam[i]["path"] + ents
            if st in (2, 3):
                print(f"pipe entry at step {step}: x {x} y {y:02x} EntrancePage {entr} {nxt}", flush=True)
                if entr == ENTR:
                    return stop(dict(path=path, state=nxt, t=t + SEG))
                continue
            if mode != 1 or st in (0x0B, 0x06, 0x01) or vs > 1 or lives < lives0 or size != size0 or x > XMAX or scrl >= LOOP:
                continue
            if phase == "reveal":
                if blk != HIDDEN and not air:
                    print(f"revealed at step {step}: x {x} y {y:02x} block {blk:02x} {nxt}", flush=True)
                    return stop(dict(path=path, state=nxt, t=t + SEG))
                key = (abs(x - XB) + (8 if air else 0), y)
            else:
                key = (y + (0x20 if air else 0), abs(x - XP))
            cands.append(dict(state=nxt, path=path, x=x, y=y, air=air, key=key, n=n, blk=blk))
        seen, beam = set(), []
        for c in sorted(cands, key=lambda c: c["key"]):
            k = (c["x"] // 2, c["y"] // 2, c["air"])
            if k in seen:
                continue
            seen.add(k)
            beam.append(c)
            if len(beam) >= K:
                break
        keep = {c["state"] for c in beam}
        for _, _, _, nxt, _ in res:
            if nxt not in keep:
                Path(nxt).unlink(missing_ok=True)
        if not beam:
            print("beam empty at step", step)
            break
        b = beam[0]
        print(f"t {t + SEG}: best x {b['x']} y {b['y']:02x} air {b['air']} block {b['blk']:02x} ({b['n']}); beam {len(beam)} of {len(cands)}", flush=True)
        t += SEG
    for w in workers:
        w.quit()


if __name__ == "__main__":
    main()
