# Milestone, 2026-09-15: the QA rig locked and the bridge reading right through the console

Three days on the bench, ending with the v1b bridge passing bytes into
an unmodified NES-001 and the console reading every one of them back
as written. What was built, what was measured, what was wrong on the
way, and what is next.

## What holds

- **The bridge, joined and correct.** B0's first gate holds: the
  console polls at 60.06 a second and the bridge counts eight clocks
  on every poll (three runs of about 1,200 polls, none other). A byte
  set on the bridge's 595 comes back on the console's D0 line at its
  own bit positions for all fifteen bytes tried (`docs/procedures/2026-09-13-breadboard-qa.md`,
  "The walk reads right"). That proves the six grey Q lines pair the
  595's outputs to the 165's inputs as the sheet says.
- **The trigger.** The bridge's `TRIG n` raises a 5.4 V pulse of 874 us
  at latch n, and it stops the scope on CH1 (bring-up step 6.1). The
  same capture shows the video field and the pad byte on one timebase.
- **The rig.** The BRIO on a metal frame, levelled, gaffer-taped and
  velcroed, the whole backing board in frame, 11.1 px on a hole both
  ways, a bench light over it; two side eyes on the lower rail; every
  camera's job, mount and scale in `docs/rig.md`, the bench itself
  photographed there. The hole map reads itself off a zoomed frame
  (`tools/board-overlay.py --read --zoomed`) and the as-built
  photograph is drawn on those frames with every check and placement
  called out.
- **The drawing package at rev M**, thirteen sheets, the as-built
  wiring sheet at 55 pins done and 5 to check (J2's lead order), the
  cheat sheet with the scope's channels and each probe's landing as a
  board column.

## What was measured that the plan had wrong

- **The DS1054Z has no external trigger input.** The design sent the
  trigger to a rear EXT TRIG that does not exist (the rear BNC is Trig
  Out). It takes CH1, the channel held for the master clock, by turns.
- **The bridge booked the wrong clocks to the wrong polls.** The loop
  read the latch counter and the clock counter apart; three layers of
  fix (the count snapshotted in the latch's interrupt, a rise told by
  the hardware counter, the pair read in one breath) before every
  poll read eight. `firmware/build-uno.sh` builds the sketch with the
  Arduino core on hand and reproduces the flashed hex.
- **A lone pressed bit shifted the register once too often.** D0's
  own falling edge re-clocked the 165 through a spike too short for
  the UNO to count and long enough for the chip (about 50 ns, seen at
  1 us/div). A 1 k and 100 pF at the clock pin and a 100 nF at the
  chip closed it; the walk is the proof.
- **Ground bounce was the wrong reading**, kept on the record beside
  the right one: the filter alone was enough.

## What the eye can and cannot do, learned here

The eye settles a wire whose bare end it sees at a hole, and it settles
nothing about a Dupont housing's positions, a raised end near the
frame's edge, or which of two same-colour wires is which. Those go to
the meter, the side eyes, or the instrument. Two placement notes were
typed against the map instead of derived from it and one of them put a
capacitor on the D0 pin: a placement note is now a thing the tool
should generate, not a thing to write.

## Next

1. **Reset and power, so the bench can bring the console back to a
   known state on its own** (bring-up sitting 5, steps 6.2 and 6.3):
   the PC817 on the reset pads, the relay in one lead of the adapter,
   both driven from the Pi's header. Until these hold, every run that
   needs a fresh console needs a hand.
2. **The pad through the bridge** (steps 4.2 and 5.2): the pad in hand,
   three buttons seen in the pad byte, then a button seen by the game.
   This also settles J2's lead order, the last check on the sheet.
3. **B1, the first recording**: MODE PASS, a game, the bridge's log
   and a triggered capture, which is what the trace plan's window
   check needs.
4. The calibration cartridge's part side (`open-items.md`) when the
   chips arrive.
