// header-probe: which header pin is this wire actually in?
//
// A QA tool, not part of the adapter. Wires standing in a 0.1 inch
// header cannot be counted from a photograph: they stand above the
// board, so parallax shifts them against the silkscreen underneath,
// and the two rows are one tenth of an inch apart seen from straight
// down. Deriving a pin from a picture is how this project put every
// jumper of the C6 build in the wrong row for four revisions.
//
// So this measures it instead. Every FREE pin on header P6 is held up
// by its own pullup. Touch the far end of a wire to any ground and
// this names the pin it is sitting in.
//
// IT DRIVES NOTHING. Every pin here is an input, so a wire that turns
// out to be in the wrong hole costs nothing while you find out.
//
// The table is GENERATED from tools/p4_header.py, which read the
// header from Waveshare's schematic. Pins the board has already
// spoken for are absent by construction, GPIO37 and GPIO38 among them:
// they are this very serial port.

struct Pin { int gpio; int p6; };

static const Pin PINS[] = {
  {23,  8},   // P6 pin 8
  {22, 11},   // P6 pin 11
  {21, 12},   // P6 pin 12
  {20, 14},   // P6 pin 14
  { 5, 15},   // P6 pin 15
  { 6, 16},   // P6 pin 16   <-- PAD1_D0
  { 4, 17},   // P6 pin 17
  { 3, 20},   // P6 pin 20   <-- PAD_CLK
  { 1, 21},   // P6 pin 21
  { 2, 22},   // P6 pin 22   <-- PAD_LATCH
  { 0, 24},   // P6 pin 24
  {32, 25},   // P6 pin 25
  {33, 30},   // P6 pin 30
  {26, 32},   // P6 pin 32
  {48, 34},   // P6 pin 34
  {46, 35},   // P6 pin 35
  {27, 37},   // P6 pin 37
  {47, 38},   // P6 pin 38
};
static const int N = sizeof(PINS) / sizeof(PINS[0]);

static bool was[N];

void setup() {
  Serial.begin(115200);
  delay(2000);
  for (int i = 0; i < N; i++) {
    pinMode(PINS[i].gpio, INPUT_PULLUP);
    was[i] = true;
  }
  Serial.println();
  Serial.println("== header-probe ==");
  Serial.printf("%d free pins on P6 held up. Touch a wire's far end to GND.\n", N);
  Serial.println("Expected for pad-ble:  P6 22 = GPIO2 latch,  20 = GPIO3 clock,  16 = GPIO6 data");
  Serial.println("(3V3 is P6 pin 18 and GND is P6 pin 26; neither can be probed this way.)");
}

void loop() {
  for (int i = 0; i < N; i++) {
    bool now = digitalRead(PINS[i].gpio);
    if (now != was[i]) {
      Serial.printf("%-7s P6 pin %-2d  GPIO%-2d\n", now ? "RELEASE" : "GROUNDED",
                    PINS[i].p6, PINS[i].gpio);
      was[i] = now;
    }
  }
  delay(15);   // -- debounce a finger, not a switch
}
