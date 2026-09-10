#!/usr/bin/env python3
"""A Specctra session file: read it, put it on a board, and check it.

The routing of `bench-v2b` is a recorded artefact, `docs/routing/*.ses`,
the same way the pin golden is a recorded artefact in the 6502
repository. It is produced once by an autorouter (`tools/route-pcb.py`,
which needs Java and freerouting) and applied every time the board is
built (`tools/make-pcb.py`, which needs neither). So a fresh clone gets
the routed board, and the expensive stochastic step is not on the path
of every deploy.

The risk in recording a routing is that it goes stale: a part moves in
`ROWS`, the traces stay where they were, and the board is quietly wrong
in a way that looks perfectly plausible. `check_placement` is the answer
to that. The session file carries every component's position, so it can
be held to the board it is about to be applied to, and it fails loudly
when they disagree.
"""
import math
import re
from pathlib import Path

import pcbnew

NM_PER_UM = 1000


def parse(text):
    """The subset of a session file that matters: where the parts are,
    and every wire and via. Written as a tokeniser rather than with a
    general s-expression reader because the shapes below are the whole
    grammar this needs, and a partial parse that silently drops a wire
    would be worse than a parse error."""
    toks = re.findall(r'"[^"]*"|[()]|[^\s()]+', text)
    i, depth = 0, 0
    places, nets = {}, {}
    cur_net = None

    def unq(s):
        return s[1:-1] if s.startswith('"') else s

    while i < len(toks):
        t = toks[i]
        if t == "(":
            head = toks[i + 1] if i + 1 < len(toks) else ""
            if head == "place":
                ref = unq(toks[i + 2])
                places[ref] = (float(toks[i + 3]), float(toks[i + 4]))
            elif head == "net":
                cur_net = unq(toks[i + 2])
                nets.setdefault(cur_net, {"wires": [], "vias": []})
            elif head == "path" and cur_net:
                layer, width = unq(toks[i + 2]), float(toks[i + 3])
                pts, j = [], i + 4
                while j + 1 < len(toks) and toks[j] not in "()":
                    pts.append((float(toks[j]), float(toks[j + 1])))
                    j += 2
                nets[cur_net]["wires"].append((layer, width, pts))
            elif head == "via" and cur_net:
                nets[cur_net]["vias"].append((unq(toks[i + 2]),
                                              float(toks[i + 3]), float(toks[i + 4])))
        i += 1
    return places, nets


def scale_from(places, board):
    """How many nanometres one session unit is, measured against the
    board rather than read off the file's own `resolution` line.

    That line says `um 10` and KiCad's exporter and freerouting's
    importer do not agree about what it means: the same part comes back
    ten times larger than it went out. Every component in the file is a
    measurement of the same scale, so take them all and insist they
    agree."""
    ratios = []
    for ref, (sx, sy) in places.items():
        fp = board.FindFootprintByReference(ref)
        if fp is None or (sx == 0 and sy == 0):
            continue
        pos = fp.GetPosition()
        for a, b in ((pos.x, sx), (-pos.y, sy)):
            if abs(b) > 1:
                ratios.append(a / b)
    if not ratios:
        raise RuntimeError("the session file names no part this board has")
    lo, hi = min(ratios), max(ratios)
    if hi - lo > 0.02 * abs(hi):
        raise RuntimeError(f"the session file is not at one scale: {lo:.3f} to {hi:.3f} nm per unit")
    return sum(ratios) / len(ratios)


def check_placement(places, board, scale, tol_nm=1000):
    """Every part in the file, where the board has it. A routing is only
    true of the placement it was made for."""
    bad = []
    refs = {fp.GetReference() for fp in board.GetFootprints()}
    for ref in sorted(refs - set(places)):
        bad.append(f"{ref} is on the board and not in the session file")
    for ref in sorted(set(places) - refs):
        bad.append(f"{ref} is in the session file and not on the board")
    for ref, (sx, sy) in sorted(places.items()):
        fp = board.FindFootprintByReference(ref)
        if fp is None:
            continue
        pos = fp.GetPosition()
        dx, dy = pos.x - sx * scale, pos.y + sy * scale
        if math.hypot(dx, dy) > tol_nm:
            bad.append(f"{ref} has moved {math.hypot(dx, dy)/1e6:.3f} mm since the routing was made")
    return bad


def apply(nets, board, scale):
    """Wires to tracks, vias to vias. Returns (tracks, vias, problems)."""
    added_t = added_v = 0
    bad = []
    for name, body in sorted(nets.items()):
        net = board.FindNet(name)
        if net is None:
            if body["wires"] or body["vias"]:
                bad.append(f"the session file routes a net this board does not have: {name}")
            continue
        for layer_name, width, pts in body["wires"]:
            layer = board.GetLayerID(layer_name)
            if layer < 0:
                bad.append(f"{name}: unknown layer {layer_name}")
                continue
            for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
                t = pcbnew.PCB_TRACK(board)
                t.SetStart(pcbnew.wxPoint(int(round(x1 * scale)), int(round(-y1 * scale))))
                t.SetEnd(pcbnew.wxPoint(int(round(x2 * scale)), int(round(-y2 * scale))))
                t.SetWidth(int(round(width * scale)))
                t.SetLayer(layer)
                t.SetNet(net)
                board.Add(t)
                added_t += 1
        for padstack, x, y in body["vias"]:
            m = re.search(r"_(\d+):(\d+)_um", padstack)
            outer, drill = (int(m.group(1)) * NM_PER_UM, int(m.group(2)) * NM_PER_UM) if m else (800000, 400000)
            v = pcbnew.PCB_VIA(board)
            v.SetPosition(pcbnew.wxPoint(int(round(x * scale)), int(round(-y * scale))))
            v.SetWidth(outer)
            v.SetDrill(drill)
            v.SetViaType(pcbnew.VIATYPE_THROUGH)
            v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            v.SetNet(net)
            board.Add(v)
            added_v += 1
    return added_t, added_v, bad


def clearances(board, clearance_nm):
    """Copper of one net too near copper of another, measured here
    rather than taken on the router's word.

    The router says it left no violations. That is the router marking
    its own homework, and the whole reason this repository writes checks
    is that a tool's own report of its work is not evidence. KiCad's own
    shape geometry does the collision, so this is the same arithmetic
    the design rule checker would do, over the pairs that can actually
    fight: pads, tracks and vias."""
    copper = [pcbnew.F_Cu, pcbnew.B_Cu]

    def entry(item, what):
        # An effective shape is flat geometry and knows nothing about
        # layers. Comparing shapes without the layers each lives on
        # reports every crossing of a front trace over a back one as a
        # violation, which is what the first version of this did: 41 of
        # them, all of them nothing.
        on = {l for l in copper if item.IsOnLayer(l)}
        return (item.GetNetCode(), on, item.GetEffectiveShape(), what, item.GetBoundingBox())

    items = [entry(pad, f"{fp.GetReference()}-{pad.GetNumber()}")
             for fp in board.GetFootprints() for pad in fp.Pads()]
    items += [entry(t, f"{'via' if t.Type() == pcbnew.PCB_VIA_T else 'track'} on {t.GetNetname()}")
              for t in board.GetTracks()]
    bad = []
    for i, (n1, l1, s1, w1, b1) in enumerate(items):
        big = pcbnew.EDA_RECT(b1.GetOrigin(), b1.GetSize())
        big.Inflate(clearance_nm)
        for n2, l2, s2, w2, b2 in items[i + 1:]:
            if n1 == n2 or not (l1 & l2) or not big.Intersects(b2):
                continue
            if s1.Collide(s2, clearance_nm):
                bad.append(f"{w1} and {w2} are closer than {clearance_nm/1e6:.2f} mm "
                           f"on {'/'.join(board.GetLayerName(l) for l in sorted(l1 & l2))}")
    return bad


def read(path):
    return parse(Path(path).read_text())
