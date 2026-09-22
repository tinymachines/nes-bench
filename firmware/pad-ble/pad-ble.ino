// An original NES pad as a Bluetooth Low Energy keyboard.
//
// docs/pad-adapter.svg, and section 4 of docs/bench-build-v1-v2.md. The
// bridge already contained the adapter: poll_pads() below is
// firmware/bridge/bridge.ino's poll_pad() with the same timings on the
// same pins, clocking both pads in one pass rather than one. What is
// new is a radio behind it instead of a shift register.
//
// Standalone: no Pi, no UNO, no bridge, no console. A pad, a C6 and two
// resistors. Wiring, per the corrected sheet:
//
//   pad GND    -> GND
//   pad +5V    -> 3V3        the 4021 is a CMOS part rated 3 to 18 V
//   pad OUT0   -> GPIO2      latch, driven
//   pad CLK    -> GPIO3      clock, driven
//   pad D0     -> GPIO6      data, with 10k up to 3V3
//   second pad -> D0 on GPIO7 with its own 10k, sharing latch and clock
//
// NOT GPIO4 and GPIO5. Those are the ESP32-S3's numbers and they are
// strapping pins on the C6. The sheet carried them until 2026-09-21.
//
//   arduino-cli compile --fqbn esp32:esp32:esp32c6 firmware/pad-ble
//   arduino-cli upload  --fqbn esp32:esp32:esp32c6 -p /dev/ttyACM0 firmware/pad-ble
//
// Serial at 115200, one line per change, plus commands:
//
//   B <pad1 byte> <pad2 byte> <state>   a change of either pad
//   STATUS                              one line: pads, link, bonded peer
//   KEYS                                the eight mappings as shipped
//   FORGET                              drop every bond stored here
//
// WHAT IS TESTED AND WHAT IS NOT. keymap.h is plain C and
// tools/test-pad-keymap.sh compiles and exercises it natively, so the
// report descriptor and the mapping are held on the desk. Everything in
// THIS file needs the part: the pad's timing at 3.3 V is measure-first
// item 4 and has never been done, and the pairing has met no phone.
// Nothing here should be described as working until it has.
//
// WHY A KEYBOARD AND NOT A GAMEPAD. Every host accepts a BLE keyboard
// with no app, no driver and no pairing shim, and browser emulators take
// keys. A generic HID gamepad is refused by iOS, which accepts only the
// MFi, Xbox, PlayStation and Switch Pro layouts. Gamepad mode belongs
// behind the mode switch on GPIO10 and is not in this build.
//
// ONE PAD SENDS KEYS, and that is a limit, not an oversight. A keyboard
// report carries six key slots. Two pads can ask for ten keys, so two
// players on one keyboard report would silently drop whatever arrived
// last. Pad 2 is polled and printed so its wiring can be proved, and
// two players want gamepad mode with two report IDs.

#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEHIDDevice.h>
#include <BLEUtils.h>
#include "keymap.h"

// The pad side, exactly firmware/bridge/bridge.ino's C6 map.
static const int PAD_LATCH = 2;
static const int PAD_CLOCK = 3;
static const int PAD1_DATA = 6;
static const int PAD2_DATA = 7;
static const int MODE_SW = 10;  // reserved for gamepad mode; read, not used
static const int LED_PIN = 11;

static const char *DEVICE_NAME = "NES Pad";

static BLEHIDDevice *hid = nullptr;
static BLECharacteristic *input = nullptr;
static bool linked = false;
static uint8_t pad1 = 0, pad2 = 0;
static uint8_t sent[PAD_REPORT_LEN] = {0};
static uint32_t dropped_total = 0;
static uint32_t polls = 0;

// ------------------------------------------------------------- the pad
// The 4021 loads while OUT0 is high and holds from its fall; the first
// bit is already on D0 before the first clock, so D0 is read BEFORE
// each rising edge and not after. A pressed button pulls D0 low, so a
// low is a 1 in the byte, which is what makes bit 0 mean "A is down"
// and matches Buttons::as_byte.
// Both pads off one latch and one clock: they are separate shift
// registers sharing a strobe, so one pass clocks both and the second
// pad costs a pin, not a poll.
static void poll_pads(uint8_t *a, uint8_t *b) {
  digitalWrite(PAD_LATCH, HIGH);
  delayMicroseconds(12);
  digitalWrite(PAD_LATCH, LOW);
  delayMicroseconds(6);
  uint8_t g1 = 0, g2 = 0;
  for (int i = 0; i < 8; i++) {
    if (digitalRead(PAD1_DATA) == LOW) {
      g1 |= 1 << i;
    }
    if (digitalRead(PAD2_DATA) == LOW) {
      g2 |= 1 << i;
    }
    digitalWrite(PAD_CLOCK, HIGH);
    delayMicroseconds(6);
    digitalWrite(PAD_CLOCK, LOW);
    delayMicroseconds(6);
  }
  *a = g1;
  *b = g2;
  polls++;
}

// ------------------------------------------------------------- the link
class Link : public BLEServerCallbacks {
  void onConnect(BLEServer *s) override {
    linked = true;
    Serial.println("# linked");
  }
  void onDisconnect(BLEServer *s) override {
    linked = false;
    Serial.println("# unlinked, advertising again");
    // A host that walks out of range must be able to walk back in
    // without the pad being power cycled.
    BLEDevice::startAdvertising();
  }
};

static void start_ble() {
  BLEDevice::init(DEVICE_NAME);

  // THE FOUR THINGS A HOST WANTS, and the reason most sketches pair on
  // Android and then fail on an iPhone. Each of these is load bearing:
  //
  //  1. Bonding with encryption. The HID characteristics are readable
  //     only on an encrypted link, so without a bond the host connects,
  //     reads nothing and drops. No display and no keypad on this end
  //     means no MITM protection is possible, so the capability is
  //     None/None and the pairing is Just Works.
  //  2. The PnP ID and the manufacturer string, below. A HID peripheral
  //     with no PnP ID is a peripheral the host cannot classify.
  //  3. A battery service, which BLEHIDDevice creates as soon as a
  //     level is set. Hosts expect one on a HID device and sulk quietly
  //     without it.
  //  4. The HID service UUID and the keyboard appearance in the
  //     ADVERTISEMENT, not only in the GATT table. A phone decides what
  //     to offer as a pairable accessory from the advertising packet
  //     alone, so a device that hides 0x1812 until after connection
  //     never gets offered.
  BLESecurity::setAuthenticationMode(true, false, true);  // bonding, no MITM, secure connections
  BLESecurity::setCapability(ESP_IO_CAP_NONE);
  BLESecurity::setKeySize(16);

  BLEServer *server = BLEDevice::createServer();
  server->setCallbacks(new Link());

  hid = new BLEHIDDevice(server);
  input = hid->inputReport(PAD_HID_REPORT_ID);
  hid->outputReport(PAD_HID_REPORT_ID);  // the LEDs the descriptor declares; writes ignored
  hid->manufacturer("tinymachines");
  // Vendor 0x02E5 is Espressif's, which is what this actually is; a
  // borrowed vendor ID would be a claim about somebody else's hardware.
  hid->pnp(0x02, 0x02E5, 0x0001, 0x0100);
  hid->hidInfo(0x00, 0x01);  // no localisation, remote wake
  hid->reportMap((uint8_t *)PAD_HID_DESC, sizeof(PAD_HID_DESC));
  hid->setBatteryLevel(100);  // no cell on this build: USB powered, so say full
  hid->startServices();

  BLEAdvertising *adv = BLEDevice::getAdvertising();
  adv->setAppearance(HID_KEYBOARD);
  adv->addServiceUUID(hid->hidService()->getUUID());
  adv->setScanResponse(true);
  BLEDevice::startAdvertising();
  Serial.printf("# advertising as \"%s\", %u descriptor bytes\n", DEVICE_NAME, (unsigned)sizeof(PAD_HID_DESC));
}

// ------------------------------------------------------------ commands
static void say_status() {
  Serial.printf("# pads %02x %02x  link %s  polls %lu  dropped %lu\n", pad1, pad2, linked ? "up" : "down",
                (unsigned long)polls, (unsigned long)dropped_total);
}

static void say_keys() {
  for (int i = 0; i < 8; i++) {
    Serial.printf("# bit %d  %s\n", i, PAD_KEYS[i].name);
  }
}

static void forget() {
  // The trap this exists for: reflashing this board can clear its bond
  // store while the phone still holds its side. The phone then believes
  // it is paired, the link is refused, and nothing says why. Clearing
  // here is only half of it, so the message names the other half.
  int rc = -1;
#if defined(CONFIG_NIMBLE_ENABLED)
  rc = ble_store_clear();
#endif
  Serial.printf("# bonds cleared here (rc %d). NOW FORGET THIS DEVICE ON THE HOST TOO:\n", rc);
  Serial.println("# a one-sided bond fails to pair and reports nothing at either end.");
}

void setup() {
  Serial.begin(115200);
  pinMode(PAD_LATCH, OUTPUT);
  pinMode(PAD_CLOCK, OUTPUT);
  digitalWrite(PAD_LATCH, LOW);
  digitalWrite(PAD_CLOCK, LOW);
  pinMode(PAD1_DATA, INPUT);
  pinMode(PAD2_DATA, INPUT);
  pinMode(MODE_SW, INPUT_PULLUP);
  pinMode(LED_PIN, OUTPUT);
  Serial.println("# nes-bench pad-ble: an original pad as a BLE keyboard");
  Serial.println("# the pad at 3V3 is measure-first item 4 and is UNPROVEN on this bench");
  say_keys();
  start_ble();
}

void loop() {
  static uint32_t last = 0;
  static uint8_t was1 = 0xFF, was2 = 0xFF;

  // 1 kHz, the rate docs/pad-adapter.svg states and the bridge's own
  // pad poll uses. The console polls at 60 Hz; polling sixteen times
  // faster costs nothing here and means a press is never waiting on
  // this loop.
  if (millis() != last) {
    last = millis();
    poll_pads(&pad1, &pad2);
  }

  if (pad1 != was1 || pad2 != was2) {
    was1 = pad1;
    was2 = pad2;
    Serial.printf("B %02x %02x %s\n", pad1, pad2, linked ? "linked" : "unlinked");
    digitalWrite(LED_PIN, pad1 || pad2);
  }

  if (linked && input) {
    uint8_t report[PAD_REPORT_LEN];
    int dropped = pad_report(pad1, report);
    // Only on a change. A keyboard that re-sends an unchanged report at
    // 1 kHz is a keyboard that floods the link and, on a host that
    // treats every report as an event, types forever.
    if (memcmp(report, sent, PAD_REPORT_LEN) != 0) {
      memcpy(sent, report, PAD_REPORT_LEN);
      input->setValue(sent, PAD_REPORT_LEN);
      input->notify();
      if (dropped) {
        dropped_total += dropped;
        Serial.printf("# %d key(s) did not fit six slots: pad %02x\n", dropped, pad1);
      }
    }
  }

  if (Serial.available()) {
    String line = Serial.readStringUntil('\n');
    line.trim();
    line.toUpperCase();
    if (line == "STATUS") {
      say_status();
    } else if (line == "KEYS") {
      say_keys();
    } else if (line == "FORGET") {
      forget();
    } else if (line.length()) {
      Serial.printf("# unknown command %s (STATUS, KEYS, FORGET)\n", line.c_str());
    }
  }
}
