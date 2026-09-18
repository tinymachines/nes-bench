#!/usr/bin/env python3
"""The x-ray: two runs of the model that differ in one byte at one
latch, the half-cycle at which their pins first differ, the
instruction executing there, and everything downstream that the byte
changed (docs/exercise.md, Programme 3).

  python3 tools/xray.py rom.nes <name> --latch N --byte HH [--frames F] [--out DIR]
                        [--bytes] [--window] [--nes ../nes] [--chip ../6502]

Traces the ROM twice with nes-console's `trace` (the base run holds 00;
the action run holds HH at latch N and 00 again at N+1), then diffs the
two `.pins` records half-cycle by half-cycle:

  diverge   the first half-cycle apart, its field and both values. The
            only door a pad byte has into the CPU is a read of $4016 or
            $4017, so a first difference anywhere else means the two
            runs were not the same run, and the tool refuses: the
            invariant, not a hope. MUTATE=1 corrupts one byte the base
            record fetched before the latch and the refusal must fire.
  the instruction   the last opcode fetch (SYNC) at or before the
            divergence, disassembled from the 6502 site's own table
            (web/disasm.js, the one place it lives).
  the path  every later half-cycle the two records differ at, grouped
            into spans and labelled with the instruction executing
            there: the RAM the routine writes, the picture-chip
            registers it reaches, the bank it switches to, taken from
            the pins and the action run's events.
  rejoin    the first half-cycle after which the records agree to the
            end, or that they never do (the byte changed the state for
            good).

A commercial cartridge's bytes are ROM content: without --bytes the
report shows addresses, mnemonics, counts and event kinds and masks
every immediate operand and fetched byte, so it carries the shape of
the routine and never its code; --bytes is for ROMs whose source is
ours. The traces themselves go to --out (default runs/xray/<name>,
which git ignores); for a commercial ROM put --out where the ROM store
is.

--window cuts a window of the action run around the divergence with
the 6502 repository's replay-recorded (rung 0 runs the record to the
instruction's fetch, about thirty thousand half-cycles a second), the
file the Halfshot page stands inside; it carries the overlay lines
that fall in it.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

MODE_LEN = {"imp": 0, "acc": 0, "imm": 1, "zp": 1, "zpx": 1, "zpy": 1, "izx": 1, "izy": 1,
            "abs": 2, "abx": 2, "aby": 2, "ind": 2, "rel": 1}


def opcode_table(chip):
    """web/disasm.js's OPCODES, read out of the file so there is one table."""
    src = (Path(chip) / "web" / "disasm.js").read_text()
    table = {}
    for m in re.finditer(r"0x([0-9a-f]{2}):\s*\['([A-Z]{3})',\s*'([a-z]{2,3})'\]", src):
        table[int(m.group(1), 16)] = (m.group(2), m.group(3))
    if len(table) != 151:
        raise SystemExit(f"{chip}/web/disasm.js: read {len(table)} opcodes, not 151")
    return table


def format_operand(mode, ops, pc, show_bytes):
    if mode in ("imp",):
        return ""
    if mode == "acc":
        return "A"
    if mode == "imm":
        return f"#${ops[0]:02X}" if show_bytes else "#$.."
    if mode == "rel":
        return f"${(pc + 2 + ((ops[0] ^ 0x80) - 0x80)) & 0xffff:04X}"
    if MODE_LEN[mode] == 1:
        v = f"${ops[0]:02X}"
    else:
        v = f"${ops[1] << 8 | ops[0]:04X}"
    return {"zp": v, "zpx": f"{v},X", "zpy": f"{v},Y", "izx": f"({v},X)", "izy": f"({v}),Y",
            "abs": v, "abx": f"{v},X", "aby": f"{v},Y", "ind": f"({v})"}[mode]


class Instr:
    """One executed instruction: its opcode fetch and operand bytes, as
    the stream passes them; the operands fill in after the fetch."""
    __slots__ = ("row", "h", "pc", "op", "ops")

    def __init__(self, row, h, pc, op):
        self.row, self.h, self.pc, self.op, self.ops = row, h, pc, op, []

    def text(self, table, show_bytes):
        if self.op not in table:
            return f"op ${self.op:02X}" if show_bytes else "op (undocumented)"
        mne, mode = table[self.op]
        if len(self.ops) < MODE_LEN[mode]:
            return mne
        return f"{mne} {format_operand(mode, self.ops, self.pc, show_bytes)}".rstrip()


def parse_row(line):
    """(h, clk0, ab, db, rw, sync, rdy): rdy is the fourth input pin; a
    SYNC held through a DMA's halt is not an instruction fetch."""
    f = line.split()
    return (int(f[0]), int(f[1]), int(f[2], 16), int(f[3], 16), int(f[4]), int(f[5]), int(f[6][3]))


def diff_records(base_path, act_path):
    """The two records streamed side by side: every differing row as
    (index, base_row, act_row, the action run's instruction there), the
    action run's instruction count, its last row, and its syncs seen.
    Nothing but the differences is kept, so a record of any length fits."""
    diffs = []
    instr = None
    n = 0
    syncs = 0
    last = None
    with open(base_path) as fb, open(act_path) as fa:
        lb = (l for l in fb if l[0].isdigit())
        la = (l for l in fa if l[0].isdigit())
        for x, y in zip(lb, la):
            ry = parse_row(y)
            if ry[5] == 1 and ry[1] == 0 and ry[6] == 1:
                instr = Instr(n, ry[0], ry[2], ry[3])
                syncs += 1
            elif instr is not None and ry[1] == 1 and ry[4] == 1 and len(instr.ops) < 2 and ry[2] == (instr.pc + 1 + len(instr.ops)) & 0xffff and n > instr.row + 1:
                instr.ops.append(ry[3])
            if x != y:
                diffs.append((n, parse_row(x), ry, instr))
            n += 1
            last = ry
        # A record that runs on past the other: after the divergence the
        # runs may differ in length (a frame's length changes with
        # rendering on or off, and the byte can change that); before it,
        # two lengths are two runs.
        extra = 0
        for _ in lb:
            extra -= 1
        for _ in la:
            extra += 1
        if extra and not diffs:
            raise SystemExit(f"the records differ in length by {abs(extra)} half-cycles and nowhere else: not the same run")
    return diffs, n, last, extra


def trace(nes, rom, name, frames, script, out):
    r = subprocess.run(["cargo", "run", "--release", "-q", "-p", "nes-console", "--example", "trace", "--",
                        str(rom), name, str(frames), str(script), str(out)], cwd=nes, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(r.stderr)
        raise SystemExit(f"trace {name} failed")
    return [l for l in r.stdout.splitlines() if l.startswith(f"{name}:")][-1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom")
    ap.add_argument("name")
    ap.add_argument("--latch", type=int, required=True)
    ap.add_argument("--byte", required=True, help="hex, the pad's order (bit 0 = A)")
    ap.add_argument("--frames", type=int, default=None, help="frames to run (default: enough for the latch, plus 3)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--bytes", action="store_true", help="show fetched bytes and immediates: a ROM whose source is ours")
    ap.add_argument("--window", action="store_true", help="cut a window around the divergence with replay-recorded")
    ap.add_argument("--nes", default=str(ROOT.parent / "nes"))
    ap.add_argument("--chip", default=str(ROOT.parent / "6502"))
    ap.add_argument("--reuse", action="store_true", help="the traces in --out are current: do not trace again")
    ap.add_argument("--spans", type=int, default=24, help="spans to print before the rest is a histogram")
    ap.add_argument("--script", default=None, help="a bench script both runs play (the way into the game); the action run adds the byte at the latch on top of it")
    a = ap.parse_args()
    byte = int(a.byte, 16)
    out = Path(a.out or ROOT / "runs" / "xray" / a.name).resolve()
    out.mkdir(parents=True, exist_ok=True)
    table = opcode_table(a.chip)
    rom = Path(a.rom).resolve()
    base_lines = ["SET 00"]
    if a.script:
        base_lines = [l.rstrip() for l in Path(a.script).read_text().splitlines() if l.split("#")[0].strip()]
    # The byte in force at the latch under the base script, restored after.
    held = 0
    for l in base_lines:
        w = l.split()
        if w[0].upper() == "SET":
            held = int(w[1], 16)
        elif w[0].upper() == "AT" and int(w[1]) <= a.latch + 1:
            held = int(w[2], 16)
    act_lines = [l for l in base_lines if not (l.split()[0].upper() == "AT" and int(l.split()[1]) in (a.latch, a.latch + 1))]
    act_lines += [f"AT {a.latch} {byte | held:02x}", f"AT {a.latch + 1} {held:02x}"]
    (out / "base.txt").write_text("\n".join(base_lines) + "\n")
    (out / "act.txt").write_text("\n".join(act_lines) + "\n")
    frames = a.frames or (a.latch // 60 + 4)   # a game polls about once a frame after it starts
    report = [f"x-ray {a.name}: {rom.name}, {byte:02X} at latch {a.latch} on top of {held:02X}" + (f" under {Path(a.script).name}" if a.script else "") + f", {frames} frames"]
    if not a.reuse:
        for n in ("base", "act"):
            report.append("  " + trace(a.nes, rom, n, frames, out / f"{n}.txt", out))
    events = json.load(open(out / "act.events.json"))
    latch_h = next((l["h"] for l in events["latches"] if l["index"] == a.latch), None)
    if latch_h is None:
        raise SystemExit(f"latch {a.latch} is not in the action run's {len(events['latches'])} latches: more frames, or a game that has not started polling")
    base_path = out / "base.pins"
    if os.environ.get("MUTATE") == "1":
        # A byte the base record fetched before the latch, corrupted: the
        # runs are no longer the same run, and the invariant must say so.
        lines = open(base_path).read().splitlines(keepends=True)
        rows = [i for i, l in enumerate(lines) if l[0].isdigit()]
        for i in rows[len(rows) // 10:]:
            r = parse_row(lines[i])
            if r[0] >= latch_h:
                break
            if r[1] == 1 and r[4] == 1 and r[2] >= 0x8000:
                f = lines[i].split()
                f[3] = f"{r[3] ^ 1:02x}"
                lines[i] = " ".join(f) + "\n"
                base_path = out / "base.mutated.pins"
                base_path.write_text("".join(lines))
                report.append(f"  MUTATE: the base record's fetch at h {r[0]} flipped, in {base_path.name}")
                break
    diffs, n_rows, last_row, extra = diff_records(base_path, out / "act.pins")
    if not diffs:
        raise SystemExit(f"{byte:02X} at latch {a.latch} changed nothing the CPU fetched, read or wrote in {frames} frames: no x-ray (the game did not read the pad, or does not act on that bit)")
    d, x, y, ins = diffs[0]
    fields = ["h", "clk0", "ab", "db", "rw", "sync"]
    field = next(f for f, p, q in zip(fields, x, y) if p != q)
    if not (field == "db" and x[4] == 1 and x[2] in (0x4016, 0x4017)):
        raise SystemExit(f"REFUSED: the records first differ at h {x[0]} in {field} (ab {x[2]:04x}, base {x[3]:02x} act {y[3]:02x}), not at a read of $4016/$4017: the pad's byte is the only door, so these were not the same run")
    report.append(f"diverge h {x[0]}: read of ${x[2]:04X} returned {x[3] & 1} in the base run and {y[3] & 1} with the byte (D0); latch {a.latch} at h {latch_h}, {x[0] - latch_h} half-cycles after it")
    report.append(f"  the instruction: {ins.text(table, a.bytes)} at ${ins.pc:04X} (its fetch at h {ins.h}), reads read {y[0] - ins.h} half-cycles in")

    # The path: the differing half-cycles as spans, each with its instruction.
    spans = []   # [first diff k, last diff k]
    for k, (i, _, _, _) in enumerate(diffs):
        if spans and i - diffs[spans[-1][1]][0] <= 4:
            spans[-1][1] = k
        else:
            spans.append([k, k])
    h_of = lambda k: diffs[k][2][0]
    # The path proper ends before the next latch: what differs after the
    # next poll is the byte's echo (a stale byte in RAM shifted out, a
    # state the game keeps), reported apart.
    next_latch = next((l["h"] for l in events["latches"] if l["h"] > x[0]), None)
    in_poll = [sp for sp in spans if next_latch is None or h_of(sp[0]) < next_latch]
    echoes = spans[len(in_poll):]
    last_k = in_poll[-1][1] if in_poll else spans[-1][1]
    path_end = h_of(last_k)
    n_instr = len({id(diffs[k][3]) for k in range(0, last_k + 1)})
    report.append(f"the path: {sum(diffs[hi][0] - diffs[lo][0] + 1 for lo, hi in in_poll)} half-cycles differ in {len(in_poll)} span(s) over {path_end - x[0] + 1} half-cycles before the next latch, {n_instr} instructions" + (f"; then {len(echoes)} span(s) after it" if echoes else ""))
    ram_writes, seen = [], set()
    shown = 0
    hist = {}
    for lo, hi in spans:
        ins2 = diffs[lo][3]
        key_h = (ins2.pc, ins2.text(table, a.bytes))
        hist[key_h] = hist.get(key_h, 0) + diffs[hi][0] - diffs[lo][0] + 1
        if shown >= a.spans:
            continue
        what = []
        for k in range(lo, hi + 1):
            _, bx, ay, _ = diffs[k]
            h, c, ab, db, rw, sync, _ = ay
            bdb = bx[3]
            if db != bdb and c == 1:
                if rw == 0 and ab < 0x2000:
                    what.append(f"RAM ${ab & 0x7ff:04X} <- {db:02X} (base {bdb:02X})")
                    if [lo, hi] in in_poll:
                        ram_writes.append((ab & 0x7ff, db, bdb))
                elif rw == 0 and 0x2000 <= ab < 0x4000:
                    what.append(f"PPU ${0x2000 + (ab & 7):04X} <- {db:02X} (base {bdb:02X})")
                elif rw == 0 and ab >= 0x8000:
                    what.append(f"cart ${ab:04X} <- {db:02X} (base {bdb:02X})")
                elif rw == 0:
                    what.append(f"${ab:04X} <- {db:02X} (base {bdb:02X})")
                elif ab < 0x2000:
                    what.append(f"RAM ${ab & 0x7ff:04X} read {db:02X} (base {bdb:02X})")
                elif ab in (0x4016, 0x4017):
                    what.append(f"pad ${ab:04X} read D0 {db & 1} (base {bdb & 1})")
                elif ab >= 0x8000 and a.bytes:
                    what.append(f"fetch ${ab:04X} {db:02X} (base {bdb:02X})")
                elif ab >= 0x8000:
                    what.append(f"fetch ${ab:04X} differs (a different code path)")
            elif ay[2] != bx[2] and c == 1:
                what.append(f"address ${ab:04X} against ${bx[2]:04X}: a different code path")
        if len(what) > 16:
            # A long span is a different code path: its shape, not its list.
            from collections import Counter
            kinds = Counter(w.split(" ")[0] for w in what)
            ram = Counter(w.split(" ")[1] for w in what if w.startswith("RAM") and "<-" in w)
            ppu = [w for w in what if w.startswith("PPU")]
            cart = [w for w in what if w.startswith("cart")]
            first_fetch = next((w.split(" ")[1] for w in what if w.startswith("fetch") or w.startswith("address")), None)
            what = [f"a different code path from {first_fetch or '?'}: {kinds.get('fetch', 0) + kinds.get('address', 0)} fetches differ",
                    f"RAM: {sum(ram.values())} writes to {len(ram)} addresses" + (f" (most: {', '.join(f'{a} x{n}' for a, n in ram.most_common(6))})" if ram else ""),
                    f"PPU: {len(ppu)} writes" + (f" ({'; '.join(ppu[:4])}{'; ...' if len(ppu) > 4 else ''})" if ppu else ""),
                    f"cart: {len(cart)} writes" + (f" ({'; '.join(cart[:4])})" if cart else "")]
        key = (key_h[1], tuple(what))
        if key in seen and len(spans) > 12:
            continue
        seen.add(key)
        shown += 1
        tag = "  " if (lo, hi) in [tuple(sp) for sp in in_poll] else "  (echo) "
        report.append(f"{tag}h {diffs[lo][2][0]}..{diffs[hi][2][0]}  {key_h[1]} at ${ins2.pc:04X}: " + ("; ".join(what[:12]) + (f"; ... {len(what) - 12} more" if len(what) > 12 else "") if what else "the bus differs"))
    if len(spans) > shown:
        top = sorted(hist.items(), key=lambda kv: -kv[1])[:10]
        report.append(f"  ... {len(spans) - shown} more span(s); the instructions most on the path: " + "; ".join(f"{t} at ${pc:04X} ({n} hc)" for (pc, t), n in top))
    after = diffs[-1][2][0]
    if extra:
        report.append(f"rejoin: never; the action run is {abs(extra)} half-cycles {'longer' if extra > 0 else 'shorter'} than the base run over the same frames (the frames changed length: rendering on or off is the usual cause), so the byte changed the run to its end")
    elif diffs[-1][0] < n_rows - 1:
        report.append(f"rejoin: the records agree again from h {after + 1} to the end ({last_row[0]})")
    else:
        report.append("rejoin: never; the byte changed the run to its end")
    # The action run's events inside the path, from the console's side.
    lo_h, hi_h = x[0], path_end
    ev = []
    for w in events.get("ppu_writes", []):
        if lo_h <= w["h"] <= hi_h:
            ev.append(f"ppu {w['h']} ${w['reg']} <- {w['value']} at frame {w['frame']} line {w['line']} dot {w['dot']}")
    for w in events.get("cart_writes", []):
        if lo_h <= w["h"] <= hi_h:
            ev.append(f"cart {w['h']} ${w['addr']} <- {w['value']} (a mapper register) at frame {w['frame']}")
    for nm in events.get("nmi_edges", []):
        if lo_h <= nm["h"] <= hi_h:
            ev.append(f"nmi {nm['h']}")
    reads = [r for r in events.get("reads", []) if lo_h <= r["h"] <= hi_h]
    if reads:
        ev.append(f"pad reads inside the path: {len(reads)}, {', '.join(str(r['h'] - lo_h) for r in reads[:9])}{'...' if len(reads) > 9 else ''} half-cycles from the divergence")
    if ev:
        report.append("events on the path (the action run):")
        report += ["  " + e for e in ev[:40]] + ([f"  ... {len(ev) - 40} more"] if len(ev) > 40 else [])
    # After the path: what the byte's consequences reach later (a menu
    # that switches banks frames after the press): every cart write, the
    # rendering and NMI switches, the DMAs, until the end of the record.
    if echoes or extra:
        later = []
        for w in events.get("cart_writes", []):
            if w["h"] > path_end:
                later.append(f"cart {w['h']} ${w['addr']} <- {w['value']} (a mapper register) at frame {w['frame']}")
        for w in events.get("ppu_writes", []):
            if w["h"] > path_end and w["reg"] in ("2000", "2001"):
                later.append(f"ppu {w['h']} ${w['reg']} <- {w['value']} at frame {w['frame']} line {w['line']}")
        dmas = sum(1 for w in events.get("ppu_writes", []) if w["h"] > path_end and w["reg"] == "4014")
        later.sort(key=lambda t: int(t.split()[1]))
        if later or dmas:
            report.append(f"after the path, to the end of the record (the action run; only what the base run did not do at the same half-cycle is the byte's):")
            base_ev = {}
            try:
                bev = json.load(open(out / "base.events.json"))
                for w in bev.get("cart_writes", []):
                    base_ev[("cart", w["h"], w["addr"], w["value"])] = 1
                for w in bev.get("ppu_writes", []):
                    if w["reg"] in ("2000", "2001"):
                        base_ev[("ppu", w["h"], w["reg"], w["value"])] = 1
            except OSError:
                pass
            own = [t for t in later if (t.split()[0], int(t.split()[1]), t.split()[2].lstrip("$"), t.split()[4]) not in base_ev]
            report += ["  " + t for t in own[:24]] + ([f"  ... {len(own) - 24} more"] if len(own) > 24 else [])
            if dmas:
                report.append(f"  sprite DMAs ($4014) after the path: {dmas}")
    addrs = sorted({diffs[lo][3].pc for lo, hi in in_poll} or {ins.pc})
    ram_addrs = sorted({f"${w:04X}" for w, _, _ in ram_writes})
    ram_text = ", ".join(ram_addrs[:12]) + (f" and {len(ram_addrs) - 12} more" if len(ram_addrs) > 12 else "") if ram_addrs else "none"
    report.append(f"signature: code at ${addrs[0]:04X}..${addrs[-1]:04X}, RAM touched {ram_text}, {len(reads)} pad reads, {sum(1 for e in ev if e.startswith('ppu'))} PPU writes, {sum(1 for e in ev if e.startswith('cart'))} cart writes on the path")

    if a.window:
        # From the instruction's fetch to a phi2 past the path's end.
        w_from = ins.h
        w_to = min(path_end + 16, last_row[0])
        w_to -= (w_to % 2 == 0)   # h even is clk0 low; the cut ends on a phi2
        wfile = out / f"{a.name}.window"
        r = subprocess.run(["cargo", "run", "--release", "-q", "-p", "v6502-pins", "--example", "replay-recorded", "--",
                            str(out / "act.pins"), "--window", str(w_from), str(w_to), str(wfile)], cwd=a.chip, capture_output=True, text=True)
        if r.returncode != 0:
            sys.stderr.write(r.stdout + r.stderr)
            raise SystemExit("the window was not cut")
        report.append(f"window: {wfile.name}, h {w_from}..{w_to} ({w_to - w_from + 1} half-cycles), {sum(1 for l in open(wfile) if l.startswith('# ') and l.split()[1] in ('latch', 'read', 'ppu', 'cart', 'nmi', 'dot', 'frame'))} overlay lines carried; copy it to 6502/web/windows/ and the Halfshot page stands in it (?window={a.name})")
    text = "\n".join(report) + "\n"
    (out / f"{a.name}.xray.txt").write_text(text)
    print(text, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
