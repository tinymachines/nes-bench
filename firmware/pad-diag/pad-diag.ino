// pad-diag: does the pad answer at all, with the clocking taken away?
//
// A QA tool, not part of the adapter. Written 2026-09-26, when
// firmware/pad-usb read B 00 on every poll and pressing A changed
// nothing. RESOLVED 2026-09-27: an original pad answered here, 27
// presses in 30 s, once a 10 ohm part fitted as the 10k pull-up was
// replaced; the first pad was a replica, which may load only on an
// edge, so "no response" here is ambiguous for one. The wiring was
// right by every check: the ESP side hole by hole with firmware/header-probe,
// the junction by the owner's list, 3.3 V on both rails by meter, and a
// real 10k from D0 to the rail. So the question is no longer where a
// wire goes. It is whether the pad answers.
//
// THIS SPLITS THE FAULT IN TWO. It holds OUT0 (the latch) HIGH and
// never clocks. A 4021 with its parallel/serial control high jams the
// parallel inputs into its register asynchronously, and its last stage
// Q8 follows input P8 continuously. On an NES pad P8 is button A, the
// first bit a normal poll reads. So with the latch held high, D0 IS
// button A, live, with no timing involved at all.
//
//   A moves D0          -> the pad works at 3.3 V. Measure-first item 4
//                          passes, and the fault is in pad-usb's clocked
//                          poll: timing or order, not the part.
//   A does not move D0  -> the D0 path or the pad itself. No clocking
//                          code can be to blame, because there is none.
//
// Pins are firmware/pad-usb's, which tools/check-sheets.py holds to
// header P6. It prints on every change and a heartbeat every two
// seconds, so silence here means a dead board rather than a quiet pad.

static const int PAD_LATCH = 2;
static const int PAD_CLOCK = 3;
static const int PAD1_DATA = 6;

void setup() {
  Serial.begin(115200);
  pinMode(PAD_LATCH, OUTPUT);
  pinMode(PAD_CLOCK, OUTPUT);
  pinMode(PAD1_DATA, INPUT);
  digitalWrite(PAD_CLOCK, LOW);
  digitalWrite(PAD_LATCH, HIGH);   // -- parallel mode, held: Q8 follows P8, which is A
  delay(1500);
  Serial.println();
  Serial.println("== pad-diag: latch held HIGH, no clock. D0 is button A, live. ==");
  Serial.println("Press and release A a few times, slowly.");
}

void loop() {
  static int last = -1;
  static unsigned long beat = 0;
  int d0 = digitalRead(PAD1_DATA);
  if (d0 != last) {
    Serial.printf("D0 %s   %s\n", d0 ? "HIGH" : "LOW ",
                  d0 ? "(A released, or the pad is not answering)" : "(A PRESSED: the pad answers at 3.3 V)");
    last = d0;
  }
  if (millis() - beat > 2000) {
    Serial.printf(". alive, D0 %s\n", d0 ? "HIGH" : "LOW");
    beat = millis();
  }
  delay(5);
}
