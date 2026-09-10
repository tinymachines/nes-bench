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


def overlaps(placed, with_text):
    """Two parts in the same place.

    `with_text` picks which bounding box, and the difference matters. The
    copper box is a fabrication error: two parts cannot occupy the same
    holes. The box including the reference and value text is a silkscreen
    problem, which makes a board harder to assemble and is not a reason
    to refuse one. The first version of this check compared text boxes
    against a packer that used copper boxes, and reported four overlaps
    that were only labels touching."""
    bad = []
    items = sorted(placed.items())
    for i, (r1, f1) in enumerate(items):
        b1 = f1.GetBoundingBox() if with_text else f1.GetBoundingBox(False, False)
        for r2, f2 in items[i + 1:]:
            b2 = f2.GetBoundingBox() if with_text else f2.GetBoundingBox(False, False)
            if b1.Intersects(b2):
                bad.append(f"{r1} and {r2}")
    return bad


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
    bad = [f"{a} overlap in copper" for a in overlaps(placed, with_text=False)]
    bad += [f"{r} is not fully inside the board outline" for r in outside(placed)]
    for m in unset + bad:
        print(f"  {m}")
    if unset or bad:
        return 1
    silk = overlaps(placed, with_text=True)
    if silk:
        print(f"  note: {len(silk)} pair(s) have overlapping silkscreen text: "
              f"{', '.join(silk[:4])}{' ...' if len(silk) > 4 else ''}")

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{SHEET}.kicad_pcb"
    board.Save(str(path))
    print(f"  {len(placed)} footprints placed, {len(keep)} nets, {applied} pads assigned")
    print(f"  wrote {path.relative_to(ROOT)}")
    readme = f"""# bench-v2b, the board: PLACED, NOT ROUTED

Generated by `tools/make-pcb.py` with KiCad {pcbnew.GetBuildVersion()}.

**Do not send this to a fabricator.** The parts are placed, every net
from the schematic is applied, the outline is drawn and ground and
supply are poured. **There are no signal traces.** A board made from
these files would be a bag of unconnected footprints with two copper
pours.

What is here, and what it is for:

- `bench-v2b.kicad_pcb` is the work. Open it in KiCad's PCB editor and
  route it, or feed it to an autorouter. The ratsnest is already correct,
  so nothing has to be typed in.
- The `.gbr`, `.drl` and positions files are the fabrication set, plotted
  from that board as it stands. They exist so the last step is proven to
  work rather than assumed: when the routing is done, re-run
  `python3 tools/make-pcb.py --plot` and these are what gets sent.

Decisions already made, and where they are written down:

- **{BOARD_W:.0f} by {BOARD_H:.0f} mm**, two layers, which is the cheap tier at most fabs.
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

Known and not fixed: four pairs of parts have overlapping silkscreen
text. That makes the board harder to read while assembling it and is not
a reason to refuse one.
"""
    (OUT / "README.md").write_text(readme)

    if a.plot:
        filled, written = plot(path, OUT)
        made = sorted(f.name for f in OUT.iterdir() if f.suffix.lower() in (".gbr", ".drl", ".csv", ".gbrjob"))
        print(f"  zones filled: {bool(filled)}; plotted {len(written)} gerber layer(s)")
        print(f"  fabrication set: {len(made)} files in {OUT.relative_to(ROOT)}")
    print("  NOT ROUTED: ground and supply are poured; the signal traces are still to do.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
