// mic_hw.cpp — owner: Reshma. The ONLY file that touches the microphone module.
// Instance from firmware/robot_mic/project.yaml: microphone (ports 2+3).
// The module's own begin() already ran in the generated setup() and started its
// background capture task, so the level below is cached and returns instantly.
#include "mic.h"

void mic_hw_begin() {}

int16_t mic_hw_level() {
  return microphone.getSoundLevel();   // RMS 0..32767
}
