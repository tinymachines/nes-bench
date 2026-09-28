# pad-usb: from a button to a keystroke, layer by layer

What travels between an original NES pad and a phone or laptop when
the pad is plugged into the bench's ESP32-P4 as a USB keyboard. Four
layers, each with its own protocol, then the host, and each one checked
on its own before the next is trusted.

Written 2026-09-27, and by the end of that evening the plan below had
run: steps 2 to 5 pass. The build itself, its wiring and why it is USB
rather than Bluetooth are in `pad-ble-build.md`; the choice of board is
in `esp32-part-choice.md`. This page is the protocol and the plan.

**A real button press reaches a host.** An original pad at 3.3 V, the
P4, full-speed USB and a Linux host (the bench's Pi) carry all eight
buttons through as their keys, chords included. **A browser sees them
too** (step 6, 2026-09-28, on `tinymachines.ai/lab/pad-keydown`): every
button as its `code`, one report per change, the host's autorepeat
visible as the host's. **On an iPhone the game moves, by four buttons
of eight** (step 7, 2026-09-28): A, B, Select and Start played on
`tinymachines.ai/nes/play`, the cross did not, and the reason is the
host layer, not the adapter; the section on the host says what.
Getting there moved the firmware off the
Arduino core's USB classes and onto a different USB controller; layer 4
says why, and what was wrong about the first version of this page.

## The chain has four layers

    NES pad            ESP32-P4                    USB             host
    MN4021B  --3 wires-->  poll_pad()  --> pad_report() --> HID report --> keydown
     8 buttons          one byte, bit=pressed   8 bytes       9 on the wire   "KeyX"

    layer 1: the pad's shift register    (latch, clock, data)
    layer 2: the byte as a key report    (keymap.h, one table)
    layer 3: the report descriptor       (how the host reads those 8 bytes)
    layer 4: USB itself                  (enumeration, one interrupt endpoint)

Each layer has a tool that sees it and nothing else, which is what lets
a failure be placed in one layer instead of guessed at across four. The
tools are listed in "The plan, one layer at a time" below.

## Layer 1: the pad is a shift register

Inside an original pad is one **MN4021B**, a CMOS 8-bit parallel-in,
serial-out shift register, with the eight buttons on its parallel
inputs. Five wires leave the pad: supply, ground, and three signals.

| signal | 4021 pin | direction | what it does |
|---|---|---|---|
| latch (OUT0) | 9, P/S | P4 to pad | high: the eight inputs are copied in; low: they stop moving |
| clock | 10, CLOCK | P4 to pad | each rising edge shifts the next button onto data |
| data (D0) | 3, Q8 | pad to P4 | the current button, **low when pressed** |
| supply | 16, VDD | | 3.3 V here (the console gives 5 V) |
| ground | 8, VSS | | |

One poll, as `firmware/pad-usb/pad-usb.ino` does it:

1. Latch high for 12 µs, then low. The eight buttons are now frozen in
   the register, and button A is already on the data line.
2. Read data, pulse the clock (6 µs high, 6 µs low), and repeat eight
   times. The eight reads are A, B, Select, Start, Up, Down, Left,
   Right, in that order.
3. A read of low sets that bit. The result is one byte, bit 0 A through
   bit 7 Right, which is the same order the console model uses
   (`nes_glue::controller::Buttons::as_byte`).

That is about 110 µs of work, repeated every 16 ms: about 60 polls a
second, the console's own rate. The data line has a 10k pull-up to
3.3 V, so a pad that is absent or unpowered reads `FF`, all eight
pressed, rather than a random byte.

**An original pad works at 3.3 V: measured 2026-09-27.** The 4021 is
rated 3 to 18 V, so the datasheet said yes; the bench now says so too,
closing measure-first item 4 (open since 2026-09-07). The first pad
tried was a replica that does not answer at 3.3 V; the original has a
genuine MN4021B. **Check the pull-up's value before blaming the pad:**
the first attempt had 10 ohms fitted where 10k belongs, the chip could
not pull the line down against it, and D0 only dipped on each press.

### The colours on the cable are not the signals

The replica's cable and Nintendo's use different colours, and two of
them collide: **red is supply on one and clock on the other**, and
yellow is ground on one and data on the other. Wire by signal, checked
with a meter against the chip's pins, never by colour. The drawing
package (rev K) draws the original's colours, and `pad-ble-build.md`
carries both tables.

## Layer 2: the byte becomes a key report

`firmware/pad-ble/keymap.h` holds one table and one function, and the
USB build uses the same file through a symlink, so there is exactly one
mapping on this bench.

| bit | button | key | HID usage |
|---|---|---|---|
| 0 | A | x | 0x1B |
| 1 | B | z | 0x1D |
| 2 | Select | right shift | modifier bit 0x20 |
| 3 | Start | enter | 0x28 |
| 4 | Up | up arrow | 0x52 |
| 5 | Down | down arrow | 0x51 |
| 6 | Left | left arrow | 0x50 |
| 7 | Right | right arrow | 0x4F |

That layout is authored, not measured: it is what browser NES
emulators default to, which is the reason keyboard mode exists at all.
Select is a modifier rather than a key because right shift is one, and
a host tracks modifiers separately from keys.

A report is eight bytes: one byte of modifiers, one reserved byte, and
six key slots filled in bit order. These are produced by the real
`pad_report()`, compiled on the desk, not written out by hand:

| pad byte | pressed | report |
|---|---|---|
| `00` | nothing | `00 00 00 00 00 00 00 00` |
| `01` | A | `00 00 1B 00 00 00 00 00` |
| `81` | A and Right | `00 00 1B 4F 00 00 00 00` |
| `0C` | Select and Start | `20 00 28 00 00 00 00 00` |
| `F0` | all four directions | `00 00 52 51 50 4F 00 00` |
| `FF` | everything | `20 00 1B 1D 28 52 51 50`, one key dropped |

Six slots against eight buttons means a report can overflow, so the
function **counts** what it drops and the serial log prints `DROPPED`
rather than losing a key quietly. A working pad cannot overflow: one
modifier, and a d-pad that cannot press opposite directions, leave at
most five keys. The last row is what a disconnected pad produces, and
it is the first thing the serial log shows with no pad wired.

A report is sent **only when the byte changes**. A keyboard that
re-sends an unchanged report is harmless over USB, but printing every
poll would bury the one line that matters, and the BLE build shares the
rule for a better reason: over BLE a repeated report can type forever.

## Layer 3: the report descriptor tells the host how to read it

At enumeration the host asks the P4 for a **report descriptor**, 65
bytes in `keymap.h`, and parses it item by item. It says: this is a
keyboard; report ID 1; eight one-bit modifiers; one constant byte; five
LED bits going the other way plus three of padding; six key slots, each
a usage from 0 to 101. The host builds its idea of the report entirely
from this. The firmware's 8-byte buffer and the descriptor's promise
have to agree, and nothing forces them to.

**That is why the descriptor is tested on the desk.** A malformed
descriptor does not fail to compile and does not fail to enumerate. It
enumerates, and then every key is the wrong key. So
`tools/test-pad-keymap.sh` compiles `keymap.h` natively, parses the
descriptor the way a host would, and compares the report size the parse
implies with what `pad_report()` actually writes: 76 checks, and
`MUTATE=1` plants two realistic bugs that must turn it red.

Because the descriptor declares a report ID, each report goes over the
wire with that ID in front: **nine bytes**, `01` and then the eight
above. A host strips it before an application ever sees the report.

The LED output (Num Lock, Caps Lock and the rest) is declared and
ignored. It is there because a keyboard that declares none is an
unusual keyboard, and the goal is a host that accepts this without
thinking about it.

## Layer 4: USB carries the report

The P4 has **two** USB controllers of its own
(`SOC_USB_OTG_SUPPORTED`, two OTG peripherals), which is the thing the
ESP32-C6 on this bench lacked entirely: one high speed, one full speed.
The firmware drives TinyUSB directly on the **full-speed** one, and the
section after next says why it is not the obvious one. What the host
is told, set in `firmware/pad-usb/usb_device.cpp` and read back from
the host's own log:

| descriptor | value | notes |
|---|---|---|
| vendor ID, product ID | `303a:0002` | Espressif's VID and its TinyUSB example PID |
| product, manufacturer, serial | `NES Pad`, `tinymachines`, `nes-bench pad-usb` | |
| speed | **full speed, 12 Mbit/s** | measured: the host logged `new full-speed USB device` |
| interface class | HID (3), subclass 0, protocol 0 | |
| endpoints | one interrupt IN, 16 bytes | holds the nine a report takes; the LED report comes over the control pipe |
| polling interval | 1 ms | one frame at full speed |

The sequence on plug-in: the host resets the device, reads its device
and configuration descriptors, sees a HID interface, fetches the report
descriptor above, and from then on polls the interrupt IN endpoint.
When a button changes, the next poll gets the nine bytes. No driver is
involved on any mainstream host: HID keyboards are a class every
operating system carries.

### It is a report-protocol keyboard, not a boot keyboard

**Corrected 2026-09-27.** `keymap.h` and `pad-ble-build.md` called this a
boot-protocol keyboard. The report *layout* is the boot layout, but the
USB interface declares subclass 0 and protocol 0, not boot, and the
report carries an ID, which boot reports never do. So a full operating
system (Android, iOS, macOS, Windows, Linux, ChromeOS) reads it through
the descriptor and is unaffected, while a BIOS setup screen, some KVM
switches and some TV boxes, which speak only boot protocol, will not
see it. Nothing on this bench's list needs those. If one ever does, the
change is `HID_ITF_PROTOCOL_KEYBOARD` in the interface descriptor and a
report descriptor with no report ID, and it would be the USB build's
own descriptor rather than the shared one, since BLE wants the ID.

### Two sockets, and which one is the keyboard

The board has two USB-C sockets and they are different devices:

- **`PWR USB TO UART`** is a CH343 serial bridge (`1a86:55d3`), the one
  the firmware is flashed over and prints its log to. On the bench it
  is `/dev/p4-uart` on the head. It stays there.
- **`USB`** (H2, "USB1.1 Type-C" in Waveshare's schematic) is the P4's
  full-speed pair on GPIO24/25, and it is the keyboard. The host plugs
  in here. The HOST/DEVICE jumper does not matter to this build.

Plugging the host into the UART socket gives it a serial port and no
keyboard, and nothing at either end says why.

**The first version of this page was wrong here, and so was the
firmware.** It said to plug into `USB` with the jumper on DEVICE, and
that could never have worked, for two reasons found that evening:

1. **The Arduino core puts the keyboard on the high-speed controller**
   on the P4 (`tusb_init(1)`, and a 512-byte endpoint that full speed
   does not allow), and on this kit the high-speed pair goes only to a
   switch (U15, FSUSB42) that the jumper drives, and from there either
   to the onboard hub or, on DEVICE, to one port of the USB-A stack J8.
   **That port's 5 V is driven by the board** (U6, always on), so a host
   plugged into it would have its own 5 V meet the board's. It was not
   used.
2. **The P4 has two full-speed PHYs, and gives the one on GPIO24/25 to
   its USB-Serial-JTAG by default.** Plugged into `USB`, the host saw
   `303a:1001 USB JTAG/serial debug unit`. Connecting the PHY to the
   OTG controller returned `ESP_OK` and changed nothing, because it
   had connected the OTG controller to the OTHER PHY (GPIO26/27, wired
   to no socket). One bit in `LP_SYS.usb_ctrl` swaps them
   (`usb_wrap_ll_phy_select(&USB_WRAP, 0)`), and with it the host saw
   the NES Pad.

So `pad-usb` defines the six callbacks TinyUSB asks the application for
itself, which also keeps the core's USB wrapper out of the link, and
the USB-Serial-JTAG leaves that socket while it runs. Flashing is over
the UART socket and is unaffected.

### What was measured at this layer, and what was not

- **Speed: full speed, measured.** A keyboard sends nine bytes a
  press; 12 Mbit/s is several thousand times what it needs.
- **Enumeration: measured.** The host's log names it
  `303a:0002 tinymachines NES Pad`, `USB HID v1.11 Keyboard`, and the
  firmware prints `# host: configured`.
- **Whether a phone powers it: not measured.** A phone acting as USB host has to
  supply the board through that socket. Whether this board runs from
  that socket alone, and within what a phone will give, has not been
  tried. On the bench the board was also powered through its UART
  socket.

## The host turns the report into a key event

Strictly outside USB, but it is where the NES game actually receives
the button, so it belongs in the chain. The operating system turns the
report into key-down and key-up events, and a browser emulator sees
them as `keydown` with two different names for the same press:

- `event.code` names the **physical key**: `KeyX`, `KeyZ`,
  `ShiftRight`, `Enter`, `ArrowUp`. It comes straight from the HID
  usage and does not change with the keyboard layout set on the host.
- `event.key` names the **character**, which does. On a German layout
  usage `0x1D` types `y`, on French it types `w`.

So B arrives as `KeyZ` everywhere, and as `z` only on hosts set to a
layout with Z in that spot. An emulator that binds by `code` works on
any host; one that binds by `key` makes B depend on the phone's
language settings. US and Japanese layouts both put Z and X in the
same place, which is why this will not show up on the bench.

MEASURED 2026-09-28 with `tools/keydown-page.html`, served unlisted at
`tinymachines.ai/lab/pad-keydown` (the page is self-contained and
copies its record as JSON lines; the host it ran on is not yet named
here). Two runs, eight buttons each, pressed one at a time:

- every press arrived as its `code`, in the order pressed: `KeyX`,
  `KeyZ`, `ShiftRight`, `Enter`, `ArrowUp`, `ArrowDown`, `ArrowLeft`,
  `ArrowRight`; every `keyup` followed its `keydown`; A and B were
  held about 65 ms in the first run and 210 to 250 ms in the second,
  the arrows 150 to 500 ms, and nothing was lost at either length;
- `key` is the host's, exactly as above: in the first run something on
  the host held its own `ShiftLeft` across A and B (the adapter never
  sends a left shift; Select is the right one, and it arrived as
  `ShiftRight` in both runs), so A and B came through as `X` and `Z`;
  in the second run, with nothing held, as `x` and `z`;
- the one `repeat: true` line was the host's autorepeat, 500 ms after
  `ArrowRight` went down and 17 ms before it went up. The adapter sends
  one report per change (`pad-usb.ino`), so a repeated `keydown` is
  the host repeating a held key, and an emulator that counts presses
  must ignore it, as it ignores a real keyboard's.

## Why USB now, and Bluetooth later

BLE was the first plan and is still the reason `pad-ble` is named what
it is. On the P4 the radio is an onboard ESP32-C6 reached over SDIO,
and the BLE build crashes inside the vendor's link to it, always
2881 ms after start, in code this project does not own. USB removes
that whole component: no radio, no co-processor, no pairing. The full
account is in `pad-ble-build.md` under "The direction changed twice".

Everything above layer 4 is shared. The same poll, the same table and
the same descriptor serve both builds, so when Bluetooth returns (the
fix is new firmware on the C6, through the board's `C6 UART` header),
only the transport changes and none of this page's first three layers
does.

## The plan, one layer at a time

Each step proves one layer and needs nothing after it. A step that
fails places the fault in its own layer.

| step | proves | tool | passes when | 2026-09-27 |
|---|---|---|---|---|
| 1 | the original's five wires reach the right 4021 pins | meter, pad unpowered | white 16, brown 8, orange 9, red 10, yellow 3 | traced from photographs of the pad's board, not beeped; step 3 confirms it in use |
| 2 | layer 1 at 3.3 V: the pad answers | `firmware/pad-diag` | holding A drives D0 low, releasing it lets it go high | **passes**, 27 presses in 30 s |
| 3 | layers 1 and 2: the byte follows the buttons | `firmware/pad-usb`, `tools/pad-watch.py` | each button alone prints its own bit, `01` through `80`, and idle is `00` | **passes**, and chords (`03`, `A0`) |
| 4 | layer 4: the host enumerates it | the host's USB log | `303a:0002`, `NES Pad`, class HID, and the speed | **passes**, full speed |
| 5 | layer 3: the host reads the report the way it was meant | the input device, read directly on Linux | A gives `KEY_X`, Select gives `KEY_RIGHTSHIFT` | **passes**, all eight keys and chords |
| 6 | the host: the browser sees it | `tools/keydown-page.html` at `tinymachines.ai/lab/pad-keydown` | A gives `code` `KeyX` | **passes** 2026-09-28, all eight codes, two runs; the host's autorepeat and modifiers seen as the host's |
| 7 | the whole chain on the device it is for | a phone and a browser emulator | the game moves | run 2026-09-28 on an iPhone and `tinymachines.ai/nes/play`, which binds by `code`: the board enumerated, A, B, Select and Start moved the game, the cross did not (the host keeps a hardware keyboard's arrows for itself unless a field is focused; the emulator now keeps one focused, as the step 6 page always did); passes when the cross moves too |

Step 2 closed measure-first item 4. Step 3 needs no host at all:
the P4 prints every change on its serial log whether or not anything
is plugged into `USB`, which is why it comes before step 4.

## Open, and not claimed

- **A phone** (step 7): an iPhone enumerates the board and a browser
  emulator on it moves, by A, B, Select and Start (2026-09-28, on
  `tinymachines.ai/nes/play`); the cross did not. The phone hands a
  hardware keyboard's arrow keys to the focused element and keeps them
  for scrolling when nothing is focused, while letters, Shift and Enter
  reach the page either way. The step 6 page keeps an off-screen input
  focused for exactly this, which is why it saw all eight; the emulator
  did not, and now does (its `playEngine.ts`, the same input). Open
  until the cross moves on the phone after that change, and until the
  phone's model, the iOS and browser versions, and whether it powered
  the board alone with the UART cable out are written here. Step 6's
  host is still to be named too.
- **Latency of the host layer.** The keydown page stamps events with
  the host's clock only, so it says nothing about the time from
  button to event.
- **Latency.** Bounded by the code, not measured: a change waits at
  most one 16 ms poll, then at most one host poll. The bench can
  measure it end to end, since the bridge stamps every console poll.
- **Two pads.** A keyboard report has six slots and two pads can ask
  for ten. Two players want gamepad mode with two report IDs, and iOS
  refuses generic HID gamepads, which is why keyboard mode came first.
- **The replica at 5 V.** It would need level shifting both ways, and
  it is not the pad this build is for.
