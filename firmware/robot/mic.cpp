// mic.cpp — owner: Reshma. Background-noise tracking + "one short word" call detector.
#include "mic.h"
#include <stdio.h>

#ifdef ARDUINO
#include <Arduino.h>
#else
unsigned long millis();   // provided by host test
#endif

// ---- Tunables (tune on the robot with robot_mic/test_mic_live.py) -----------------
static const uint16_t STEP_MS            = 20;     // analyse the level 50x per second
static const float    START_RATIO        = 3.0f;   // a sound starts above floor x 3 ...
static const int      START_MIN_DELTA    = 150;    // ... and at least floor + 150
static const float    END_RATIO          = 2.0f;   // it continues while above floor x 2 ...
static const int      END_MIN_DELTA      = 80;     // ... and floor + 80
static const uint16_t WORD_MIN_MS        = 250;    // shorter = clap / knock
static const uint16_t WORD_MAX_MS        = 1200;   // longer  = sentence / music
static const uint16_t QUIET_AFTER_MS     = 400;    // quiet needed after the word (also bridges syllable gaps)
static const uint16_t COOLDOWN_MS        = 1500;   // min time between two calls
static const uint16_t MUTE_AFTER_PLAY_MS = 1000;   // ignore the room this long after our own speaker
static const uint16_t FLOOR_TAU_MS       = 2000;   // background noise adapts over ~2 s
static const int      FLOOR_MIN          = 30;
static const uint16_t STUCK_MS           = 5000;   // a "sound" this long is the new background
static const float    LEVEL_FULL         = 4000.0f;// RMS that maps to level 1.0
static const uint16_t SOUND_REPORT_MS    = 200;    // robot.sound at 5 Hz

// ---- State ------------------------------------------------------------------------
enum Phase : uint8_t { P_QUIET, P_SOUND, P_AFTER };  // AFTER = word may be over, waiting for quiet
static Phase g_phase = P_QUIET;
static float g_floor = FLOOR_MIN;
static bool  g_floor_init = false;
static int   g_level = 0;
static unsigned long g_last_step = 0, g_last_report = 0;
static unsigned long g_seg_start = 0, g_last_loud = 0;
static unsigned long g_muted_until = 0;
static unsigned long g_last_call_at = 0;
static bool  g_has_called = false;
static bool  g_called = false;
static uint16_t g_last_call_ms = 0;

static float maxf(float a, float b) { return a > b ? a : b; }

static void classify(unsigned long now) {
  unsigned long dur = g_last_loud - g_seg_start + STEP_MS;
  if (dur < WORD_MIN_MS || dur > WORD_MAX_MS) return;              // clap or sentence
  if (g_has_called && now - g_last_call_at < COOLDOWN_MS) return;  // too soon after the last call
  g_called = true;
  g_has_called = true;
  g_last_call_at = now;
  g_last_call_ms = (uint16_t)dur;
  char buf[64];
  snprintf(buf, sizeof buf, "{\"type\":\"robot.heard\",\"kind\":\"call\",\"ms\":%u}", (unsigned)dur);
  comms_send(buf);
}

// ---- API ----------------------------------------------------------------------------
void mic_begin() {
  mic_hw_begin();
  g_phase = P_QUIET;
  g_floor_init = false;
  g_called = g_has_called = false;
  g_muted_until = 0;
  g_last_step = g_last_report = millis();
}

void mic_tick() {
  unsigned long now = millis();
  if (now - g_last_step < STEP_MS) return;
  g_last_step = now;

  int lvl = mic_hw_level();
  if (lvl < 0) lvl = 0;
  g_level = lvl;
  if (!g_floor_init) { g_floor = maxf((float)lvl, (float)FLOOR_MIN); g_floor_init = true; }

  float start_th = maxf(g_floor * START_RATIO, g_floor + START_MIN_DELTA);
  float end_th   = maxf(g_floor * END_RATIO,   g_floor + END_MIN_DELTA);

  bool playing = audio_is_playing();
  if (playing) g_muted_until = now + MUTE_AFTER_PLAY_MS;
  bool muted = playing || (long)(now - g_muted_until) < 0;

  if (muted) {
    g_phase = P_QUIET;                                  // drop any half-heard sound
  } else {
    switch (g_phase) {
      case P_QUIET:
        if (lvl >= start_th) { g_phase = P_SOUND; g_seg_start = g_last_loud = now; }
        else {                                          // learn the background noise
          g_floor += (lvl - g_floor) * ((float)STEP_MS / FLOOR_TAU_MS);
          if (g_floor < FLOOR_MIN) g_floor = FLOOR_MIN;
        }
        break;
      case P_SOUND:
        if (lvl >= end_th) g_last_loud = now;
        else g_phase = P_AFTER;
        if (now - g_seg_start > STUCK_MS) {              // fan/music: accept it as background
          g_floor = (float)lvl; g_phase = P_QUIET;
        }
        break;
      case P_AFTER:
        if (lvl >= end_th) { g_phase = P_SOUND; g_last_loud = now; }        // next syllable / word
        else if (now - g_last_loud >= QUIET_AFTER_MS) { classify(now); g_phase = P_QUIET; }
        break;
    }
  }

  if (now - g_last_report >= SOUND_REPORT_MS) {
    g_last_report = now;
    char buf[64];
    snprintf(buf, sizeof buf, "{\"type\":\"robot.sound\",\"level\":%.3f,\"loud\":%s}",
             (double)mic_level(), mic_loud() ? "true" : "false");
    comms_send(buf);
  }
}

float mic_level() {
  float v = g_level / LEVEL_FULL;
  return v > 1.0f ? 1.0f : v;
}

bool mic_loud()    { return g_phase == P_SOUND; }
bool mic_talking() { return g_phase != P_QUIET; }

bool mic_called() {
  if (!g_called) return false;
  g_called = false;
  return true;
}

uint16_t mic_last_call_ms() { return g_last_call_ms; }
