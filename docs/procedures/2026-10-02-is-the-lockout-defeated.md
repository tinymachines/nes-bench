# 2026-10-02: is the lockout defeated

**Outcome:** answered by eye at step 1, 2026-10-02: the screen was a
steady gray and did not blink, so the lock is not resetting the console.
Steps 2 to 6 are still open and would turn "by eye" into a photograph,
three meter readings and a record off the reset line.

## Why

The calibration cart has no lockout chip, so it only runs on a console
whose lock has been defeated. Its first board gave a gray screen on
2026-10-01, and both chips read back whole afterwards, which leaves the
board's soldering (being redone on a second board) and the console. The
console's half of that is this cycle: whether the lock was really taken
out, checked four ways, cheapest first. What the modification is and
what each check means are in `docs/lockout.md`; this page is only the
order of work and what was seen.

## The steps

Each step can end the cycle. A blink at step 1 already says the lock is
alive; a steady screen says it is not, and the rest then documents how
the work was done.

1. **You: steady or blinking.** Any cartridge with no lockout chip in
   the slot (the first cal cart board will do, working or not), or the
   slot empty. Power on and watch for ten seconds. A blink about once a
   second is the lock. Steady, of any colour, is not. Say which.
2. **You: photograph the chip.** Board out, component side up. One
   picture square on to the 16-pin chip marked 3193A with its notch in
   frame, one from low on the pin 1 to 8 side so the fourth leg shows.
   Send both; the page gets them and the work gets read off them.
3. **You: the meter, unpowered.** With the stub of pin 4 under one
   probe:
   - to the pad it left: open or closed
   - to pin 16 of the same chip: open or closed
   - to pin 13 of the same chip: open or closed
   Flex the board gently while the first one is on the meter.
4. **You: find the reset line and clip on.** Scope CH1 at 1X, ground
   clip to board ground. The point is the CPU's pin 3, the PPU's pin 22
   or the lock's pin 9, whichever is easiest to hold. Ring it to one of
   the other two first, unpowered, and say which two rang.
5. **The tools: twelve seconds, twice.** Console on, keyless cartridge
   in or slot empty, then from the workstation:

   ```bash
   python3 tools/lockout-check.py --cart keyless --channel 1
   ```

   The first record wants hands off. The second asks for one press of
   Reset, about a second long, five seconds after it says so.
6. **Optional: the leg itself.** CH2 on the stub of pin 4, and add
   `--pin4 2` to the command.

## Observations

- **2026-10-02, the owner, of the 2026-10-01 power-on:** "it was steady
  gray, not blinking". The cartridge in the slot was the calibration
  cart's first board, which has no lockout chip. A live lock blinks a
  keyless cartridge at about once a second (`docs/lockout.md`), so this
  is the lock not acting, and the gray is the cartridge's.
