# pad-usb: from a button to a keystroke, layer by layer

What travels between an original NES pad and a phone or laptop when
the pad is plugged into the bench's ESP32-P4 as a USB keyboard. Four
layers, each with its own protocol, then the host, and each one checked
on its own before the next is trusted.

Written 2026-09-27. The build itself, its wiring and why it is USB
rather than Bluetooth are in `pad-ble-build.md`; the choice of board is
in `esp32-part-choice.md`. This page is the protocol and the plan.

**No layer here has carried a real button press to a host yet.** The
P4 end of the wiring is measured hole by hole, the key mapping and
report descriptor are tested on the desk, and the USB descriptors below
are read out of the library the firmware is built against. The pad at
3.3 V, the enumeration and the keystroke are the plan, and each is
marked as such where it appears.

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

**Open: whether an original pad works at 3.3 V.** The 4021 is rated
3 to 18 V, so the datasheet says yes. This bench has not seen it, and
it has been measure-first item 4 since 2026-09-07. The first pad tried
was a replica that does not answer at 3.3 V; the original has a genuine
MN4021B and is the one to test.

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

The P4 has its own USB controller (`SOC_USB_OTG_SUPPORTED`), which is
the thing the ESP32-C6 on this bench lacked entirely. The firmware
uses the Arduino core's `USBHID` over TinyUSB. What the host is told,
read out of esp32 core 3.3.11 rather than observed:

| descriptor | value | where it comes from |
|---|---|---|
| vendor ID | `0x303A` (Espressif) | core default |
| product ID | `0x0002` | core default |
| product string | `NES Pad` | `pad-usb.ino` |
| manufacturer | `tinymachines` | `pad-usb.ino` |
| interface class | HID (3) | `USBHID` |
| interface subclass, protocol | 0, 0 | `USBHID HID;` takes the default |
| endpoints | one interrupt IN, one interrupt OUT | `TUD_HID_INOUT_DESCRIPTOR` |
| polling interval field | 1 | same |

The sequence on plug-in: the host resets the device, reads its device
and configuration descriptors, sees a HID interface, fetches the report
descriptor above, and from then on polls the interrupt IN endpoint.
When a button changes, the next poll gets the nine bytes. No driver is
involved on any mainstream host: HID keyboards are a class every
operating system carries.

### It is a report-protocol keyboard, not a boot keyboard

**Corrected 2026-09-27.** `keymap.h` and `pad-ble-build.md` call this a
boot-protocol keyboard. The report *layout* is the boot layout, but the
USB interface declares subclass 0 and protocol 0, not boot, and the
report carries an ID, which boot reports never do. So a full operating
system (Android, iOS, macOS, Windows, Linux, ChromeOS) reads it through
the descriptor and is unaffected, while a BIOS setup screen, some KVM
switches and some TV boxes, which speak only boot protocol, will not
see it. Nothing on this bench's list needs those. If one ever does, the
change is `USBHID HID(HID_ITF_PROTOCOL_KEYBOARD)` and a descriptor with
no report ID, and it would be the USB build's own descriptor rather
than the shared one, since BLE wants the ID.

### Two sockets, and which one is the keyboard

The board has two USB-C sockets and they are different devices:

- **`PWR USB TO UART`** is a CH343 serial bridge (`1a86:55d3`), the one
  the firmware is flashed over and prints its log to. On the bench it
  is `/dev/p4-uart` on the head. It stays there.
- **`USB`** is the P4's own controller, and it is the keyboard. The host
  plugs in here, with the board's jumper set to **DEVICE**.

Plugging the host into the UART socket gives it a serial port and no
keyboard, and nothing at either end says why.

### Unmeasured at this layer

- **Which speed the port runs at.** The P4 has a high-speed PHY and a
  full-speed one, and the polling interval field means 1 ms at full
  speed but 125 µs at high speed. `lsusb -v` on a Linux host reads it
  off in one line.
- **Whether a phone powers it.** A phone acting as USB host has to
  supply the board through that socket. Whether this board runs from
  that socket alone, and within what a phone will give, has not been
  tried.

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

| step | proves | tool | passes when |
|---|---|---|---|
| 1 | the original's five wires reach the right 4021 pins | meter, pad unpowered | white 16, brown 8, orange 9, red 10, yellow 3 |
| 2 | layer 1 at 3.3 V: the pad answers | `firmware/pad-diag` | holding A drives D0 low, releasing it lets it go high |
| 3 | layers 1 and 2: the byte follows the buttons | `firmware/pad-usb`, `tools/pad-watch.py` | each button alone prints its own bit, `01` through `80`, and idle is `00` |
| 4 | layer 4: the host enumerates it | `lsusb -v` on Linux | `303a:0002`, `NES Pad`, class HID, and the speed |
| 5 | layer 3: the host reads the report the way it was meant | `evtest` on Linux | A gives `KEY_X`, Select gives `KEY_RIGHTSHIFT` |
| 6 | the host: the browser sees it | a `keydown` logger page | A gives `code` `KeyX` |
| 7 | the whole chain on the device it is for | a phone and a browser emulator | the game moves |

Steps 1 and 2 close measure-first item 4. Step 3 needs no host at all:
the P4 prints every change on its serial log whether or not anything
is plugged into `USB`, which is why it comes before step 4.

## Open, and not claimed

- **An original pad at 3.3 V** (measure-first item 4, step 2 above).
- **Enumeration, speed and phone power** (layer 4, steps 4 and 7).
- **Latency.** Bounded by the code, not measured: a change waits at
  most one 16 ms poll, then at most one host poll. The bench can
  measure it end to end, since the bridge stamps every console poll.
- **Two pads.** A keyboard report has six slots and two pads can ask
  for ten. Two players want gamepad mode with two report IDs, and iOS
  refuses generic HID gamepads, which is why keyboard mode came first.
- **The replica at 5 V.** It would need level shifting both ways, and
  it is not the pad this build is for.
