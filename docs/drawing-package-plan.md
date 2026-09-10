# Plan: a drawing package, and the road to a fabricated board

Written 2026-09-09. **M1 is built and is in this commit.** M2 to M5 are
proposed and nothing has been done on them.

## What this is for

Two goals that sound like one and are not:

1. **A document.** Border, title block, sheet numbering, one PDF, prints
   the same every time, and the same template reused by every future
   project.
2. **A fabricated board.** Gerbers, a drill file, a position file, a BOM
   a assembler can read.

The first is a drawing problem. The second is a netlist problem, and it
is the reason the order below is what it is: **a drawing that cannot
produce a netlist cannot produce a board**, no matter how good it looks.

## The thing that made this tractable

`tools/draw-schematics.py` has always drawn each pin as
`(number, name, net)`. Nobody had ever read it back. So the sheets have
carried a complete netlist since the day they were written, and
`tools/netlist.py` now extracts it: 8 references, 67 pins and 24 nets on
v1b alone.

That single fact is what makes both goals reachable from where we are,
rather than from a rewrite in a different tool.

## M1: the package. BUILT

- `tools/sheetframe.py` draws a sheet: ANSI B by default, an outer rule,
  a zone grid lettered A to D and numbered 8 to 1 so a note can say "U2
  is in B6" and mean it on paper, a header, a footer and a title block
  carrying project, sheet title, drawing number, revision, date, drawn
  by, source commit, scale and **sheet N of M**. Page sizes ANSI A/B and
  A3/A4 are in one table; nothing else in the file knows the size.
- `tools/make-package.py` reads `docs/package.json` and emits the sheets
  and one PDF. `rsvg-convert` writes the multi-page PDF at exactly 0.75
  points per unit, so an ANSI B sheet measures 17 by 11 inches in the
  PDF and prints as one.
- Five sheet kinds so far: `cover` with a sheet index, `schematic` which
  nests an existing SVG scaled to fit, `wiring` and `parts` which are
  derived, and `steps` which comes from the bring-up tool.
- **Nothing in the package is committed.** The SVGs are the artefact and
  `check-sheets.py` holds them to the wiring tables; the PDF is a
  rendering, made on demand, like the PNGs.

Two things it already taught, both fixed:

- A placed schematic carries its own white background, so a title block
  drawn before the content was **painted over and invisible**. The frame
  and the title block are drawn last now, and the drawing area stops
  above the title block rather than running under it.
- The title block's bottom row was 26 units tall for a label at +12 and
  a value at height minus 8, so the two collided. It has an assertion
  now: a row under 30 units fails loudly instead of overlapping.

## M2: make the schematics say what is true

`tools/netlist.py --erc` reports **19 errors across five sheets**. They
are not all bugs, and sorting them is the work:

- **`C1..C3` and `C1,C2` are not reference designators.** They are three
  capacitors drawn as one symbol with a range for a name. A wiring list
  cannot say which one, and a board cannot place them. Every part needs
  its own designator.
- **v1b's J1 shows +5 V on pin 7.** Step 1.1 rang this console out: pin
  7 carries nothing and the supply is on pin 5. **The connector on the
  sheet does not describe the console on the bench**, and the wiring
  list inherits that. This is the most important one.
- **v2b names PAD_LATCH, PAD_CLK, PAD1_D0, PAD2_D0 and VIDEO with one
  end each.** The pads and the video source are described in a note
  rather than drawn. Prose is not a connection.
- **Off-sheet nets need to be modelled as such**: PI_USB, `serial`,
  `radio`, USB_HID and v1b's EXT_TRIG are cables and radio links, not
  copper. They want an off-sheet symbol, not silence.
- **v1's relay VCC sits on PI_5V with nothing else on it**, and the
  PC817's VCC is deliberately unconnected but drawn blank rather than
  marked. A deliberate no-connect should say so.

The ERC is **not a deploy gate yet**, and will not be until it is clean.
A check that is known to fail teaches everyone to ignore it.

## M3: the wiring diagram, for building rather than reading

A schematic says what connects. It does not say where to put it. The
"for dummies" artefact is two pieces:

- **The wiring list**, which is built and on sheet 4: every net, every
  end, read out of the schematic so it cannot disagree with it.
- **A breadboard picture**, which is not built. It needs a *placement*:
  which row each chip sits in, which rail each lead lands on. That is
  authored, one table, and then **every wire is derived from the
  netlist**. Authored placement, derived wires, the same split this
  project uses everywhere else.

## M4: the netlist out, in a format an EDA tool takes

KiCad is not installed here. It does not need to be for this step: the
netlist can be written as a KiCad `.net` s-expression or the older
Protel format, both of which nearly every tool imports. That is the
handoff, and it is small once M2 is done.

## M5: a board

Honest about what this costs. A netlist is not a board. A board needs a
footprint chosen for every part, a placement, a route, a design rule
check against the fab's capabilities, and then Gerbers, an Excellon
drill file, a position file and a BOM. **That is real work and it is
done in an EDA tool, not here.** KiCad is the obvious choice: free,
scriptable, and `kicad-cli` can export the whole fab package headlessly
once a layout exists.

Worth saying plainly: **v1b is three DIP chips, three capacitors and a
resistor.** A board for it is a nice object and a good way to learn the
flow, but it buys reliability that a socketed breadboard mostly already
has. **v2b is the one that wants a board**: two register pairs, a sync
separator, and enough wires that a breadboard becomes the experiment's
biggest error source.

## The order, and why

M2 before everything. Every later step reads the netlist, so the netlist
has to be true first. A wiring diagram derived from a connector that
does not match the console would send somebody's probe to pin 7.
