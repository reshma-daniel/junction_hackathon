#ifndef KAAMOS_MOTION_WAIT_CPP_INCLUDED
#define KAAMOS_MOTION_WAIT_CPP_INCLUDED
#include <stdint.h>

// Fixed PWM; RSSI alone triggers a return from leading.
struct MotionDrive {
  enum Phase { IDLE, STILL_WAIT, APPROACH, LEAD };
  Phase phase = IDLE;
  int target = 0, speed = 0;
  bool armed = false, reversing = false;
  uint32_t lastContact = 0, stoppedAt = 0, stillSince = 0;
  bool initialRssiValid = false, started = false;
  bool sessionActive = false;
  bool returning = false;
  int lastMoving = -1;
  bool leadRssiValid = false;
  // Calibrated close-range signal reference, not a measured physical distance.
  static constexpr float CLOSE_RSSI_DBM = -80.0f;
  // 10*log10(1/0.8): a 20% drop in received power, not 20% of dBm.
  static constexpr float RETURN_DROP_DB = 0.96910f;
  float initialRssi = 0, leadInitialRssi = 0;

  const char* phaseName() const {
    switch (phase) {
      case STILL_WAIT: return "still_wait";
      case APPROACH: return returning ? "return" : "approach";
      case LEAD: return "lead";
      default: return "idle";
    }
  }
  void setTarget(int next, uint32_t now) {
    if (next == target) return;
    if (speed && next && ((speed > 0) != (next > 0))) {
      speed = 0; reversing = true; stoppedAt = now;
    }
    target = next;
    if (!next) { speed = 0; reversing = false; }
  }
  void approach(uint32_t now, bool isReturn = false) {
    phase = APPROACH; started = true;
    returning = isReturn;
    setTarget(255, now);
  }
  void lead(uint32_t now) {
    phase = LEAD; returning = false;
    leadInitialRssi = initialRssi; leadRssiValid = initialRssiValid;
    setTarget(-255, now);
  }
  void receive(bool moving, uint32_t now) {
    if (!sessionActive) beginSession();
    lastContact = now; armed = true;
    // Do not let repeated true reports undo an RSSI-triggered return.
    bool changed = lastMoving != int(moving);
    lastMoving = int(moving);
    if (!changed) return;
    if (!moving) {
      if (!started) {
        phase = STILL_WAIT; stillSince = now;
        setTarget(0, now);
      }
    } else if (started && phase == APPROACH && !returning) {
      lead(now);
    } else if (phase == STILL_WAIT) {
      phase = IDLE; setTarget(0, now);
    }
  }
  void ping(uint32_t now) { if (armed) lastContact = now; }
  void stop() {
    phase = IDLE; target = speed = 0; armed = reversing = false;
    initialRssiValid = started = leadRssiValid = false;
    lastMoving = -1;
    sessionActive = false;
    returning = false;
  }
  void beginSession() { stop(); sessionActive = true; }
  void tick(uint32_t now, bool rssiFresh, float rssi) {
    // Capture once at bridge session start, before the first departure. Do not
    // overwrite this when approaching, leading, reversing or receiving duplicates.
    if (sessionActive && !initialRssiValid && rssiFresh) {
      initialRssi = rssi; initialRssiValid = true;
    }
    if (!armed) return;
    if (uint32_t(now - lastContact) >= 3000) { stop(); return; }
    if (phase == STILL_WAIT && uint32_t(now - stillSince) >= 10000 && rssiFresh) {
      approach(now);
    }
    if (phase != APPROACH && phase != LEAD) return;
    if (!rssiFresh) {
      setTarget(0, now);
      return;
    }
    if (phase == LEAD && !leadRssiValid) {
      leadInitialRssi = initialRssi; leadRssiValid = true;
    }
    // Check every loop with a fresh smoothed RSSI, not only at trend windows.
    if (phase == LEAD && rssi < CLOSE_RSSI_DBM && rssi <= leadInitialRssi - RETURN_DROP_DB) {
      approach(now, true);
    } else if (phase == APPROACH && returning && rssi >= CLOSE_RSSI_DBM) {
      lead(now);
    }
    setTarget(phase == APPROACH ? 255 : -255, now);
    if (reversing) {
      if (uint32_t(now - stoppedAt) < 200) return;
      reversing = false;
    }
    speed = target;
  }
};

#endif
