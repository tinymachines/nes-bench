// The AT schedule, packed: two bytes an entry instead of five.
//
// The protocol keeps absolute latch numbers (AT n hh, n increasing), and
// the head, the tools and the C6 build keep them too. Only the UNO's RAM
// holds them differently: each entry stores the GAP from the previous
// entry's latch in one byte, and the byte to hold in the other. A gap of
// 0..254 is a change of byte; the value 255 is a FILLER, "advance 255
// latches and change nothing", so a gap longer than 254 costs one extra
// entry per 255 latches and no filler ever has to name a byte (which
// would be wrong before the first entry, where the held byte is SET's).
//
// Why: the UNO has 2048 bytes of RAM. Five-byte entries (a uint32_t
// latch and a byte) held 128 in 640 bytes, and 256 did not link. A hand
// playing Super Mario Bros. for a minute changes the pad's byte 289
// times (nes-bench run 20260919-012524). Two-byte entries hold 320 in the
// same 640 bytes; with the sketch's strings moved to flash it holds 600.
//
// A RING since 2026-10-18 (streaming): an applied entry frees its slot,
// so a run longer than the schedule is fed while it plays. The head
// loads what fits before the console leaves reset and sends the rest as
// the latches go by; `len` is the entries held now, not the entries
// appended since RESET. A planned Super Mario Bros. run from power-on to
// World 2-2 is 258 changes of byte, and 2-2's swimming costs two a
// stroke, which is what made 600 a wall.
//
// Plain C++ with no Arduino header, so tools/test-uno-schedule.sh builds
// it natively and checks it against absolute latches, fed whole and fed
// as a stream through a small ring; its MUTATE builds (a filler that sets
// the byte to zero; SCHEDULE_MUTATE_RING, a cursor that wraps a slot
// short) must go red.

#ifndef NESBENCH_SCHEDULE_H
#define NESBENCH_SCHEDULE_H

#include <stdint.h>

static const uint8_t SCHEDULE_FILLER = 255;   // a gap, not a change

struct Packed {
  uint8_t gap;    // latches after the previous entry; 255 = filler
  uint8_t byte;   // the byte to hold from this entry's latch on
};

template <int N>
struct Schedule {
  Packed e[N];
  uint16_t len = 0;        // entries held now (appended, not yet applied)
  uint16_t cursor = 0;     // the slot of the next entry to apply
  uint16_t tail = 0;       // the slot the next append writes
  uint32_t last = 0;       // the absolute latch of the last entry appended
  uint32_t cursor_at = 0;  // the absolute latch the cursor counts from
  bool any = false;        // something appended since clear()

  void clear() { len = 0; cursor = 0; tail = 0; last = 0; cursor_at = 0; any = false; }

  // The entries an AT at latch n costs: its fillers and itself.
  uint16_t cost(uint32_t n) const {
    uint32_t gap = n - last;
    return (uint16_t)(gap / 255 + 1);
  }

  // 0: taken. 1: full (nothing appended). 2: n before the last entry.
  int append(uint32_t n, uint8_t b) {
    if (any && n < last) return 2;
    uint32_t gap = n - last;
    uint32_t need = gap / 255 + 1;
    if (len + need > (uint32_t)N) return 1;
    while (gap >= 255) {
      e[tail].gap = SCHEDULE_FILLER;
      e[tail].byte = 0;
      tail = (uint16_t)((tail + 1) % N);
      len++;
      gap -= 255;
    }
    e[tail].gap = (uint8_t)gap;
    e[tail].byte = b;
    tail = (uint16_t)((tail + 1) % N);
    len++;
    last = n;
    any = true;
    return 0;
  }

  // Apply every entry due at or before `latches` to `held`; called with
  // the latch index as it grows (by one, or by several when the loop
  // looked late). Each applied entry's slot is free again.
  void due(uint32_t latches, uint8_t &held) {
    while (len > 0) {
      uint32_t at = cursor_at + e[cursor].gap;
      if (at > latches) break;
      cursor_at = at;
#ifdef SCHEDULE_MUTATE
      held = e[cursor].byte;              // the mutation: a filler sets 0
#else
      if (e[cursor].gap != SCHEDULE_FILLER) held = e[cursor].byte;
#endif
#ifdef SCHEDULE_MUTATE_RING
      cursor = (uint16_t)((cursor + 1) % (N - 1));   // the mutation: wraps a slot short
#else
      cursor = (uint16_t)((cursor + 1) % N);
#endif
      len--;
    }
  }
};

#endif
