// The UNO's packed schedule (firmware/bridge-uno/schedule.h) against the
// meaning the protocol gives AT lines: from latch n on, hold the byte of
// the last entry at or before n. Built natively by
// tools/test-uno-schedule.sh; its -DSCHEDULE_MUTATE build must fail.
#include <cstdio>
#include <cstdlib>
#include <vector>
#include <fstream>
#include <sstream>
#include <string>
#include "../firmware/bridge-uno/schedule.h"

struct Abs { uint32_t n; uint8_t b; };

// The protocol's meaning, from absolute latches.
static uint8_t reference(const std::vector<Abs> &s, uint32_t latch, uint8_t set) {
  uint8_t held = set;
  for (auto &a : s) if (a.n <= latch) held = a.b;
  return held;
}

// Play one schedule: the packed one fed a growing latch index, compared
// at every latch it is asked about. Returns the number of mismatches.
static int play(const std::vector<Abs> &s, unsigned seed, bool jumps) {
  static Schedule<600> sch;
  sch.clear();
  for (auto &a : s) {
    if (sch.append(a.n, a.b) != 0) { std::printf("append refused at %u\n", a.n); return 1; }
  }
  uint8_t held = 0x00;   // SET 00
  uint32_t end = s.empty() ? 100 : s.back().n + 300;
  std::srand(seed);
  int bad = 0;
  for (uint32_t latch = 0; latch <= end; latch += jumps ? 1 + std::rand() % 3 : 1) {
    sch.due(latch, held);
    uint8_t want = reference(s, latch, 0x00);
    if (held != want) {
      if (bad < 3) std::printf("  latch %u: held %02x, the protocol says %02x\n", latch, held, want);
      bad++;
    }
  }
  return bad;
}

// Stream one schedule through a small ring, as the head feeds the UNO:
// before latch 0 append what fits, then at each latch append more as
// applied entries free their slots, never an entry whose latch is gone
// (the firmware refuses those). Returns mismatches, or 1 if the stream
// starved (an entry not in by its latch).
static int stream(const std::vector<Abs> &s, unsigned seed, bool jumps) {
  static Schedule<64> sch;
  sch.clear();
  size_t next = 0;
  auto feed = [&](uint32_t now) {
    while (next < s.size() && sch.len + sch.cost(s[next].n) <= 64) {
      if (s[next].n < now) return false;
      if (sch.append(s[next].n, s[next].b) != 0) return false;
      next++;
    }
    return true;
  };
  if (!feed(0)) { std::printf("  stream refused before latch 0\n"); return 1; }
  uint8_t held = 0x00;
  uint32_t end = s.empty() ? 100 : s.back().n + 300;
  std::srand(seed);
  int bad = 0;
  for (uint32_t latch = 0; latch <= end; latch += jumps ? 1 + std::rand() % 3 : 1) {
    if (next < s.size() && s[next].n <= latch) {
      // the head fell behind: in the firmware this is "# late", and the
      // test says so rather than counting it a match
      std::printf("  starved at latch %u (entry for %u not in)\n", latch, s[next].n);
      return 1;
    }
    sch.due(latch, held);
    if (!feed(latch + 1)) { std::printf("  stream refused at latch %u\n", latch); return 1; }
    uint8_t want = reference(s, latch, 0x00);
    if (held != want) {
      if (bad < 3) std::printf("  streamed, latch %u: held %02x, the protocol says %02x\n", latch, held, want);
      bad++;
    }
  }
  return bad;
}

int main(int argc, char **argv) {
  int bad = 0, cases = 0;
  // Random schedules: gaps from 0 (two ATs at one latch) to 2000 (fillers),
  // bytes arbitrary, some starting past latch 254 so fillers precede the
  // first entry.
  for (unsigned seed = 1; seed <= 400; seed++) {
    std::srand(seed);
    std::vector<Abs> s;
    uint32_t n = std::rand() % 600;
    int k = 1 + std::rand() % 120;
    Schedule<600> probe; probe.clear();
    for (int i = 0; i < k; i++) {
      uint8_t b = (uint8_t)(std::rand() & 0xff);
      if (probe.append(n, b) != 0) break;
      s.push_back({n, b});
      int r = std::rand() % 10;
      n += r == 0 ? 0 : r < 8 ? std::rand() % 60 : 200 + std::rand() % 1800;
    }
    bad += play(s, seed, seed % 2) ? 1 : 0;
    cases++;
  }
  // Streamed: schedules many times the ring's 64 entries (a whole planned
  // run is several hundred), dense enough to wrap the ring repeatedly but
  // never more than the ring can hold ahead (gaps of at least one latch,
  // as a plan's are), fed as slots free.
  for (unsigned seed = 1; seed <= 200; seed++) {
    std::srand(seed * 7919);
    std::vector<Abs> s;
    uint32_t n = std::rand() % 40;
    int k = 300 + std::rand() % 600;
    for (int i = 0; i < k; i++) {
      s.push_back({n, (uint8_t)(std::rand() & 0xff)});
      int r = std::rand() % 10;
      n += r < 8 ? 1 + std::rand() % 30 : 200 + std::rand() % 600;
    }
    bad += stream(s, seed, seed % 2) ? 1 : 0;
    cases++;
  }
  // A real record: every AT line of a b3.py record, if one is named.
  if (argc > 1) {
    std::ifstream f(argv[1]);
    std::string line;
    std::vector<Abs> s;
    while (std::getline(f, line)) {
      std::istringstream in(line);
      std::string w; unsigned n; std::string hx;
      if (in >> w && w == "AT" && in >> n >> hx) s.push_back({n, (uint8_t)std::strtoul(hx.c_str(), nullptr, 16)});
    }
    Schedule<600> probe; probe.clear();
    unsigned used = 0; for (auto &a : s) { used += probe.cost(a.n); probe.append(a.n, a.b); }
    std::printf("%s: %zu changes, %u entries packed (of 600)\n", argv[1], s.size(), used);
    bad += play(s, 7, true) ? 1 : 0;
    bad += stream(s, 7, true) ? 1 : 0;
    cases += 2;
  }
  // The capacity edge: the append that does not fit is refused whole.
  {
    Schedule<4> t; t.clear();
    int r1 = t.append(10, 1), r2 = t.append(700, 2), r3 = t.append(701, 3);
    // 10: 1 entry; 700: gap 690 = 2 fillers + 1 = 3 more (4 used); 701: full.
    if (r1 != 0 || r2 != 0 || r3 != 1 || t.len != 4) { std::printf("capacity: %d %d %d len %u\n", r1, r2, r3, t.len); bad++; }
    if (t.append(5, 9) != 2) { std::printf("an AT before the last was taken\n"); bad++; }
    cases++;
  }
  std::printf("%d of %d cases wrong\n", bad, cases);
  return bad ? 1 : 0;
}
