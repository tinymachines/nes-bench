# One pad, both ways: `firmware/pad`

An original NES pad as a keyboard, over USB when a host is on the
cable and over Bluetooth Low Energy when none is. One sketch, one pad
poll, two sinks. This closes the shape of nes-bench#4; what it does not
close is said at the end.

`firmware/pad-usb` (proven on the Pi, 2026-09-27) and `firmware/pad-ble`
(played on an iPhone, 2026-10-04) stay as they are. They are the
single-path builds the merged one is made of, and the only two that
have met hardware.

## The parts

A USB keyboard needs a USB OTG controller; a BLE keyboard needs a
radio. In the ESP32 family exactly two arrangements have both:

| part | USB | radio | state here |
|---|---|---|---|
| ESP32-S3 | on the die | on the die | none on the bench; two XIAO ESP32S3 on the order list |
| ESP32-P4 module | on the die | an ESP32-C6 beside it, over SDIO | the Waveshare kit on the bench, running `pad-usb` on the Pi |

The classic ESP32 has the radio and no USB controller at all (its
socket is a CP2102 bridge); the C6 has the radio and a fixed-function
serial unit that cannot be a keyboard. `docs/esp32-part-choice.md` has
the table and the `SOC_USB_OTG_SUPPORTED` line that decides it. The
merged sketch refuses to compile for either.

## Which path, and who decides

The pad pins belong to one poll loop, `poll_pad`, the same routine the
bridge and both single-path builds run. USB and BLE are sinks for the
byte it produces. The live sink follows the **host**, not the cable:

1. TinyUSB starts at boot. A host that configures the device within
   1.5 s makes the path USB, and the radio is never started.
2. No host in that time: the radio starts, the path is BLE. A wall
   charger gives VBUS and no host, so a pad on a charger goes to BLE,
   which is what a phone wants.
3. A host configuring the device later takes the reports. BLE stays
   linked and gets nothing.
4. A host gone for 2 s hands the reports back to BLE, starting the
   radio if it never ran.
5. The mode switch low at boot (GPIO21 on the P4, GPIO7 on the S3)
   forces BLE: charge from a PC without the PC taking the keyboard.

Every decision prints as `# path: ...`; `STATUS` says it again. The
test for "a host" is `tud_mounted()`, the device being configured, not
VBUS: that is what tells a charger from a computer.

## Two shapes of one report

USB sends report ID 1 (TinyUSB prepends it, every host reads it). BLE
sends no ID at all: BlueZ 5.66 dropped a numbered report it read from
its cache before the Report Reference descriptor (2026-10-04,
`pad-ble-build.md`). The single-path builds chose one at compile time
through `PAD_HID_REPORT_ID`. The merged build serves both from one
binary, so `keymap.h` now writes the descriptor body once as a macro
and defines both arrays, `PAD_HID_DESC_USB` and `PAD_HID_DESC_BLE`.
`PAD_HID_DESC` is still the one the ID selects, for the two old builds.

`tools/test-pad-keymap.sh` parses both arrays the way a host does and
holds them to describe the same report and to differ byte for byte by
exactly the two-byte Report ID item. 82 checks per ID; `MUTATE=1` goes
red.

## Pins

| | P4 (header P6) | S3 (XIAO ESP32S3) |
|---|---|---|
| latch | GPIO2 | GPIO4 (D3) |
| clock | GPIO3 | GPIO5 (D4) |
| data, 10k up to 3V3 | GPIO6 | GPIO6 (D5) |
| mode switch, to GND | GPIO21 | GPIO7 (D8) |
| light | GPIO20 | GPIO21 (the user LED, lit low) |

The P4 column is `pad-ble`'s, checked by `tools/p4_header.py` against
the board's schematic. The S3 column is **authored**: the S3's strapping
pins are GPIO0, 3, 45 and 46 and these avoid them, and GPIO4 and 5 are
the numbers the first pad-ble sheet carried before the C6 took over. No
S3 has been wired here.

The pad runs from 3V3 (the 4021 is rated 3 to 18 V, measured working on
2026-09-27). On the XIAO the battery pads on the underside feed its own
charger, which covers the battery half of nes-bench#4 without a module;
a level readout would need a divider to an ADC pin and is not in this
build.

## Building

    arduino-cli compile --fqbn "esp32:esp32:esp32p4:FlashSize=16M,PartitionScheme=fatflash,PSRAM=enabled" --export-binaries firmware/pad
    arduino-cli compile --fqbn "esp32:esp32:esp32s3:USBMode=default" --export-binaries firmware/pad

On the P4, flash over the socket marked `PWR USB TO UART` and plug the
host into the one marked `USB`; Serial is the UART socket, because the
keyboard takes the other (`pad-usb-protocol.md`, layer 4). On the S3
the one native socket is the keyboard once TinyUSB takes it, so Serial
is UART0's pins and flashing is by holding BOOT across a reset.

## The P4's radio: the C6 has to answer

The P4 die has no radio. The module's radio is an ESP32-C6 over SDIO,
and the P4 side (esp-hosted 2.12.11, in arduino-esp32 3.3.11) asks it
for its firmware version at init. The C6 the kit shipped with runs an
older slave build that does not know the request:

    E rpc_core: Response not received for [0x15e](Req_GetCoprocessorFwVersion)

The core then records the co-processor as 0.0.0 and the BLE init path
has read a bad pointer 2881 ms later on every try since 2026-09-25
(`pad-ble-build.md`, "Move two"). Other people with Waveshare P4 boards
hit the identical line on the identical versions, and the fix on every
report is the matching slave image on the C6.

So on the P4 the merged sketch **asks the C6 first**. `hostedInitWiFi()`
brings the link up (the name is the core's; no Wi-Fi is used) and the
version is read back; on 0.0.0 the radio is refused with a line saying
so, and the pad goes on working on USB. The crash lived inside the BLE
init that this never reaches. Measured 2026-10-12 on the kit, after the
C6 was updated: the link came up in 2 s, the C6 answered 2.12.11, and
the radio advertised. The refusal branch itself has not been exercised,
because the C6 was updated before the merged build first ran.

### Updating the C6 over the link it already has

The core itself names the image: `esp32-hal-hosted.c` builds the URL
`https://espressif.github.io/arduino-esp32/hosted/<target>-v<host version>.bin`,
and its `ESP_HostedOTA` library would fetch it over Wi-Fi, through the
C6 that cannot answer. `tools/fetch-c6-image.py` reads the host version
out of the installed core's header, fetches that file, checks its
SHA-256 against the one recorded in the script (2.12.11:
`5b05e153...d709cb`, read 2026-10-12), checks the image header says
ESP32-C6, and writes it into `firmware/p4-c6-update/c6_image.c`
(generated, gitignored). The sketch pushes the bytes through the same
four calls the core's OTA uses: begin, write, end, activate.

    python3 tools/fetch-c6-image.py
    arduino-cli compile --fqbn "esp32:esp32:esp32p4:FlashSize=16M,PartitionScheme=app3M_fat9M_16MB,PSRAM=enabled" --export-binaries firmware/p4-c6-update
    arduino-cli upload  --fqbn "esp32:esp32:esp32p4:FlashSize=16M,PartitionScheme=app3M_fat9M_16MB,PSRAM=enabled" -p /dev/ttyACMx firmware/p4-c6-update

Every step prints its verdict. The OTA request is itself an RPC, and a
slave old enough to miss the version request may miss it too: one
Waveshare report says theirs did. A refusal at `begin` is the signal
for the way below. After `activate`, power-cycle, then `VERSION`.

**MEASURED 2026-10-12, on the kit, over the Pi's serial port:** the
factory C6 that never answered the version request took the in-band
update. `begin` accepted, 1,226,800 bytes written in about 6 s, `end`
and `activate` accepted; after a restart the link came up in 2 s
instead of timing out at 3, and the C6 reported 2.12.11, the host's
own number. The UART way below was not needed on this board. (The
first restart re-ran the update for nothing; the sketch now skips a
matching C6 unless told `AGAIN`.)

### The C6 over its UART: header P2

Read off Waveshare's schematic (`ESP32-P4-Module-DEV-KIT.pdf`, sheet 1,
connector P2, an SH1.0 4-pin socket with an ESD diode on each line):

| P2 pin | net |
|---|---|
| 1 | C6_U0TXD |
| 2 | C6_U0RXD |
| 3 | GND |
| 4 | C6_IO9 |

This is **not** the order on Waveshare's larger P4 boards (their J7 has
IO9 on 3 and GND on 4). Read the drawing for the board in hand.

1. Power off. Bridge P2 pin 4 (IO9) to pin 3 (GND): the C6 boots into
   download mode with IO9 low.
2. A 3.3 V USB-UART adapter: adapter TX to pin 2 (the C6's RXD),
   adapter RX to pin 1 (the C6's TXD), GND to pin 3. Adapters label
   their pins both ways; if nothing answers, swap the two.
3. Hold the P4's BOOT button while powering up. GPIO54 is the C6's
   reset and the P4 drives it (active high); a P4 held in its own
   download mode leaves the C6 alone.
4. Back up, then write only the app partition at 0x10000. The factory
   bootloader and partition table stay:

       esptool --chip esp32c6 --port /dev/ttyUSBx --before no-reset --after no-reset read-flash 0x0 0x400000 c6-factory-backup.bin
       esptool --chip esp32c6 --port /dev/ttyUSBx --before no-reset --after no-reset write-flash 0x10000 firmware/p4-c6-update/esp32c6-v2.12.11.bin

5. Remove the bridge, power-cycle, and read the version with the
   updater's `VERSION` or the pad's `STATUS`.

Step 4 is one Waveshare owner's recipe for the same symptom on a
different board (their J7); the offset is the slave's standard app
partition and the backup is what makes a wrong guess recoverable. None
of this has been done here yet.

## Pairing on the P4: legacy, because the hosted radio fails the DHKey check

With secure connections on, as `pad-ble` pairs on the classic ESP32,
pairing from the bench Pi (BlueZ 5.66) failed three times out of three
with `AuthenticationFailed`, and the Pi's radio trace (`btmon`) says
where: the whole SC exchange ran, both public keys, confirm, randoms,
the Pi's DHKey check sent, and then the **pad** answered

    SMP: Pairing Failed (0x05)  Reason: DHKey check failed (0x0b)

The P4's NimBLE host and the C6's controller across the hosted link do
not agree on the ECDH result. So on the P4 the merged sketch asks for
legacy just-works pairing (bonding on, no MITM, no SC), which has no
ECDH in it. Measured 2026-10-13 on the first try after the change: the
Pi paired, bonded and connected, subscribed to the input report, and
the kernel made a keyboard of it (`Bus=0005 ... Name="NES Pad"`).
An iPhone accepted it the same night: linked, subscribed to the input
report, every press delivered (status 1 on the pad's log), and the
owner saw the keys arrive. The classic ESP32 build keeps SC.

Two things worth knowing about pairing from the Pi: `bluetoothctl`'s
yes/no prompt reads from a terminal, so piped answers are lost and the
pairing times out with "No agent available"; `tools/btpair.py` drives
it through a pseudo-terminal and answers the prompt. And `trust` the
address before `pair`, or BlueZ asks the agent to authorize a just-works
pairing it could have accepted itself.

## What is and is not done

Done, on the desk: the merged sketch compiles for the P4 and the S3;
both descriptors are held to each other by the desk test; the two
single-path builds compile unchanged against the new header; the C6
image is fetched, checked and built into the updater.

Done, on the kit (2026-10-12 and 13, flashed and read over the bench
Pi's serial port, the kit's UART socket on the Pi): the factory C6 took
the in-band update and answers 2.12.11; the merged sketch on the P4
with no USB host starts the radio, advertises, and the Pi hears it;
the Pi pairs (legacy), bonds, connects and gets a keyboard device.

Done, end to end (2026-10-13): the USB path typed into the owner's
machine (B as z, A as x, Select held as shift) and the BLE path typed
into an iPhone, both from one binary on the P4. The pad's log showed
56 button changes on the BLE path, each delivered. nes-bench#4 is
closed on that.

Two traps met on the way, both recorded above: the Pi, bonded and
trusted, reconnects to the pad on its own and holds it, so a phone sees
nothing until the Pi is told `block`; and a disconnect from the Pi once
never reached the pad over the hosted link (it kept saying linked and
stopped advertising until power-cycled), while the next time it did.

Not done:

- The refusal branch (a C6 that does not answer) has not run.
- A cell and a charger: the P4 kit has no battery input, so that is the
  XIAO's job, nes-bench#6, drawing package TM-NESB-004.
- Latency, press to key, either path (nes-bench item 11).
