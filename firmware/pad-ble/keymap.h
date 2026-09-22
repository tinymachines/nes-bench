// The pad byte as a HID keyboard report, and the report descriptor that
// tells a host how to read it. Plain C, no Arduino: the two things in
// here are pure data and a pure function, so tools/test-pad-keymap.sh
// compiles this same header natively and exercises it on the desk,
// exactly as tools/test-uno-schedule.cpp does for the UNO's schedule.
//
// That split is the point. The radio, the pairing and the pad's own
// timing cannot be tested without the part in the room; the descriptor
// and the mapping can, and they are where a silent wrong answer would
// live. A malformed descriptor does not fail to compile and does not
// fail to pair: it pairs, and then every key is the wrong key.
//
// KEYMAP_MUTATE builds two plausible bugs into this file, and
// tools/test-pad-keymap.sh must go red on it. Both are mistakes
// somebody makes rather than random corruption: a key slot index that
// forgets the two leading bytes, and a descriptor whose slot count
// stops matching the code's.
#pragma once
#include <stdint.h>

#define PAD_HID_REPORT_ID 1
#define PAD_REPORT_LEN 8
#define PAD_KEY_SLOTS 6

// The count the DESCRIPTOR promises, which must equal the number of
// slots the code fills. Two numbers that have to agree while living
// thirty lines apart is the shape of bug the desk test exists for.
#ifdef KEYMAP_MUTATE
#define PAD_KEY_SLOTS_DECLARED 5
#else
#define PAD_KEY_SLOTS_DECLARED PAD_KEY_SLOTS
#endif

// ---------------------------------------------------------------- report
// A boot-protocol keyboard, report ID 1: one modifier byte, one reserved
// byte, six key slots. This is the shape every host has accepted since
// USB 1.1 and it is deliberately not a clever one.
//
// The LED output report is here because a keyboard that declares no
// output report is a slightly unusual keyboard, and the goal is a host
// accepting this with no driver and no app. Nothing drives an LED at
// this end; the report is declared and its writes are ignored.
static const uint8_t PAD_HID_DESC[] = {
    0x05, 0x01,                    // Usage Page (Generic Desktop)
    0x09, 0x06,                    // Usage (Keyboard)
    0xA1, 0x01,                    // Collection (Application)
    0x85, PAD_HID_REPORT_ID,       //   Report ID (1)
    0x05, 0x07,                    //   Usage Page (Keyboard/Keypad)
    0x19, 0xE0,                    //   Usage Minimum (224, Left Control)
    0x29, 0xE7,                    //   Usage Maximum (231, Right GUI)
    0x15, 0x00,                    //   Logical Minimum (0)
    0x25, 0x01,                    //   Logical Maximum (1)
    0x75, 0x01,                    //   Report Size (1)
    0x95, 0x08,                    //   Report Count (8)
    0x81, 0x02,                    //   Input (Data, Var, Abs): the eight modifiers
    0x95, 0x01,                    //   Report Count (1)
    0x75, 0x08,                    //   Report Size (8)
    0x81, 0x03,                    //   Input (Const): the reserved byte
    0x95, 0x05,                    //   Report Count (5)
    0x75, 0x01,                    //   Report Size (1)
    0x05, 0x08,                    //   Usage Page (LEDs)
    0x19, 0x01,                    //   Usage Minimum (1, Num Lock)
    0x29, 0x05,                    //   Usage Maximum (5, Kana)
    0x91, 0x02,                    //   Output (Data, Var, Abs): five LEDs
    0x95, 0x01,                    //   Report Count (1)
    0x75, 0x03,                    //   Report Size (3)
    0x91, 0x03,                    //   Output (Const): pad the LED byte to eight bits
    0x95, PAD_KEY_SLOTS_DECLARED,  //   Report Count (6): the key slots
    0x75, 0x08,                    //   Report Size (8)
    0x15, 0x00,                    //   Logical Minimum (0)
    0x25, 0x65,                    //   Logical Maximum (101)
    0x05, 0x07,                    //   Usage Page (Keyboard/Keypad)
    0x19, 0x00,                    //   Usage Minimum (0)
    0x29, 0x65,                    //   Usage Maximum (101)
    0x81, 0x00,                    //   Input (Data, Array): the key slots
    0xC0                           // End Collection
};

// ------------------------------------------------------------- the eight
// AUTHORED, not measured, and the same choice docs/pad-adapter.svg
// states: A is x, B is z, Select is right shift, Start is enter, the
// d-pad is the arrows. It is the layout browser emulators default to,
// which is the whole reason keyboard mode exists.
//
// The index is the bit in the pad byte, and that order is not decided
// here either: it is nes_glue::controller::Buttons::as_byte, bit 0 A
// through bit 7 Right. tools/check-pad.py holds head/pad.py to the same
// Rust; tools/test-pad-keymap.cpp holds this table's order to the names.
//
// `mod` is a modifier mask and `key` a usage code, and exactly one of
// them is set per entry. Select is a modifier because right shift IS a
// modifier: putting usage 0xE5 in a key slot would send it, but a host
// that tracks modifier state separately would then see shift held in a
// way no keyboard produces.
typedef struct {
  uint8_t mod;
  uint8_t key;
  const char *name;
} PadKey;

static const PadKey PAD_KEYS[8] = {
    {0x00, 0x1B, "A = x"},
    {0x00, 0x1D, "B = z"},
    {0x20, 0x00, "Select = right shift"},
    {0x00, 0x28, "Start = enter"},
    {0x00, 0x52, "Up = up arrow"},
    {0x00, 0x51, "Down = down arrow"},
    {0x00, 0x50, "Left = left arrow"},
    {0x00, 0x4F, "Right = right arrow"},
};

// The pad byte (bit set = pressed) as one eight-byte report. Returns the
// number of keys that did not fit.
//
// Six slots against eight buttons, so an overflow is arithmetically
// possible and is therefore counted rather than trusted away. In
// practice one modifier and a d-pad that cannot close opposite contacts
// leave at most five keys, but "in practice" is not a bound: a pad with
// a shorted d-pad membrane would present six directions, and a caller
// that ignored the return would send a report quietly missing whichever
// button the loop reached last.
static inline int pad_report(uint8_t pad, uint8_t out[PAD_REPORT_LEN]) {
  int n = 0, dropped = 0;
  for (int i = 0; i < PAD_REPORT_LEN; i++) {
    out[i] = 0;
  }
  for (int i = 0; i < 8; i++) {
    if (!((pad >> i) & 1)) {
      continue;
    }
    if (PAD_KEYS[i].mod) {
      out[0] |= PAD_KEYS[i].mod;
    } else if (n < PAD_KEY_SLOTS) {
#ifdef KEYMAP_MUTATE
      out[n++] = PAD_KEYS[i].key;  // the mutation: slots counted from byte 0, over the modifier
#else
      out[2 + n++] = PAD_KEYS[i].key;
#endif
    } else {
      dropped++;
    }
  }
  return dropped;
}
