#include <assert.h>
#include "../dock.cpp"
int main() {
  PillDock d;
  assert(!d.update(0, 16, 16, 0));
  assert(d.update(0, 16, 16, 100) && d.state == 0);
  assert(!d.update(12, 16, 16, 200));
  assert(!d.update(4, 16, 16, 250));  // Partial coverage breaks a candidate.
  assert(!d.update(12, 16, 16, 300));
  assert(d.update(12, 16, 16, 400) && d.state == 1);
  assert(!d.update(0, 16, 0, 500));  // Invalid grids are not an empty dock.
  assert(!d.update(0, 16, 16, 600));
  assert(!d.update(1, 16, 16, 650)); // Open must be zero close zones.
  assert(!d.update(0, 16, 16, 700));
  assert(d.update(0, 16, 16, 800) && d.state == 0);
  assert(!d.update(0, 16, 16, 900)); // No repeated state change.
  PillDock threshold;
  assert(!threshold.update(19, 64, 64, 0)); // 29.7% is below 30%.
  assert(!threshold.update(19, 64, 64, 100));
  assert(threshold.state == -1);
  assert(!threshold.update(20, 64, 64, 200));
  assert(threshold.update(20, 64, 64, 300) && threshold.state == 1);
  PillDock wrap;
  wrap.update(12, 16, 16, UINT32_MAX - 50);
  assert(wrap.update(12, 16, 16, 49));
}
