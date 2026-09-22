# pad-ble: an original pad as a Bluetooth keyboard, standalone

The bridge's own pad poll with a radio behind it instead of a shift
register. No Pi, no UNO, no console: a pad, the ESP32-C6 already seated
on the breadboard, and two resistors. It pairs to a phone, a tablet or
a laptop as a plain BLE keyboard, which is what lets a forty-year-old
controller drive a browser emulator with no app at either end.

Written 2026-09-21. **Nothing here has been built or measured.** The
firmware compiles and its mapping is tested on the desk; the wiring
below has never had current in it, and one thing it rests on has been
an open measure-first item since 2026-09-07.

## Why this and not the adapter sheet

`pad-adapter.svg` is the whole idea: two pads, a mode switch, a cell, a
charger, an LDO, and either an S3 for USB HID or a C6 for BLE. Most of
that is on order. This is the subset whose parts are all in the drawer,
and it is a sheet of its own for the same reason `bench-v1b` is a sheet
of its own rather than a note on `bench-v1`: a drawing somebody builds
from has to show the parts they have, or the evening goes on reading
around the ones they do not.

## What decided the part, and it was read not recalled

The board on the breadboard is an **ESP32-C6-DevKitC-1 v1.2**. That was
settled on 2026-09-21 off the bench eye at zoom 500, not from the parts
list: its silkscreen reads `RGB@IO8`, and the C6 devkit puts its RGB LED
on GPIO8 where the S3 devkit puts its on GPIO48. Both boards carry two
USB-C ports labelled UART and USB, so the ports do not tell them apart
and the LED does.

**That decides the Bluetooth question, in silicon rather than in
firmware.** The C6 cannot be a USB keyboard. Its port marked USB is a
USB-Serial-JTAG bridge, and its `soc_caps.h` defines
`SOC_USB_SERIAL_JTAG_SUPPORTED` while defining no
`SOC_USB_OTG_SUPPORTED`; the Arduino core gates `USBHIDKeyboard.h` on
the latter, so on this target it compiles to nothing. Checked against
the installed esp32 core 3.3.11. USB HID needs an S3, S2 or P4, and an
S3 would give both modes on one board, which is the one good reason to
order one.

So: BLE keyboard. Not a preference, the only HID this board can do.

## Parts, all on hand

| ref | part | note |
|---|---|---|
| U1 | ESP32-C6-DevKitC-1 v1.2 | already on the breadboard |
| J1, J2 | an original pad each | the plug half of the cable |
| R1, R2 | 10k | one per pad, D0 up to 3V3 |
| C1 | 100nF | across the devkit's 3V3 and GND |

No LDO, no charger, no cell, no switch. The devkit runs from whatever
USB supplies it and its own regulator makes the 3V3 that the pads run
from.

## The wiring, drawn to build from

Two drawings of one circuit, both derived from the same netlist so
neither can show a wire the other does not.

![pad-ble v1: the schematic, two pads into the C6 with what the board can and cannot do](pad-ble.svg)

![pad-ble v1 at right angles: every wire, on the packages as they sit](wiring-pad-ble.svg)

## The wire list

Five conductors per pad. Both pads share the latch and the clock, so
those two nets reach four pins between them; only D0 is per pad.

| pad plug pin | signal | lead colour | to |
|---|---|---|---|
| 1 | GND | yellow | GND |
| 2 | CLK | blue | GPIO3, driven by the C6 |
| 3 | OUT0 | black | GPIO2, driven by the C6 |
| 4 | D0 | green | GPIO6 (pad 1) or GPIO7 (pad 2), each with 10k up to 3V3 |
| 5 | +5V | red | **3V3**, not 5 V |

**The lead colours are in dispute and must be metered before they are
believed.** The table above is the bridge's own, measured and committed
in `tools/wiring-diagram.py` as `LEAD = {1: yellow, 2: blue, 3: black,
4: green, 5: red}`. On 2026-09-21 the colours were given at the bench as
"black, yellow, blue, green, red", which is the same five colours with
the first three in a different order. Both readings agree on green at
pin 4 and red at pin 5 and disagree on GND, CLK and OUT0, so taking the
wrong one puts the console's clock on ground. It is one continuity run
to settle and it has to happen before power.

**Not GPIO4, GPIO5 or GPIO15.** Those are the S3's numbers for this job
and they are strapping pins on the C6. The three above are the pins
`firmware/bridge/bridge.ino` already polls a pad on, which is why
`firmware/pad-ble` reuses `poll_pad` unedited, and
`tools/check-sheets.py` holds the sheet and the firmware to each other
so they cannot drift apart again.

## Measure first

Before anything is powered, and in this order:

1. **Ring the pad's cable out with the plug in nothing.** Measure-first
   item 1 exists because of what happened on 2026-09-09: a tone through
   a cable still plugged into the console runs through the console's own
   pull-ups and port buffers, and pins that share nothing beep. That
   first pass put two port pins on one lead, repeatably, and it was the
   instrument talking. Write the result beside the colour table above.
2. **An original pad at 3V3 follows its buttons.** This is measure-first
   item 4 and it has been open since 2026-09-07. The 4021 is a CMOS part
   rated 3 to 18 V, so the datasheet says yes, but these pads are forty
   years old and some may not be genuine. If one will not run at 3V3,
   the fix is drawn on the adapter sheet already: a 74LVC245 and 5 V to
   the pad, and the 245 is on hand.

Nothing beyond this point is worth doing until item 2 has an answer,
because every version of this adapter rests on it.

## Build order

1. Wire one pad only: GND, OUT0 to GPIO2, CLK to GPIO3, D0 to GPIO6,
   supply to 3V3, and the 10k from GPIO6 up to 3V3.
2. Flash `firmware/pad-ble` and open the serial port at 115200. It
   prints `B <pad1> <pad2> unlinked` on every change of either pad.
3. **First light is that byte following your thumbs, and it needs no
   radio.** If it moves, the hardware half is done and everything after
   it is software. If it does not, no amount of Bluetooth would have
   helped, and the answer is measure-first item 2.
4. Only then pair it. It advertises as `NES Pad` and should appear in a
   phone's Bluetooth settings as an ordinary keyboard.
5. Add the second pad: D0 to GPIO7 with its own 10k, sharing the latch
   and the clock. It is polled and printed but does not send keys.

## What the host sees

A boot-protocol keyboard, report ID 1, with the layout browser
emulators default to: A is `x`, B is `z`, Select is right shift, Start
is enter, and the d-pad is the arrows. Select is a modifier rather than
a key slot because right shift is a modifier, and a host that tracks
modifier state separately would otherwise see shift held in a way no
keyboard produces.

**One pad sends keys, and that is a limit rather than an oversight.** A
keyboard report carries six key slots; two pads can ask for ten, so two
players on one report would silently drop whichever arrived last. Two
players wants gamepad mode with two report IDs, on a part that can do
it. Gamepad mode is also not built, for a different reason: iOS refuses
a generic HID gamepad, taking only the MFi, Xbox, PlayStation and
Switch Pro layouts, which is what made keyboard mode first.

## What is tested, and what is not

Kept apart deliberately, because the two halves are not comparable.

**Tested on the desk, with no pad and no host in the room.** The report
descriptor and the key mapping are plain C in
`firmware/pad-ble/keymap.h`, and `tools/test-pad-keymap.sh` compiles
that same header natively and exercises it: 76 checks, and `MUTATE=1`
plants two realistic bugs and produces twelve failures. The descriptor
is not compared against a copy of itself, it is parsed item by item the
way a host parses it, and what the parse says the report's size is gets
compared with what the code actually writes. Those two are worth
mechanising because a bad descriptor still pairs and a bad mapping still
types: neither announces itself.

**Not tested, and not to be described as working.** The radio, the
pairing, the pad's own timing at 3.3 V, and the wiring. The firmware
compiles for the C6 at 56% of flash and that is all that is known about
it.

## The trap that will cost the most time

A reflash can clear this board's bond store while the phone still holds
its side. A one-sided bond refuses to pair and reports nothing at either
end, on the phone or on the serial port. The `FORGET` command clears
this end and then says, in as many words, to forget the device on the
host as well, because doing only one is the failure.

## Open, and recorded in `open-items.md`

- The adapter has met no pad and no host.
- An original pad at 3V3 is unproven (measure-first item 4).
- The lead colours disagree between the committed table and the bench.
- The latency is unmeasured. Worth measuring here rather than guessing,
  because this bench can: the bridge stamps every poll with its latch
  index, so the number is one subtraction of `head.log` against
  `bridge.log`.
