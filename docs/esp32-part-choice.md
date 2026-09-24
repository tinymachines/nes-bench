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
| ESP32-P4 | **no radio in the silicon**, see below | yes, two OTG | the module on this bench carries a C6 and does both |

## The board on this bench is a P4 module, and that changes its row

Identified 2026-09-24 off its own silkscreen:

    ESP32-P4-Module
    SoC: ESP32-P4NRW32
    WiFi: 802.11 b/g/n/ax
    Flash: 16MB

The table above says the P4 has no radio, and that is correct about the
die: `soc_caps.h` defines neither `SOC_BLE_SUPPORTED` nor
`SOC_WIFI_SUPPORTED` for it. **The module is not the die.** That
silkscreen line is the tell, and `ax` is the specific word that gives
it away: Wi-Fi 6 means there is a second Espressif part in the can, and
the core names it.

Measured in the same core, 3.3.11, in `tools/esp32p4-libs/3.3.11`:

    lib/libbt.a                          the NimBLE host, built for P4
    lib/libespressif__esp_hosted.a       the link to the co-processor

    sdkconfig:
      CONFIG_BT_ENABLED=y
      CONFIG_BT_NIMBLE_ENABLED=y
      CONFIG_BT_CONTROLLER_DISABLED=y     no local controller, correct
      CONFIG_ESP_HOSTED_ENABLED=y
      CONFIG_ESP_HOSTED_CP_TARGET_ESP32C6=y
      CONFIG_ESP_HOSTED_IDF_SLAVE_TARGET="esp32c6"
      CONFIG_ESP_HOSTED_ENABLE_BT_NIMBLE=y
      CONFIG_ESP_HOSTED_NIMBLE_HCI_VHCI=y
      CONFIG_ESP_HOSTED_SDIO_HOST_INTERFACE=y

So the arrangement is: **the Bluetooth host stack runs on the P4 and
the radio is an ESP32-C6 reached over SDIO.** The controller is
disabled locally because there is nothing to control locally, and HCI
goes out over the hosted link instead.

### The Arduino BLE classes say so in their own gate

This is not an inference about what might work. The core's BLE headers
carry a two-armed condition, and the second arm is exactly this case:

    libraries/BLE/src/BLEDevice.h:36     #if defined(SOC_BLE_SUPPORTED) || defined(CONFIG_ESP_HOSTED_ENABLE_BT_NIMBLE)
    libraries/BLE/src/BLEHIDDevice.h:36  #if defined(SOC_BLE_SUPPORTED) || defined(CONFIG_ESP_HOSTED_ENABLE_BT_NIMBLE)
    libraries/BLE/src/BLESecurity.h:34   #if defined(SOC_BLE_SUPPORTED) || defined(CONFIG_ESP_HOSTED_ENABLE_BT_NIMBLE)

Those three headers are the three this project's firmware includes.

### pad-ble compiles for the P4 unedited

The test that settles it, run 2026-09-24:

    arduino-cli compile --fqbn esp32:esp32:esp32p4 firmware/pad-ble

    Sketch uses 791942 bytes (60%) of program storage space.
    Global variables use 26564 bytes (8%) of dynamic memory.

Not one line of `pad-ble.ino` or `keymap.h` changed. The same sketch is
56% of a C6's flash and 60% of the P4's partition.

**A compile is not a run.** It proves the classes exist and link for
this target. It proves nothing about the radio, because the radio is a
second chip that this workstation has never spoken to.

### The pins do not collide, which was not obvious

The hosted link is not free: it occupies real GPIOs on the P4 side,
and they are fixed by the module's wiring, not chosen.

    SDIO to the C6      GPIO 14, 15, 16, 17, 18, 19
    C6 reset            GPIO 54
    boot strapping      GPIO 35 (BOOT_MODE), GPIO 36 (BOOT_MODE2, pullup)
    console UART        GPIO 37 (TX), GPIO 38 (RX)

`pad-ble` uses GPIO 2, 3, 6, 10 and 11. None of those appear above, so
the pad map carries over unchanged, the same way it was chosen to avoid
the C6's strapping pins. That is luck rather than design and is worth
re-checking against the board's own exposed header before wiring.

### What is still unknown about it

- **The SDIO pin map above is the core's default**, written for
  Espressif's own P4 board. A different module may wire the two parts
  differently. If BLE initialises and finds no controller, this is the
  first suspect, and it is a build-time setting rather than a wiring
  fault.
- **The C6 must be running matching esp-hosted slave firmware.** Vendor
  boards ship it flashed. A version mismatch between host and slave is
  a known and confusing failure, and it is not a hardware problem.
- **Nothing has been flashed to this board and nothing has run on it.**

### What it means for the two questions asked

Both of them are answered yes by one board already in the room:

| | |
|---|---|
| BLE keyboard to a phone | yes, host on the P4, radio on the onboard C6 |
| USB-C keyboard to a phone | yes, `SOC_USB_OTG_PERIPH_NUM` is 2 and there is a UTMI PHY, so one of them is high speed |

An S3 remains the simpler part for this job: one chip, one radio, no
co-processor and no hosted link to go wrong. The P4 module is the more
capable part that is already on the bench, and it is the only one here
that can be tried in both modes without buying anything.

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
would not close any of them, and the P4 compile above closes none of
them either.
