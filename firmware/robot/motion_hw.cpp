// motion_hw.cpp — owner: Sara. The ONLY file that touches the motor modules.
// TODO(M0): fill in once PORTS.md has the real ports and the Atech motor API is known.
#include "motion.h"

// Per-side sign: flip if +speed drives the wrong way (verify on the bench).
static const int LEFT_SIGN  = -1;  // left motors (ports 14, 9) are mounted mirrored
static const int RIGHT_SIGN = +1;

void motion_hw_write(int left, int right) {
  left  *= LEFT_SIGN;
  right *= RIGHT_SIGN;
  // Instances from firmware/robot_test/project.yaml: m14 FL, m9 RL, m6 FR, m1 RR
  m14.setSpeed(left);  m9.setSpeed(left);
  m6.setSpeed(right);  m1.setSpeed(right);
}
