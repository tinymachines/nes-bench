#!/usr/bin/env python3
"""Two poll logs, latch for latch: the part's (tools/sniff.py) and the
model's (nes-console's pad-log example), both `L n hh c` lines.

  python3 tools/compare-logs.py part.log model.log [--from N] [--to N]

Prints each side's histogram of clocks per poll, the latches where the
clocks differ and where the bytes differ, and the first divergence of
each kind. Exit 1 if either differs within the compared range. A log
that has no polls at all is refused by name: a comparison of nothing
passes on nothing.
"""
import argparse
import collections
import sys


def read(path):
    polls = {}
    for line in open(path):
        f = line.split()
        if len(f) == 4 and f[0] == "L":
            polls[int(f[1])] = (int(f[2], 16), int(f[3]))
    return polls


def hist(polls):
    return dict(sorted(collections.Counter(c for _, c in polls.values()).items()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("part")
    ap.add_argument("model")
    ap.add_argument("--from", dest="lo", type=int, default=0)
    ap.add_argument("--to", dest="hi", type=int, default=None)
    a = ap.parse_args()
    p, m = read(a.part), read(a.model)
    for name, polls in (("part", p), ("model", m)):
        if not polls:
            print(f"{name}: no polls in the log; nothing to compare")
            return 2
        print(f"{name}: {len(polls)} polls, latches {min(polls)}..{max(polls)}, clocks per poll {hist(polls)}")
    hi = a.hi if a.hi is not None else min(max(p), max(m))
    idx = [n for n in range(a.lo, hi + 1) if n in p and n in m]
    if not idx:
        print("no latch index is in both logs within the range")
        return 2
    clocks_diff = [n for n in idx if p[n][1] != m[n][1]]
    bytes_diff = [n for n in idx if p[n][0] != m[n][0]]
    print(f"compared latches {idx[0]}..{idx[-1]} ({len(idx)} present on both sides)")
    for label, d in (("clocks", clocks_diff), ("bytes", bytes_diff)):
        if d:
            n = d[0]
            print(f"{label} differ at {len(d)} latch(es), first at {n}: part {p[n][0]:02x}/{p[n][1]} model {m[n][0]:02x}/{m[n][1]}; all: {d[:40]}{' ...' if len(d) > 40 else ''}")
        else:
            print(f"{label} agree on every compared latch")
    return 1 if clocks_diff or bytes_diff else 0


if __name__ == "__main__":
    sys.exit(main())
