// eyes_hw.cpp — owner: Reshma. The ONLY file that touches the LED Grid modules.
// Instances from firmware/robot_eyes/project.yaml: eye_left (port 13), eye_right (port 10).
// If the eyes come out swapped on the robot, swap the two ports in project.yaml.
#include "eyes.h"

static const uint8_t BRIGHTNESS = 51;   // module caps at 51 (20%); colours are scaled by it

static void push(NeoPixelGrid& grid, const uint32_t px[9]) {
  for (int i = 0; i < 9; i++)
    grid.setPixel(i, (px[i] >> 16) & 0xFF, (px[i] >> 8) & 0xFF, px[i] & 0xFF);
  grid.show();
}

void eyes_hw_begin() {
  eye_left.setBrightness(BRIGHTNESS);  eye_left.clear();  eye_left.show();
  eye_right.setBrightness(BRIGHTNESS); eye_right.clear(); eye_right.show();
}

void eyes_hw_show(const uint32_t left[9], const uint32_t right[9]) {
  push(eye_left, left);
  push(eye_right, right);
}
