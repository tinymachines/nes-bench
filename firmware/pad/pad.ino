// pad: an original NES pad as a keyboard, over USB when a host is on the
// cable and over Bluetooth Low Energy when none is. One sketch, one
// pad poll, two sinks. This is firmware/pad-usb and firmware/pad-ble
// folded together (nes-bench#4); those two stay as the single-path
// builds they were proven as.
//
// WHICH PATH, AND WHO DECIDES. The pad pins belong to one poll loop,
// poll_pad below, which is the bridge's and both single-path builds'.
// The paths are sinks for the byte it produces, and the live sink
// follows the HOST, not the cable:
//
//   - TinyUSB starts at boot. If a host configures the device within
//     USB_WAIT_MS the path is USB and the radio is never started. A
//     wall charger gives VBUS and no host, so a pad on a charger goes
//     to BLE, which is the case a phone wants.
//   - Otherwise the radio starts and the path is BLE.
//   - A host configuring the device later takes the reports (BLE stays
//     linked, gets nothing); a host gone for USB_GONE_MS hands them
//     back to BLE, starting the radio if it never ran.
//   - The mode switch low at boot forces BLE: charge from a PC without
//     the PC taking the keyboard.
//
// Every decision prints as "# path: ..." so the log says which way the
// keys went. STATUS says it again on demand.
//
// TWO SHAPES OF THE SAME REPORT. keymap.h now defines both descriptors
// from one body: PAD_HID_DESC_USB carries Report ID 1 (TinyUSB prepends
// it, every host reads it) and PAD_HID_DESC_BLE carries no ID at all
// (BlueZ 5.66 dropped a numbered report, measured 2026-10-04). The
// desk test holds the two to differ by exactly that item.
//
// THE PARTS THIS BUILDS FOR. A USB OTG controller and a radio, in one
// package or on one board:
//
//   ESP32-P4 (the Waveshare ESP32-P4-Module-DEV-KIT on this bench):
//     USB is native and proven (pad-usb, 2026-09-27, on the Pi). The
//     radio is the module's onboard ESP32-C6 over SDIO, driven by
//     esp-hosted, and it answers only if the C6 runs esp-hosted slave
//     firmware the host can talk to. The kit shipped with one that does
//     not (the 2.12.11 host asks it for its version, gets nothing, and
//     the failure path has read a bad pointer 2881 ms later on every
//     try since 2026-09-25). So on the P4 this sketch asks the C6 first
//     and REFUSES the radio if it does not answer, instead of crashing
//     a pad that is working on USB. firmware/p4-c6-update puts the
//     matching slave firmware on the C6 over the same link, or
//     docs/pad-build.md says how to do it through header P2.
//   ESP32-S3 (the XIAO ESP32S3 on the order list): both on the die.
//     AUTHORED, not measured: no S3 has been on this bench.
//
// Anything else is refused at compile time: a C6 or a classic ESP32
// cannot be a USB keyboard (docs/esp32-part-choice.md), so the merged
// build would be a lie on them. firmware/pad-ble is the build for those.
//
// Serial at 115200, one line per change, plus commands:
//
//   B <pad byte> <path>                 a change of the pad
//   STATUS                              pads, path, host, link, versions
//   KEYS                                the eight mappings as shipped
//   FORGET                              drop every bond stored here
//
// On the P4, Serial is the UART socket (GPIO37/38): the socket marked
// USB is the keyboard while this runs. On the S3 it is UART0's pins.

#include "sdkconfig.h"
#include "soc/soc_caps.h"
#if !SOC_USB_OTG_SUPPORTED
#error "firmware/pad needs a USB OTG controller: an S3 or a P4. Build firmware/pad-ble for a radio-only part."
#endif

#include "tusb.h"
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEHIDDevice.h>
#include <BLEUtils.h>
#if CONFIG_IDF_TARGET_ESP32P4
#include "esp32-hal-hosted.h"
#endif
#include "keymap.h"
#include "usb_device.h"

// --------------------------------------------------------------- pins
#if CONFIG_IDF_TARGET_ESP32P4
// Exactly firmware/pad-ble's P4 map (header P6, the run around the
// second 3V3): GPIO2, 3 and 6 for the pad, GPIO21 and 20 for the
// switch and the light, all on the even row. tools/p4_header.py holds
// them against the board's schematic.
static const int PAD_LATCH = 2;
static const int PAD_CLOCK = 3;
static const int PAD1_DATA = 6;
static const int MODE_SW = 21;  // low at boot = BLE regardless of USB
static const int LED_PIN = 20;
#else
// The S3's numbers, the ones the first pad-ble sheet carried before the
// C6 took over: not strapping pins (those are 0, 3, 45, 46). On a XIAO
// ESP32S3 these are D3, D4, D5 for the pad, D8 for the switch, and the
// user LED on GPIO21, which that board lights LOW. AUTHORED.
static const int PAD_LATCH = 4;
static const int PAD_CLOCK = 5;
static const int PAD1_DATA = 6;
static const int MODE_SW = 7;
static const int LED_PIN = 21;
#endif

// How long a host gets to configure the device before the radio is
// started instead, and how long a host must be gone before the reports
// go back to the radio. Enumeration on the Pi took under a second
// (dmesg, 2026-10-12: the debug unit dropped and the pad came up 0.35 s
// later); a charger never configures anything.
static const uint32_t USB_WAIT_MS = 1500;
static const uint32_t USB_GONE_MS = 2000;

static const char *DEVICE_NAME = "NES Pad";

enum Path { PATH_NONE, PATH_USB, PATH_BLE };
static Path path = PATH_NONE;
static bool ble_started = false;   // the radio was brought up (or refused: see ble_refused)
static bool ble_refused = false;   // the P4's C6 did not answer; BLE is off for good this boot
static bool linked = false;        // a BLE host is connected
static bool force_ble = false;     // the mode switch at boot

static BLEHIDDevice *hid = nullptr;
static BLECharacteristic *input = nullptr;
static uint8_t pad1 = 0;
static uint8_t sent_usb[PAD_REPORT_LEN] = {0};
static uint8_t sent_ble[PAD_REPORT_LEN] = {0};
static uint32_t dropped_total = 0;
static uint32_t polls = 0;

static const char *path_name(Path p) {
  return p == PATH_USB ? "usb" : p == PATH_BLE ? "ble" : "none";
}

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
    Serial.println("# ble: linked");
  }
  void onDisconnect(BLEServer *s) override {
    linked = false;
    Serial.println("# ble: unlinked, advertising again");
    BLEDevice::startAdvertising();
  }
};

class Cccd : public BLEDescriptorCallbacks {
  void onWrite(BLEDescriptor *d) override {
    uint8_t *v = d->getValue();
    Serial.printf("# ble: host wrote the report CCCD: %02x %02x (01 00 = send me keys)\n", v[0], v[1]);
  }
};

class Delivery : public BLECharacteristicCallbacks {
  int last = -1;
  void onStatus(BLECharacteristic *c, Status st, uint32_t code) override {
    if ((int)st != last) {
      last = (int)st;
      Serial.printf("# ble: report delivery status %d code %lu (1 = sent, 3 = notify off, 6 = no subscriber)\n", (int)st, (unsigned long)code);
    }
  }
};

// The radio, exactly as firmware/pad-ble brings it up (the four things
// a phone wants are explained there), serving the UNNUMBERED
// descriptor. Returns false if it was refused rather than started.
static bool start_ble() {
#if CONFIG_IDF_TARGET_ESP32P4
  // Ask the C6 before trusting it. hostedInitWiFi brings the SDIO link
  // up and asks the co-processor its esp-hosted version; a C6 on the
  // factory firmware never answers (about 2.9 s), and the core then
  // leaves the version at 0.0.0. BLEDevice::init on that state is what
  // has crashed this board since 2026-09-25, so the version is read
  // here first and the radio refused on 0.0.0. "WiFi" is the name of
  // the entry point that does only the link; no Wi-Fi is used. The
  // later BLEDevice::init finds the link already up and adds the
  // controller to it, which is the ordinary second step.
  uint32_t hM, hm, hp, sM, sm, sp;
  hostedGetHostVersion(&hM, &hm, &hp);
  Serial.printf("# p4: asking the onboard C6 (host esp-hosted %lu.%lu.%lu)...\n", (unsigned long)hM, (unsigned long)hm, (unsigned long)hp);
  bool up = hostedInitWiFi();
  hostedGetSlaveVersion(&sM, &sm, &sp);
  Serial.printf("# p4: link %s, C6 esp-hosted %lu.%lu.%lu\n", up ? "up" : "DOWN", (unsigned long)sM, (unsigned long)sm, (unsigned long)sp);
  if (!up || (sM == 0 && sm == 0 && sp == 0)) {
    Serial.println("# ble: REFUSED. The C6 did not answer, so the radio stays off this boot.");
    Serial.println("# ble: firmware/p4-c6-update puts the matching slave firmware on it (docs/pad-build.md).");
    ble_refused = true;
    return false;
  }
#endif
  BLEDevice::init(DEVICE_NAME);
#if CONFIG_IDF_TARGET_ESP32P4
  // LEGACY PAIRING ON THE P4, MEASURED 2026-10-13. With secure
  // connections on, the Pi's radio trace (btmon) shows the whole SC
  // exchange run, both public keys, confirm, randoms, the Pi's DHKey
  // check sent, and then the PAD answering "Pairing Failed: DHKey
  // check failed (0x0b)": the P4's NimBLE host and the C6's controller
  // across the hosted link do not agree on the ECDH result. Three
  // attempts, the same byte. Legacy just-works pairing has no ECDH in
  // it, and is what this line asks for. Bonding stays on.
  BLESecurity::setAuthenticationMode(true, false, false);  // bonding, no MITM, LEGACY (no SC): see above
#else
  BLESecurity::setAuthenticationMode(true, false, true);  // bonding, no MITM, secure connections
#endif
  BLESecurity::setCapability(ESP_IO_CAP_NONE);
  BLESecurity::setKeySize(16);

  BLEServer *server = BLEDevice::createServer();
  server->setCallbacks(new Link());

  hid = new BLEHIDDevice(server);
  input = hid->inputReport(PAD_HID_REPORT_ID_BLE);
  input->setCallbacks(new Delivery());
  BLEDescriptor *cccd = input->getDescriptorByUUID(BLEUUID((uint16_t)0x2902));
  if (cccd) {
    cccd->setCallbacks(new Cccd());
  } else {
    // NimBLE (the P4's and the C6's stack) keeps the CCCD inside the
    // stack and hands out no descriptor object, so a host's subscribe
    // is not logged here; it still works. MEASURED 2026-10-12 on the
    // P4: this line printed and the pad advertised and was heard.
    Serial.println("# ble: the stack keeps the CCCD itself: a host's subscribe will not be logged");
  }
  hid->outputReport(PAD_HID_REPORT_ID_BLE);
  hid->manufacturer()->setValue("tinymachines");  // the no-argument form creates it; see pad-ble
  hid->pnp(0x02, 0x02E5, 0x0001, 0x0100);
  hid->hidInfo(0x00, 0x01);
  hid->reportMap((uint8_t *)PAD_HID_DESC_BLE, sizeof(PAD_HID_DESC_BLE));
  hid->setBatteryLevel(100);  // no gauge yet: say full
  hid->startServices();

  BLEAdvertising *adv = BLEDevice::getAdvertising();
  adv->setAppearance(HID_KEYBOARD);
  adv->addServiceUUID(hid->hidService()->getUUID());
  adv->setScanResponse(true);
  BLEDevice::startAdvertising();
  Serial.printf("# ble: advertising as \"%s\", %u descriptor bytes, no report ID\n", DEVICE_NAME, (unsigned)sizeof(PAD_HID_DESC_BLE));
  return true;
}

// Start the radio once, and set the path by what happened.
static void take_ble(const char *why) {
  if (!ble_started && !ble_refused) {
    ble_started = start_ble();
  }
  path = ble_started ? PATH_BLE : PATH_NONE;
  Serial.printf("# path: %s (%s)\n", path_name(path), why);
}

// ------------------------------------------------------------ commands
static void say_status() {
  Serial.printf("# pad %02x  path %s  usb %s  ble %s%s  polls %lu  dropped %lu\n", pad1, path_name(path),
                tud_mounted() ? "host configured" : "no host",
                ble_refused ? "refused" : !ble_started ? "off" : linked ? "linked" : "advertising",
                force_ble ? "  (switch: BLE forced)" : "",
                (unsigned long)polls, (unsigned long)dropped_total);
#if CONFIG_IDF_TARGET_ESP32P4
  uint32_t hM, hm, hp, sM, sm, sp;
  hostedGetHostVersion(&hM, &hm, &hp);
  hostedGetSlaveVersion(&sM, &sm, &sp);
  Serial.printf("# esp-hosted host %lu.%lu.%lu  C6 %lu.%lu.%lu%s\n", (unsigned long)hM, (unsigned long)hm, (unsigned long)hp,
                (unsigned long)sM, (unsigned long)sm, (unsigned long)sp, ble_started || ble_refused ? "" : " (not asked yet)");
#endif
}

static void say_keys() {
  for (int i = 0; i < 8; i++) {
    Serial.printf("# bit %d  %s\n", i, PAD_KEYS[i].name);
  }
}

static void forget() {
  if (!ble_started) {
    Serial.println("# the radio is not running: nothing stored here to clear this boot");
    return;
  }
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
  pinMode(MODE_SW, INPUT_PULLUP);
  pinMode(LED_PIN, OUTPUT);
  Serial.println("# nes-bench pad: an original pad as a keyboard, USB with a host, BLE without");
  say_keys();

  usb_start();
  force_ble = digitalRead(MODE_SW) == LOW;
  uint32_t t0 = millis();
  while (!force_ble && !tud_mounted() && millis() - t0 < USB_WAIT_MS) {
    delay(10);
  }
  if (force_ble) {
    take_ble("the mode switch is low");
  } else if (tud_mounted()) {
    path = PATH_USB;
    Serial.printf("# path: usb (host configured in %lu ms)\n", (unsigned long)(millis() - t0));
  } else {
    take_ble("no host configured the device in time");
  }
  Serial.println("# A byte prints on every CHANGE, not every poll.");
}

void loop() {
  static uint32_t last = 0;
  static uint8_t was1 = 0xFF;
  static bool was_mounted = false;
  static uint32_t gone_since = 0;

  // The live sink follows the host.
  bool mounted = tud_mounted();
  if (mounted != was_mounted) {
    was_mounted = mounted;
    Serial.println(mounted ? "# usb: host configured" : "# usb: host gone");
    gone_since = millis();
  }
  if (!force_ble) {
    if (mounted && path != PATH_USB) {
      path = PATH_USB;
      Serial.println("# path: usb (a host configured the device)");
    } else if (!mounted && path == PATH_USB && millis() - gone_since >= USB_GONE_MS) {
      take_ble("the host has been gone 2 s");
    }
  }

  // 1 kHz, the bridge's own pad rate: a press is never waiting on
  // this loop.
  if (millis() != last) {
    last = millis();
    pad1 = poll_pad();
  }

  if (pad1 != was1) {
    was1 = pad1;
    Serial.printf("B %02x %s\n", pad1, path_name(path));
    digitalWrite(LED_PIN, pad1 != 0);
  }

  uint8_t report[PAD_REPORT_LEN];
  int dropped = pad_report(pad1, report);
  if (path == PATH_USB) {
    // Only on a change, and only when the host has a buffer for it.
    if (memcmp(report, sent_usb, PAD_REPORT_LEN) != 0 && tud_hid_ready()) {
      memcpy(sent_usb, report, PAD_REPORT_LEN);
      tud_hid_report(PAD_HID_REPORT_ID_USB, report, PAD_REPORT_LEN);
      if (dropped) {
        dropped_total += dropped;
        Serial.printf("# %d key(s) did not fit six slots: pad %02x\n", dropped, pad1);
      }
    }
  } else if (path == PATH_BLE && linked && input) {
    if (memcmp(report, sent_ble, PAD_REPORT_LEN) != 0) {
      memcpy(sent_ble, report, PAD_REPORT_LEN);
      input->setValue(sent_ble, PAD_REPORT_LEN);
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
