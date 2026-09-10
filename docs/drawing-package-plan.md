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

## M2: make the schematics say what is true. DONE 2026-09-09

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

**All five sheets are clean and the ERC is a deploy gate now.** Three
mutations put it back to red: a repeated designator, a net renamed at
one end only, and a supply pin left silent.

**What the ERC cannot catch, and what does.** A connector drawn with the
right connections and the wrong pinout passes every connectivity rule:
it is perfectly wired and perfectly wrong, and it is the error that
sends a probe to a pin carrying nothing. So the pinout is held to the
measurement instead of to itself. `docs/wiring.md`'s port table is now
the one place it is written down, and `tools/check-sheets.py` holds both
the schematic's connector symbol and `tools/bringup.py` to it. Putting
the published pinout back on the sheet fails that check on three pins.

## M3: the wiring diagram, for building rather than reading. DONE 2026-09-09

A schematic says what connects. It does not say where to put it. The
"for dummies" artefact is two pieces:

- **The wiring list**, which is built and on sheet 4: every net, every
  end, read out of the schematic so it cannot disagree with it.
- **A breadboard picture**, `tools/breadboard.py`, which is built. The
  placement is authored, one table at the top of that file: which column
  each package starts in, where each cable comes in, where the
  decoupling sits. **Every wire is derived from the netlist**: 21
  numbered jumpers and 16 rail stubs on v1b. Changing a net in the
  schematic changes the picture, which is how the claim is tested.

  Three things it taught:

  - **The hole a pin lands in is computed, not placed.** A DIP with its
    notch left puts pin 1 at the bottom-left and counts anticlockwise,
    so pin i of an N-pin package is at column c0+(i-1) below and
    c0+(N-i) above. Get that rule wrong and every wire is wrong while
    the picture still looks like a breadboard, so it is asserted against
    both package sizes' known supply pins.
  - **A wire does not plug into a pin.** The leg is already in that
    hole. It goes into another hole in the same column, which is the
    same node, and the drawing has to say which one: the key gives a
    column and a row for every end.
  - **The first router drew all 37 wires as orthogonal runs in lanes**,
    every one correct and the picture unreadable. Curved jumpers with a
    numbered key read the way an assembly drawing reads, and are closer
    to what a jumper actually looks like lying on a board.

## M4: the netlist out, in a format an EDA tool takes. DONE 2026-09-09

`tools/export-netlist.py` writes, per sheet, into `docs/fab/`:

- `<sheet>.net`, a KiCad netlist for File > Import > Netlist,
- `<sheet>.protel.net`, which nearly every other tool takes,
- `<sheet>-bom.csv`, grouped by value and footprint.

v1b is 10 components and 21 routable nets; v2b is 21 and 39. Neither
needs KiCad installed to produce.

**The connections are derived; the footprints are a decision.** A 100 nF
capacitor can be any of a dozen packages and only the person with the
drawer knows which, so `FOOTPRINTS` is authored and `--check` fails on a
part that has not been given one. The deploy runs that check, so a new
part on a sheet cannot ship as an empty field.

**Two things the export refused to paper over.**

- **A1 is not a component.** It is an Arduino board. Giving it a
  footprint at all is already a decision: `Module:Arduino_UNO_R3_Shield`
  says this PCB plugs into the UNO's headers. If it is meant to sit
  beside the UNO on a cable, A1 becomes a pin header instead. Every file
  written says so.
- **A schematic pin is a label; a netlist node is a pad.** "D2 (INT0)"
  and "D13 SCK" become D2 and D13, which are pads. A pin that names more
  than one physical pin cannot become a node at all, and the exporter
  refuses to invent one rather than guessing. The UNO's serial is drawn
  as a single pin "D0, D1", which is two pads; it happens to sit on an
  off-sheet net, so nothing is lost today, but the same rule will stop a
  future sheet quietly.

Single-node nets are left out of the netlists and named in the output:
they are connectors leaving the board, real but with nothing to route.

**The writer is checked against itself.** Every file is read back and
compared node for node with the schematic it came from. A writer that
drops one node produces a perfectly well formed file that nothing
downstream would question, so dropping a node deliberately is the test:
it reports the missing pad on every net it touches.

## M5: a board. PLACED 2026-09-09, ROUTED 2026-09-10 (M8)

Honest about what this costs. A netlist is not a board. A board needs a
footprint chosen for every part, a placement, a route, a design rule
check against the fab's capabilities, and then Gerbers, an Excellon
drill file, a position file and a BOM. **That is real work and it is
done in an EDA tool, not here.** KiCad is the obvious choice: free,
scriptable, and `kicad-cli` can export the whole fab package headlessly
once a layout exists.

**Decided 2026-09-09: v2b, and a cable rather than a shield.** A1 is a
20 way IDC header with a ribbon to the UNO. Sixteen signals would fit a
16 way part exactly and would carry SCK and two console clocks with one
ground for the whole cable; the 20 way part costs the same and its four
spare pads are grounds, sitting beside the fastest edges. `A1_HEADER` in
`tools/export-netlist.py` is that pinout.

KiCad 6.0.2 is installed here now, and `tools/make-pcb.py` builds the
board through its own `pcbnew` module: 21 footprints placed, 39 nets
applied, 131 pads assigned, a 100 by 100 mm outline, ground poured on
the back and supply on the front. The fabrication set plots: nine
Gerbers, two drill files and a position file. 146 plated holes, which is
exactly the pad count of the 21 parts.

**It was not routed, and the folder's own README said so in its first
line. M8 is where that changed.**

Three things it taught:

- **A footprint name is a claim about a file.** Two of mine were guesses
  and both were wrong: DIP-08 is spelled DIP-8, and the axial resistor
  needs its `_Horizontal` suffix. The check that passed them only asked
  whether a string was present. It looks in the library now.
- **Authored coordinates are a mistake I will keep making.** The first
  placement put nine parts on top of each other, because I was doing
  footprint arithmetic in my head against sizes I had guessed. The
  arrangement is authored as rows; the coordinates come from the
  footprints' own bounding boxes.
- **Two bounding boxes mean two different things.** Copper overlap is a
  fabrication error; silkscreen overlap is an assembly annoyance. The
  first version compared one against the other and reported four faults
  that were only labels touching. It then reported the same four for a
  week, and M9 is where they turned out not to exist.

Worth saying plainly: **v1b is three DIP chips, three capacitors and a
resistor.** A board for it is a nice object and a good way to learn the
flow, but it buys reliability that a socketed breadboard mostly already
has. **v2b is the one that wants a board**: two register pairs, a sync
separator, and enough wires that a breadboard becomes the experiment's
biggest error source.

## M6: landscape letter, and coordinates nobody types. DONE 2026-09-10

The package built at M4 was ANSI B, 17 by 11 inches, because that is
what the drawings happened to be. `bench-v1b.svg` was 1900 by 1000
units, it landed on the page at 76%, and a third of the sheet was
white. On the letter paper that is actually in the house it would have
placed at 63%, which puts a 9.5 px pin name on paper at **4.5 pt**.

Three changes, and the middle one is the only interesting one.

**The page decides how big the drawing may be, not the other way
round.** `sheetframe.drawing_box("ansi-a")` answers 952 by 542 units,
title block and header already subtracted, and `draw-schematics.py`
asks it rather than carrying a copy. The title block is proportioned to
the paper too: 470 units is a fifth of an ANSI B sheet and nearly half
a letter one, and at letter size it was eating the drawing.

**The coordinates are derived.** This is the same authored/derived
split as the PCB placer and the breadboard sheet, arriving in the last
place that still typed numbers. A sheet body now says which band,
column and row each part sits in and nothing else; the body is drawn
twice, once to measure every part where it stands and once to draw it
where the measurements say it goes. Columns are as wide as their widest
part **including its net flags**, rows as tall as their tallest, and
the dashed band boxes are derived from what is inside them. Adding a
pin to a chip moves its neighbours instead of quietly overlapping them,
and the sheet's own size falls out at the end.

**A sheet that will not print is refused.** `place_svg` is the one
place that knows both a drawing's type size and the scale it is being
placed at, so it is the only place that can tell. Below 5 pt it raises
rather than shrinks. That is not decoration: it is what forced the rest
of this milestone, and it is what said, in numbers, that

- **v1b does not fit on one letter sheet.** Five parts in a row is
  1500 units wide before the flags; letter gives 952. It is now **one
  schematic on two sheets of paper**, console side and bridge side,
  with the nets that cross carrying a link flag with the other sheet's
  number in it. The netlist tools collect both bodies under the one
  name `bench-v1b`, so the rule check still sees a whole design: what
  is split is the paper, not the circuit.
- **v2b does not fit on any paper in this house.** 2300 by 1580 places
  at 48% on ANSI B and 3.3 pt. It is out of this package until it gets
  the same split, and the cover says so rather than the reader finding
  out with a magnifier.
- **the breadboard and the timing lanes need ANSI B**, so they declare
  it in `package.json` and the index prints a paper column. A breadboard
  is 63 columns long and one poll is one poll wide; neither shrinks.

Two things it cost, both worth the same lesson:

- **The rule check caught the first draft immediately.** A body drawn
  twice was recorded twice, so every pin on the sheet came back as
  drawn more than once. The recorders now ask the sheet whether it is
  measuring. The check that found it is the one built at M2, on its
  own work, two days later.
- **`bank()` was never in the bill of materials.** Wrapping the
  recorders to fix the double count is what made it obvious that three
  of them wrap `chip` and `twopin` and none of them wrapped `bank`.
  C4 and C5 have been on the v2 sheet and in nobody's drawer since the
  day banks were added.

Left open, by name: the v2b package, and a breadboard sheet split into
two letter pages if the ANSI B one turns out to be a nuisance to print.
The v2b package is M7.

## M7: the v2b package. DONE 2026-09-10

`TM-NESB-002`, nine pages, landscape letter, and the drawing that M6
refused is now four sheets that print:

| sheet | what is on it | places at |
|---|---|---|
| 1 | port 1: J1, the inverter, U2 | 83% |
| 2 | port 2: J3, U6, and the decoupling | 92% |
| 3 | the UNO and both output registers on one SPI chain | 79% |
| 4 | the LM1881, both pads, the trigger and the passives | 92% |

**Three columns is the letter limit** and it is arithmetic, not taste:
a DIP with net flags on both sides wants about 310 units, letter gives
952, and two rows of tall parts is 650 units of height against 542. The
split follows the circuit rather than the page, which is why port 1 and
port 2 get a sheet each even though port 2's sheet has room to spare:
the pair of them are the same circuit twice and reading them side by
side is the point.

**Nothing about the design changed.** The rule check still collects all
four bodies under the one name `bench-v2b` and reports the same 21
references, 143 pins and 42 nets it did when this was one sheet, so
what was split is the paper.

Four things this milestone added to the machinery, each because a sheet
made it necessary:

- **Each package has its own manifest and its own directory.**
  `make-package.py` with no arguments builds every `docs/package*.json`
  into `docs/package/<docno>/`. Before this, a second package would
  have deleted the first one's sheets on its way past.
- **Wiring and parts lists paginate**, the way the build sequence
  already did. v2b's 42 nets do not fit on a letter page; the driver
  adds the sheet and re-renders the package so "sheet n of m" is still
  true on every page. The table itself no longer writes "continues on
  the next sheet", because it is not the table's business whether there
  is one.
- **A parts list can be scoped to its own sheets.** A person building
  v1b does not need the pad adapter's LiPo charger in their list.
- **The sheet title fits its cell.** "Bridge v2b, sheet 4: sync, the
  pads and the trigger" ran out through the right-hand rule and off the
  paper at 19 px. It is set smaller when it has to be, down to 10 px,
  which is the same trade the revision strip makes by truncating.

Still open: routing the v2b board, and the breadboard sheet on ANSI B.

## M8: the board is routed. DONE 2026-09-10

**506 track segments, 7 vias, 0 unconnected items, 0 clearance
violations at 200 um.** Two layers, 250 um track, ground poured on the
back and supply on the front and both also carried as traces.

The router is freerouting 2.1.0, run headless, and it is not in this
repository: `tools/route-pcb.py` finds a jar through `$FREEROUTING_JAR`
or `~/.cache/freerouting/` and says how to fetch one if there is none.
Version 2.4.1 needs a newer Java than this box has, which is worth
knowing before somebody chases the same afternoon.

**The routing is a recorded artefact**, `docs/routing/bench-v2b.ses`,
committed, and read on every build by `tools/session.py`. It is the same
argument as the pin golden in the 6502 repository: the output of a long
search, checkable against the thing it describes, and worth nothing to
re-derive on each build. A fresh clone gets a routed board and no build
needs Java.

What keeps a recorded routing honest is that it carries the placement it
was made for. Every part's position is in the session file, so
`check_placement` holds it to the board it is about to go onto and the
build stops by name when a part has moved in `ROWS`. Old traces on a new
placement is exactly the failure a recording invites, and it would look
perfectly plausible in a viewer.

Three things this cost, and all three are the same lesson:

- **The router's own report is not evidence.** The first run came back
  "0 incomplete connections, 0 clearance violations" and had left three
  pads with no copper path to their net. The pours had gone out as
  planes, so it counted every pad on GND and +5V as already connected,
  and then its own signal traces cut the pours into eleven islands. The
  pours come off before the export now, both rails route as ordinary
  nets, and the pours go back on over the top.
- **A check that reports what you hoped is not a check either.** The
  first clearance check ignored layers, so every crossing of a front
  trace over a back one was a violation: 41 of them, all of them
  nothing. The second one, with layers, went green on the board **and
  green on a deliberately broken one**, which is the failure that
  matters. `MUTATE=1` lands a track on a pad of another net;
  `MUTATE_OPEN=1` deletes a track. Both must refuse, and the tool
  asserts that MUTATE did.
- **The order of the two checks is not a preference.** Clearance is
  measured before the pour and connectivity after it. In a process that
  has already built a board with `CreateEmptyBoard`, running the zone
  filler leaves KiCad's shape geometry unable to see collisions at all:
  the mutated track that collides three ways before the fill collides
  with nothing after it. Connectivity is the other way round, because an
  unfilled pour connects nothing. That is the same family as the
  segfault M5 found in the plot controller, and the same fix: do not
  trust a board this tool built in this process.

Left open: the board has never been made.

## M9: the silkscreen, measured on the silkscreen. DONE 2026-09-10

**There were no silkscreen overlaps.** The four this repository has been
carrying as a known defect since M5 were an artefact of the check.

It compared each footprint's whole bounding box, and a footprint's box
includes the Value field. These libraries put Value on **F.Fab**, which
is not a silkscreen, is not plotted, and is not in the fabrication set
at all. J2's value is the string "original pad, on the bridge": twenty
one millimetres of text on a three and a half millimetre connector. Four
of those, four "overlaps", none of which anything will ever print.

The check now reads the two silk layers and nothing else: the reference
label when the label lives there, plus the footprint's outline, item by
item rather than part by part. It asks two questions instead of one,
because they are different questions:

- a label on top of another part's silkscreen, which is what makes a
  reference designator unreadable;
- silkscreen over anybody's pad, which a fab clips off and which leaves
  the outline with pieces missing.

Both come back **zero**, and neither refuses a board: they are assembly
problems, not fabrication ones, and they are reported as notes with the
count printed on every run so that silence is not mistaken for a check
that did not run.

`MUTATE_SILK=1` drags one reference label onto its neighbour's, and the
tool asserts that it went red. That is the part worth keeping: a check
that reports nothing on a clean board **and nothing on a broken one** is
reporting nothing, and that is precisely the state this one was in.

One rule holds all three mutations together, because without it they
disagreed: **under any MUTATE flag, exit 0 means the check caught it.**
Two of them refused the board and so exited 1, the third only wrote a
note and so exited 0, and nothing scripting the three could tell a proof
from a pass. A mutation run is not asking whether the board is good.

## The order, and why

M2 before everything. Every later step reads the netlist, so the netlist
has to be true first. A wiring diagram derived from a connector that
does not match the console would send somebody's probe to pin 7.
