// p4-c6-update: put the esp-hosted slave firmware the Arduino core
// expects onto the ESP32-P4 module's onboard ESP32-C6, over the SDIO
// link the two already share. Run once; then firmware/pad's BLE path
// (and anything else that wants the radio) has a co-processor that
// answers.
//
// WHY. The P4 die has no radio. On the Waveshare ESP32-P4-Module the
// radio is an ESP32-C6 reached over SDIO, and the P4 side (esp-hosted
// 2.12.11 in arduino-esp32 3.3.11) asks it for its firmware version at
// init. The C6 the module shipped with runs an older slave build that
// does not know that request, so it never answers:
//
//     E rpc_core: Response not received for [0x15e](Req_GetCoprocessorFwVersion)
//
// and the host then reports the co-processor as 0.0.0 and, in the BLE
// init path, read a bad pointer 2881 ms later on every try since
// 2026-09-25. Other people with Waveshare P4 boards hit the identical
// line on the identical versions; the fix on every report is the
// matching slave image on the C6.
//
// THE IMAGE IS NOT TYPED HERE. The core itself names the file it wants:
// esp32-hal-hosted.c builds the URL
//   https://espressif.github.io/arduino-esp32/hosted/<target>-v<host version>.bin
// and the core's own ESP_HostedOTA library would fetch it, over Wi-Fi,
// through the very C6 that cannot answer. So tools/fetch-c6-image.py
// reads the host version out of the installed core, fetches that file,
// checks its SHA-256 against the one recorded in the script, and writes
// it into this sketch as c6_image.c (generated, not committed). This
// sketch then pushes those bytes through the same four calls the core's
// OTA path uses, with no network in the loop.
//
// WHAT CAN GO WRONG, AND HOW IT SAYS SO. The OTA request is itself an
// RPC. A slave old enough to miss the version request may miss the OTA
// requests too (one Waveshare report says theirs did: in-band OTA
// failed and the C6 was flashed over its UART header instead). This
// sketch tries the in-band way first because it needs no wiring, and
// every step prints its verdict; a refusal at "begin" is the signal to
// use header P2 instead, which docs/pad-build.md walks through.
//
// BUILD. The image is 1.2 MB of flash alongside the sketch, which the
// pad builds' 2 MB app partition does not hold with the hosted libraries:
//
//   python3 tools/fetch-c6-image.py
//   arduino-cli compile --fqbn "esp32:esp32:esp32p4:FlashSize=16M,PartitionScheme=app3M_fat9M_16MB,PSRAM=enabled" \
//       --export-binaries firmware/p4-c6-update
//   arduino-cli upload  --fqbn "esp32:esp32:esp32p4:FlashSize=16M,PartitionScheme=app3M_fat9M_16MB,PSRAM=enabled" \
//       -p /dev/ttyACMx firmware/p4-c6-update
//
// over the socket marked "PWR USB TO UART", which is also where this
// prints. Afterwards flash firmware/pad (or pad-usb) back the same way.
//
// Serial commands: AGAIN (run the update once more), VERSION (ask the
// C6 again), RESET (restart the P4).

#include "sdkconfig.h"
#if !CONFIG_IDF_TARGET_ESP32P4 || !CONFIG_ESP_HOSTED_ENABLED
#error "p4-c6-update is for the ESP32-P4 with its hosted ESP32-C6"
#endif
#include "esp32-hal-hosted.h"

extern "C" {
extern const uint8_t c6_image[];
extern const uint32_t c6_image_len;
extern const char c6_image_name[];
extern const char c6_image_sha256[];
}

static bool link_up = false;

static void versions(uint32_t *sM, uint32_t *sm, uint32_t *sp) {
  uint32_t hM, hm, hp;
  hostedGetHostVersion(&hM, &hm, &hp);
  hostedGetSlaveVersion(sM, sm, sp);
  Serial.printf("# esp-hosted host %lu.%lu.%lu  C6 %lu.%lu.%lu\n", (unsigned long)hM, (unsigned long)hm, (unsigned long)hp,
                (unsigned long)*sM, (unsigned long)*sm, (unsigned long)*sp);
}

static void update() {
  uint32_t sM, sm, sp;
  if (!link_up) {
    Serial.println("# bringing the SDIO link up (a C6 on the factory firmware takes about 3 s to not answer)...");
    link_up = hostedInitWiFi();  // the link only; no Wi-Fi is used
    Serial.printf("# link: %s\n", link_up ? "up" : "DOWN");
    if (!link_up) {
      Serial.println("# the link itself failed: nothing to update over. Header P2 (docs/pad-build.md).");
      return;
    }
  }
  versions(&sM, &sm, &sp);
  if (sM == 0 && sm == 0 && sp == 0) {
    Serial.println("# the C6 did not say its version: that is the factory firmware, as expected. Trying the OTA requests anyway.");
  }
  Serial.printf("# image %s, %lu bytes, sha256 %s\n", c6_image_name, (unsigned long)c6_image_len, c6_image_sha256);

  Serial.println("# begin...");
  if (!hostedBeginUpdate()) {
    Serial.println("# REFUSED at begin: the C6's firmware does not answer the OTA request either.");
    Serial.println("# Flash it over header P2 instead: docs/pad-build.md, 'The C6 over its UART'.");
    return;
  }
  Serial.println("# begin: accepted. Writing in 2 KB pieces, a dot per 32 KB:");
  const uint32_t piece = 2048;
  uint32_t done = 0;
  while (done < c6_image_len) {
    uint32_t n = c6_image_len - done < piece ? c6_image_len - done : piece;
    if (!hostedWriteUpdate((uint8_t *)(c6_image + done), n)) {
      Serial.printf("\n# FAILED at byte %lu of %lu.\n", (unsigned long)done, (unsigned long)c6_image_len);
      return;
    }
    done += n;
    if (done % (32 * 1024) < piece) {
      Serial.print(".");
    }
  }
  Serial.printf("\n# written %lu bytes. end...\n", (unsigned long)done);
  if (!hostedEndUpdate()) {
    Serial.println("# FAILED at end: the C6 did not accept the image.");
    return;
  }
  Serial.println("# end: accepted. activate...");
  bool act = hostedActivateUpdate();
  Serial.printf("# activate: %s\n", act ? "accepted (the C6 restarts into the new image)" : "FAILED");
  Serial.println("# POWER-CYCLE the board now, then run this sketch's VERSION (or firmware/pad's STATUS) to read the C6's version.");
}

void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println("# nes-bench p4-c6-update: the esp-hosted slave image onto the onboard C6");
  update();
}

void loop() {
  if (Serial.available()) {
    String line = Serial.readStringUntil('\n');
    line.trim();
    line.toUpperCase();
    if (line == "AGAIN") {
      update();
    } else if (line == "VERSION") {
      uint32_t sM, sm, sp;
      if (!link_up) {
        link_up = hostedInitWiFi();
      }
      versions(&sM, &sm, &sp);
    } else if (line == "RESET") {
      ESP.restart();
    } else if (line.length()) {
      Serial.printf("# unknown command %s (AGAIN, VERSION, RESET)\n", line.c_str());
    }
  }
}
