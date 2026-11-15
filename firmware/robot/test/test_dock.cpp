#include <assert.h>
#include "../dock.cpp"
int main() {
  PillDock d;
  assert(!d.update(0, 16, 16, 0));
  assert(d.update(0, 16, 16, 100) && d.state == 0);
  assert(!d.update(12, 16, 16, 200));
  assert(!d.update(5, 16, 16, 250));  // Partial coverage breaks a candidate.
  assert(!d.update(12, 16, 16, 300));
  assert(d.update(12, 16, 16, 400) && d.state == 1);
  assert(!d.update(0, 16, 0, 500));  // Invalid grids are not an empty dock.
  assert(!d.update(0, 16, 16, 600));
  assert(!d.update(1, 16, 16, 650)); // Open must be zero close zones.
  assert(!d.update(0, 16, 16, 700));
  assert(d.update(0, 16, 16, 800) && d.state == 0);
  assert(!d.update(0, 16, 16, 900)); // No repeated state change.
  PillDock wrap;
  wrap.update(12, 16, 16, UINT32_MAX - 50);
  assert(wrap.update(12, 16, 16, 49));
}
