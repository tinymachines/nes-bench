# 2026-09-09: parts to gather, and sitting 3's build

**State: open, and it is a shopping and soldering-iron task rather than a
measuring one.** Sitting 2 is finished: six of fourteen steps hold, the
cut cable is mapped, and the console's own poll is measured. Sitting 3 is
the first thing on this bench that gets built rather than measured, and
it cannot be run until it exists.

## The list is generated, not written

`docs/parts.md` is the bill of materials, and `tools/parts.py` makes it
by importing the same file that draws the schematics and recording what
each sheet asks to be drawn. A part cannot be on a sheet and missing
from the list, and it cannot be renamed on a sheet without the list
following.

One column is authored and says so: **status**, because no drawing knows
what is in a drawer. It lives in a `STATUS` table in the tool, and a
part with no entry is rendered as **unlisted** with a line telling you
to add it. That guard immediately found five parts I had not thought
about, which is the entire reason it is there rather than being a
comment.

## What actually needs ordering

One thing.

- **LM1881N**, the sync separator on `bench-v2b.svg`. An old National
  part, still sold but mostly through resellers. **Buy two.** It is
  DIP-8, so a socket with it.
- **680 k** for its RSET, and **1 k** in series into its video input.
  Both single resistors; check the drawer first.
- **A second controller cable to cut**, for port 2, broken out at both
  ends exactly like the first.

Everything else on `docs/parts.md` is already in the pile, and the
second 74HC165 and 74HC595 that v2b needs come out of the TI bag and the
box of thirty.

Two caveats before spending anything on v2b, both written into
`bench-v1b-uno.md` rather than drawn as settled: its **L line carries
six fields** where `b3.py`, `compare-logs.py` and `headd.py` all require
exactly four, so it needs a protocol version and those three moved
together; and its **CSYNC load is arithmetic, not a measurement**, and
it is the number that decides whether one UNO can carry all six counted
lines.

## Sitting 3, when you are ready to build

`docs/build-guide.md` has it pin by pin. The three things worth
repeating here, because each one was wrong in the guide until today:

- **The supply is the UNO's own 5 V pin**, fed by its USB from the Pi.
  Not the console's. v1b is one 5 V domain and the console shares only
  ground.
- **Use the marks on the leads, never a port pin number.** On this
  console the moulded numbers and the published function table
  disagree, and the marks are the only thing that was measured:
  **yellow GND, blue CLK, black OUT0, green D0, red +5 V.**
- **Nothing goes on the red lead.** That is the console's own 5 V, and
  this bridge runs from the UNO's.

Sockets, not chips straight into the board.

## What I need from you to run it

Step 3.1 captures U2's QH on the scope and decodes eight bits against
the links you set, so it needs two things that only exist at the bench:

1. The console-facing half built: U1 and U2 in, decoupling on each, and
   **wire links on U2's eight inputs making a byte you choose**. In pad
   order A, B, Select, Start, Up, Down, Left, Right those are pins 6, 5,
   4, 3, 14, 13, 12, 11, and **LOW is pressed**.
2. **CH2 moved from the blue lead to U2 pin 9 (QH).** CH1 stays on
   black. Grounds stay on yellow.

Tell me the byte you wired and that the probe has moved, and I will run
it.

## Outcome

Open.
