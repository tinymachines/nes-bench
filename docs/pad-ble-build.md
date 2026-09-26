# pad-ble: an original pad as a USB or Bluetooth keyboard, standalone

The bridge's own pad poll with a host interface behind it instead of a
shift register. No Pi, no UNO, no console: a pad, one ESP32 board and
one resistor. It presents to a phone, a tablet or a laptop as a plain
keyboard, which is what lets a forty-year-old controller drive a
browser emulator with no app at either end.

**The board is a Waveshare ESP32-P4-Module-DEV-KIT and the interface
is USB**, both of which changed under this document; the reasoning is
in "The direction changed twice" below. The ESP32-C6 the early sheets
are drawn around never accepted a flash.

Written 2026-09-21, updated 2026-09-23.

**Nothing here has been built, and nothing about the circuit has been
measured.** The firmware compiles and its key mapping is tested on the
desk, but the wiring below has never had current in it, no pad has been
wired to it, no host has paired it, and one thing it rests on has been
an open measure-first item since 2026-09-07.

What HAS been measured is the board, not the circuit: which part it is,
where it sits on the breadboard, and the order of its header pins. Each
of those says where it was read and by what. The two are kept apart on
purpose, because a page that mixes a measurement of the part with a
plan for a circuit launders one into the other.

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
| J1 | an original pad | the plug half of the cable |
| R1 | 10k | the pad's D0 up to 3V3 |
| C1 | 100nF | across the devkit's 3V3 and GND |

No LDO, no charger, no cell, no switch. The devkit runs from whatever
USB supplies it and its own regulator makes the 3V3 the pad runs from.

## The wiring, drawn to build from

Three drawings of one circuit, all derived from the same netlist, so no
one of them can show a wire the others do not.

![pad-ble v1: the schematic, one pad into the C6 with what the board can and cannot do](pad-ble.svg)

![pad-ble v1 at right angles: every wire, on the packages as they sit](wiring-pad-ble.svg)

![pad-ble v1 on the breadboard: which hole everything goes in](breadboard-pad-ble.svg)

The breadboard sheet is the one that says **which hole**, and it needed
a fact the other two did not: the physical order of the pins along the
devkit's headers. That is measured (below) and lives in
`tools/breadboard.py` as `C6_HEADER`, read from the USB end.

## The wire list

Five conductors, one pad.

| pad plug pin | signal | lead colour | to |
|---|---|---|---|
| 1 | GND | yellow | GND |
| 2 | CLK | blue | GPIO3, driven by the C6 |
| 3 | OUT0 | black | GPIO2, driven by the C6 |
| 4 | D0 | green | GPIO6, with a 10k up to 3V3 |
| 5 | +5V | red | **3V3**, not 5 V |

**The colours are the bridge's own, confirmed at the bench on
2026-09-22 as the same five.** The table is `LEAD = {1: yellow, 2:
blue, 3: black, 4: green, 5: red}` in `tools/wiring-diagram.py`,
metered on the bridge's cable and printed on the pad connector of
`wiring-pad-ble.svg`. A listing of the five colours in another order
was a listing of the set, not of the pin order, and nothing needed
changing.

Ring the cable out anyway before power. Not because the table is in
doubt, but because this is a different cable from the one that was
metered, and the rule here is that colours are not evidence. Unplugged:
on 2026-09-09 a tone through a cable still in the console ran through
its pull-ups and pins that share nothing beeped, repeatably.

**Not GPIO4, GPIO5 or GPIO15.** Those are the S3's numbers for this job
and they are strapping pins on the C6. The three above are the pins
`firmware/bridge/bridge.ino` already polls a pad on, which is why
`firmware/pad-ble` reuses `poll_pad` unedited, and
`tools/check-sheets.py` holds the sheet and the firmware to each other
so they cannot drift apart again.

## Where it sits now, measured off the bench eye

Read 2026-09-22 from the board eye at zoom 500 and 1000, against the
breadboard's own printed column numbers:

| | |
|---|---|
| the devkit's PCB | the middle breadboard, spanning about **columns 37 to 56** |
| its headers | **sixteen pins a side, so sixteen columns**; the USB connectors overhang the rest of the PCB at one end |
| its rows | pins in **B and I**, straddling the channel, leaving A and J free |
| the cable | a cut pad cable is stripped and lying at the board's low-column end, five conductors |

Believed to within a column, exactly as the bridge's own placement was
("counted from the printed marks and believed to within one column").
The sheet draws the headers at columns 39 to 54, which is that reading
rounded to the pin count; nothing in the circuit depends on the choice,
only on the relative positions, so seat it where it suits you and read
the columns off the sheet.

**Only rows A and J are reachable in the devkit's columns.** It is wide
enough to cover C through H, so those holes are underneath it. A wire
to an upper-header pin goes into row A and a wire to a lower-header pin
into row J. Every pad-ble wire is on the upper header, so **every one
goes into row A**.

**Which header is upper was drawn backwards until 2026-09-23**, and it
is worth saying how it was settled rather than just corrected. The
header photographs show one edge at a time and say nothing about which
edge; the first reading worked it out by rotating the strip and got it
inverted. That put every address on the breadboard sheet on the wrong
header, two of whose pins are the C6's own RX and TX. It was settled at
the bench in one sentence: **with the antenna facing up, 3V3 is the
top-left pin.** Turn that so USB is at the left, which is how the
devkit sits here, and the left side goes to the top.

**The eye could not read the pin labels, and that is now a recorded
limit.** They are about a millimetre and rotated, and at zoom 1000 they
are below what the BRIO resolves at this working distance; refocusing
onto the devkit's raised surface (focus 26 against the board plane's 18)
is blurrier, so it is resolution and not focus. The same eye reads the
BOARD perfectly, which is how the part was identified from its
`RGB@IO8` silkscreen, several times larger.

## The headers, measured

Read 2026-09-22 from photographs of the board taken by hand, since the
bench eye cannot. **Each row is read from the USB end**, the end the two
USB-C connectors are on. `G` is the board's own spelling of ground, and
it appears more than once.

| row | pins, from the USB end |
|---|---|
| the pad-ble side, **upper** | NC, G, 5V, **3**, **2**, 11, 10, 8, 1, 0, 7, **6**, 5, 4, RST, **3V3** |
| the other side, **lower** | NC, G, 12, 13, G, 9, 18, 19, 20, 21, 22, 23, 15, RX, TX, G |

Sixteen a side. This table lives once, in `tools/breadboard.py` as
`C6_HEADER`, and the sheet is drawn from it.

**Every pin this circuit needs is on one row.** GPIO2, GPIO3, GPIO6,
a 3V3 and a ground are all on the first row above, so no wire crosses
to the other side of the board. That is worth knowing before you start,
and it was not a given.

**The trap that row sets.** GPIO4 and GPIO5 sit immediately beside
GPIO6, and GPIO8 is four the other way. All three are strapping pins
on the C6. Counting one hole wrong along that row does not give you a
dead input, it gives you a board that may not boot. Count from the
printed labels, not from the end.

## The part changed: the board that actually works is a P4

**2026-09-24.** The C6 these drawings are around has never accepted a
flash. A Waveshare **ESP32-P4-Module-DEV-KIT** on the same bench
connected on the first attempt, took the firmware, and put a BLE
advertisement on the air that an independent radio heard. So the build
moves to that part, and this section is the wiring for it.

`docs/esp32-part-choice.md` has the measurement behind the choice. The
short of it: the P4 die has no radio at all, the module carries an
ESP32-C6 as one, and the Arduino core's BLE classes are gated to allow
exactly that arrangement. `firmware/pad-ble` builds for `esp32p4` with
the pad map unedited.

### The five wires

Read on 2026-09-24 out of **Waveshare's own schematic** for this board,
connector **P6**, by rendering the page at 900 dpi. It is not read off
a photograph, and that is deliberate: this document shipped four
revisions with the C6's two header rows swapped because a pinout was
derived from a rotated picture instead of from the drawing that
defines it.

| lead | net | goes in | which is |
|---|---|---|---|
| Red | `3V3` | **P6 pin 18** | 3V3 |
| Yellow | `GND` | **P6 pin 26** | GND |
| Black | `PAD_LATCH` | **P6 pin 22** | GPIO2 |
| Blue | `PAD_CLK` | **P6 pin 20** | GPIO3 |
| Green | `PAD1_D0` | **P6 pin 16** | GPIO6 |

**Every one of those is an even pin, so all five wires land in one row
and nothing crosses the header. They are also CONSECUTIVE, which is the
useful way to say it:**

    6    3V3    3    2    0    GND
   p16   p18   p20  p22  p24  p26

**Find the second `3V3` on the even row and the circuit is that hole
and the four around it, taking every one except `0`.** Data, supply,
clock, latch, skip, ground.

That the five are even was chosen, so nothing crosses the header. That
they are also a run was not noticed until the board was wired on
2026-09-25, and it matters: wiring it from the pin numbers, two of the
three signal wires went in wrong. Yellow landed on `SCL`, which the
board pulls up itself, so the clock would have been fighting hardware
and the symptom would have been silence. A grey landed on `0`, one
hole past the latch. Both were found by measuring, not by looking. The lead colours are looked up from
`tools/bringup.py`'s `LEADS`, the cable as it was actually rung out on
2026-09-09, not from the colours anyone remembers: rev E carried three
of the five wrong because they were typed from a set of colours rather
than read from the measurement. The 10k pullup from `PAD1_D0` up to
3V3 is unchanged and still belongs on the breadboard beside the board.

### Pin 1 is not where a Raspberry Pi puts it

The header is physically Pi-shaped and numbered the other way round:

    5V    P6 pins 1 and 3      a Pi has 5V on 2 and 4
    3V3   P6 pins 2 and 18     a Pi has 3V3 on 1 and 17
    GND   5, 10, 13, 19, 26, 29, 33, 40

Every ground is one pin away from where a Pi user reaches for it. **A
Pi HAT will fit this board and will not work.** Count from the
schematic, not from habit.

### Four pins that reach the header and are still not yours

    GPIO54  pin 31   the onboard C6's RESET. Take it and the radio dies.
    GPIO45  pin 39   the MicroSD card's power switch
    GPIO53  pin 36   the speaker amplifier's CTRL
    GPIO36  pin 23   BOOT_MODE2, a strapping pin, pulled up

`GPIO24` and `GPIO25` (pins 28 and 27) are the high-speed USB pair, and
`GPIO7` and `GPIO8` (pins 4 and 6) are the audio codec's I2C with 2.2k
pullups already on the board. The full table, with what is free, is
`tools/p4_header.py` and sheet 5 of TM-NESB-003.

### The two spare pins had to move

On the C6, `MODE_SW` and `LED` were GPIO10 and GPIO11 and cost nothing
because neither was wired. On this board those numbers are the ES8311
audio codec's I2S, and they are not on the header at all. The firmware
moves them to **GPIO21 and GPIO20**, header pins 12 and 14, free and on
the same even row. Neither is wired; both are declared, because an
unmentioned pin is silence.

### What is proven about this board, and what is not

Proven by test on 2026-09-24: it flashes, it runs, its BLE address
reaches an independent receiver, and the firmware compiles for it with
the pad map untouched. **Not proven: anything at all about the pad.**
No pad has been wired to this board, and measure-first item 4 below is
still open.

## The direction changed twice, and this is why

**2026-09-25.** This began as a Bluetooth adapter and ships as a USB
one. Both moves were forced by measurement, not preference, and both
are worth keeping because the reasoning is reusable.

### Move one: the C6 to the P4

The ESP32-C6 never accepted a flash. Two evenings of `no serial data
received`, with the port, the cable, the wiring and ModemManager each
ruled out by test. A Waveshare ESP32-P4-Module-DEV-KIT on the same
bench connected first try, took the firmware, and put a BLE
advertisement on the air that an independent radio heard. That is
`docs/esp32-part-choice.md`.

### Move two: BLE to USB

The BLE firmware crashes on the P4, and not in this project's code.

    E rpc_core: Response not received for [0x15e](Req_GetCoprocessorFwVersion)
    Guru Meditation Error: Core 1 panic'ed (Load access fault)

The P4 has no radio. The module carries an ESP32-C6 as one, reached
over SDIO, and the host's **esp-hosted 2.12.11** asks that C6 for its
firmware version. It gets no answer, and the failure path then reads a
pointer nobody filled in. **Always 2881 ms after `BLEDevice::init`**,
in every variant tried.

Five explanations were tested and eliminated:

| tried | result |
|---|---|
| build options, 16M flash and PSRAM on | no change |
| removing the `BLESecurity` block | no change |
| `delay(3000)` before `BLEDevice::init` | crash moved by exactly 3000 ms |
| `delay(4000)` after `BLEDevice::init` | never reached; the crash is inside init |
| moving all GPIO setup after BLE | no change |

**The radio probe hits the identical timeout at the identical latency
and survives it.** That is what names the kind of bug: the failure path
reads uninitialised memory, and whether it kills you depends on what
was in that memory, which differs per binary. The probe is lucky. It is
not correct.

So the fault is the unanswered RPC, and the honest fix is the C6's
slave firmware, through the board's `C6 UART` header. **That has not
been done.**

### Why USB rather than a workaround

USB removes the component that is failing instead of stepping around
it: no radio, no co-processor, no SDIO link, no pairing. The P4
declares `SOC_USB_OTG_SUPPORTED` with two OTG peripherals and a UTMI
PHY, which the C6 never had at all, so this is a thing only this part
can do. It is also what was asked for on the first day of this work.

`firmware/pad-usb` boots clean at 18% of flash and prints `B FF` with
no pad wired, which is correct: `D0` floats with no pullup, so all
eight bits read pressed, and the six-slot limit reports `DROPPED`
rather than losing keys quietly. **With the pullup fitted it should
read `B 00`**, and that is the next confirmation, needing no host.

Its `keymap.h` is a **symlink** to `firmware/pad-ble/keymap.h`, so both
builds send the same eight buttons as the same eight keys, and
`tools/test-pad-keymap.sh` holds that one file to its own descriptor on
the desk. `tools/check-sheets.py` refuses a copy.

### What did not change

The wiring. Both builds poll `GPIO2`, `GPIO3` and `GPIO6`, the same map
`firmware/bridge/bridge.ino` already uses, so the five wires and the
run they sit in are unaffected by either move.

### Using it

Plug the host into the socket marked **`USB`**, not `PWR USB TO UART`,
and set the jumper to **`DEVICE`**. The UART socket stays on the bench
head, which is where the serial log comes from.

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

## What the host sees

A boot-protocol keyboard, report ID 1, with the layout browser
emulators default to: A is `x`, B is `z`, Select is right shift, Start
is enter, and the d-pad is the arrows. Select is a modifier rather than
a key slot because right shift is a modifier, and a host that tracks
modifier state separately would otherwise see shift held in a way no
keyboard produces.

**One pad, and that is the design rather than a first step.** A keyboard
report carries six key slots and two pads can ask for ten, so a second
pad could be polled and never sent. One was on these drawings until
2026-09-23 doing exactly that: wired, pulled up, given a pin, and
thrown away. It came off when the person holding the cable asked why a
standalone keyboard for a phone had two of them, which was the right
question and the sheet's own stated purpose was the argument against
it: a drawing somebody builds from has to show the parts they have.

Two players wants gamepad mode with two report IDs, which is
`pad-adapter.svg`'s job. Gamepad mode is not built for a second reason
anyway: iOS refuses a generic HID gamepad, taking only the MFi, Xbox,
PlayStation and Switch Pro layouts, which is what made keyboard mode
first.

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
- The bench eye cannot read a devkit's silkscreen, which is why the
  header order above was read by hand. It will be true of the next
  devkit too.
- The latency is unmeasured. Worth measuring here rather than guessing,
  because this bench can: the bridge stamps every poll with its latch
  index, so the number is one subtraction of `head.log` against
  `bridge.log`.
