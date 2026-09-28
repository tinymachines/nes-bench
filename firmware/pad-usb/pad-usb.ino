// pad-usb: an original NES pad as a USB HID keyboard, on the ESP32-P4.
//
// WHY THIS EXISTS AND NOT ONLY pad-ble. The BLE build crashes on this
// board, and not in our code: the P4 has no radio, its radio is an
// onboard ESP32-C6 over SDIO, and the host's esp-hosted 2.12.11 asks
// that C6 for its firmware version and gets no answer. The failure
// path then reads a pointer nobody filled in. MEASURED 2026-09-25:
// always 2881 ms after BLEDevice::init, in every variant tried, while
// a smaller sketch survives the identical timeout because the garbage
// it reads happens to be harmless. Five explanations were tested and
// eliminated: build options and PSRAM, the security block, a delay
// before init, a delay after init, and our own GPIO setup.
//
// USB REMOVES THE WHOLE COMPONENT THAT IS FAILING. No radio, no
// co-processor, no SDIO link, no pairing.
//
// THIS DRIVES TINYUSB DIRECTLY, ON THE FULL-SPEED CONTROLLER, AND THAT
// IS DELIBERATE (2026-09-27). The P4 has two USB OTG controllers. The
// Arduino core's USB classes hard-code the HIGH-speed one on this
// target (tusb_init(1) and a 512-byte endpoint size), and on the
// Waveshare kit that controller reaches only the USB-A stack J8,
// through a switch, on a port whose VBUS the board DRIVES: a host
// plugged in there would meet the board's 5 V with its own. The
// Type-C socket marked "USB" (H2, "USB1.1 Type-C" in Waveshare's
// schematic) is the one built to be a device: its VBUS is an input
// behind an ideal diode, and its data pair is the FULL-speed PHY on
// GPIO24/25. Measured on the bench: plugged there with the core's
// classes, the host saw only the chip's own USB-Serial-JTAG
// (303a:1001), never the keyboard. So this sketch connects that PHY to
// the full-speed OTG controller itself, starts TinyUSB on port 0, and
// supplies the six callbacks TinyUSB asks the application for. The
// USB-Serial-JTAG leaves that socket while this runs; flashing is over
// the UART socket, which is unaffected.
//
// THE MAPPING IS NOT COPIED. keymap.h here is a SYMLINK to
// firmware/pad-ble/keymap.h, so both builds send the same eight
// buttons as the same eight keys, and tools/test-pad-keymap.sh holds
// that one file to its own descriptor on the desk.
//
// WIRING: header P6, the run around the second 3V3.
//   6 = data (GPIO6), 3V3, 3 = clock (GPIO3), 2 = latch (GPIO2),
//   skip 0, GND. Verified hole by hole with firmware/header-probe.
//   The pull-up on data is 10k: a 10 ohm part in that place on
//   2026-09-27 held D0 high against the 4021 and looked exactly like a
//   pad that does not answer.
//
// PLUG THE HOST INTO THE TYPE-C SOCKET MARKED "USB", not "PWR USB TO
// UART". The UART socket is the one this sketch prints to and is
// flashed over. The jumper that selects HOST or DEVICE belongs to the
// high-speed switch and does not matter to this build.

#include "tusb.h"
#include "keymap.h"
#include "usb_device.h"

// The pad side. Same three pins as firmware/bridge and firmware/pad-ble,
// so poll_pad is the same routine on every part this bench owns.
static const int PAD_LATCH = 2;
static const int PAD_CLOCK = 3;
static const int PAD1_DATA = 6;

// One poll of the 4021: OUT0 high to load, its fall latches, then eight
// clocks, one per button. A pressed button pulls D0 LOW, so the bit is
// set when the line reads low. Bit 0 is A, and the order is
// nes_glue::controller::Buttons::as_byte's.
static uint8_t poll_pad() {
  uint8_t b = 0;
  digitalWrite(PAD_LATCH, HIGH);
  delayMicroseconds(12);
  digitalWrite(PAD_LATCH, LOW);
  delayMicroseconds(6);
  for (int i = 0; i < 8; i++) {
    if (digitalRead(PAD1_DATA) == LOW) {
      b |= (uint8_t)(1 << i);
    }
    digitalWrite(PAD_CLOCK, HIGH);
    delayMicroseconds(6);
    digitalWrite(PAD_CLOCK, LOW);
    delayMicroseconds(6);
  }
  return b;
}

void setup() {
  Serial.begin(115200);
  pinMode(PAD_LATCH, OUTPUT);
  pinMode(PAD_CLOCK, OUTPUT);
  digitalWrite(PAD_LATCH, LOW);
  digitalWrite(PAD_CLOCK, LOW);
  pinMode(PAD1_DATA, INPUT);

  Serial.println("# nes-bench pad-usb: an original pad as a USB HID keyboard");
  Serial.println("# full-speed controller, on the Type-C socket marked USB");
  for (int i = 0; i < 8; i++) {
    Serial.printf("# bit %d  %s\n", i, PAD_KEYS[i].name);
  }

  usb_start();
  Serial.println("# A byte prints on every CHANGE, not every poll.");
}

void loop() {
  static uint8_t last = 0;
  static bool first = true;
  static bool mounted = false;
  if (tud_mounted() != mounted) {
    mounted = tud_mounted();
    Serial.println(mounted ? "# host: configured" : "# host: gone");
  }
  uint8_t b = poll_pad();
  if (first || b != last) {
    uint8_t report[PAD_REPORT_LEN];
    int dropped = pad_report(b, report);
    bool ready = tud_hid_ready();
    // Printed on change only: a pad polled at 60 Hz that printed every
    // poll would bury the one line that matters under a thousand.
    Serial.printf("B %02X%s%s\n", b, ready ? "" : "  (no host yet)", dropped ? "  DROPPED" : "");
    if (ready) {
      tud_hid_report(PAD_HID_REPORT_ID, report, PAD_REPORT_LEN);
    }
    last = b;
    first = false;
  }
  delay(16);  // -- about 60 polls a second, the console's own rate
}
