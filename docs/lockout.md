# The lockout chip: what defeating it is, and how to tell it took

Written 2026-10-02, after the calibration cart's first board gave a gray
screen and the question came up whether the console's lockout had ever
really been defeated. The cart pages have said so since 2026-09-14, on
the owner's word, and nothing in this repository had measured it. This
page is the modification done the right way, the ways it goes wrong,
and a measurement that answers the question in twelve seconds.

Everything about the chip itself is from the nesdev wiki (CIC lockout
chip, its pinout, the CPU and PPU pinouts, the cartridge connector; all
read 2026-10-02) and is marked as such. Pin numbers are the published
ones. None has been identified on this console's board yet, and the
procedure below does not ask anybody to trust one without a meter.

## What the chip does, from the published account

A front-loading NES carries a small microcontroller, the lockout chip
(on this console a 3193A, on an NES-CPU-10 board: `wiring.md`). A
licensed cartridge carries the same part. The one in the console is
wired as a **lock** and the one in the cartridge as a **key**, and the
only difference between them is one pin:

- **Pin 4 selects which it is.** It "is pulled to +5V inside the NES
  and grounded on the Cart".
- The lock and the key exchange a stream on two data lines, sharing a
  4 MHz clock. If the key does not answer correctly, "the lock will
  pull the /CPU & PPU RESET line low with a 1Hz square wave".
- Only a lock does that. "It is only the lock, not the key, [that]
  asserts its reset output."

| pin | name | what it is |
|---|---|---|
| 1 | Data Out | the stream to the other chip |
| 2 | Data In | the stream from it |
| 3 | Seed | |
| 4 | Lock/Key | +5 V in the console (lock), ground on a cartridge (key) |
| 5 | not connected | |
| 6 | Clk in | 4 MHz |
| 7 | Reset | the chip's own reset, in: the console's reset bus |
| 8 | Gnd | |
| 9 | /Host reset | out, to the CPU's and the PPU's reset pins |
| 10 | Slave CIC reset | out, to the key's reset |
| 11, 12 | Gnd (reset speed A, B) | |
| 13, 14, 15 | Gnd | |
| 16 | +5 V | |

Four of those lines reach the cartridge connector: pins 34 and 35 (the
two data lines), 70 (the key's reset) and 71 (the clock). On the
calibration cart they end at the empty pads of U2 and nothing answers.

## The modification is one pin taken off the board

The method is nesdev's "pin 4 method": "configuring the CIC in the
console as a key prevents it from resetting. This can be done by
disconnecting the console CIC's pin 4 from the board. Optionally, this
disconnected pin can be tied to ground, but the CIC has internal
pulldowns that make the pin read as 0 even if left floating."

Done carefully, with the checks that make it hard to cut the wrong
thing:

1. **Board out, component side up, unpowered.** The lockout chip is on
   the same side as the CPU and the PPU. The cut is made from this
   side. From the solder side every pin is mirrored, and counting there
   is how the wrong pin gets cut.
2. **Find pin 4 by counting, then prove it with a meter.** Notch (or
   dot) at the top: pin 1 is top left, the numbers run down the left
   side to 8 and back up the right side from 9 to 16. Pin 4 is the
   fourth down the left side, and pin 13 is directly across the chip
   from it. Powered, before anything is cut, pin 4 reads +5 V and pin
   13 reads 0 V. If the fourth pin down does not read +5 V, the chip is
   the other way up or it is the wrong chip, and nothing gets cut.
3. **Take the pin off the board, and only the pin.** Cut the leg low,
   close to the board, and bend the stub outward so it stands clear of
   its pad and of pins 3 and 5. Or desolder it and lift it. Either
   leaves a stub on the chip long enough to solder to, which is what
   makes step 4 possible and the whole thing reversible. Do not cut the
   trace on the board.
4. **Tie the stub to ground.** nesdev calls this optional. This page
   does it anyway: a floating input that relies on a pulldown inside a
   forty-year-old part is the kind of thing that works on the bench and
   not on a damp day. Pin 13 is directly across the chip and is ground;
   a short wire over the top of the package does it.
5. **Check it unpowered.** Stub to its old pad: open. Stub to pin 16
   (+5 V): open. Stub to pin 8 or 13 (ground): closed if it was tied
   down in step 4.

There is a second published method that cuts nothing: two wires, the
lock's pin 7 to pin 1 of the 74HCU04 and that inverter's pin 2 to the
lock's pin 9, which holds the lock in reset and lets the Reset button
drive the CPU and PPU directly. It is not what was done here and is
named only so that somebody finding two extra wires knows what they
are.

## How it goes wrong

- **The wrong pin.** Counted from the wrong end, or counted on the
  solder side without mirroring. Step 2's reading catches both.
- **The leg is cut and still touching.** A cut leg springs back onto
  its pad, or the stub leans on it. It then works until the board is
  moved. Step 5's first reading catches it only if the board is flexed
  a little while the meter is on.
- **The trace was cut instead of the leg.** Pin 4 then still reaches
  whatever is left of the trace, and what that is depends on where the
  cut fell.
- **The leg floats near pin 3 or pin 5** and a flux bridge or a whisker
  joins them.
- **A meter cannot tell a floating leg from a grounded one** when the
  board is powered: the meter's own ten megohms pulls a floating input
  to zero. That reading only says the leg is not at +5 V. Whether it is
  tied down is step 5's question, unpowered.

## What a keyless cartridge shows on the screen, either way

This is the check that needs no instrument, and it is worth doing
first.

With **no key in the slot** (an empty slot, or a cartridge with no
lockout chip on it, which the calibration cart is) a working lock
resets the CPU and the PPU about once a second. The PPU's reset "is
used in the NES to clear the screen when the console is reset either by
the button or the CIC", so the picture blinks at about that rate and
the program starts again each time.

So the two states look different on a television:

| the lock is | what a keyless cartridge shows |
|---|---|
| alive | a blink, about once a second, whatever the cartridge is |
| defeated | whatever the cartridge does: its picture if it works, a **steady** gray if it does not |

**A steady gray screen is not the lock.** It is a cartridge whose
program never ran. A blinking one is the lock, or it is a cartridge
that also does not work under a lock that is alive, and the blink says
nothing about the cartridge until the lock is out of the way.

## The reset line says it in twelve seconds

`tools/lockout-check.py` puts one scope channel on the reset line and
reads the answer off it. With no key in the slot the line either sits
high or is a square wave of about a second.

```bash
python3 tools/lockout-check.py --cart keyless --channel 1            # the cal cart in the slot
python3 tools/lockout-check.py --cart none --channel 1               # the slot empty
python3 tools/lockout-check.py --cart keyless --channel 1 --pin4 2   # and the cut leg's level on CH2
python3 tools/lockout-check.py --selftest                            # no bench: MUTATE=1 must go red
```

It takes two records of twelve seconds each:

- **watch**, hands off the console. Steady high for the whole record,
  or pulsing.
- **button**, during which Reset is pressed once and let go. The line
  has to fall and come back.

| it says | meaning |
|---|---|
| DEFEATED | steady high with no key, and it fell under the button |
| NOT DEFEATED | a square wave of about a second on the line, or pin 4's leg still at +5 V |
| NOT SHOWN | anything else, with the reason: never high, never a logic level, sat high but never fell |

The button record exists because the +5 V rail also sits high for
twelve seconds, and a probe on it would otherwise read as a defeated
lock. `--cart licensed` is refused: with a real key in the slot a
working lock holds the line high too, and the record could not tell
the two apart.

**What the tool cannot check, and a meter has to.** The front panel's
Reset button does not drive the CPU; it drives the lock's own reset
input (pin 7), and that line also falls under the button and never
carries the square wave. A probe there would be told DEFEATED with the
lock alive. So before the reading counts, the probe point is rung
through to the CPU's reset pin, unpowered. The tool prints that
reminder with every DEFEATED and cannot do it for you.

## Where the reset line is

One net, three published places: the lock's pin 9, the CPU's pin 3
(2A03, `/RST`) and the PPU's pin 22 (2C02, `/RST`). On a 40-pin chip
with its notch at the top, pin 3 is the third down the left side and
pin 22 is the second up from the bottom of the right side. From the
solder side both are mirrored.

Any of the three will do, and the largest pad that is easy to hold a
probe on is the right one. Probe at 1X (the bench's other steps arm the
scope that way), ground clip to board ground. Ring the chosen point to
the other two before powering up: that is the same reading the tool
asks for, and it is also the first identification of these three pins
on this board.

## What this console has shown so far

- **Claimed defeated** in `build-the-cal-cart.md`, `cart-blanks.md`
  and `tools/nesprep.py` since 2026-09-14, on the owner's word. Not
  measured.
- **2026-10-01:** the calibration cart's first board, which has no
  lockout chip, gave a gray screen. **Steady, not blinking** (the
  owner's report, 2026-10-02). By the table above that is the lock not
  resetting the console, so the modification holds, by eye, and the
  gray belongs to the cartridge. Both of its chips read back whole
  afterwards (`cal-cart-build.md`).
- **2026-10-02:** the tool's whole path was run against the scope with
  no probe on the console. It recorded twelve seconds, said NOT SHOWN
  (the line sat low), and put the scope's setup back. That is the
  instrument proven, and nothing about the console.

Answered by eye. Still open, and what would make it a measurement: a
photograph of the chip and its pin 4; the meter readings of step 5; the
tool on the reset line. The working document for that sitting is
`procedures/2026-10-02-is-the-lockout-defeated.md`.

Sources: <https://www.nesdev.org/wiki/CIC_lockout_chip>,
<https://www.nesdev.org/wiki/CIC_lockout_chip_pinout>,
<https://www.nesdev.org/wiki/CPU_pinout>,
<https://www.nesdev.org/wiki/PPU_pinout>,
<https://www.nesdev.org/wiki/Cartridge_connector>.
