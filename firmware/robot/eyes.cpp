// eyes.cpp — owner: Reshma. Mood -> colour + animation for the two 3x3 LED grids.
#include "eyes.h"
#include <math.h>
#include <string.h>

#ifdef ARDUINO
#include <Arduino.h>
#else
unsigned long millis();   // provided by host test
#endif

// ---- Tunables -------------------------------------------------------------------
static const uint16_t FRAME_MS        = 30;     // redraw rate (~33 fps)
static const uint32_t HAPPY_MS        = 2000;   // happy blinking lasts this long, then calm
static const uint16_t SPARKLE_STEP_MS = 90;     // new twinkle pattern this often
static const uint16_t BLINK_MS        = 100;    // one quick blink (off time)

// Default period per pattern (ms). Index = EyePattern.
static const uint16_t DEFAULT_PERIOD[PAT_COUNT] = {
  0,     // solid
  1000,  // blink: one on+off cycle
  4000,  // breathe: one slow breath
  1000,  // pulse: about once a second
  0,     // sparkle (uses SPARKLE_STEP_MS)
  2000,  // double_blink: every 2 s
  6000,  // glow: very slow
  0,     // half
  3000,  // sweep: full left->right->left cycle (10 steps)
};

// ---- Mood table: colour (0xRRGGBB) + pattern + period. Each mood blinks at its own speed ----
struct MoodSpec { const char* name; uint32_t rgb; EyePattern pattern; uint16_t period_ms; };
static const MoodSpec MOODS[MOOD_COUNT] = {
  {"calm",        0x3C78FF, PAT_BLINK,        3000},  // soft blue, slow blink 1.5 s on / 1.5 s off
  {"listening",   0xFFFFFF, PAT_SOLID,           0},  // bright white, steady
  {"happy",       0x1EFF3C, PAT_BLINK,         200},  // green, very fast blink (2 s, then calm)
  {"pleading",    0xFF8C00, PAT_BLINK,        1000},  // warm amber, blink once a second
  {"encouraging", 0x28E0D0, PAT_DOUBLE_BLINK, 2000},  // turquoise, double blink every 2 s
  {"sad",         0x7828C8, PAT_GLOW,         6000},  // dim purple, very slow faint glow
  {"sleepy",      0x401900, PAT_HALF,            0},  // dim orange, middle row only
  {"searching",   0x96C8FF, PAT_SWEEP,        3000},  // pale blue bar, 0.3 s per step
};

static const char* const PATTERN_NAMES[PAT_COUNT] = {
  "solid", "blink", "breathe", "pulse", "sparkle", "double_blink", "glow", "half", "sweep",
};

// ---- State ------------------------------------------------------------------------
static EyeMood    g_mood = MOOD_COUNT;        // MOOD_COUNT = custom (set via eyes_set)
static uint32_t   g_rgb[2] = {0, 0};          // [0] left, [1] right
static EyePattern g_pattern = PAT_SOLID;
static uint16_t   g_period = 0;
static unsigned long g_since = 0;             // animation start
static unsigned long g_last_frame = 0;
static bool       g_happy_timer = false;
static unsigned long g_happy_until = 0;
static bool       g_dirty = true;             // force a redraw on next tick
static uint32_t   g_frame[2][9];
static uint32_t   g_shown[2][9];

// ---- Helpers ------------------------------------------------------------------------
static uint32_t scale(uint32_t rgb, float k) {
  if (k <= 0.0f) return 0;
  if (k > 1.0f) k = 1.0f;
  uint32_t r = (uint32_t)(((rgb >> 16) & 0xFF) * k + 0.5f);
  uint32_t g = (uint32_t)(((rgb >> 8) & 0xFF) * k + 0.5f);
  uint32_t b = (uint32_t)((rgb & 0xFF) * k + 0.5f);
  return (r << 16) | (g << 8) | b;
}

// Smooth 0..1..0 over `period` (starts dark).
static float wave(unsigned long t, uint16_t period) {
  float p = (float)(t % period) / (float)period;
  return 0.5f - 0.5f * cosf(p * 6.2831853f);
}

static uint32_t xorshift(uint32_t x) {
  x ^= x << 13; x ^= x >> 17; x ^= x << 5;
  return x;
}

static void fill_eye(int eye, uint32_t rgb) {
  for (int i = 0; i < 9; i++) g_frame[eye][i] = rgb;
}

// Render the current pattern at time t (ms since it started) into g_frame.
static void render(unsigned long t) {
  memset(g_frame, 0, sizeof(g_frame));
  uint16_t period = g_period ? g_period : DEFAULT_PERIOD[g_pattern];

  switch (g_pattern) {
    case PAT_SOLID:
      for (int e = 0; e < 2; e++) fill_eye(e, g_rgb[e]);
      break;

    case PAT_BLINK:                            // on for the first half, off for the second
      if (t % period < period / 2u)
        for (int e = 0; e < 2; e++) fill_eye(e, g_rgb[e]);
      break;

    case PAT_BREATHE: {                        // 10% .. 100%
      float k = 0.10f + 0.90f * wave(t, period);
      for (int e = 0; e < 2; e++) fill_eye(e, scale(g_rgb[e], k));
      break;
    }

    case PAT_PULSE: {                          // fast rise (12%), slow fade, floor 12%
      float p = (float)(t % period) / (float)period;
      float k = p < 0.12f ? p / 0.12f : 1.0f - (p - 0.12f) / 0.88f;
      k = 0.12f + 0.88f * k * k;
      for (int e = 0; e < 2; e++) fill_eye(e, scale(g_rgb[e], k));
      break;
    }

    case PAT_SPARKLE: {                        // ~40% of pixels lit, random brightness
      uint32_t x = (uint32_t)(t / SPARKLE_STEP_MS) * 2654435761u + 0x9E3779B9u;
      for (int e = 0; e < 2; e++)
        for (int i = 0; i < 9; i++) {
          x = xorshift(x);
          if ((x >> 8) % 10 < 4) g_frame[e][i] = scale(g_rgb[e], 0.35f + 0.65f * ((x >> 16) & 0xFF) / 255.0f);
        }
      break;
    }

    case PAT_DOUBLE_BLINK: {                   // off, on, off at the start of each period
      unsigned long p = t % period;
      bool off = p < BLINK_MS || (p >= 2 * BLINK_MS && p < 3 * BLINK_MS);
      if (!off) for (int e = 0; e < 2; e++) fill_eye(e, g_rgb[e]);
      break;
    }

    case PAT_GLOW: {                           // faint: 8% .. 60%
      float k = 0.08f + 0.52f * wave(t, period);
      for (int e = 0; e < 2; e++) fill_eye(e, scale(g_rgb[e], k));
      break;
    }

    case PAT_HALF:                             // middle row (pixels 3,4,5)
      for (int e = 0; e < 2; e++)
        for (int i = 3; i <= 5; i++) g_frame[e][i] = g_rgb[e];
      break;

    case PAT_SWEEP: {                          // positions 0..5 = left cols 0-2, right cols 0-2
      uint16_t step_ms = period / 10; if (step_ms == 0) step_ms = 1;
      int s = (int)((t / step_ms) % 10);       // 0..9 -> 0,1,2,3,4,5,4,3,2,1
      int pos = s <= 5 ? s : 10 - s;
      int e = pos / 3, col = pos % 3;
      for (int row = 0; row < 3; row++) g_frame[e][row * 3 + col] = g_rgb[e];
      break;
    }

    default: break;
  }
}

// ---- API ----------------------------------------------------------------------------
void eyes_begin() {
  eyes_hw_begin();
  memset(g_shown, 0, sizeof(g_shown));
  g_mood = MOOD_COUNT;
  eyes_set_mood(MOOD_CALM);
}

void eyes_set(uint32_t left_rgb, uint32_t right_rgb, EyePattern pattern, uint16_t period_ms) {
  if (pattern >= PAT_COUNT) pattern = PAT_SOLID;
  g_rgb[0] = left_rgb & 0xFFFFFF;
  g_rgb[1] = right_rgb & 0xFFFFFF;
  g_pattern = pattern;
  g_period = period_ms;
  g_since = millis();
  g_mood = MOOD_COUNT;                         // custom until eyes_set_mood says otherwise
  g_happy_timer = false;
  g_dirty = true;
}

void eyes_set_mood(EyeMood mood) {
  if (mood >= MOOD_COUNT) return;
  if (mood == g_mood && mood != MOOD_HAPPY) return;   // same mood: keep animation running
  const MoodSpec& m = MOODS[mood];
  eyes_set(m.rgb, m.rgb, m.pattern, m.period_ms);
  g_mood = mood;
  if (mood == MOOD_HAPPY) { g_happy_timer = true; g_happy_until = g_since + HAPPY_MS; }
}

bool eyes_set_mood_name(const char* name) {
  if (!name) return false;
  for (int i = 0; i < MOOD_COUNT; i++)
    if (strcmp(name, MOODS[i].name) == 0) { eyes_set_mood((EyeMood)i); return true; }
  return false;
}

EyeMood eyes_mood() { return g_mood; }

const char* eyes_mood_name(EyeMood mood) {
  return mood < MOOD_COUNT ? MOODS[mood].name : "custom";
}

bool eyes_pattern_from_name(const char* name, EyePattern* out) {
  if (!name) return false;
  for (int i = 0; i < PAT_COUNT; i++)
    if (strcmp(name, PATTERN_NAMES[i]) == 0) { if (out) *out = (EyePattern)i; return true; }
  return false;
}

void eyes_tick() {
  unsigned long now = millis();
  if (g_happy_timer && (long)(now - g_happy_until) >= 0) eyes_set_mood(MOOD_CALM);
  if (!g_dirty && now - g_last_frame < FRAME_MS) return;
  g_last_frame = now;
  g_dirty = false;

  render(now - g_since);
  if (memcmp(g_frame, g_shown, sizeof(g_frame)) != 0) {   // only push when something changed
    memcpy(g_shown, g_frame, sizeof(g_frame));
    eyes_hw_show(g_shown[0], g_shown[1]);
  }
}
