// The bridge: an ESP32 between the console's controller port and an
// original pad (docs/wiring.md). The 74HCT165 on the board is the pad
// the console clocks; this sketch only writes its eight inputs between
// polls, counts the console's latch and clock pulses in hardware (the
// pulse counter peripheral, no interrupt in the path), polls the
// original pad on its own lines, and streams one line per latch:
//
//   L <latch index> <byte the register held> <clocks the poll took>
//
// the same line nes-console's pad-log example prints for the model, so
// tools/compare-logs.py diffs the two. Commands, one per line, over USB
// serial at 921600:
//
//   MODE PASS        the original pad's state goes to the register (default)
//   MODE INJECT      the register holds SET's byte, or the AT schedule's
//   SET hh           the byte to hold now (bit 0 = A, set = pressed)
//   AT n hh          from latch n on, hold hh (any number of these)
//   TRIG n           raise the trigger pin at latch n for a millisecond
//   RESET            zero the latch index, clear the schedule and the trigger
//   STATUS           one line: mode, latch index, byte, pad byte, schedule size
//
// Nothing here is measured yet: B0 of docs/bench-plan.md is where this
// meets the part. Built with arduino-cli and the esp32 core 3.x
// (Arduino as ESP-IDF's driver/pulse_cnt.h); the bench's board is an
// ESP32-C6-DevKitC-1: arduino-cli compile --fqbn esp32:esp32:esp32c6.

#include "driver/pulse_cnt.h"

// Pins, per docs/wiring.md. The board on the bench is an
// ESP32-C6-DevKitC-1 (RISC-V, GPIO0..23 on the headers; 8, 9 and 15 are
// strapping pins, 12 and 13 the USB port, 16 and 17 the UART port, all
// left alone), which leaves fourteen: exactly what the bridge needs
// once the D0 monitor is dropped. The classic ESP32 map stays for a
// board that has input-only pins.
#if CONFIG_IDF_TARGET_ESP32C6
// The register's inputs, H down to A: A, B, Select, Start, Up, Down,
// Left, Right (a 74HCT165 shifts H out first). Pressed is LOW.
static const int REG_PINS[8] = {18, 19, 20, 21, 22, 23, 10, 11};
// The console's lines through the 74LVC245.
static const int CON_LATCH = 0;  // OUT0, counted on its rise
static const int CON_CLOCK = 1;  // CLK (/OE1), counted on its fall
static const int CON_DATA = -1;  // not monitored on the C6 (no pin to spare)
// The original pad on the bridge's own lines, at 3.3 V.
static const int PAD_LATCH = 2;
static const int PAD_CLOCK = 3;
static const int PAD_DATA = 6;
// The scope's EXT TRIG.
static const int TRIG = 7;
#else
static const int REG_PINS[8] = {16, 17, 18, 19, 21, 22, 23, 25};
static const int CON_LATCH = 34; // input-only pins carry the console side
static const int CON_CLOCK = 35;
static const int CON_DATA = 36;  // D0 as the console sees it (reported by STATUS)
static const int PAD_LATCH = 26;
static const int PAD_CLOCK = 27;
static const int PAD_DATA = 32;
static const int TRIG = 33;
#endif

static const int PCNT_LIMIT = 32000;

static pcnt_unit_handle_t latch_unit = nullptr;
static pcnt_unit_handle_t clock_unit = nullptr;

enum Mode { PASS, INJECT };
static Mode mode = PASS;
static uint8_t held = 0;        // what the register's inputs show now
static uint8_t set_byte = 0;    // SET's byte for INJECT
static uint8_t pad_byte = 0;    // the original pad's last poll
static uint64_t latches = 0;    // the latch index (rises seen since RESET)
static uint64_t clocks = 0;     // clocks seen since RESET
static uint64_t clocks_at_latch = 0;
static uint8_t byte_at_latch = 0;
static bool have_latch = false;
static int last_latch_count = 0;
static int last_clock_count = 0;
static long trig_at = -1;
static unsigned long trig_until = 0;

struct At { uint64_t latch; uint8_t byte; };
static At schedule[256];
static int schedule_len = 0;

static pcnt_unit_handle_t make_unit(int pin, bool on_fall) {
  pcnt_unit_config_t unit_config = {};
  unit_config.high_limit = PCNT_LIMIT;
  unit_config.low_limit = -1;
  pcnt_unit_handle_t unit = nullptr;
  pcnt_new_unit(&unit_config, &unit);
  // 50 ns of glitch filter: the clock pulse is a few hundred ns wide.
  pcnt_glitch_filter_config_t filter = {};
  filter.max_glitch_ns = 50;
  pcnt_unit_set_glitch_filter(unit, &filter);
  pcnt_chan_config_t chan_config = {};
  chan_config.edge_gpio_num = pin;
  chan_config.level_gpio_num = -1;
  pcnt_channel_handle_t chan = nullptr;
  pcnt_new_channel(unit, &chan_config, &chan);
  if (on_fall) {
    pcnt_channel_set_edge_action(chan, PCNT_CHANNEL_EDGE_ACTION_HOLD, PCNT_CHANNEL_EDGE_ACTION_INCREASE);
  } else {
    pcnt_channel_set_edge_action(chan, PCNT_CHANNEL_EDGE_ACTION_INCREASE, PCNT_CHANNEL_EDGE_ACTION_HOLD);
  }
  pcnt_unit_enable(unit);
  pcnt_unit_clear_count(unit);
  pcnt_unit_start(unit);
  return unit;
}

static int delta(pcnt_unit_handle_t unit, int &last) {
  int now = 0;
  pcnt_unit_get_count(unit, &now);
  int d = now - last;
  if (d < 0) d += PCNT_LIMIT;
  last = now;
  return d;
}

static void write_register(uint8_t b) {
  for (int i = 0; i < 8; i++) {
    // Pressed is a set bit here and a LOW on the register.
    digitalWrite(REG_PINS[i], (b >> i) & 1 ? LOW : HIGH);
  }
  held = b;
}

// The original pad, polled the way the console polls it, at leisure.
static uint8_t poll_pad() {
  digitalWrite(PAD_LATCH, HIGH);
  delayMicroseconds(12);
  digitalWrite(PAD_LATCH, LOW);
  delayMicroseconds(6);
  uint8_t b = 0;
  for (int i = 0; i < 8; i++) {
    if (digitalRead(PAD_DATA) == LOW) b |= 1 << i;
    digitalWrite(PAD_CLOCK, HIGH);
    delayMicroseconds(6);
    digitalWrite(PAD_CLOCK, LOW);
    delayMicroseconds(6);
  }
  return b;
}

static uint8_t scheduled_byte() {
  uint8_t b = set_byte;
  for (int i = 0; i < schedule_len; i++) {
    if (schedule[i].latch <= latches) b = schedule[i].byte;
  }
  return b;
}

static void handle(String line) {
  line.trim();
  if (line == "MODE PASS") { mode = PASS; Serial.println("# mode pass"); }
  else if (line == "MODE INJECT") { mode = INJECT; Serial.println("# mode inject"); }
  else if (line.startsWith("SET ")) { set_byte = strtoul(line.c_str() + 4, nullptr, 16); Serial.printf("# set %02x\n", set_byte); }
  else if (line.startsWith("AT ")) {
    char *end;
    unsigned long n = strtoul(line.c_str() + 3, &end, 10);
    unsigned long b = strtoul(end, nullptr, 16);
    if (schedule_len < 256) { schedule[schedule_len++] = { (uint64_t)n, (uint8_t)b }; Serial.printf("# at %lu %02lx\n", n, b); }
    else Serial.println("# schedule full");
  }
  else if (line.startsWith("TRIG ")) { trig_at = strtol(line.c_str() + 5, nullptr, 10); Serial.printf("# trig at %ld\n", trig_at); }
  else if (line == "RESET") {
    latches = 0; clocks = 0; have_latch = false; schedule_len = 0; trig_at = -1;
    pcnt_unit_clear_count(latch_unit); pcnt_unit_clear_count(clock_unit);
    last_latch_count = 0; last_clock_count = 0;
    Serial.println("# reset");
  }
  else if (line == "STATUS") {
    Serial.printf("# mode %s latch %llu clocks %llu held %02x pad %02x schedule %d data %d\n",
                  mode == PASS ? "pass" : "inject", latches, clocks, held, pad_byte, schedule_len, CON_DATA >= 0 ? digitalRead(CON_DATA) : -1);
  }
  else if (line.length()) Serial.println("# ? " + line);
}

void setup() {
  Serial.begin(921600);
  for (int i = 0; i < 8; i++) pinMode(REG_PINS[i], OUTPUT);
  write_register(0);
  pinMode(CON_LATCH, INPUT);
  pinMode(CON_CLOCK, INPUT);
  if (CON_DATA >= 0) pinMode(CON_DATA, INPUT);
  pinMode(PAD_LATCH, OUTPUT);
  pinMode(PAD_CLOCK, OUTPUT);
  pinMode(PAD_DATA, INPUT_PULLUP);
  pinMode(TRIG, OUTPUT);
  digitalWrite(TRIG, LOW);
  latch_unit = make_unit(CON_LATCH, false);
  clock_unit = make_unit(CON_CLOCK, true);
  Serial.println("# nes-bench bridge: B0 sniff; MODE PASS");
}

void loop() {
  static unsigned long last_pad_poll = 0;
  static String line;
  // Commands.
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') { handle(line); line = ""; }
    else if (c != '\r') line += c;
  }
  // The original pad, once a millisecond.
  unsigned long now = micros();
  if (now - last_pad_poll >= 1000) {
    last_pad_poll = now;
    pad_byte = poll_pad();
  }
  // What the register should hold.
  uint8_t want = mode == PASS ? pad_byte : scheduled_byte();
  if (want != held) write_register(want);
  // The console's pulses.
  int dl = delta(latch_unit, last_latch_count);
  int dc = delta(clock_unit, last_clock_count);
  clocks += dc;
  if (dl > 0) {
    // A latch closes the previous poll: its line carries the byte the
    // register held at that latch and the clocks since it. More than
    // one latch in one look (100 us apart at most) is reported as such.
    if (have_latch) {
      Serial.printf("L %llu %02x %llu\n", latches - 1, byte_at_latch, clocks - clocks_at_latch);
    }
    if (dl > 1) Serial.printf("# %d latches in one look at %llu\n", dl, latches);
    latches += dl;
    clocks_at_latch = clocks;
    byte_at_latch = held;
    have_latch = true;
    if (trig_at >= 0 && (uint64_t)trig_at < latches) {
      digitalWrite(TRIG, HIGH);
      trig_until = millis() + 1;
      trig_at = -1;
      Serial.printf("# trigger at latch %llu\n", latches - 1);
    }
  }
  if (trig_until && millis() >= trig_until) { digitalWrite(TRIG, LOW); trig_until = 0; }
  delayMicroseconds(100);
}
