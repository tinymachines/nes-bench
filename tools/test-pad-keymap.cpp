// The pad-to-keyboard mapping and its HID report descriptor, checked
// natively. Built by tools/test-pad-keymap.sh; its -DKEYMAP_MUTATE
// build must fail.
//
// Why this is worth a native test when the firmware it belongs to has
// never met a pad: everything else in firmware/pad-ble needs the part,
// but these two are pure. And they are the pair most likely to be
// wrong in a way nothing reports. A bad descriptor still pairs. A bad
// mapping still types. The host believes whatever it is told about the
// shape of the report, so the only thing that can catch a descriptor
// disagreeing with the code that fills it is a reader that walks both.
//
// So the descriptor is not compared against a copy of itself. It is
// PARSED, as a host parses it, and what the parse says about the
// report's size is compared with what pad_report actually writes.
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
#include "../firmware/pad-ble/keymap.h"

static int fails = 0;
static int oks = 0;

static void ok(bool cond, const std::string &why) {
  if (cond) {
    oks++;
  } else {
    fails++;
    printf("FAIL %s\n", why.c_str());
  }
}

// ------------------------------------------------- the descriptor, parsed
// A HID item is a prefix byte plus 0, 1, 2 or 4 data bytes: the low two
// bits give the size (3 meaning 4), bits 2 and 3 the type, the top four
// the tag. This walks the items the way a host does and adds up what
// each Input and Output actually declares.
struct Parsed {
  int input_bits = 0;
  int output_bits = 0;
  int report_id = -1;
  int depth = 0, max_depth = 0, collections = 0;
  int key_slots = -1;     // Report Count in force at the array Input
  int key_slot_size = -1; // Report Size there
  bool balanced = false;
  bool ok = true;
  std::string why;
};

static Parsed parse(const uint8_t *d, size_t n) {
  Parsed p;
  size_t i = 0;
  int size = 0, count = 0;
  while (i < n) {
    uint8_t prefix = d[i];
    int bsize = prefix & 0x03;
    if (bsize == 3) {
      bsize = 4;
    }
    uint8_t tag = prefix & 0xFC;
    if (i + 1 + bsize > n) {
      p.ok = false;
      p.why = "an item's data runs off the end of the descriptor";
      return p;
    }
    uint32_t v = 0;
    for (int k = 0; k < bsize; k++) {
      v |= (uint32_t)d[i + 1 + k] << (8 * k);
    }
    switch (tag) {
      case 0x84: p.report_id = (int)v; break;              // Report ID
      case 0x74: size = (int)v; break;                     // Report Size
      case 0x94: count = (int)v; break;                    // Report Count
      case 0x80:                                           // Input
        p.input_bits += size * count;
        // The array Input (not a bitfield): Report Size 8 is the key
        // slots. The modifier Input is size 1, the reserved byte is
        // count 1, so this picks out the one that carries keycodes.
        if (size == 8 && count > 1) {
          p.key_slots = count;
          p.key_slot_size = size;
        }
        break;
      case 0x90: p.output_bits += size * count; break;      // Output
      case 0xA0: p.depth++; p.collections++;                // Collection
        if (p.depth > p.max_depth) p.max_depth = p.depth;
        break;
      case 0xC0: p.depth--; break;                          // End Collection
      default: break;
    }
    i += 1 + bsize;
  }
  p.balanced = (p.depth == 0);
  return p;
}

// ------------------------------------------------------------------ main
int main() {
  Parsed p = parse(PAD_HID_DESC, sizeof(PAD_HID_DESC));
  ok(p.ok, "the descriptor did not parse: " + p.why);
  ok(p.balanced, "the descriptor's collections are not balanced");
  ok(p.collections == 1, "the descriptor opens " + std::to_string(p.collections) + " collections, want 1");
  ok(p.report_id == PAD_HID_REPORT_ID,
     "the descriptor declares report ID " + std::to_string(p.report_id) + ", the code sends "
         + std::to_string(PAD_HID_REPORT_ID));

  // The one that matters: what the host will believe about the report's
  // size, against the buffer the firmware actually notifies.
  ok(p.input_bits == PAD_REPORT_LEN * 8,
     "the descriptor declares " + std::to_string(p.input_bits) + " input bits, the code sends "
         + std::to_string(PAD_REPORT_LEN * 8) + " (a host reads the descriptor, not the buffer)");
  ok(p.output_bits % 8 == 0 && p.output_bits == 8,
     "the output report is " + std::to_string(p.output_bits) + " bits, want 8");
  ok(p.key_slots == PAD_KEY_SLOTS,
     "the descriptor promises " + std::to_string(p.key_slots) + " key slots, the code fills up to "
         + std::to_string(PAD_KEY_SLOTS));

  // ------------------------------------------------------- the table
  static const char *order[8] = {"A", "B", "Select", "Start", "Up", "Down", "Left", "Right"};
  for (int i = 0; i < 8; i++) {
    std::string name = PAD_KEYS[i].name ? PAD_KEYS[i].name : "";
    ok(name.rfind(order[i], 0) == 0,
       "bit " + std::to_string(i) + " is named '" + name + "', and Buttons::as_byte puts " + order[i] + " there");
    ok((PAD_KEYS[i].mod != 0) != (PAD_KEYS[i].key != 0),
       "bit " + std::to_string(i) + " sets both a modifier and a key, or neither");
  }

  // Every key distinct, or two buttons are one button.
  for (int i = 0; i < 8; i++) {
    for (int j = i + 1; j < 8; j++) {
      bool same = PAD_KEYS[i].key && PAD_KEYS[i].key == PAD_KEYS[j].key;
      ok(!same, "bits " + std::to_string(i) + " and " + std::to_string(j) + " send the same usage code");
    }
  }

  // ------------------------------------------------------ the reports
  uint8_t r[PAD_REPORT_LEN];

  ok(pad_report(0x00, r) == 0 && r[0] == 0 && r[2] == 0, "nothing pressed is not an empty report");

  // Each button alone, where it must land.
  for (int i = 0; i < 8; i++) {
    pad_report(1 << i, r);
    if (PAD_KEYS[i].mod) {
      ok(r[0] == PAD_KEYS[i].mod && r[2] == 0,
         std::string(order[i]) + " alone should be a modifier and no key slot");
    } else {
      ok(r[0] == 0 && r[2] == PAD_KEYS[i].key,
         std::string(order[i]) + " alone should put its usage in the first key slot with no modifier");
    }
    ok(r[1] == 0, "the reserved byte is not zero after " + std::string(order[i]));
  }

  // A real hand: running right and jumping. Two keys, no modifier.
  pad_report((1 << 0) | (1 << 7), r);
  ok(r[0] == 0 && ((r[2] == 0x1B && r[3] == 0x4F) || (r[2] == 0x4F && r[3] == 0x1B)),
     "A and Right should be two key slots and nothing else");

  // Select is a modifier, so it must not consume a slot that a key
  // needs. Five keys plus Select still fits.
  pad_report((1 << 0) | (1 << 1) | (1 << 2) | (1 << 3) | (1 << 4) | (1 << 6), r);
  int used = 0;
  for (int i = 2; i < PAD_REPORT_LEN; i++) {
    if (r[i]) used++;
  }
  ok(r[0] == 0x20, "Select in a crowded report did not reach the modifier byte");
  ok(used == 5, "five keys plus Select should use five slots, used " + std::to_string(used));

  // All eight at once: a pad cannot do it, so this is the bound, not a
  // scenario. Seven keys into six slots must report one dropped and
  // must not write past the report.
  uint8_t guard[PAD_REPORT_LEN + 4];
  memset(guard, 0xAA, sizeof(guard));
  int dropped = pad_report(0xFF, guard);
  ok(dropped == 1, "eight buttons is seven keys into six slots: want 1 dropped, got " + std::to_string(dropped));
  for (size_t i = PAD_REPORT_LEN; i < sizeof(guard); i++) {
    ok(guard[i] == 0xAA, "pad_report wrote past the end of the report");
  }

  printf("\n%d check(s) agree, %d disagree.\n", oks, fails);
  return fails ? 1 : 0;
}
