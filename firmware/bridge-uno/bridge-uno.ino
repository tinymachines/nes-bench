// The bridge, v1b: an Arduino UNO between the console's controller port
// and an original pad (docs/bench-v1b-uno.md, docs/bench-v1b.svg). The
// ATmega328P is a 5 V part, so the console, the register and the pad
// all sit in one voltage domain and no level shifter exists on the
// board. That is the whole reason this version is built before the
// ESP32-C6 one in firmware/bridge/: the 74HC parts that arrived need a
// 3.5 V high at 5 V, which a 3.3 V GPIO does not give.
//
// The line protocol is byte-for-byte the C6's (docs/script.md), so
// head/headd.py and every tool need nothing but the serial speed:
//
//   L <latch index> <byte the register held> <clocks the poll took>
//
//   MODE PASS        the original pad's state goes to the register (default)
//   MODE INJECT      the register holds SET's byte, or the AT schedule's
//   SET hh           the byte to hold now (bit 0 = A, set = pressed)
//   AT n hh          from latch n on, hold hh (in increasing n; see below)
//   TRIG n           raise the trigger pin at latch n for a millisecond
//   RESET            zero the latch index, clear the schedule and the trigger
//   STATUS           one line: mode, latch index, byte, pad byte, schedule size
//   MUTATE ON|OFF    the clock counter is fed the LATCH line: the
//                    clocks-per-latch check must go red (B0's mutation)
//
// Nothing here is measured yet: B0 of docs/bench-plan.md is where this
// meets the part. Build:
//
//   arduino-cli compile --fqbn arduino:avr:uno firmware/bridge-uno
//   arduino-cli upload  --fqbn arduino:avr:uno -p /dev/ttyACM0 firmware/bridge-uno
//
// THREE THINGS THE ATmega328P FORCES THAT THE C6 DID NOT, each of which
// would have been a silent wrong answer rather than a build error:
//
//  1. There is no Serial.printf on the AVR core, and avr-libc's printf
//     carries no 64-bit conversion. The C6 sketch's uint64_t counters
//     and %llu would compile to nothing useful. Everything here is
//     uint32_t and %lu: the latch index wraps after 2.2 years at 60
//     polls a second, the clock count after 103 days at 480 a second.
//  2. The C6's 2048-entry schedule is 32 KB. This part has 2 KB of SRAM
//     in total. SCHEDULE_MAX is 128, which is not a guess: at 256 the
//     compiler reports 2161 bytes of globals, 105 percent, and refuses
//     to link; at 128 it reports 1521 bytes and leaves 527 for the
//     stack. A B3 record with more than 128 changes of byte does not
//     fit, gets the protocol's existing "# schedule full" reply, and
//     is refused by tools/b3.py before the run rather than replayed
//     with its tail missing. Longer records need the C6 build or a
//     streamed schedule, which is a v2 item and is not pretended to
//     work here.
//  3. Timer1's external clock input is the T1 pin and nothing else, so
//     the latch line has to be D5. That is not a preference.

#include <SPI.h>

// ------------------------------------------------------------- pins
// Per docs/bench-v1b-uno.md's table and the A1 chip on the v1b sheet,
// which tools/check-sheets.py holds equal to each other.
static const uint8_t PIN_RCLK      = 10;  // 74HC595 RCLK: one rise moves the byte
static const uint8_t PIN_CON_LATCH = 5;   // console OUT0. Timer1's T1 input; also readable as a level
static const uint8_t PIN_CON_CLOCK = 2;   // console CLK (/OE1). INT0
static const uint8_t PIN_TRIG      = 3;   // to the scope's EXT TRIG through R1
static const uint8_t PIN_PAD_LATCH = 6;
static const uint8_t PIN_PAD_CLOCK = 7;
static const uint8_t PIN_PAD_DATA  = 8;
// D11 MOSI and D13 SCK belong to the SPI peripheral; D0 and D1 to the
// serial port. The console's D0 line is the 165's output and is not
// monitored on this build, as on the C6.
static const int CON_DATA = -1;

// 256 * 5 bytes = 1280 of the 2048. The compiler's own report is the
// authority; if it says the globals leave under ~300 bytes for the
// stack, this number is what to lower.
static const int SCHEDULE_MAX = 128;

struct At { uint32_t latch; uint8_t byte; };
static At schedule[SCHEDULE_MAX];
static int schedule_len = 0;
static int schedule_cursor = 0;   // a cursor, not a scan: AT arrives in order

enum Mode { PASS, INJECT };
static Mode mode = PASS;
static bool mutated = false;
static uint8_t held = 0;          // what the register's inputs show now
static uint8_t set_byte = 0;      // SET's byte for INJECT
static uint8_t pad_byte = 0;      // the original pad's last poll
static uint32_t latches = 0;      // the latch index (rises seen since RESET)
static uint32_t clocks = 0;       // clocks seen since RESET
static uint32_t clocks_at_latch = 0;
static uint8_t byte_at_latch = 0;
static bool have_latch = false;
static uint16_t last_tcnt = 0;
static long trig_at = -1;
static unsigned long trig_until = 0;
static uint16_t deferred_writes = 0;
static uint16_t torn_writes = 0;  // the load window opened across the RCLK edge
static bool torn_pending = false;

// The clock counter. INT0 feeds it normally; under MUTATE the LATCH
// line's pin-change interrupt feeds it instead, which is B0's stated
// sabotage ("the bridge's clock counter fed the latch line") done in
// software, with no jumper to forget to move back.
static volatile uint32_t clock_edges = 0;

static void clock_isr() { if (!mutated) clock_edges++; }

// D5 is PD5, which is PCINT21. Rises only, so a mutated run reports one
// "clock" per latch instead of eight and the 8-per-latch gate is red.
ISR(PCINT2_vect) { if (mutated && (PIND & _BV(PD5))) clock_edges++; }

// --------------------------------------------------------- register
// The 74HC595's QA..QH feed the 74HC165's H..A, and the 165 shifts H
// out first, so QA is the A button. SPI is MSB first: the first bit
// sent travels furthest and lands on QH, the last bit sent stays on QA.
// So sending bit 7 first puts our bit 0 on QA, which is what we want.
// The register is active low (pressed = LOW), hence the complement.
// Get either of those backwards and the pad is silently mirrored.
static inline uint8_t reg_byte_for(uint8_t b) { return (uint8_t)~b; }

// The 165 loads while OUT0 is HIGH, so its inputs must not move inside
// that window. Shifting into the 595 is free (its outputs do not move
// until RCLK), so the only thing that must land outside the window is
// the RCLK edge itself, which is one instruction, 62.5 ns. Check the
// line before and after it; if the window opened across that edge, say
// so on the next L line rather than pretending the byte was clean.
static bool write_register(uint8_t b) {
  if (digitalRead(PIN_CON_LATCH) == HIGH) { deferred_writes++; return false; }
  SPI.transfer(reg_byte_for(b));
  if (digitalRead(PIN_CON_LATCH) == HIGH) { deferred_writes++; return false; }
  PORTB |= _BV(PB2);   // D10 high
  PORTB &= ~_BV(PB2);  // and low again
  held = b;
  if (digitalRead(PIN_CON_LATCH) == HIGH) { torn_writes++; torn_pending = true; }
  return true;
}

// -------------------------------------------------------------- pad
// The original pad on the bridge's own lines, at the 5 V it was built
// for, polled the way the console polls it but at leisure.
static uint8_t poll_pad() {
  digitalWrite(PIN_PAD_LATCH, HIGH);
  delayMicroseconds(12);
  digitalWrite(PIN_PAD_LATCH, LOW);
  delayMicroseconds(6);
  uint8_t b = 0;
  for (uint8_t i = 0; i < 8; i++) {
    if (digitalRead(PIN_PAD_DATA) == LOW) b |= (uint8_t)(1 << i);
    digitalWrite(PIN_PAD_CLOCK, HIGH);
    delayMicroseconds(6);
    digitalWrite(PIN_PAD_CLOCK, LOW);
    delayMicroseconds(6);
  }
  return b;
}

static uint8_t scheduled_byte() {
  while (schedule_cursor < schedule_len && schedule[schedule_cursor].latch <= latches) {
    set_byte = schedule[schedule_cursor].byte;
    schedule_cursor++;
  }
  return set_byte;
}

// ---------------------------------------------------------- commands
static char line[64];
static uint8_t line_len = 0;

static void say(const char *s) { Serial.println(s); }

static void handle(char *s) {
  while (*s == ' ') s++;
  for (char *e = s + strlen(s); e > s && (e[-1] == '\r' || e[-1] == ' '); e--) e[-1] = 0;
  char out[64];
  if (!strcmp(s, "MODE PASS")) { mode = PASS; say("# mode pass"); }
  else if (!strcmp(s, "MODE INJECT")) { mode = INJECT; say("# mode inject"); }
  else if (!strncmp(s, "SET ", 4)) {
    set_byte = (uint8_t)strtoul(s + 4, NULL, 16);
    snprintf(out, sizeof out, "# set %02x", set_byte); say(out);
  }
  else if (!strncmp(s, "AT ", 3)) {
    char *end;
    unsigned long n = strtoul(s + 3, &end, 10);
    unsigned long b = strtoul(end, NULL, 16);
    if (schedule_len < SCHEDULE_MAX) {
      schedule[schedule_len].latch = (uint32_t)n;
      schedule[schedule_len].byte = (uint8_t)b;
      schedule_len++;
      snprintf(out, sizeof out, "# at %lu %02lx", n, b); say(out);
    } else say("# schedule full");
  }
  else if (!strncmp(s, "TRIG ", 5)) {
    trig_at = strtol(s + 5, NULL, 10);
    snprintf(out, sizeof out, "# trig at %ld", trig_at); say(out);
  }
  else if (!strcmp(s, "RESET")) {
    uint8_t sreg = SREG; cli();
    latches = 0; clock_edges = 0; last_tcnt = TCNT1;
    SREG = sreg;
    clocks = 0; clocks_at_latch = 0; have_latch = false;
    schedule_len = 0; schedule_cursor = 0; trig_at = -1;
    deferred_writes = 0; torn_writes = 0; torn_pending = false;
    say("# reset");
  }
  else if (!strcmp(s, "STATUS")) {
    snprintf(out, sizeof out, "# mode %s latch %lu clocks %lu held %02x",
             mode == PASS ? "pass" : "inject", latches, clocks, held); say(out);
    snprintf(out, sizeof out, "# pad %02x schedule %d/%d data %d deferred %u torn %u mutate %s",
             pad_byte, schedule_len, SCHEDULE_MAX, CON_DATA, deferred_writes, torn_writes,
             mutated ? "on" : "off"); say(out);
  }
  else if (!strcmp(s, "MUTATE ON") || !strcmp(s, "MUTATE OFF")) {
    mutated = !strcmp(s, "MUTATE ON");
    say(mutated ? "# mutate on: the clock counter is fed the latch line"
                : "# mutate off: the counters on their own lines");
  }
  else if (*s) { snprintf(out, sizeof out, "# ? %.58s", s); say(out); }
}

// ------------------------------------------------------------- setup
void setup() {
  Serial.begin(115200);

  pinMode(PIN_RCLK, OUTPUT);
  digitalWrite(PIN_RCLK, LOW);
  SPI.begin();
  SPI.beginTransaction(SPISettings(4000000, MSBFIRST, SPI_MODE0));
  // Nothing pressed until told: all eight register inputs high.
  SPI.transfer(reg_byte_for(0));
  PORTB |= _BV(PB2); PORTB &= ~_BV(PB2);
  held = 0;

  pinMode(PIN_CON_LATCH, INPUT);   // T1 needs it as an input
  pinMode(PIN_CON_CLOCK, INPUT);
  pinMode(PIN_PAD_LATCH, OUTPUT);
  pinMode(PIN_PAD_CLOCK, OUTPUT);
  pinMode(PIN_PAD_DATA, INPUT_PULLUP);
  pinMode(PIN_TRIG, OUTPUT);
  digitalWrite(PIN_TRIG, LOW);

  // Timer1 counting the latch line in hardware: external clock on T1,
  // rising edge, no prescaler in the path and no timer interrupt. The
  // edge is sampled against the 16 MHz clock, so a pulse shorter than
  // 62.5 ns would be missed; the console's latch is microseconds wide.
  TCCR1A = 0;
  TCCR1B = _BV(CS12) | _BV(CS11) | _BV(CS10);
  TIMSK1 = 0;
  TCNT1 = 0;
  last_tcnt = 0;

  attachInterrupt(digitalPinToInterrupt(PIN_CON_CLOCK), clock_isr, FALLING);
  // The mutation's path, armed but inert while mutated is false.
  PCMSK2 |= _BV(PCINT21);
  PCICR |= _BV(PCIE2);

  say("# nes-bench bridge v1b (UNO, all 5 V): B0 sniff; MODE PASS");
}

// -------------------------------------------------------------- loop
void loop() {
  static unsigned long last_pad_poll = 0;
  char out[64];

  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n') { line[line_len] = 0; handle(line); line_len = 0; }
    else if (line_len < sizeof(line) - 1) line[line_len++] = c;
  }

  unsigned long now = micros();
  if (now - last_pad_poll >= 1000) { last_pad_poll = now; pad_byte = poll_pad(); }

  // The console's pulses first, so a latch is logged with the byte the
  // register held at it, before any new byte is written.
  uint16_t now16;
  uint8_t sreg = SREG; cli(); now16 = TCNT1; SREG = sreg;
  uint16_t dl = (uint16_t)(now16 - last_tcnt);   // unsigned: the wrap takes care of itself
  last_tcnt = now16;
  uint32_t edges;
  sreg = SREG; cli(); edges = clock_edges; SREG = sreg;
  clocks = edges;

  if (dl > 0) {
    if (have_latch) {
      snprintf(out, sizeof out, "L %lu %02x %lu", latches - 1, byte_at_latch, clocks - clocks_at_latch);
      say(out);
      if (torn_pending) { say("# the load window opened across an RCLK edge: the byte above may be torn"); torn_pending = false; }
    }
    if (dl > 1) { snprintf(out, sizeof out, "# %u latches in one look at %lu", dl, latches); say(out); }
    latches += dl;
    clocks_at_latch = clocks;
    byte_at_latch = held;
    have_latch = true;
    if (trig_at >= 0 && (uint32_t)trig_at < latches) {
      digitalWrite(PIN_TRIG, HIGH);
      trig_until = millis() + 1;
      trig_at = -1;
      snprintf(out, sizeof out, "# trigger at latch %lu", latches - 1); say(out);
    }
  }
  if (trig_until && millis() >= trig_until) { digitalWrite(PIN_TRIG, LOW); trig_until = 0; }

  uint8_t want = (mode == PASS) ? pad_byte : scheduled_byte();
  if (want != held) write_register(want);
  delayMicroseconds(100);
}
