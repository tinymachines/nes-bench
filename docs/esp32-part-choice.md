# Which ESP32 does which job

Asked on 2026-09-24, while the pad-ble C6 was refusing to flash: is
there another part in the drawer that does Bluetooth, and is there one
that would let the adapter be a USB-C cable to a phone instead of a
radio?

This document answers it from the vendor's own headers rather than
from memory, because the one time this question was answered from
memory the answer was a pin map for the wrong chip.

## The table, measured

Every Espressif part defines its capabilities as macros in
`soc_caps.h`, one header per target, and the Arduino core ships all of
them. Measured on this workstation against **esp32 arduino core
3.3.11**:

    cd ~/.arduino15/packages/esp32/tools
    grep -E '^#define SOC_(USB_OTG|USB_SERIAL_JTAG|BT|BLE|BT_CLASSIC|WIFI)_SUPPORTED' \
        <target>-libs/3.3.11/include/soc/<target>/include/soc/soc_caps.h

A blank cell is the macro being **absent**, which is how these headers
say no: they define a capability only when the silicon has it.

    target     OTG      SER_JTAG BT     BLE    BT_CLASS WIFI
    esp32                   1     (1)    (1)      1       1
    esp32s2      1                                        1
    esp32s3      1          1      1     (1)              1
    esp32c3                 1      1     (1)              1
    esp32c6                 1      1     (1)              1
    esp32h2                 1      1     (1)
    esp32c5                 1      1     (1)              1
    esp32p4      1          1

Read as a parts table:

| Chip | BLE HID | USB HID device | Note |
|---|---|---|---|
| ESP32 classic | yes, plus Bluetooth Classic | **no**, no USB block at all | UART bridge only |
| ESP32-S2 | **no Bluetooth of any kind** | yes | Wi-Fi only radio |
| **ESP32-S3** | **yes** | **yes** | the only part that does both |
| ESP32-C3 | yes | no | serial/JTAG only |
| **ESP32-C6** (on hand) | yes | **no** | serial/JTAG only |
| ESP32-H2 | yes | no | no Wi-Fi either: BLE and 802.15.4 |
| ESP32-C5 | yes | no | serial/JTAG only |
| ESP32-P4 | **no radio at all** | yes, two OTG | needs a companion chip to be wireless |

## Why SOC_USB_OTG_SUPPORTED is the line that matters

It is not a documentation note. It is the preprocessor condition the
Arduino core wraps the whole USB HID class in:

    libraries/USB/src/USBHID.h:18          #if SOC_USB_OTG_SUPPORTED
    libraries/USB/src/USBHIDKeyboard.h:25  #if SOC_USB_OTG_SUPPORTED

On a C6 those headers compile to nothing. `USBHIDKeyboard` is not a
missing library, it is an empty file, so the sketch fails with a type
that does not exist rather than with anything that points at the
reason.

**`SOC_USB_SERIAL_JTAG_SUPPORTED` is not a substitute and this is the
whole trap.** The C6 has a USB-C socket that enumerates on a host, so
the part looks like it has USB. That port is a fixed-function CDC
serial and JTAG unit in ROM. It cannot be re-declared as a keyboard,
a gamepad or anything else, because there is no device controller
behind it to declare with.

Note also that the S3 defines **both**, which is why the same board
can be flashed over its native port and then present itself as a
keyboard.

## What is actually in the drawer

`docs/parts.md` lists one: **ESP32-C6-DevKitC-1 v1.2**. That is the
part every pad-ble sheet is drawn around, and by the table above it is
the one part in the family that can never do the USB version of this
job.

Nothing ESP-shaped is on the workstation's USB bus (`lsusb`,
2026-09-24), so any other board is unrecorded. A larger board with a
Pi-shaped 40-pin header was mentioned; it has not been identified, and
until it is, nothing here says what it can do.

## Identifying an unknown board

In order of effort, cheapest first:

1. **Read the metal can.** It prints the module name outright:
   `ESP32-S3-WROOM-1`, `ESP32-WROOM-32`, `ESP32-C6-WROOM-1`. This is
   how the pad-ble board was identified.
2. **Read the RGB LED's silkscreen.** The C6 devkit prints `RGB@IO8`,
   the S3 devkit prints `RGB@IO48`. Recorded in `pad-ble-build.md`.
3. **`lsusb`.** An Espressif `303a:*` means the chip's own USB is
   enumerating. A `10c4:ea60` or `1a86:7523` is a bridge chip, which
   says nothing about the part behind it.
4. **`esptool chip-id`.** Prints the family by name. It needs download
   mode, which is the thing currently failing on the C6, so it is last.

## USB-C to a phone, if the part is an S3

- **iPhone 15 and later, and every USB-C iPad**: host a plain USB HID
  keyboard with no adapter and no app. A C-to-C cable, with the phone
  supplying VBUS.
- **Lightning iPhones**: need the Camera Adapter, which argues about
  power.
- **Android with OTG**: takes a USB keyboard without complaint.

This is authored from the USB HID class being generic, not measured
here. No phone has been connected to anything on this bench.

## The second reason an S3 is interesting right now

The pad-ble C6 has never spoken. Every flash attempt has gone through
the devkit's CP2102N bridge and its auto-reset transistor pair, and
the bridge, the cable, the port, the wiring and ModemManager have each
been ruled out by test while the silence survived all of them.

On an S3 the native USB port is **both** the flashing port and the HID
port. No bridge chip, no auto-reset circuit, no ModemManager probe
window, because the ROM speaks USB itself. Every component currently
under suspicion is absent from that path.

The C6 has the same native port, marked `USB` beside the one marked
`UART`, and whether it enumerates as `303a:*` has been asked twice and
never confirmed. **That test is free and should happen before any part
is bought.**

## What this document does not claim

Nothing here has been built. The pad-ble circuit is still a drawing
(TM-NESB-003 rev D), no pad has been wired to any firmware, no host
has paired with anything, and measure-first item 4, that an original
pad's 4021 follows its buttons at 3.3 V, has been open since
2026-09-07. A different part would change which of those are easy. It
would not close any of them.
