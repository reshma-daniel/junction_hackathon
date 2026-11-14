// motion.cpp — owner: Sara
#include "motion.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef ARDUINO
#include <Arduino.h>
#else
unsigned long millis();   // provided by host test
#endif

// ---- Tunables (shared/config.yaml values mirrored here; tune on hardware) ----
static const int   OBSTACLE_STOP_MM = 250;   // config: obstacle_stop_mm
static const int   FOLLOW_MM        = 400;   // config: follow_distance_mm
static const int   FOLLOW_NEAR_MM   = 300;   // tracking window
static const int   FOLLOW_FAR_MM    = 1200;
static const int   MIN_PWM          = 170;   // measured 2026-11-14: port 9 starts at 170, others at <=160
static const int   CRUISE           = 150;   // walk speed
static const int   TURN_SPEED       = 130;
static const int   RAMP_PER_S       = 500;   // PWM units per second
static const uint32_t TURN_MIN_MS   = 400;
static const uint32_t TURN_MAX_MS   = 2500;
static const int   CLEAR_MM         = OBSTACLE_STOP_MM + 150;
static const uint32_t COME_HOLD_MS  = 500;
static const uint32_t STATE_PERIOD_MS = 1000;

static MotionMode g_mode = MODE_IDLE;
static float cur_l = 0, cur_r = 0;       // ramped output (pre min-PWM mapping)
static int   tgt_l = 0, tgt_r = 0;
static unsigned long last_ms = 0, last_state_ms = 0;
static bool  last_out_nonzero = false;

// walk sub-state
static bool  turning = false;
static int   turn_dir = 1;               // +1 = turn right, -1 = turn left
static unsigned long turn_start = 0;
// come
static unsigned long come_since = 0;

static int clampi(int v, int lo, int hi) { return v < lo ? lo : (v > hi ? hi : v); }

static void set_target(int l, int r) {
  tgt_l = clampi(l, -255, 255);
  tgt_r = clampi(r, -255, 255);
}

static int apply_min_pwm(float v) {
  // Map (0,255] -> [MIN_PWM,255] so small commands still move, 0 stays 0.
  if (v > -0.5f && v < 0.5f) return 0;
  float a = v < 0 ? -v : v;
  int out = MIN_PWM + (int)(a * (255 - MIN_PWM) / 255.0f);
  return v < 0 ? -out : out;
}

static void reset_substates() { turning = false; come_since = 0; }

void motion_set_mode(MotionMode m) {
  if (m == g_mode) return;
  g_mode = m;
  reset_substates();
  if (m == MODE_IDLE || m == MODE_STOP) { motion_stop(); }
}

bool motion_set_mode_name(const char* n) {
  if (!n) return false;
  if (!strcmp(n, "idle"))   { motion_set_mode(MODE_IDLE);   return true; }
  if (!strcmp(n, "walk"))   { motion_set_mode(MODE_WALK);   return true; }
  if (!strcmp(n, "follow")) { motion_set_mode(MODE_FOLLOW); return true; }
  if (!strcmp(n, "come"))   { motion_set_mode(MODE_COME);   return true; }
  if (!strcmp(n, "stop"))   { motion_set_mode(MODE_STOP);   return true; }
  return false;
}

void motion_drive(int l, int r) {
  g_mode = MODE_MANUAL;
  reset_substates();
  set_target(l, r);
}

void motion_stop() {
  tgt_l = tgt_r = 0;
  cur_l = cur_r = 0;
  motion_hw_write(0, 0);
  last_out_nonzero = false;
}

MotionMode motion_mode() { return g_mode; }
bool motion_driving() { return last_out_nonzero; }

// ---- Mode behaviours -------------------------------------------------------
static void do_walk(const Range& r, unsigned long now) {
  if (turning) {
    bool timed = now - turn_start >= TURN_MIN_MS;
    bool clear = r.min_mm >= CLEAR_MM;
    if ((timed && clear) || now - turn_start >= TURN_MAX_MS) turning = false;
    else { set_target(turn_dir * TURN_SPEED, -turn_dir * TURN_SPEED); return; }
  }
  if (r.blocked || r.min_mm < OBSTACLE_STOP_MM) {
    turning = true;
    turn_start = now;
    turn_dir = (r.left_mm > r.right_mm) ? -1 : 1;  // toward the freer side
    // stop first (ramp down), turning begins next tick via target
    set_target(0, 0);
    cur_l = cur_r = 0;
    return;
  }
  set_target(CRUISE, CRUISE);
}

// Shared by follow/come. Returns true if a target is tracked.
static bool do_follow(const Range& r) {
  if (r.min_mm < FOLLOW_NEAR_MM - 100 || r.min_mm > FOLLOW_FAR_MM) {
    set_target(0, 0);            // nobody in window: hold still
    return false;
  }
  int err = r.min_mm - FOLLOW_MM;                 // + = too far
  int fwd = abs(err) < 50 ? 0 : clampi(err / 4, -80, CRUISE);
  if (fwd < 0) fwd = 0;                           // never reverse blind
  int steer = (int)(r.bearing * 100.0f);          // +bearing = user on right
  if (abs(steer) < 12) steer = 0;                 // deadband
  set_target(fwd + steer, fwd - steer);
  return true;
}

static void do_come(const Range& r, unsigned long now) {
  bool tracked = do_follow(r);
  if (tracked && abs(r.min_mm - FOLLOW_MM) < 60) {
    if (!come_since) come_since = now;
    if (now - come_since >= COME_HOLD_MS) motion_set_mode(MODE_IDLE);
  } else {
    come_since = 0;
  }
}

// ---- Safety + output ------------------------------------------------------
static void apply_safety(const Range& r) {
  // Forward motion is never allowed within obstacle_stop_mm, whatever the mode.
  // Remove the forward component, keep any turning component.
  if (r.min_mm < OBSTACLE_STOP_MM || r.blocked) {
    int fwd = (tgt_l + tgt_r) / 2;
    if (fwd > 0) { tgt_l -= fwd; tgt_r -= fwd; }
    float cf = (cur_l + cur_r) / 2;
    if (cf > 0) { cur_l -= cf; cur_r -= cf; }
  }
}

static void ramp(float& cur, int tgt, float step) {
  if (cur < tgt) { cur += step; if (cur > tgt) cur = tgt; }
  else if (cur > tgt) { cur -= step; if (cur < tgt) cur = tgt; }
}

static void send_state(unsigned long now) {
  static const char* names[] = {"idle", "walk", "follow", "come", "stop", "manual"};
  char buf[96];
  snprintf(buf, sizeof buf, "{\"type\":\"robot.state\",\"mode\":\"%s\",\"driving\":%s}",
           names[g_mode], last_out_nonzero ? "true" : "false");
  comms_send(buf);
  last_state_ms = now;
}

void motion_tick() {
  unsigned long now = millis();
  float dt = (now - last_ms) / 1000.0f;
  if (dt > 0.1f) dt = 0.1f;          // avoid jumps after a stall
  last_ms = now;

  Range r = range_get();

  if (comms_watchdog_tripped()) {
    motion_stop();
    if (g_mode != MODE_IDLE) g_mode = MODE_IDLE;
  } else {
    switch (g_mode) {
      case MODE_WALK:   do_walk(r, now);  break;
      case MODE_FOLLOW: do_follow(r);     break;
      case MODE_COME:   do_come(r, now);  break;
      case MODE_IDLE:
      case MODE_STOP:   set_target(0, 0); break;
      case MODE_MANUAL: break;            // target set by motion_drive
    }
    apply_safety(r);
    float step = RAMP_PER_S * dt;
    ramp(cur_l, tgt_l, step);
    ramp(cur_r, tgt_r, step);
    int ol = apply_min_pwm(cur_l), or_ = apply_min_pwm(cur_r);
    motion_hw_write(ol, or_);
    last_out_nonzero = (ol != 0 || or_ != 0);
  }

  if (now - last_state_ms >= STATE_PERIOD_MS) send_state(now);
}
