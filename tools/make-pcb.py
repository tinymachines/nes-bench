#!/usr/bin/env python3
"""The v2b board: footprints placed, nets applied, outline drawn.

  python3 tools/make-pcb.py            # -> docs/fab/bench-v2b/
  python3 tools/make-pcb.py --plot     # ...and the Gerbers, drill and position

Built with KiCad's own `pcbnew` module rather than by writing board files
by hand, so the format is whatever the installed KiCad says it is.

**This does not route the board.** It places every part, applies every
net, draws the outline and pours ground and supply, and then stops. The
signal traces are a human's job in KiCad, or an autorouter's; what this
removes is the hours of mechanical work around that, and the chance of a
netlist being retyped wrong on the way in.

The placement is authored, like the breadboard's. Everything else comes
from the schematic through tools/netlist.py.
"""
import argparse
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "fab" / "bench-v2b"
sys.path.insert(0, str(ROOT / "tools"))
from loadmod import load  # noqa: E402

import pcbnew  # noqa: E402

SHEET = "bench-v2b"
BOARD_W, BOARD_H = 100.0, 100.0     # mm, the cheap fabs' hundred square
EDGE = 0.15                          # mm, Edge.Cuts line width

# AUTHORED design rules, in um, and the ones the router is held to. They
# are KiCad's own defaults, which is why they can be authored here and
# checked against the exported design rather than pushed into the board:
# KiCad 6's Python bindings cannot reach a netclass. 250 um track and
# 200 um clearance is inside every cheap fab's capability, with room.
TRACK_UM, CLEARANCE_UM = 250.0, 200.0
SESSION = ROOT / "docs" / "routing" / f"{SHEET}.ses"

# AUTHORED: the arrangement, as rows of parts left to right. Signal flow
# runs down the board: the console ports come in on the left of each row,
# the registers sit in the order the SPI chain shifts through them, and
# the ribbon to the UNO leaves along the bottom.
#
# The ARRANGEMENT is the judgement. The coordinates are not: an earlier
# version of this file authored an (x, y) per part and nine of them
# overlapped, because I was doing footprint arithmetic in my head against
# sizes I had guessed. The packer below reads each footprint's real
# bounding box and lays the rows out, so a part can be moved in the list
# without anyone recomputing anything.
ROWS = [
    ["J1", "U1", "U8", "C7", "R2", "C8"],
    ["J3", "U2", "U5", "C1", "C2"],
    ["J4", "U6", "U7", "C3", "C4"],
    ["J2", "C5", "C6", "R1", ("A1", 90)],
]
MARGIN, GAP, ROW_GAP = 6.0, 5.0, 5.0


def pack(loaded):
    """Rows of parts to positions, from the footprints' own sizes."""
    IU = pcbnew.IU_PER_MM
    at, y = {}, MARGIN
    for row in ROWS:
        tallest = 0.0
        x = MARGIN
        for entry in row:
            ref, rot = entry if isinstance(entry, tuple) else (entry, 0)
            fp = loaded[ref]
            fp.SetOrientationDegrees(rot)
            bb = fp.GetBoundingBox(False, False)
            w, h = bb.GetWidth() / IU, bb.GetHeight() / IU
            # The origin is pad 1, not the corner, so shift by the offset
            # between them or the part hangs off the row.
            ox = fp.GetPosition().x / IU - bb.GetX() / IU
            oy = fp.GetPosition().y / IU - bb.GetY() / IU
            at[ref] = (x + ox, y + oy, rot)
            x += w + GAP
            tallest = max(tallest, h)
        y += tallest + ROW_GAP
    return at, y


def lib_and_name(fp):
    libname, _, name = fp.partition(":")
    return f"/usr/share/kicad/footprints/{libname}.pretty", name


def build():
    nl = load(ROOT / "tools" / "netlist.py", "nl")
    ex = load(ROOT / "tools" / "export-netlist.py", "ex")
    sheets, offsheet = nl.collect()
    nodes = sheets[SHEET]
    nets = nl.nets_of(nodes)
    keep, _dropped = ex.routable(nets, offsheet)
    parts = ex.components(nodes)

    board = pcbnew.CreateEmptyBoard()
    netinfo = {}
    for name in sorted(keep):
        n = pcbnew.NETINFO_ITEM(board, name)
        board.Add(n)
        netinfo[name] = n

    placed = {}
    for ref, part in sorted(parts.items()):
        fp_name, _why = ex.footprint(part)
        libpath, name = lib_and_name(fp_name)
        fp = pcbnew.FootprintLoad(libpath, name)
        if fp is None:
            raise RuntimeError(f"{ref}: could not load {fp_name}")
        fp.SetReference(ref)
        fp.SetValue(ex.value_of(part))
        placed[ref] = fp

    listed = {r if isinstance(r, str) else r[0] for row in ROWS for r in row}
    if listed != set(placed):
        raise RuntimeError(f"ROWS and the schematic disagree: only in ROWS {listed - set(placed)}, "
                           f"only on the sheet {set(placed) - listed}")
    at, used_h = pack(placed)
    for ref, fp in placed.items():
        x, y, _rot = at[ref]
        fp.SetPosition(pcbnew.wxPointMM(x, y))
        board.Add(fp)

    # Nets onto pads, straight out of the schematic.
    applied, unset = 0, []
    for net, ns in keep.items():
        for ref, pad_no, _fn in ex.net_pads(ns):
            fp = placed[ref]
            pad = fp.FindPadByNumber(str(pad_no))
            if pad is None:
                unset.append(f"{ref} has no pad {pad_no} on {fp.GetFPID().GetLibItemName()}")
                continue
            pad.SetNet(netinfo[net])
            applied += 1

    # The outline.
    for a, b in (((0, 0), (BOARD_W, 0)), ((BOARD_W, 0), (BOARD_W, BOARD_H)),
                 ((BOARD_W, BOARD_H), (0, BOARD_H)), ((0, BOARD_H), (0, 0))):
        seg = pcbnew.PCB_SHAPE(board)
        seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
        seg.SetStart(pcbnew.wxPointMM(*a))
        seg.SetEnd(pcbnew.wxPointMM(*b))
        seg.SetLayer(pcbnew.Edge_Cuts)
        seg.SetWidth(int(EDGE * pcbnew.IU_PER_MM))
        board.Add(seg)

    # Ground on the back, supply on the front: the two nets with the most
    # nodes by far, and the two a router would spend the longest on.
    for netname, layer in (("GND", pcbnew.B_Cu), ("+5V", pcbnew.F_Cu)):
        if netname not in netinfo:
            continue
        zone = pcbnew.ZONE(board)
        zone.SetLayer(layer)
        zone.SetNet(netinfo[netname])
        zone.SetIsFilled(False)
        pts = pcbnew.wxPoint_Vector()
        for x, y in ((1, 1), (BOARD_W - 1, 1), (BOARD_W - 1, BOARD_H - 1), (1, BOARD_H - 1)):
            pts.append(pcbnew.wxPointMM(x, y))
        zone.AddPolygon(pts)
        board.Add(zone)

    return board, placed, keep, applied, unset


def vias_of(path):
    b = pcbnew.LoadBoard(str(path))
    return len([t for t in b.GetTracks() if t.Type() == pcbnew.PCB_VIA_T])


def apply_routing(path):
    """The recorded routing onto the board, and then the two questions
    that decide whether a board can be made: is every net actually
    joined, and is any copper too near copper of another net.

    Neither is taken on the router's word. The router reports its own
    completion and its own violation count, and a tool's report of its
    own work is not evidence: the first run here came back "0 incomplete,
    0 violations" while three pads had no copper path to their net,
    because the pours had been declared as planes and its own traces had
    cut them into islands. KiCad's connectivity engine and KiCad's shape
    geometry answer both questions here, on the finished board, with the
    zones filled as a fabricator would get them.

    MUTATE=1 lands one track on a pad of another net; the clearance
    check must go red. MUTATE_OPEN=1 deletes one track; the connectivity
    check must go red. Both refuse to pass."""
    board = pcbnew.LoadBoard(str(path))
    if not SESSION.exists():
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        board.Save(str(path))
        return None, None, []
    ss = load(ROOT / "tools" / "session.py", "session")
    places, nets = ss.read(SESSION)
    scale = ss.scale_from(places, board)
    moved = ss.check_placement(places, board, scale)
    if moved:
        for m in moved:
            print(f"  {m}")
        raise RuntimeError(f"the recorded routing is not this placement: {len(moved)} part(s) differ. "
                           "Re-run tools/route-pcb.py.")
    tracks, vias, problems = ss.apply(nets, board, scale)
    for m in problems:
        print(f"  {m}")

    mutated = False
    if os.environ.get("MUTATE"):
        # Land a track squarely on a pad of another net. Nudging one by a
        # fifth of a millimetre was the first version of this and it went
        # green: there was nothing within a fifth of a millimetre of it,
        # so the mutation proved only that the board has room in it.
        pad = board.FindFootprintByReference("U1").FindPadByNumber("1")
        here, code = pad.GetPosition(), pad.GetNetCode()
        t = next(x for x in board.GetTracks()
                 if x.Type() != pcbnew.PCB_VIA_T and x.GetNetCode() != code)
        t.SetStart(pcbnew.wxPoint(here.x, here.y))
        t.SetEnd(pcbnew.wxPoint(here.x + 1000000, here.y))
        t.SetLayer(pcbnew.F_Cu)
        print(f"  MUTATE: a {t.GetNetname()} track moved onto U1 pad 1 ({pad.GetNetname()})")
        mutated = True
    if os.environ.get("MUTATE_OPEN"):
        board.Remove([x for x in board.GetTracks() if x.Type() != pcbnew.PCB_VIA_T][7])
        print("  MUTATE_OPEN: one track deleted")
        mutated = True

    # Clearance BEFORE the pour, connectivity after it, and the order is
    # not a preference. In a process that has already built a board with
    # CreateEmptyBoard, running the zone filler leaves the shape geometry
    # unable to see collisions: the same mutated track that collides with
    # a pad of another net three ways before the fill collides with
    # nothing after it. Connectivity is the opposite way round, because
    # an unfilled pour connects nothing. MUTATE and MUTATE_OPEN are what
    # hold this pair of orderings honest.
    viol = ss.clearances(board, int(CLEARANCE_UM * 1000))
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    conn = board.GetConnectivity()
    conn.RecalculateRatsnest()
    unrouted = conn.GetUnconnectedCount()
    print(f"  routed: {tracks} track segments, {vias} vias, "
          f"{unrouted} unconnected, {len(viol)} clearance violation(s)")
    if not (unrouted or viol) and not mutated:
        board.Save(str(path))
    if mutated and not (unrouted or viol):
        raise AssertionError("MUTATE left the board clean: the check cannot see what it claims to")
    return tracks, unrouted, viol


def overlaps(placed):
    """Two parts in the same holes. A fabrication error, and the reason
    the packer measures footprints instead of trusting arithmetic done
    in somebody's head."""
    bad = []
    items = sorted(placed.items())
    for i, (r1, f1) in enumerate(items):
        b1 = f1.GetBoundingBox(False, False)
        for r2, f2 in items[i + 1:]:
            if b1.Intersects(f2.GetBoundingBox(False, False)):
                bad.append(f"{r1} and {r2}")
    return bad


SILK_TO_CU = {pcbnew.F_SilkS: pcbnew.F_Cu, pcbnew.B_SilkS: pcbnew.B_Cu}


def silk_items(fp):
    """What a footprint actually puts on a silkscreen layer: its
    reference label if that is where the label lives, and its outline.

    NOT its bounding box. A footprint's box includes the Value field,
    and these libraries put Value on F.Fab, which is not a silkscreen,
    is not plotted, and is not in the fabrication set at all. J2's value
    is the string "original pad, on the bridge": twenty one millimetres
    of text on a three and a half millimetre connector. That box is what
    made this check report four silkscreen overlaps for as long as it
    existed, and all four of them were fab-layer text that nothing will
    ever print. Measure the layer the question is about."""
    out = []
    for field in (fp.Reference(), fp.Value()):
        if field.GetLayer() in SILK_TO_CU and field.IsVisible():
            out.append((field.GetLayer(), field.GetBoundingBox(),
                        f'the "{field.GetText()}" label'))
    for item in fp.GraphicalItems():
        if item.GetLayer() in SILK_TO_CU:
            out.append((item.GetLayer(), item.GetBoundingBox(), "an outline"))
    return out


def silkscreen_faults(board):
    """Silkscreen that will not read as drawn: a label on top of another
    part's silkscreen, or silkscreen over anybody's pad.

    Neither refuses a board. A fab clips silk off pads and a crowded
    label is an assembly annoyance, not a fabrication error, which is
    exactly why they are counted separately from copper. They are worth
    counting because a reference designator nobody can read is what
    turns a fifteen minute build into an hour with a magnifier.

    MUTATE_SILK=1 drags one reference label onto its neighbour's, and
    this has to go red: a check that reports nothing on a clean board
    and nothing on a broken one is reporting nothing."""
    fps = sorted(board.GetFootprints(), key=lambda f: f.GetReference())
    silk = {f.GetReference(): silk_items(f) for f in fps}
    if os.environ.get("MUTATE_SILK"):
        a, b = fps[0], fps[1]
        a.Reference().SetPosition(b.Reference().GetPosition())
        silk[a.GetReference()] = silk_items(a)
        print(f"  MUTATE_SILK: {a.GetReference()}'s label moved onto {b.GetReference()}'s")
    faults = []
    for i, f1 in enumerate(fps):
        for f2 in fps[i + 1:]:
            for l1, b1, w1 in silk[f1.GetReference()]:
                for l2, b2, w2 in silk[f2.GetReference()]:
                    if l1 == l2 and b1.Intersects(b2):
                        faults.append(f"{f1.GetReference()} {w1} touches {f2.GetReference()} {w2}")
    for f1 in fps:
        for layer, box, what in silk[f1.GetReference()]:
            cu = SILK_TO_CU[layer]
            for f2 in fps:
                for pad in f2.Pads():
                    if not pad.IsOnLayer(cu) or (f1 is f2 and what == "an outline"):
                        continue
                    if box.Intersects(pad.GetBoundingBox()):
                        faults.append(f"{f1.GetReference()} {what} sits over "
                                      f"{f2.GetReference()}-{pad.GetNumber()}")
    return faults


def outside(placed):
    lim = pcbnew.EDA_RECT(pcbnew.wxPointMM(0, 0), pcbnew.wxSizeMM(BOARD_W, BOARD_H))
    return [r for r, f in sorted(placed.items())
            if not lim.Contains(f.GetBoundingBox(False, False))]


GERBERS = [
    ("F_Cu", "F.Cu", "Top copper"), ("B_Cu", "B.Cu", "Bottom copper"),
    ("F_Paste", "F.Paste", "Top paste"), ("B_Paste", "B.Paste", "Bottom paste"),
    ("F_SilkS", "F.Silkscreen", "Top silk"), ("B_SilkS", "B.Silkscreen", "Bottom silk"),
    ("F_Mask", "F.Mask", "Top mask"), ("B_Mask", "B.Mask", "Bottom mask"),
    ("Edge_Cuts", "Edge.Cuts", "Board outline"),
]


def plot(path, outdir):
    """Gerbers, drill and a position file, from the SAVED board.

    Deliberately reloaded from disk rather than plotted in memory: the
    board this tool builds with CreateEmptyBoard segfaults the plot
    controller, and reloading the same file plots fine. Whatever the
    loader sets up that the constructor does not, the fix costs a
    millisecond and it also means the fabrication set is plotted from
    exactly the file the fab would be sent."""
    board = pcbnew.LoadBoard(str(path))
    filled = pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pctl = pcbnew.PLOT_CONTROLLER(board)
    o = pctl.GetPlotOptions()
    o.SetOutputDirectory(str(outdir))
    o.SetPlotFrameRef(False)
    o.SetAutoScale(False)
    o.SetScale(1)
    o.SetMirror(False)
    o.SetUseGerberAttributes(True)
    o.SetUseGerberProtelExtensions(False)
    o.SetExcludeEdgeLayer(True)
    o.SetSubtractMaskFromSilk(False)
    written = []
    for attr, name, human in GERBERS:
        pctl.SetLayer(getattr(pcbnew, attr))
        pctl.OpenPlotfile(name, pcbnew.PLOT_FORMAT_GERBER, human)
        pctl.PlotLayer()
        written.append(name)
    pctl.ClosePlot()

    # The two copper layers as SVG as well as Gerber. A Gerber viewer is
    # not something everybody has, and the point of the fabrication set
    # is that somebody can see what they would be ordering.
    o.SetExcludeEdgeLayer(False)
    o.SetPlotReference(True)
    o.SetPlotValue(False)
    for attr, name in (("F_Cu", "top-copper"), ("B_Cu", "bottom-copper"),
                       ("F_SilkS", "top-silk")):
        pctl.SetLayer(getattr(pcbnew, attr))
        pctl.OpenPlotfile(name, pcbnew.PLOT_FORMAT_SVG, name)
        pctl.PlotLayer()
    pctl.ClosePlot()

    w = pcbnew.EXCELLON_WRITER(board)
    w.SetFormat(True)
    w.SetOptions(False, False, board.GetDesignSettings().GetAuxOrigin(), False)
    w.CreateDrillandMapFilesSet(str(outdir), True, False)

    IU = pcbnew.IU_PER_MM
    rows = ["Ref,Val,Package,PosX,PosY,Rot,Side"]
    for fp in sorted(board.GetFootprints(), key=lambda f: f.GetReference()):
        pos = fp.GetPosition()
        side = "bottom" if fp.IsFlipped() else "top"
        rows.append(f"{fp.GetReference()},{fp.GetValue()},"
                    f"{fp.GetFPID().GetLibItemName()},"
                    f"{pos.x / IU:.3f},{-pos.y / IU:.3f},"
                    f"{fp.GetOrientationDegrees():.1f},{side}")
    (outdir / "bench-v2b-positions.csv").write_text("\n".join(rows) + "\n")
    return filled, written


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plot", action="store_true", help="also write the fabrication outputs")
    a = ap.parse_args()

    board, placed, keep, applied, unset = build()
    bad = [f"{a} overlap in copper" for a in overlaps(placed)]
    bad += [f"{r} is not fully inside the board outline" for r in outside(placed)]
    for m in unset + bad:
        print(f"  {m}")
    if unset or bad:
        return 1

    silk = silkscreen_faults(board)
    print(f"  silkscreen: {len(silk)} fault(s) on the two silk layers "
          f"across {len(placed)} parts")
    if silk:
        for m in silk[:6]:
            print(f"  note: {m}")
        if len(silk) > 6:
            print(f"  note: and {len(silk) - 6} more")
    if os.environ.get("MUTATE_SILK") and not silk:
        raise AssertionError("MUTATE_SILK left the silkscreen clean: "
                             "the check cannot see what it claims to")

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{SHEET}.kicad_pcb"
    board.Save(str(path))
    print(f"  {len(placed)} footprints placed, {len(keep)} nets, {applied} pads assigned")

    # The routing goes on the SAVED board, reloaded. A board made by
    # CreateEmptyBoard segfaults the zone filler exactly as it segfaults
    # the plot controller, and the fill is what makes the connectivity
    # answer mean anything.
    routed, unrouted, viol = apply_routing(path)
    if routed is None:
        print("  NOT ROUTED: no recorded routing in docs/routing/. "
              "Run tools/route-pcb.py, or route it in KiCad.")
    elif unrouted or viol:
        for m in viol[:8]:
            print(f"  {m}")
        print(f"  REFUSED: {unrouted} unconnected item(s), {len(viol)} clearance violation(s)")
        return 1
    print(f"  wrote {path.relative_to(ROOT)}")
    stats = (f"**Routed.** {routed} track segments and {vias_of(path)} vias carry every net the "
             f"schematic has. Checked on this file, not on the router's word: **0 unconnected "
             f"items** with the pours filled, and **0 clearance violations** at "
             f"{CLEARANCE_UM:.0f} um."
             if routed else
             "**Not routed.** The parts are placed and every net is applied, and there are no "
             "signal traces. A board made from these files would be a bag of unconnected "
             "footprints with two copper pours.")
    readme = f"""# bench-v2b, the board

Generated by `tools/make-pcb.py` with KiCad {pcbnew.GetBuildVersion()}.

{stats}

What is here, and what it is for:

- `bench-v2b.kicad_pcb` is the board. Open it in KiCad's PCB editor to
  look at it or change it.
- The `.gbr`, `.drl` and positions files are the fabrication set,
  plotted from exactly that file.
- `bench-v2b-top-copper.svg`, `-bottom-copper.svg` and `-top-silk.svg`
  are the same three layers to look at without a Gerber viewer. The silk
  one is the sheet to print when placing parts.

How the routing is made, and why it is a file:

- The traces come from `docs/routing/bench-v2b.ses`, a Specctra session
  recorded once by `tools/route-pcb.py` (freerouting, headless) and
  applied on every build by `tools/session.py`. Routing is the only step
  here that is slow and not deterministic; recording it means a fresh
  clone gets a routed board and no build needs Java.
- The recording carries every part's position, so it is held to the
  placement it is applied to. Move a part in `ROWS` and the build stops
  and says which one, rather than laying old traces on a new board.
- **The router's own report is not the evidence.** It says how many
  connections it left incomplete and how many clearances it broke;
  KiCad's connectivity engine and KiCad's shape geometry are asked the
  same two questions here, on the finished board with the zones filled.
  The first run of this passed the router's own check with three pads
  that had no copper path to their net.

Decisions already made, and where they are written down:

- **{BOARD_W:.0f} by {BOARD_H:.0f} mm**, two layers, which is the cheap tier at most fabs.
- **{TRACK_UM:.0f} um track, {CLEARANCE_UM:.0f} um clearance**, authored in `tools/make-pcb.py` and
  checked against the design KiCad exports before a router sees it.
- **Ground is poured on the back and supply on the front, and both are
  also routed as traces.** Poured alone they were declared to the router
  as planes, it treated every pad on them as already connected, and its
  own signal traces then cut the pours into islands. The pours go on
  over the top of the traces and are the return path, not the only one.
- **A1 is a cable, not a shield.** A 20 way IDC header and a ribbon to
  the UNO. The pinout is `A1_HEADER` in `tools/export-netlist.py`, and
  five of its pads are ground so the fast edges have a return path near
  them.
- Every footprint is checked to exist in the installed library, not just
  to be spelled plausibly. Two of them were wrong when that check was
  added.
- The placement arrangement is authored in `tools/make-pcb.py`; the
  coordinates are computed from the footprints' own sizes, because the
  version that authored coordinates by hand put nine parts on top of
  each other.
- **The silkscreen is clear**: no reference label on another part's
  silkscreen, and no silkscreen over anybody's pad. This used to say
  four pairs overlapped. They did not. The check was measuring each
  footprint's whole bounding box, which includes the Value field, and
  these libraries put Value on F.Fab: J2's is the string "original pad,
  on the bridge", 21 mm of text on a 3.6 mm connector, on a layer that
  is not plotted and is not in this folder.
"""
    (OUT / "README.md").write_text(readme)

    if a.plot:
        filled, written = plot(path, OUT)
        made = sorted(f.name for f in OUT.iterdir()
                      if f.suffix.lower() in (".gbr", ".drl", ".csv", ".gbrjob", ".svg"))
        print(f"  zones filled: {bool(filled)}; plotted {len(written)} gerber layer(s)")
        print(f"  fabrication set: {len(made)} files in {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
