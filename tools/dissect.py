#!/usr/bin/env python3
"""A game's frame, dissected from the model's record: what the CPU does
when, against the PPU's scanlines, and the routines it does it in
(docs/exercise.md, Programme 3; the encyclopedia's raw material).

  python3 tools/dissect.py <dir>/<name> --frames A[-B] [--bytes] [--chip ../6502] [--top N]

Reads <name>.pins and <name>.events.json (nes-console's trace) over the
frames asked for and prints, for each:

  timeline   the frame's events in scanline order: the NMI edge, every
             PPU register write with its line and dot ($2000/1 as
             control, $2005/6 as scroll and address, $2007 bursts as
             one line with their count, $4014 as the DMA), every read
             of $2002 (the status poll: a spin on it is a wait for the
             blank or a sprite-0 hit), the pad's poll, and the idle: a
             tight loop of a few instructions repeated until the next
             interrupt, with where it sits and how long it spun.
  routines   the JSR call tree: each target with its calls in the
             frame, the half-cycles spent inside (JSR to matching RTS,
             by stack depth), and its caller; a return through an RTS
             to an address no JSR pushed is a jump-engine dispatch
             (pull-and-jump), reported as such with the table's
             address; the NMI's entry and RTI.
  layout     the code's pages ($xx00) by half-cycles executed, the map
             of where the game lives.

Addresses, counts, lines and mnemonics are a game's shape; the bytes
are its ROM content, so without --bytes no fetched byte or immediate
is printed. A commercial cartridge's record stays where its ROM store
is; this tool's output is what may leave.
"""
import argparse
import bisect
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from xray import opcode_table, format_operand, MODE_LEN  # noqa: E402


from xray import parse_row  # noqa: E402


def frame_rows(path, h_lo, h_hi):
    """The rows with h in [h_lo, h_hi], streamed."""
    with open(path) as f:
        for l in f:
            if not l[0].isdigit():
                continue
            h = int(l[: l.index(" ")])
            if h < h_lo:
                continue
            if h > h_hi:
                break
            yield parse_row(l)


class Frame:
    def __init__(self, idx, ev, table, show_bytes):
        self.idx, self.ev, self.table, self.show_bytes = idx, ev, table, show_bytes
        fr = ev["frames"][idx]
        self.h_hi = fr["h_end"]
        self.h_lo = ev["frames"][idx - 1]["h_end"] + 1 if idx else 0
        self.dots_start = ev["frames"][idx - 1]["dots_end"] if idx else 0
        self.dots_end = fr["dots_end"]
        self.master_end = fr["master_end"]

    def line_of(self, h):
        """The PPU's scanline and dot at a half-cycle, from the frame's
        end counted back (a CPU half-cycle is 6 master half-steps, a dot
        4, so 1.5 dots per CPU half-cycle) and from the frame's own
        start counted forward. The PPU's frame runs the pre-render line
        261 first, then 0..=260, and a rendered odd frame is a dot
        short; until 2026-09-18 this took the absolute dot count modulo
        a full frame and numbered the pre-render line 0, so every line
        it printed was one high less a dot per skipped dot (0.7 line by
        the menu's frame 212, 0.15 by frame 585), which is where most of
        the part's "0.6 line early" poll came from (poll-line.py; the
        model's own latch positions are `POSITIONS=1 pad-log`)."""
        d = int(self.dots_end - (self.h_hi - h) * 1.5) - self.dots_start
        return (d // 341 + 261) % 262, d % 341


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("record", help="<dir>/<name> of a trace")
    ap.add_argument("--frames", required=True)
    ap.add_argument("--bytes", action="store_true")
    ap.add_argument("--chip", default=str(ROOT.parent / "6502"))
    ap.add_argument("--top", type=int, default=24)
    ap.add_argument("--no-timeline", action="store_true")
    ap.add_argument("--per-frame", action="store_true", help="one line per frame: the NMI's line, rendering back on, the handler's RTI, the idle")
    a = ap.parse_args()
    table = opcode_table(a.chip)
    rec = Path(a.record)
    ev = json.load(open(str(rec) + ".events.json"))
    lo, _, hi = a.frames.partition("-")
    f_lo, f_hi = int(lo), int(hi or lo)
    frames = [Frame(i, ev, table, a.bytes) for i in range(f_lo, f_hi + 1)]
    h_lo, h_hi = frames[0].h_lo, frames[-1].h_hi
    # Events by frame, from the console's side.
    ppu = defaultdict(list)
    for w in ev["ppu_writes"]:
        if f_lo <= w["frame"] <= f_hi:
            ppu[w["frame"]].append(w)
    nmis = [n["h"] for n in ev.get("nmi_edges", []) if h_lo <= n["h"] <= h_hi]
    latches = [l for l in ev["latches"] if h_lo <= l["h"] <= h_hi]
    reads = [r for r in ev["reads"] if h_lo <= r["h"] <= h_hi]

    # One pass over the pins: syncs (pc, op, operands), $2002 reads, JSR/RTS/RTI, the idle loop.
    syncs = []          # (h, pc, op, ops)
    status_reads = []   # h of reads of $2002
    stack = []          # JSR frames: (target, h_entry, return address, caller pc)
    calls = []          # (target, h_entry, h_exit, caller, depth)
    dispatches = []     # (h, rts_pc, to)
    nmi_entries = []    # (h, vector target)
    rows_by_h = {}
    pending = None
    last_sync = None
    cur = None
    page_cycles = Counter()
    ram_writes = Counter()
    ram_pages = Counter()
    for row in frame_rows(str(rec) + ".pins", h_lo, h_hi):
        h, c, ab, db, rw, sync, rdy = row
        if rw == 0 and c == 1 and ab < 0x2000 and rdy == 1:
            ram_writes[ab & 0x7ff] += 1
            ram_pages[(ab & 0x7ff) >> 8] += 1
        if sync == 1 and c == 0 and rdy == 1:
            cur = [h, ab, db, []]
            syncs.append(cur)
            page_cycles[ab >> 8] += 1
        elif cur is not None and c == 1 and rw == 1 and len(cur[3]) < 2 and ab == (cur[1] + 1 + len(cur[3])) & 0xffff and h > cur[0] + 1:
            cur[3].append(db)
        if c == 1 and rw == 1 and ab == 0x2002:
            status_reads.append(h)
        # The vector fetch: a read of $FFFA/$FFFB (NMI) or $FFFE/F.
        if c == 1 and rw == 1 and ab in (0xfffa, 0xfffb, 0xfffe, 0xffff):
            if ab in (0xfffa, 0xfffe):
                pending = (h, db, ab)
            elif pending and ab == pending[2] + 1:
                nmi_entries.append((pending[0], (db << 8) | pending[1], "NMI" if ab == 0xfffb else "IRQ/BRK"))
                pending = None
        if page_cycles and cur is not None:
            page_cycles[cur[1] >> 8] += 0
    # Second look, over the syncs: calls and returns.
    # A JSR's target is its operands; its return is pc + 3. An RTS returns
    # to the next sync's pc: if that is a pushed return, it closes the
    # call; else it is a dispatch (the game pushed a table entry).
    # A jump engine: a routine entered by JSR that pulls its own return
    # address (two PLAs before any RTS) and lands somewhere by JMP
    # indirect; the table it indexes follows the JSR. Its frame closes
    # at the JMP, and the routine it lands on runs as a call of its own,
    # closed by the RTS that returns to the engine's caller's caller.
    for i, (h, pc, op, ops) in enumerate(syncs):
        nxt = syncs[i + 1] if i + 1 < len(syncs) else None
        if op == 0x20 and len(ops) == 2:
            target = ops[1] << 8 | ops[0]
            stack.append([target, h, (pc + 3) & 0xffff, pc, len(stack), 0])
        elif op == 0x68 and stack and stack[-1][5] < 2:
            stack[-1][5] += 1
        elif op == 0x6c and stack and stack[-1][5] == 2 and nxt is not None:
            eng = stack.pop()
            calls.append((eng[0], eng[1], h, eng[3], eng[4]))
            dispatches.append((h, eng[0], eng[2], nxt[1]))
            stack.append([nxt[1], nxt[0], None, eng[0], len(stack), 0])
        elif op == 0x60 and nxt is not None:
            to = nxt[1]
            k = next((j for j in range(len(stack) - 1, -1, -1) if stack[j][2] == to), None)
            if k is not None:
                for fr in stack[k:]:
                    calls.append((fr[0], fr[1], nxt[0], fr[3], fr[4]))
                del stack[k:]
            else:
                dispatches.append((h, None, pc, to))
    for fr in stack:
        calls.append((fr[0], fr[1], h_hi, fr[3], fr[4]))
    rtis = [(h, pc) for h, pc, op, ops in syncs if op == 0x40]

    def text_of(pc, op, ops):
        if op not in table:
            return f"op ${op:02X}" if a.bytes else "op (undocumented)"
        mne, mode = table[op]
        if len(ops) < MODE_LEN[mode]:
            return mne
        return f"{mne} {format_operand(mode, ops, pc, a.bytes)}".rstrip()

    sync_h = [s[0] for s in syncs]
    def instr_at(h):
        k = bisect.bisect_right(sync_h, h) - 1
        return syncs[k] if k >= 0 else None

    # The idle loop: runs of the same short PC cycle.
    idles = []
    i = 0
    while i < len(syncs) - 4:
        pc0 = syncs[i][1]
        # a loop of length L (1..4 instructions) repeating
        found = None
        for L in (1, 2, 3, 4):
            if i + 2 * L < len(syncs) and all(syncs[i + k][1] == syncs[i + k + L][1] for k in range(L)):
                found = L
                break
        if found:
            j = i
            while j + 2 * found <= len(syncs) - 1 and all(syncs[j + k][1] == syncs[j + k + found][1] for k in range(found)):
                j += found
            reps = (j - i) // found
            if reps >= 8:
                idles.append((syncs[i][0], syncs[j][0], [syncs[i + k] for k in range(found)], reps))
            i = j + found
        else:
            i += 1

    out = []
    for fr in frames:
        if a.per_frame:
            nmi_l = next((fr.line_of(h)[0] for h, _, _ in nmi_entries if fr.h_lo <= h <= fr.h_hi), None)
            rti_l = next((fr.line_of(h)[0] for h, _ in rtis if fr.h_lo <= h <= fr.h_hi), None)
            on = next((fr.line_of(w["h"])[0] for w in ppu[fr.idx] if w["reg"] == "2001" and int(w["value"], 16) & 0x18), None)
            idle_hc = sum(min(h1, fr.h_hi) - max(h0, fr.h_lo) for h0, h1, loop, reps in idles if loop[0][1] == 0x8057 and h0 <= fr.h_hi and h1 >= fr.h_lo)
            vram = sum(1 for w in ppu[fr.idx] if w["reg"] == "2007")
            lat = next((l for l in latches if fr.h_lo <= l["h"] <= fr.h_hi), None)
            out.append(f"frame {fr.idx}: NMI line {nmi_l}, rendering on line {on}, VRAM bytes {vram}, RTI line {rti_l}, idle {100 * idle_hc / (fr.h_hi - fr.h_lo + 1):4.1f}%" + (f", pad {lat['byte']}" if lat else ""))
            continue
        out.append(f"frame {fr.idx}: h {fr.h_lo}..{fr.h_hi} ({fr.h_hi - fr.h_lo + 1} half-cycles)")
        if a.no_timeline:
            continue
        items = []
        for n in nmis:
            if fr.h_lo <= n <= fr.h_hi:
                items.append((n, "nmi", "NMI edge"))
        for h, tgt, kind in nmi_entries:
            if fr.h_lo <= h <= fr.h_hi:
                items.append((h, "vec", f"{kind} vector taken -> ${tgt:04X}"))
        for h, pc in rtis:
            if fr.h_lo <= h <= fr.h_hi:
                items.append((h, "rti", f"RTI at ${pc:04X}: the handler ends"))
        burst = None
        dma = None
        for w in ppu[fr.idx]:
            reg = w["reg"]
            if reg == "4014":
                dma = [w["h"], 0]
                items.append((w["h"], "ppu", f"$4014 <- {w['value']} (OAM DMA from ${w['value']}00)"))
                continue
            if reg == "2004" and dma is not None and w["h"] - dma[0] < 1100:
                dma[1] += 1
                if dma[1] == 256:
                    l1, d1 = fr.line_of(w["h"])
                    items.append((dma[0] + 1, "ppu", f"  the DMA's 256 writes of $2004, to line {l1} dot {d1}"))
                continue
            if reg == "2007":
                if burst and w["h"] - burst[1] < 60:
                    burst[1] = w["h"]; burst[2] += 1
                    continue
                burst = [w["h"], w["h"], 1, w["line"], w["dot"]]
                items.append((w["h"], "vram", burst))
                continue
            what = {"2000": "ctrl", "2001": "mask", "2003": "oam addr", "2004": "oam data", "2005": "scroll", "2006": "addr", "4014": "OAM DMA"}.get(reg, reg)
            items.append((w["h"], "ppu", f"${reg} <- {w['value']} ({what})"))
        # $2002 reads as runs.
        run = None
        for h in status_reads:
            if not (fr.h_lo <= h <= fr.h_hi):
                continue
            if run and h - run[1] < 40:
                run[1] = h; run[2] += 1
                continue
            run = [h, h, 1]
            items.append((h, "stat", run))
        for l in latches:
            if fr.h_lo <= l["h"] <= fr.h_hi:
                n = sum(1 for r in reads if r["after_latch"] == l["index"])
                s = instr_at(l["h"])
                items.append((l["h"], "pad", f"latch {l['index']} byte {l['byte']}, {n} reads, in {text_of(s[1], s[2], s[3]) if s else '?'} at ${s[1]:04X}" if s else f"latch {l['index']}"))
        for h0, h1, loop, reps in idles:
            if fr.h_lo <= h0 <= fr.h_hi or fr.h_lo <= h1 <= fr.h_hi:
                items.append((max(h0, fr.h_lo), "idle", (h0, h1, loop, reps)))
        items.sort(key=lambda t: t[0])
        for h, kind, payload in items:
            line, dot = fr.line_of(h)
            where = f"  line {line:3d} dot {dot:3d}  h {h}"
            if kind == "vram":
                h0, h1, n, l0, d0 = payload
                l1, d1 = fr.line_of(h1)
                s0 = instr_at(h0)
                out.append(f"{where}  $2007 x{n} (VRAM burst to line {l1} dot {d1})" + (f" by {text_of(s0[1], s0[2], s0[3])} at ${s0[1]:04X}" if s0 else ""))
            elif kind == "stat":
                h0, h1, n = payload
                l1, d1 = fr.line_of(h1)
                s = instr_at(h0)
                out.append(f"{where}  $2002 read x{n}" + (f" until line {l1} dot {d1}: a spin on the status" if n > 2 else "") + (f", at ${s[1]:04X}" if s else ""))
            elif kind == "idle":
                h0, h1, loop, reps = payload
                l1, d1 = fr.line_of(min(h1, fr.h_hi))
                out.append(f"{where}  idle: {' / '.join(text_of(s[1], s[2], s[3]) for s in loop)} at ${loop[0][1]:04X}, x{reps} until line {l1} dot {d1} ({min(h1, fr.h_hi) - max(h0, fr.h_lo)} half-cycles)")
            else:
                out.append(f"{where}  {payload}")

    # Routines over the whole range.
    out.append(f"routines over frames {f_lo}..{f_hi} ({len(calls)} calls, {len(dispatches)} dispatches, {len(nmi_entries)} interrupts):")
    prof = defaultdict(lambda: [0, 0, Counter(), 0])
    for target, h0, h1, caller, depth in calls:
        p = prof[target]
        p[0] += 1
        p[1] += h1 - h0
        p[2][caller] += 1
        p[3] = min(p[3], depth) if p[0] > 1 else depth
    rows = sorted(prof.items(), key=lambda kv: -kv[1][1])[: a.top]
    for target, (n, hc, callers, depth) in rows:
        cs = ", ".join(f"${c:04X}" for c, _ in callers.most_common(3))
        out.append(f"  ${target:04X}  x{n:<5} {hc:>9} hc  depth {depth}  from {cs}")
    if dispatches:
        engines = Counter(e for _, e, _, _ in dispatches if e is not None)
        out.append(f"  jump-engine dispatches: {len(dispatches)}" + ("; engine at " + ", ".join(f"${e:04X} x{n}" for e, n in engines.most_common(3)) if engines else ""))
        tables = defaultdict(Counter)
        for _, e, tab, to in dispatches:
            tables[tab][to] += 1
        for tab, tos in sorted(tables.items(), key=lambda kv: -sum(kv[1].values()))[:12]:
            out.append(f"    table after the JSR at ${tab - 3:04X} -> " + ", ".join(f"${t:04X} x{n}" for t, n in tos.most_common(8)))
    out.append(f"RAM over frames {f_lo}..{f_hi}: {sum(ram_writes.values())} writes to {len(ram_writes)} addresses; by page: " + ", ".join(f"${p:02X}00 {n}" for p, n in sorted(ram_pages.items())))
    out.append("  most written: " + ", ".join(f"${ad:04X} x{n}" for ad, n in ram_writes.most_common(16)))
    out.append(f"layout: code pages by half-cycles executed over frames {f_lo}..{f_hi}:")
    total = sum(page_cycles.values())
    for page, n in sorted(page_cycles.items(), key=lambda kv: -kv[1])[: a.top]:
        out.append(f"  ${page:02X}00  {n:>8} instruction fetches  {100 * n / total:5.1f}%")
    print("\n".join(out))


if __name__ == "__main__":
    main()
