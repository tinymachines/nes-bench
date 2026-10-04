// An original NES pad as a Bluetooth Low Energy keyboard.
//
// docs/pad-adapter.svg, and section 4 of docs/bench-build-v1-v2.md. The
// bridge already contained the adapter: poll_pad() below is
// firmware/bridge/bridge.ino's own, with the same timings on the same
// pins. What is new is a radio behind it instead of a shift register.
//
// Standalone: no Pi, no UNO, no bridge, no console. A pad, an ESP32
// board and one resistor. Wiring, per the corrected sheet:
//
//   pad GND    -> GND
//   pad +5V    -> 3V3        the 4021 is a CMOS part rated 3 to 18 V
//   pad OUT0   -> GPIO2      latch, driven
//   pad CLK    -> GPIO3      clock, driven
//   pad D0     -> GPIO6      data, with 10k up to 3V3
//
// NOT GPIO4 and GPIO5. Those are the ESP32-S3's numbers and they are
// strapping pins on the C6. The sheet carried them until 2026-09-21.
//
// On a classic ESP32 (an ESP32-WROOM-32 devkit, added 2026-09-30 when
// the C6 board turned out dead) the three pad pins are GPIO25, 26 and
// 27 instead, for the reason at the pin block below, and the build is
// plain, with Serial on the CP2102 that is the board's only socket:
//
//   arduino-cli compile --fqbn esp32:esp32:esp32 --export-binaries firmware/pad-ble
//
//   arduino-cli compile --fqbn esp32:esp32:esp32c6:CDCOnBoot=cdc --export-binaries firmware/pad-ble
//   arduino-cli upload  --fqbn esp32:esp32:esp32c6:CDCOnBoot=cdc -p /dev/ttyACM0 firmware/pad-ble
//
// CDCOnBoot=cdc puts Serial on the board's own USB socket. Without it
// the C6 target sends Serial to the UART0 pins, the socket shows only
// the ROM's boot lines, and a write from the host times out because
// nothing on the chip drains it: MEASURED 2026-09-28, and it looked
// exactly like a sketch that had hung before its first print. (The
// bench reads the P4's log off its UART socket, so the P4 build does
// not want this.) Flashed that day from the bench head with esptool
// over the USB-Serial-JTAG (the four images from --export-binaries at
// the offsets in build/*/flash_args), which is how a board that is
// plugged into the Pi rather than the workstation gets its firmware.
//
// Serial at 115200, one line per change, plus commands:
//
//   B <pad byte> <state>                a change of the pad
//   STATUS                              one line: pads, link, bonded peer
//   KEYS                                the eight mappings as shipped
//   FORGET                              drop every bond stored here
//
// WHAT IS TESTED AND WHAT IS NOT. keymap.h is plain C and
// tools/test-pad-keymap.sh compiles and exercises it natively, so the
// report descriptor and the mapping are held on the desk. Everything in
// THIS file needs the part. The pad's timing at 3.3 V (measure-first
// item 4) was proven on 2026-09-27 through firmware/pad-usb's identical
// poll_pad on the P4; the pairing has met no phone, and on the P4
// BLEDevice::init crashes (pad-usb.ino says why). Nothing about the
// radio here should be described as working until it has.
//
// WHY A KEYBOARD AND NOT A GAMEPAD. Every host accepts a BLE keyboard
// with no app, no driver and no pairing shim, and browser emulators take
// keys. A generic HID gamepad is refused by iOS, which accepts only the
// MFi, Xbox, PlayStation and Switch Pro layouts. Gamepad mode belongs
// behind the mode switch (GPIO10 on the C6, GPIO21 on the P4) and is not
// in this build.
//
// ONE PAD, and that is the design rather than a first step. A keyboard
// report carries six key slots and two pads can ask for ten, so a
// second pad could be polled and never sent. One was wired on the sheet
// and polled here until 2026-09-23 doing exactly that, which is a part
// on a buildable drawing doing nothing. Two players wants gamepad mode
// with two report IDs, on a part that can present them.

#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEHIDDevice.h>
#include <BLEUtils.h>
// No report ID on the air: see keymap.h. The library still writes a
// Report Reference of {0, input}, which is what an unnumbered report is.
#define PAD_HID_REPORT_ID 0
#include "keymap.h"

#if CONFIG_IDF_TARGET_ESP32
// THE CLASSIC ESP32 CANNOT TAKE THE C6 MAP AT ALL.
//
// On an ESP32-WROOM-32 module GPIO6 to GPIO11 are wired to the
// module's own SPI flash, so GPIO6 as the pad's data line and GPIO10
// and GPIO11 as the spare pins would be driving the flash this program
// runs from; and GPIO3 is U0RXD, the receive side of the UART bridge
// that is this board's only serial console. None of the five below has
// a second job on the WROOM-32. GPIO2 is the devkit's own blue LED, so
// the pad-held light needs no wiring on this board.
//
// MEASURED 2026-09-30 on the bench Pi: the board is an ESP32-D0WD-V3
// (revision v3.1) behind a CP2102, by esptool chip-id; it arrived
// running an AT firmware (an at_customize partition, version line
// 2.4.0). Header positions READ OFF THE BOARD from the owner's photo
// of 2026-09-30 (a 30-pin devkit, USB socket at the breadboard's row 1
// end, the pins in rows 6 to 20): the three pad pins are adjacent on
// the EN side, D25 in row 13, D26 in row 12, D27 in row 11; GND is
// row 7 on both sides and 3V3 is row 6 on the D23 side. The full
// order is in docs/pad-ble-build.md.
static const int PAD_LATCH = 25;
static const int PAD_CLOCK = 26;
static const int PAD1_DATA = 27;
static const int MODE_SW = 4;   // reserved for gamepad mode; read, not used
static const int LED_PIN = 2;   // the devkit's onboard LED
#else
// The pad side, exactly firmware/bridge/bridge.ino's C6 map. GPIO2, 3
// and 6 exist and are free on BOTH the C6 and the P4, so poll_pad runs
// unedited either way and there is one pad map, not two.
static const int PAD_LATCH = 2;
static const int PAD_CLOCK = 3;
static const int PAD1_DATA = 6;

#if CONFIG_IDF_TARGET_ESP32P4
// THE TWO SPARE PINS MOVE, AND THEY HAVE TO.
//
// On the C6 these were GPIO10 and GPIO11, which cost nothing because
// nothing was wired to them. On the Waveshare ESP32-P4-Module-DEV-KIT
// those same numbers are the ES8311 audio codec's I2S clock and data
// (GPIO9 to GPIO13), and they are not brought out to the header at
// all. Reading one with a pullup and driving the other would be
// fighting a part that is soldered down.
//
// GPIO21 and GPIO20 are header pins 12 and 14, free by
// tools/p4_header.py, and on the same even row as the pad's five, so
// if either is ever wired it does not cross the header either.
static const int MODE_SW = 21;  // P6 pin 12; reserved for gamepad mode
static const int LED_PIN = 20;  // P6 pin 14
#else
static const int MODE_SW = 10;  // reserved for gamepad mode; read, not used
static const int LED_PIN = 11;
#endif
#endif

static const char *DEVICE_NAME = "NES Pad";

static BLEHIDDevice *hid = nullptr;
static BLECharacteristic *input = nullptr;
static bool linked = false;
static uint8_t pad1 = 0;
static uint8_t sent[PAD_REPORT_LEN] = {0};
static uint32_t dropped_total = 0;
static uint32_t polls = 0;

// ------------------------------------------------------------- the pad
// The 4021 loads while OUT0 is high and holds from its fall; the first
// bit is already on D0 before the first clock, so D0 is read BEFORE
// each rising edge and not after. A pressed button pulls D0 low, so a
// low is a 1 in the byte, which is what makes bit 0 mean "A is down"
// and matches Buttons::as_byte.
static uint8_t poll_pad() {
  digitalWrite(PAD_LATCH, HIGH);
  delayMicroseconds(12);
  digitalWrite(PAD_LATCH, LOW);
  delayMicroseconds(6);
  uint8_t b = 0;
  for (int i = 0; i < 8; i++) {
    if (digitalRead(PAD1_DATA) == LOW) {
      b |= 1 << i;
    }
    digitalWrite(PAD_CLOCK, HIGH);
    delayMicroseconds(6);
    digitalWrite(PAD_CLOCK, LOW);
    delayMicroseconds(6);
  }
  polls++;
  return b;
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
#if CONFIG_BT_BLUEDROID_ENABLED
  // The reason a host left is the first thing to ask of a host that
  // pairs and then types nothing (0x13 the host closed it, 0x08 a
  // timeout, 0x3d a MIC failure, i.e. the two ends disagree on a key).
  void onDisconnect(BLEServer *s, esp_ble_gatts_cb_param_t *param) override {
    Serial.printf("# host left, reason 0x%02x\n", param->disconnect.reason);
    onDisconnect(s);
  }
#endif
};

// ------------------------------------------------------- what a host did
// A keyboard host must do two things before a key can reach it: finish
// pairing with encryption, and write 01 00 into the input report's CCCD
// to ask for notifications. The bench head did both and typed; an iPhone
// paired, showed nothing, and this end could not tell which step it
// skipped. These lines say. Added 2026-10-04.
#if CONFIG_BT_BLUEDROID_ENABLED
class Security : public BLESecurityCallbacks {
  bool onSecurityRequest() override { return true; }
  void onAuthenticationComplete(esp_ble_auth_cmpl_t a) override {
    if (a.success) {
      Serial.printf("# paired and encrypted, auth mode 0x%02x\n", a.auth_mode);
    } else {
      Serial.printf("# pairing FAILED, reason 0x%02x\n", a.fail_reason);
    }
  }
};
#endif

class Cccd : public BLEDescriptorCallbacks {
  void onWrite(BLEDescriptor *d) override {
    uint8_t *v = d->getValue();
    Serial.printf("# host wrote the report CCCD: %02x %02x (01 00 = send me keys)\n", v[0], v[1]);
  }
};

class Delivery : public BLECharacteristicCallbacks {
  int last = -1;
  void onStatus(BLECharacteristic *c, Status st, uint32_t code) override {
    // Once per change of status: every report would flood the log.
    if ((int)st != last) {
      last = (int)st;
      Serial.printf("# report delivery status %d code %lu (1 = sent, 3 = notify off, 6 = no subscriber)\n", (int)st, (unsigned long)code);
    }
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
#if CONFIG_BT_BLUEDROID_ENABLED
  BLEDevice::setSecurityCallbacks(new Security());
#endif

  BLEServer *server = BLEDevice::createServer();
  server->setCallbacks(new Link());

  hid = new BLEHIDDevice(server);
  input = hid->inputReport(PAD_HID_REPORT_ID);
  input->setCallbacks(new Delivery());
  BLEDescriptor *cccd = input->getDescriptorByUUID(BLEUUID((uint16_t)0x2902));
  if (cccd) {
    cccd->setCallbacks(new Cccd());
  } else {
    Serial.println("# no CCCD on the input report: no host can subscribe");
  }
  hid->outputReport(PAD_HID_REPORT_ID);  // the LEDs the descriptor declares; writes ignored
  // manufacturer() with no argument CREATES the characteristic and
  // returns it; manufacturer(name) only writes through the pointer that
  // call sets, and the library leaves that pointer uninitialised. The
  // one-argument form alone was a load access fault at the first byte
  // of setValue, MEASURED 2026-09-28 on the first C6 that ever got past
  // BLEDevice::init (the P4 crashed before reaching this line, which
  // is why the fault hid).
  hid->manufacturer()->setValue("tinymachines");
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
  Serial.printf("# pad %02x  link %s  polls %lu  dropped %lu\n", pad1, linked ? "up" : "down",
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
#elif defined(CONFIG_BT_BLUEDROID_ENABLED)
  // The classic ESP32's core is Bluedroid, where there is no store to
  // clear in one call: the bonds are listed and removed one by one.
  // Without this branch FORGET printed rc -1 and cleared nothing on
  // that part (MEASURED 2026-09-30: the build's map has no
  // ble_store_clear), while a reflash of the merged image blanks the
  // bond store anyway, which is the one-sided bond with no way out.
  int n = esp_ble_get_bond_device_num();
  if (n > 0) {
    esp_ble_bond_dev_t *devs = (esp_ble_bond_dev_t *)malloc(n * sizeof(esp_ble_bond_dev_t));
    if (devs && esp_ble_get_bond_device_list(&n, devs) == ESP_OK) {
      rc = 0;
      for (int i = 0; i < n; i++) {
        if (esp_ble_remove_bond_device(devs[i].bd_addr) != ESP_OK) rc++;
      }
    }
    free(devs);
  } else {
    rc = 0;
  }
  Serial.printf("# %d bond(s) were stored here\n", n);
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
  pinMode(MODE_SW, INPUT_PULLUP);
  pinMode(LED_PIN, OUTPUT);
  Serial.println("# nes-bench pad-ble: an original pad as a BLE keyboard");
  Serial.println("# the pad at 3V3 is measure-first item 4 and is UNPROVEN on this bench");
  say_keys();
  start_ble();
}

void loop() {
  static uint32_t last = 0;
  static uint8_t was1 = 0xFF;

  // 1 kHz, the rate docs/pad-adapter.svg states and the bridge's own
  // pad poll uses. The console polls at 60 Hz; polling sixteen times
  // faster costs nothing here and means a press is never waiting on
  // this loop.
  if (millis() != last) {
    last = millis();
    pad1 = poll_pad();
  }

  if (pad1 != was1) {
    was1 = pad1;
    Serial.printf("B %02x %s\n", pad1, linked ? "linked" : "unlinked");
    digitalWrite(LED_PIN, pad1 != 0);
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
