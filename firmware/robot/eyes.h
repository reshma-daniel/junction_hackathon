// eyes.* — owner: Reshma. The robot's two eyes: 2x LED Grid (3x3 NeoPixel), ports 13 and 10.
// Contract: docs/MESSAGES.md (robot.eyes). Moods: docs/tasks/reshma.md.
//
//   Mood         Colour        How it moves
//   calm         soft blue     slow blink: 1.5 s on, 1.5 s off
//   listening    bright white  steady
//   happy        green         very fast blink (0.1 s on/off) for 2 s, then back to calm
//   pleading     warm amber    blink once a second: 0.5 s on, 0.5 s off
//   encouraging  turquoise     steady, with a quick double blink every 2 s
//   sad          dim purple    very slow, faint glow (6 s per cycle)
//   sleepy       dim orange    only the middle row lit, like half-closed eyes
//   searching    pale blue     a bar sweeping side to side across both eyes (0.3 s per step)
//
// Pixels are numbered 0..8 row by row (0 1 2 / 3 4 5 / 6 7 8), row 0 at the top.
#pragma once
#include <stdint.h>

enum EyeMood : uint8_t {
  MOOD_CALM = 0,
  MOOD_LISTENING,
  MOOD_HAPPY,
  MOOD_PLEADING,
  MOOD_ENCOURAGING,
  MOOD_SAD,
  MOOD_SLEEPY,
  MOOD_SEARCHING,
  MOOD_COUNT
};

enum EyePattern : uint8_t {
  PAT_SOLID = 0,     // steady
  PAT_BLINK,         // hard on/off, half the period each
  PAT_BREATHE,       // slow smooth brighten/dim
  PAT_PULSE,         // quick beat: sharp rise, slower fade
  PAT_SPARKLE,       // random twinkling pixels
  PAT_DOUBLE_BLINK,  // steady + two quick blinks each period
  PAT_GLOW,          // very slow, faint breathing
  PAT_HALF,          // middle row only
  PAT_SWEEP,         // one column lit, sweeping left<->right across both eyes
  PAT_COUNT
};

// ---- Main API ---------------------------------------------------------------
void eyes_begin();                          // call once in setup
void eyes_tick();                           // call every loop; non-blocking, redraws every ~30 ms

void eyes_set_mood(EyeMood mood);           // preferred: one of the moods above
bool eyes_set_mood_name(const char* name);  // "calm", "happy", ... ; false if unknown
EyeMood eyes_mood();
const char* eyes_mood_name(EyeMood mood);

// Raw form of robot.eyes: any colour (0xRRGGBB) per eye + pattern. period_ms 0 = pattern default.
void eyes_set(uint32_t left_rgb, uint32_t right_rgb, EyePattern pattern, uint16_t period_ms);
bool eyes_pattern_from_name(const char* name, EyePattern* out);  // "solid", "breathe", ...

// ---- Hardware layer (eyes_hw.cpp) ---------------------------------------------
// Only place that touches the Atech LED Grid API. Colours are 0xRRGGBB, already scaled.
void eyes_hw_begin();
void eyes_hw_show(const uint32_t left[9], const uint32_t right[9]);
