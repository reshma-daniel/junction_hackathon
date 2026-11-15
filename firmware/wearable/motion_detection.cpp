// Included by wearable.cpp; also usable in host tests without Arduino.
#ifndef WEARABLE_MOTION_DETECTION_CPP
#define WEARABLE_MOTION_DETECTION_CPP
#include <stdint.h>

struct MotionDebounce {
  uint32_t moveSamples = 5;
  uint32_t stillSamples = 20;
  uint32_t aboveRun = 0, belowRun = 0;
  int state = -1;

  void resetCandidates() { aboveRun = belowRun = 0; }

  int update(bool above) {
    if (above) {
      belowRun = 0;
      if (aboveRun < moveSamples) ++aboveRun;
      if (aboveRun >= moveSamples) state = 1;
    } else {
      aboveRun = 0;
      if (belowRun < stillSamples) ++belowRun;
      if (belowRun >= stillSamples) state = 0;
    }
    return state;
  }
};
#endif
