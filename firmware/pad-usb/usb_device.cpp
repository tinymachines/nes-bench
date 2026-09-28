// The USB half of pad-usb: descriptors, the six callbacks TinyUSB asks
// the application for, and bringing the full-speed controller up. In a
// .cpp of its own because the Arduino preprocessor rewrites C-linkage
// declarations in a .ino; see pad-usb.ino for why this build drives
// TinyUSB directly instead of through the core's USB classes.

#include <Arduino.h>
#include "tusb.h"
#include "esp_private/usb_phy.h"
#include "hal/usb_wrap_ll.h"
#include "keymap.h"
#include "usb_device.h"

// ------------------------------------------------------------ descriptors
// Espressif's VID and the PID its own TinyUSB examples use, so the
// device reads as what it is: an ESP32 running TinyUSB. The strings say
// which one.
static const tusb_desc_device_t DEVICE_DESC = {
    .bLength = sizeof(tusb_desc_device_t),
    .bDescriptorType = TUSB_DESC_DEVICE,
    .bcdUSB = 0x0200,
    .bDeviceClass = 0x00,  // -- the class is per interface
    .bDeviceSubClass = 0x00,
    .bDeviceProtocol = 0x00,
    .bMaxPacketSize0 = CFG_TUD_ENDPOINT0_SIZE,
    .idVendor = 0x303A,
    .idProduct = 0x0002,
    .bcdDevice = 0x0100,
    .iManufacturer = 1,
    .iProduct = 2,
    .iSerialNumber = 3,
    .bNumConfigurations = 1,
};

// One interface, one interrupt IN endpoint. 16 bytes holds the nine a
// report takes with its ID in front; full speed allows up to 64. The
// interval is in frames of 1 ms at full speed. The keyboard's LED
// output report comes over the control pipe, so no OUT endpoint.
#define EP_IN 0x81
#define EP_SIZE 16
#define EP_INTERVAL_MS 1
#define CONFIG_LEN (TUD_CONFIG_DESC_LEN + TUD_HID_DESC_LEN)
static const uint8_t CONFIG_DESC[] = {
    TUD_CONFIG_DESCRIPTOR(1, 1, 0, CONFIG_LEN, TUSB_DESC_CONFIG_ATT_REMOTE_WAKEUP, 100),
    TUD_HID_DESCRIPTOR(0, 0, HID_ITF_PROTOCOL_NONE, sizeof(PAD_HID_DESC), EP_IN, EP_SIZE, EP_INTERVAL_MS),
};

static const char *STRINGS[] = {"tinymachines", "NES Pad", "nes-bench pad-usb"};

// ------------------------------------------------------------- callbacks
// The six TinyUSB asks for. Defining them here is also what keeps the
// core's own USB wrapper out of the link, since it is only pulled in to
// supply them.
extern "C" {

uint8_t const *tud_descriptor_device_cb(void) {
  return (uint8_t const *)&DEVICE_DESC;
}

uint8_t const *tud_descriptor_configuration_cb(uint8_t index) {
  (void)index;
  return CONFIG_DESC;
}

uint16_t const *tud_descriptor_string_cb(uint8_t index, uint16_t langid) {
  (void)langid;
  static uint16_t buf[32];
  uint8_t n;
  if (index == 0) {
    buf[1] = 0x0409;  // -- English (US), the one language offered
    n = 1;
  } else {
    if (index > sizeof(STRINGS) / sizeof(STRINGS[0])) {
      return NULL;
    }
    const char *s = STRINGS[index - 1];
    for (n = 0; s[n] && n < 31; n++) {
      buf[1 + n] = s[n];
    }
  }
  buf[0] = (uint16_t)((TUSB_DESC_STRING << 8) | (2 * n + 2));
  return buf;
}

// The same bytes the BLE build serves, out of the same header.
uint8_t const *tud_hid_descriptor_report_cb(uint8_t instance) {
  (void)instance;
  return PAD_HID_DESC;
}

// A host may poll a report over the control pipe; this answers with an
// empty one rather than stalling.
uint16_t tud_hid_get_report_cb(uint8_t instance, uint8_t report_id, hid_report_type_t type,
                               uint8_t *buffer, uint16_t reqlen) {
  (void)instance;
  (void)report_id;
  (void)type;
  uint16_t n = reqlen < PAD_REPORT_LEN ? reqlen : PAD_REPORT_LEN;
  memset(buffer, 0, n);
  return n;
}

// The LED report. Declared by the descriptor, driven by nothing here.
void tud_hid_set_report_cb(uint8_t instance, uint8_t report_id, hid_report_type_t type,
                           uint8_t const *buffer, uint16_t bufsize) {
  (void)instance;
  (void)report_id;
  (void)type;
  (void)buffer;
  (void)bufsize;
}

}  // extern "C"

static void usb_task(void *) {
  for (;;) {
    tud_task();
  }
}

void usb_start() {
  // The full-speed PHY, taken from the USB-Serial-JTAG and given to the
  // OTG controller, as a device. Both results are printed: a refusal
  // here is the whole answer to "why does the host see nothing".
  usb_phy_config_t phy = {};
  phy.controller = USB_PHY_CTRL_OTG;
  phy.target = USB_PHY_TARGET_INT;
  phy.otg_mode = USB_OTG_MODE_DEVICE;
  phy.otg_speed = USB_PHY_SPEED_FULL;
  static usb_phy_handle_t phy_handle;
  esp_err_t e = usb_new_phy(&phy, &phy_handle);
  Serial.printf("# usb phy: %s\n", esp_err_to_name(e));
  // The P4 has TWO full-speed PHYs. By default the USB-Serial-JTAG has
  // PHY 0, which is GPIO24/25 and so the socket marked USB, and the OTG
  // controller has PHY 1 (GPIO26/27, not wired to a socket on this kit).
  // usb_new_phy above left that mapping alone: MEASURED 2026-09-27, it
  // returned ESP_OK, TinyUSB started, and the host still saw the
  // debug unit. One bit in LP_SYS swaps them.
  usb_wrap_ll_phy_select(&USB_WRAP, 0);
  Serial.println("# full-speed PHY 0 (GPIO24/25) swapped to the OTG controller");

  tusb_rhport_init_t init = {};
  init.role = TUSB_ROLE_DEVICE;
  init.speed = TUSB_SPEED_FULL;
  bool ok = tusb_rhport_init(0, &init);
  Serial.printf("# tinyusb on port 0: %s\n", ok ? "started" : "REFUSED");
  xTaskCreate(usb_task, "usbd", 4096, NULL, configMAX_PRIORITIES - 1, NULL);
}
