#!/usr/bin/env python3
"""The flow of discovery behind PLAN, as one drawing (docs/plan-discovery.svg).
  python3 tools/plan-discovery.py
Authored, not measured: each row is a level that broke something, what it
broke and the rule or tool that came out of it, in the order it happened,
with the bench's own lessons in a second lane. The levels that taught
nothing are the gaps between rows; the whole sequence is docs/plan-log.md
and the retrospective is docs/plan-retro.md.
"""
from pathlib import Path

ROWS = [
    # (level, date, lane, what broke, what it taught)
    ("1-1", "10-17", "plan", "A greedy walk hits the first goomba and cannot take it back",
     "Back up by segment: a move that dies is undone and the next best taken"),
    ("1-2", "10-17", "plan", "Enemy groups need timing; a pipe holds Mario past the lookahead",
     "Saved states (nes branch), a lookahead per move, a held segment is no stall"),
    ("1-3", "10-18", "plan", "A gentler rule committed Mario to a gap",
     "Keep a move only when a way on lives; keep the way on that found the flag"),
    ("1-4", "10-18", "plan", "A castle has no flagpole",
     "Done at the axe: $0770 turns 2, then the next world"),
    ("2-2", "10-18", "plan", "Water, and an exit pipe that puts Mario back",
     "--swim (A tapped at measured rates); a pipe taken counts above x"),
    ("2-3", "10-18", "bench", "The grabber timed out before the intro frame",
     "Grab at latches read off the bridge log, not on a clock"),
    ("3-1", "10-18", "bench", "A schedule larger than the head's room",
     "The UNO's schedule became a ring: the head streams the rest during the run"),
    ("3-3", "10-18", "plan", "The way on is up, and depth first cannot keep that route alive",
     "--beam: keep several positions a segment"),
    ("3-3", "10-18", "bench", "The console restarted itself mid-run with a clean poll log",
     "A part failure is not a plan failure: run it again, count only a clean run"),
    ("3-4", "10-18", "plan", "A frame holding two polls played a jump one poll late",
     "The model stops on the poll, not at the frame's end"),
    ("4-2", "10-18", "plan", "The ceiling leads to a warp zone; the beam has no room for height; a jump cannot keep A across a segment",
     "--beam-high, --no-ceiling, a warp is a death, A held as a way on, --resume with .json sidecars; one stretch by hand"),
    ("4-4", "10-19", "plan", "A castle maze sends Mario back unless he stands at a height as the screen reaches a page",
     "The checks read out of the game's code; the loop-back a death; the height slot aimed at the next check; one gap by hand"),
    ("6-1", "10-19", "bench", "Two polls seen in one look, the count starting at 1",
     "Compare from the last reset line of the bridge log, not the last L 0"),
    ("6-4", "10-19", "bench", "A clean run with no frames: the grabber's limit was shorter than the run",
     "A limit set from the schedule's length"),
    ("7-2", "10-19", "plan", "The beam stood at the water's exit pipe for twenty segments",
     "A pipe passed stays passed: each position carries the pipes its own path entered"),
    ("8-4", "10-20", "plan", "Checks that fire whatever Mario does, and the beam stalled at x 1266 twice",
     "Read in the code: the loop-back is a page shift under his feet, progress once per check"),
    ("8-4", "10-20", "plan", "Counted every time, the beam circled a section four times; a wrong pipe took it to page 1",
     "A repeat of the same check is a death; a pipe that sets Mario back a page in the loaded area is a trap"),
    ("8-4", "10-20", "plan", "A climb gains nothing to the right, so the beam never strings it together",
     "tools/plan-climb.py: a six-poll beam ranked by height, spliced on; the water pipe's entry judged alive by $074F, not $0750"),
]

W, LEFT, MID, RIGHT = 1180, 120, 430, 560
RH, GAP, TOP = 74, 10, 118
H = TOP + len(ROWS) * (RH + GAP) + 150
LANE = {"plan": ("#2563eb", "planner"), "bench": ("#b45309", "bench")}


def esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def wrap(t, width):
    out, line = [], ""
    for w in t.split():
        if len(line) + len(w) + 1 > width and line:
            out.append(line)
            line = w
        else:
            line = (line + " " + w).strip()
    if line:
        out.append(line)
    return out


def text(x, y, lines, size=13, fill="#111", weight="normal", anchor="start", family="system-ui, sans-serif"):
    s = ""
    for i, l in enumerate(lines):
        s += f'<text x="{x}" y="{y + i * (size + 4)}" font-size="{size}" font-family="{family}" font-weight="{weight}" fill="{fill}" text-anchor="{anchor}">{esc(l)}</text>'
    return s


def main():
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
         f'aria-label="The flow of discovery behind PLAN: each level that broke something, what it broke and the rule that came of it">',
         f'<rect width="{W}" height="{H}" fill="#fbfaf7"/>',
         text(24, 40, ["PLAN: the flow of discovery, Super Mario Bros. on the bench, 2026-10-17 to 2026-10-20"], 20, weight="600"),
         text(24, 64, ["Each row is a level that broke something. Left: what broke. Right: the rule or tool that came out of it, kept from then on."], 13, "#444"),
         text(LEFT + MID + 10, 92, ["WHAT BROKE"], 11, "#666", "600"),
         text(LEFT + 50 + MID - 20 + 38, 92, ["WHAT IT TAUGHT"], 11, "#666", "600"),
         text(24, 92, ["LEVEL"], 11, "#666", "600")]
    # the spine
    sx = 70
    s.append(f'<line x1="{sx}" y1="{TOP - 10}" x2="{sx}" y2="{TOP + len(ROWS) * (RH + GAP) - GAP + 10}" stroke="#bbb" stroke-width="2"/>')
    for i, (lv, date, lane, broke, taught) in enumerate(ROWS):
        y = TOP + i * (RH + GAP)
        col, name = LANE[lane]
        s.append(f'<circle cx="{sx}" cy="{y + RH / 2}" r="7" fill="{col}"/>')
        s.append(text(24, y + RH / 2 - 6, [lv], 15, "#111", "700"))
        s.append(text(24, y + RH / 2 + 12, [date], 11, "#777"))
        s.append(text(sx + 14, y + RH / 2 + 4, [name], 10, col, "600"))
        bx = LEFT + 50
        s.append(f'<rect x="{bx}" y="{y}" width="{MID - 20}" height="{RH}" rx="8" fill="#fff" stroke="#ddd"/>')
        s.append(text(bx + 12, y + 24, wrap(broke, 52), 13, "#222"))
        tx = bx + MID - 20 + 8
        s.append(f'<path d="M{tx} {y + RH / 2} l 18 0" stroke="{col}" stroke-width="2" marker-end="url(#a)"/>')
        rx = tx + 30
        s.append(f'<rect x="{rx}" y="{y}" width="{RIGHT}" height="{RH}" rx="8" fill="{col}" fill-opacity="0.07" stroke="{col}" stroke-opacity="0.5"/>')
        s.append(text(rx + 12, y + 24, wrap(taught, 70), 13, "#111"))
    y = TOP + len(ROWS) * (RH + GAP) + 16
    s.append(f'<rect x="24" y="{y}" width="{W - 48}" height="96" rx="10" fill="#e8f5e9" stroke="#2e7d32"/>')
    s.append(text(40, y + 28, ["The end: one schedule of 1,752 button bytes, searched on the model level by level and played on the part from",
                               "power-on, run 20261020-192022: thirty-two levels, 77,402 polls checked against the script, none wrong, none",
                               "missing, no life lost. Twenty of the thirty-two levels taught nothing: the beam crossed them on its own."], 13, "#1b4d20"))
    s.append(text(40, y + 84, ["Authored by tools/plan-discovery.py; the measured record is docs/plan-log.json and docs/plan-log.md."], 11, "#4a6b4d"))
    s.insert(1, '<defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" fill="#888"/></marker></defs>')
    s.append("</svg>")
    out = Path(__file__).resolve().parent.parent / "docs" / "plan-discovery.svg"
    out.write_text("\n".join(s) + "\n")
    print("wrote", out, f"{len(ROWS)} rows")


if __name__ == "__main__":
    main()
