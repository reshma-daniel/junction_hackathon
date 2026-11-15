#ifndef KAAMOS_DOCK_CPP_INCLUDED
#define KAAMOS_DOCK_CPP_INCLUDED
#include <stdint.h>

// Coverage hysteresis from Wanhui's pill_dock.ino, without hardware dependencies.
struct PillDock {
  int nearMm = 10, coverPct = 60, openPct = 0;
  uint32_t holdMs = 100;
  int state = -1, candidate = -1;
  uint32_t candidateSince = 0;

  bool update(int close, int zones, int valid, uint32_t now) {
    if (zones <= 0 || valid * 2 < zones) { candidate = -1; return false; }
    int pct = close * 100 / zones;
    int raw = pct >= coverPct ? 1 : pct <= openPct ? 0 : -1;
    if (raw < 0 || raw == state) { candidate = -1; return false; }
    if (raw != candidate) { candidate = raw; candidateSince = now; }
    if (uint32_t(now - candidateSince) < holdMs) return false;
    state = raw; candidate = -1; return true;
  }
};
#endif
