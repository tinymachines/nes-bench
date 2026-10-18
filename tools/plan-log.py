#!/usr/bin/env python3
"""PLAN's level sequence as a visual log (docs/plan-log.md).

  python3 tools/plan-log.py --trace trace.txt [--check]

Draws, into docs/ (flat names, as the roof's pull serves docs/*.svg):
  plan-log-overview.svg   the whole run from power-on: a band per level, Mario's
                 progress through each, the schedule's entries as they
                 accumulate, where the head began to stream
  plan-log-<w>-<l>.svg   one per level: Mario's path through it seen from the side
                 (the level's x across, his height up), held stretches (a
                 pipe, the game walking him) dashed, each jump marked where
                 it began; under it the buttons over the level's latches

and writes the table between the plan-log markers in docs/plan-log.md.

What it reads:
  docs/plan-log.json      the record: per level the measured fields (from
                          the planner's log, the head's run directory and a
                          check of each run's bridge.log) and the authored
                          lesson, labelled as such
  exercise/smb-plan.txt   the schedule itself: the bench script the part
                          played (button bytes only; no ROM content)
  --trace                 the model's replay of that schedule, NOT committed:
                          it is the game's state at every latch, and only the
                          drawn summaries here are published. Regenerate with
                            WATCH=0770,000e,006d,0086,00ce,00b5,075c,075f,0760 \\
                              ../nes/target/release/examples/watch rom.nes \\
                              <schedule without its WAIT/POWER OFF tail> 900 > trace.txt

No picture of the game is drawn or embedded: the grabber's frames of a
commercial cartridge stay off the site. --check redraws into a temporary
directory and fails if any committed file differs.
"""
import argparse
import filecmp
import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs"
PREFIX = "plan-log-"   # flat, as the roof serves docs/*.svg by name
DOC = ROOT / "docs" / "plan-log.md"
RECORD = ROOT / "docs" / "plan-log.json"
FIELDS = ["mode", "state", "page", "x", "y", "vscreen", "level", "world", "area"]
CASTLE = {"1-4", "2-4", "3-4", "4-4", "5-4", "6-4", "7-4", "8-4"}

LIGHT = dict(ink="#1f2328", line="#57606a", fill="#ffffff", tint="#f3f5f7", net="#0a5b9c", warm="#b3261e", ok="#1a7f37")
DARK = dict(ink="#e6edf3", line="#9aa4b2", fill="#0d1117", tint="#161b22", net="#79c0ff", warm="#ff7b72", ok="#3fb950")


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class Svg:
    def __init__(self, w, h, label):
        self.w, self.h, self.label, self.parts = w, h, label, []

    def add(self, s):
        self.parts.append(s)

    def text(self, x, y, s, cls="sub", anchor="start"):
        self.add(f'<text class="{cls}" x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}">{esc(s)}</text>')

    def render(self):
        def rules(c):
            return f"""
      text {{ font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Helvetica, Arial, sans-serif; fill: {c['ink']}; }}
      .title {{ font-size: 14px; font-weight: 600; fill: {c['ink']}; }}
      .sub {{ font-size: 11px; fill: {c['line']}; }}
      .lane {{ font-size: 10px; fill: {c['line']}; }}
      .lvl {{ font-size: 12px; font-weight: 600; fill: {c['ink']}; }}
      .bg {{ fill: {c['fill']}; }}
      .band {{ fill: {c['tint']}; }}
      .axis {{ stroke: {c['line']}; stroke-width: 1; fill: none; }}
      .grid {{ stroke: {c['line']}; stroke-width: 0.5; stroke-dasharray: 2 4; fill: none; }}
      .path {{ stroke: {c['net']}; stroke-width: 1.6; fill: none; stroke-linejoin: round; }}
      .held {{ stroke: {c['line']}; stroke-width: 1.4; fill: none; stroke-dasharray: 3 3; }}
      .jump {{ fill: {c['warm']}; }}
      .entries {{ stroke: {c['ink']}; stroke-width: 1.2; fill: none; }}
      .done {{ fill: {c['ok']}; }}
      .hold {{ fill: {c['net']}; }}
      .holdb {{ fill: {c['line']}; }}
      .tap {{ stroke: {c['warm']}; stroke-width: 1.2; }}
      .stream {{ fill: {c['net']}; opacity: 0.12; }}"""
        style = "\n    <style>" + rules(LIGHT) + "\n      @media (prefers-color-scheme: dark) {" + rules(DARK).replace("\n      ", "\n        ") + "\n      }\n    </style>"
        body = "\n".join(self.parts)
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.w} {self.h}" width="{self.w}" height="{self.h}" '
                f'role="img" aria-label="{esc(self.label)}">{style}\n<rect class="bg" x="0" y="0" width="{self.w}" height="{self.h}"/>\n{body}\n</svg>\n')


def read_trace(path):
    rows = {}
    for line in Path(path).read_text().splitlines():
        if line.startswith("W "):
            f = line.split()
            rows[int(f[1])] = dict(zip(FIELDS, (int(v, 16) for v in f[2:])))
    if not rows:
        sys.exit(f"{path}: no W lines (a watch trace with WATCH={','.join(FIELDS)})")
    return rows


def read_schedule(path):
    return [(int(n), int(b, 16)) for n, b in re.findall(r"^AT (\d+) ([0-9a-fA-F]{2})$", Path(path).read_text(), re.M)]


def held_at(schedule, k):
    b = 0
    for n, v in schedule:
        if n > k:
            break
        b = v
    return b


def level_rows(rows, lv):
    m = lv["measured"]
    return [(k, rows[k]) for k in range(m["first"], m["done"] + 1) if k in rows]


def draw_level(lv, rows, schedule):
    name, m = lv["level"], lv["measured"]
    lr = level_rows(rows, lv)
    # state 00 is the blank between areas, before Mario is placed: not drawn
    pts = [(k, r["page"] * 256 + r["x"], (r["vscreen"] - 1) * 256 + r["y"], r["state"], r["area"])
           for k, r in lr if r["mode"] in (1, 2) and r["state"] != 0x00]
    xmax = max(p[1] for p in pts) or 1
    W, H = 1200, 360
    s = Svg(W, H, f"PLAN, Super Mario Bros. {name}: Mario's path through the level, measured on the model, and the buttons the part was given")
    L, R, T = 60, W - 24, 46
    PH = 170  # the path panel
    s.text(L, 24, f"World {name}", "title")
    s.text(L + 90, 24, f"latches {m['first']} to {m['done']}, {m['entries']} entries in the schedule by its end, "
           f"{m['backtracks']} backtrack{'s' if m['backtracks'] != 1 else ''}; on the part: run {m['run']}, "
           f"{m['polls']} polls, {m['wrong']} wrong", "sub")
    s.add(f'<rect class="band" x="{L}" y="{T}" width="{R - L}" height="{PH}"/>')
    sx = lambda x: L + (R - L) * x / xmax
    ymin, ymax = -40, 260   # screen y: 0 the top, about 0xB0 the ground; a fall goes past 240
    sy = lambda y: T + PH * (min(max(y, ymin), ymax) - ymin) / (ymax - ymin)
    # the path, broken where Mario jumps across the level (a pipe, an area)
    seg, cls = [], None

    def flush():
        if len(seg) > 1:
            s.add(f'<polyline class="{cls}" points="{" ".join(f"{sx(x):.1f},{sy(y):.1f}" for x, y in seg)}"/>')

    last = None
    for k, x, y, st, ar in pts:
        c = "path" if st == 0x08 else "held"
        if last is None or c != cls or abs(x - last[0]) > 40 or ar != last[2]:
            flush()
            seg = [(x, y)] if (last is None or abs(x - last[0]) > 40 or ar != last[2]) else [seg[-1], (x, y)]
            cls = c
        else:
            seg.append((x, y))
        last = (x, y, ar)
    flush()
    # where each jump began: an A press edge, at Mario's place at that latch
    pos = {k: (x, y) for k, x, y, st, ar in pts}
    prev = 0
    jumps = 0
    for n, b in schedule:
        if m["first"] <= n <= m["done"] and b & 0x01 and not prev & 0x01 and n in pos:
            x, y = pos[n]
            s.add(f'<circle class="jump" cx="{sx(x):.1f}" cy="{sy(y) - 6:.1f}" r="2.4"/>')
            jumps += 1
        prev = b
    s.text(L - 8, T + 10, "up", "lane", "end")
    s.text(L - 8, T + PH, "down", "lane", "end")
    s.text(L, T + PH + 14, "0", "lane")
    s.text(R, T + PH + 14, f"x {xmax}", "lane", "end")
    s.text((L + R) / 2, T + PH + 14, "the level's x (the side view, measured on the model)", "lane", "middle")
    # the buttons over the level's latches
    BT = T + PH + 36
    lanes = [("Right", 0x80, "hold"), ("Left", 0x40, "hold"), ("B (run)", 0x02, "holdb"), ("A", 0x01, "tap")]
    span = m["done"] - m["first"] or 1
    tx = lambda k: L + (R - L) * (k - m["first"]) / span
    for i, (lab, bit, cl) in enumerate(lanes):
        y = BT + i * 22
        s.text(L - 8, y + 10, lab, "lane", "end")
        s.add(f'<line class="grid" x1="{L}" y1="{y + 14}" x2="{R}" y2="{y + 14}"/>')
        start = None
        for k in range(m["first"], m["done"] + 2):
            on = k <= m["done"] and held_at(schedule, k) & bit
            if on and start is None:
                start = k
            elif not on and start is not None:
                if cl == "tap":
                    s.add(f'<line class="tap" x1="{tx(start):.1f}" y1="{y + 2}" x2="{tx(start):.1f}" y2="{y + 14}"/>')
                else:
                    s.add(f'<rect class="{cl}" x="{tx(start):.1f}" y="{y + 4}" width="{max(tx(k) - tx(start), 1):.1f}" height="9"/>')
                start = None
    s.text(L, BT + 4 * 22 + 12, f"latch {m['first']}", "lane")
    s.text(R, BT + 4 * 22 + 12, f"latch {m['done']}", "lane", "end")
    s.text((L + R) / 2, BT + 4 * 22 + 12, f"the buttons, one latch a frame; {jumps} press{'es' if jumps != 1 else ''} of A (the dots above: a jump, or in the water a stroke)", "lane", "middle")
    return s.render()


def draw_overview(levels, rows, schedule, stream_from):
    W, H = 1200, 354
    s = Svg(W, H, "PLAN, Super Mario Bros.: one schedule from power-on through every level, measured on the model and played on the part")
    L, R, T, PH = 60, W - 60, 84, 190
    end = levels[-1]["measured"]["done"]
    sx = lambda k: L + (R - L) * k / end
    s.text(L, 26, "One schedule from power-on", "title")
    s.text(L, 44, f"{len(levels)} levels, {levels[-1]['measured']['entries']} entries, {end} latches; every band a level, "
           "the blue line Mario's way through it, the black line the schedule's entries so far", "sub")
    if stream_from is not None and stream_from < end:
        s.add(f'<rect class="stream" x="{sx(stream_from):.1f}" y="{T}" width="{R - sx(stream_from):.1f}" height="{PH}"/>')
    for i, lv in enumerate(levels):
        m = lv["measured"]
        a, b = sx(m["first"]), sx(m["done"])
        if i % 2 == 0:
            s.add(f'<rect class="band" x="{a:.1f}" y="{T}" width="{b - a:.1f}" height="{PH}"/>')
        s.text((a + b) / 2, T - 6, lv["level"], "lvl", "middle")
        lr = [(k, r["page"] * 256 + r["x"]) for k, r in level_rows(rows, lv) if r["mode"] == 1 and r["state"] != 0x00]
        xmax = max((x for _, x in lr), default=1) or 1
        # broken where x jumps (a pipe: past 2-2's Mario lands further left)
        run, last = [], None
        for k, x in lr[::4]:
            if last is not None and abs(x - last) > 40:
                if len(run) > 1:
                    s.add(f'<polyline class="path" points="{" ".join(run)}"/>')
                run = []
            run.append(f"{sx(k):.1f},{T + PH - PH * 0.9 * x / xmax:.1f}")
            last = x
        if len(run) > 1:
            s.add(f'<polyline class="path" points="{" ".join(run)}"/>')
        mark = "axe" if lv["level"] in CASTLE else "flag"
        s.add(f'<circle class="done" cx="{b:.1f}" cy="{T + PH + 10}" r="3.5"/>')
        s.text(b, T + PH + 26, mark, "lane", "middle")
    # the schedule's entries as they accumulate
    total = len(schedule)
    pts, n = [], 0
    for k, _ in schedule:
        n += 1
        pts.append(f"{sx(min(k, end)):.1f},{T + PH - PH * 0.95 * n / total:.1f}")
    s.add(f'<polyline class="entries" points="{" ".join(pts)}"/>')
    s.text(R + 6, T + PH * 0.05 + 4, str(total), "lane")
    s.text(R + 6, T + PH, "0", "lane")
    s.add(f'<line class="axis" x1="{L}" y1="{T + PH}" x2="{R}" y2="{T + PH}"/>')
    if stream_from is not None and stream_from < end:
        s.text(R, T - 22, "shaded: the head streams the schedule from here on", "lane", "end")
    s.text(L, T + PH + 44, "latch 0 (power-on, then the reset)", "lane")
    s.text(R, T + PH + 44, f"latch {end}", "lane", "end")
    return s.render()


def table(levels):
    rows = ["| level | latches | entries | planned in | backtracks | on the part | polls | wrong | what it taught |",
            "|---|---|---|---|---|---|---|---|---|"]
    for lv in levels:
        m = lv["measured"]
        t = f"{m['plan_s'] / 60:.1f} min" if m["plan_s"] else "not timed"
        rows.append(f"| {lv['level']} | {m['first']} to {m['done']} | {m['entries']} | {t} | {m['backtracks']} | "
                    f"`{m['run']}`{' (streamed)' if m['streamed'] else ''} | {m['polls']} | {m['wrong']} | {lv['lesson']} |")
    return "\n".join(rows)


def build(out, trace):
    rec = json.loads(RECORD.read_text())
    levels = rec["levels"]
    schedule = read_schedule(ROOT / rec["schedule"])
    rows = read_trace(trace)
    stream_from = rec.get("stream_from")
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{PREFIX}overview.svg").write_text(draw_overview(levels, rows, schedule, stream_from))
    for lv in levels:
        (out / f"{PREFIX}{lv['level']}.svg").write_text(draw_level(lv, rows, schedule))
    return table(levels)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trace", required=True, help="the model's replay of the schedule (see the docstring)")
    ap.add_argument("--check", action="store_true", help="redraw into a temporary directory and compare")
    a = ap.parse_args()
    if a.check:
        with tempfile.TemporaryDirectory() as tmp:
            t = build(Path(tmp), a.trace)
            bad = [p.name for p in Path(tmp).iterdir() if not (OUT / p.name).exists() or not filecmp.cmp(p, OUT / p.name, shallow=False)]
            # a level dropped from the record leaves its drawing behind
            bad += [p.name for p in OUT.glob(f"{PREFIX}*.svg") if not (Path(tmp) / p.name).exists()]
            if t not in DOC.read_text():
                bad.append("plan-log.md table")
            if bad:
                sys.exit(f"plan-log: out of date: {', '.join(sorted(bad))}")
        print("plan-log: every drawing and the table agree")
        return
    t = build(OUT, a.trace)
    text = DOC.read_text()
    new, n = re.subn(r"<!-- plan-log:table -->.*?<!-- /plan-log:table -->",
                     lambda mm: "<!-- plan-log:table -->\n" + t + "\n<!-- /plan-log:table -->", text, flags=re.S)
    if n == 0:
        sys.exit("docs/plan-log.md has no plan-log table markers")
    DOC.write_text(new)
    print(f"wrote {len(list(OUT.glob(PREFIX + '*.svg')))} drawings docs/{PREFIX}*.svg and the table in {DOC.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
