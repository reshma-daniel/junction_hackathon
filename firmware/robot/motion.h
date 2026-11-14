// motion.* — owner: Sara. Drive layer for the 4 DC motors (2 sides).
// Contract: docs/MESSAGES.md (robot.mode, robot.drive, robot.state).
#pragma once
#include <stdint.h>

enum MotionMode : uint8_t {
  MODE_IDLE = 0,
  MODE_WALK,
  MODE_FOLLOW,
  MODE_COME,
  MODE_STOP,
  MODE_MANUAL,   // set implicitly by robot.drive
};

// Called by comms when robot.mode arrives. Unknown names return false.
bool motion_set_mode_name(const char* name);
void motion_set_mode(MotionMode mode);

// left/right -255..255. Switches to MODE_MANUAL. Ramped; safety still applies.
void motion_drive(int left, int right);

void motion_stop();     // immediate: target 0 and output 0 (no ramp)
void motion_tick();     // call every loop; non-blocking

MotionMode motion_mode();
bool motion_driving();

// ---- Interfaces motion needs from other owners ----------------------------
struct Range {           // Reshma, range.*
  int left_mm, right_mm, min_mm;
  float bearing;         // -1 left .. +1 right, nearest object
  bool blocked;          // min_mm < obstacle_stop_mm
};
Range range_get();

bool comms_watchdog_tripped();           // Wanhui: true if no laptop msg for 2 s
void comms_send(const char* json_line);  // Wanhui: send one JSON object

// ---- Hardware layer (motion_hw.cpp) ----------------------------------------
// Only place that touches the Atech motor API. left/right already -255..255.
void motion_hw_write(int left, int right);
