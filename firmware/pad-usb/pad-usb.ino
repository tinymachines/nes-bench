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
// co-processor, no SDIO link, no pairing. The P4 declares
// SOC_USB_OTG_SUPPORTED with two OTG peripherals, which the C6 never
// had, so this is a thing only this part can do.
//
// THE MAPPING IS NOT COPIED. keymap.h here is a SYMLINK to
// firmware/pad-ble/keymap.h, so both builds send the same eight
// buttons as the same eight keys, and tools/test-pad-keymap.sh holds
// that one file to its own descriptor on the desk.
//
// WIRING: header P6, the run around the second 3V3.
//   6 = data (GPIO6), 3V3, 3 = clock (GPIO3), 2 = latch (GPIO2),
//   skip 0, GND. Verified hole by hole with firmware/header-probe.
//
// PLUG THE HOST INTO THE PORT MARKED "USB", not "PWR USB TO UART".
// The UART port is the one this sketch prints to and is flashed over;
// the USB port is the P4's own, and is what the phone or laptop sees.

#include "USB.h"
#include "USBHID.h"
#include "keymap.h"

// The pad side. Same three pins as firmware/bridge and firmware/pad-ble,
// so poll_pad is the same routine on every part this bench owns.
static const int PAD_LATCH = 2;
static const int PAD_CLOCK = 3;
static const int PAD1_DATA = 6;

static USBHID HID;

class PadKeyboard : public USBHIDDevice {
public:
  PadKeyboard() {
    HID.addDevice(this, sizeof(PAD_HID_DESC));
  }
  // The host asks for the report descriptor once, at enumeration. It
  // gets the SAME bytes the BLE build serves, out of the same header.
  uint16_t _onGetDescriptor(uint8_t *buffer) override {
    memcpy(buffer, PAD_HID_DESC, sizeof(PAD_HID_DESC));
    return sizeof(PAD_HID_DESC);
  }
  bool send(const uint8_t *report) {
    return HID.SendReport(PAD_HID_REPORT_ID, report, PAD_REPORT_LEN);
  }
};

static PadKeyboard pad_kb;

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
  Serial.println("# the pad at 3V3 is measure-first item 4 and is UNPROVEN on this bench");
  Serial.println("# plug the HOST into the port marked USB, and set the jumper to DEVICE");
  for (int i = 0; i < 8; i++) {
    Serial.printf("# bit %d  %s\n", i, PAD_KEYS[i].name);
  }

  USB.productName("NES Pad");
  USB.manufacturerName("tinymachines");
  HID.begin();
  USB.begin();
  Serial.println("# USB started. A byte prints on every CHANGE, not every poll.");
}

void loop() {
  static uint8_t last = 0;
  static bool first = true;
  uint8_t b = poll_pad();
  if (first || b != last) {
    uint8_t report[PAD_REPORT_LEN];
    int dropped = pad_report(b, report);
    // Printed on change only: a pad polled at 60 Hz that printed every
    // poll would bury the one line that matters under a thousand.
    Serial.printf("B %02X%s%s\n", b, HID.ready() ? "" : "  (no host yet)",
                  dropped ? "  DROPPED" : "");
    if (HID.ready()) {
      pad_kb.send(report);
    }
    last = b;
    first = false;
  }
  delay(16);   // -- about 60 polls a second, the console's own rate
}
