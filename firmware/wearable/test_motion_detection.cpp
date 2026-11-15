#include <cassert>
#include "motion_detection.cpp"

int main() {
  MotionDebounce motion;
  for (int i = 0; i < 4; ++i) assert(motion.update(true) == -1);
  assert(motion.update(true) == 1);
  for (int i = 0; i < 19; ++i) assert(motion.update(false) == 1);
  assert(motion.update(false) == 0);
  for (int i = 0; i < 4; ++i) assert(motion.update(true) == 0);
  assert(motion.update(false) == 0); // Interrupted run cannot trigger movement.
  for (int i = 0; i < 4; ++i) assert(motion.update(true) == 0);
  motion.resetCandidates(); // Missing IMU window breaks consecutiveness.
  for (int i = 0; i < 4; ++i) assert(motion.update(true) == 0);
  assert(motion.update(true) == 1);
  for (int i = 0; i < 10000; ++i) assert(motion.update(true) == 1);
  assert(motion.aboveRun == 5); // Counters saturate rather than overflow.
}
