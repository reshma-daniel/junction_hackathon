// behavior.cpp — owner: Reshma. Wake up, then alternate idle/search; "Charlie" -> happy.
#include "behavior.h"
#include "eyes.h"
#include "mic.h"
#include <stdio.h>

#ifdef ARDUINO
#include <Arduino.h>
#else
unsigned long millis();   // provided by host test
#endif

// ---- Tunables -----------------------------------------------------------------------
static const uint32_t BEH_WAKE_SLEEPY_MS = 2000;   // half-closed eyes ...
static const uint32_t BEH_WAKE_MS        = 3000;   // ... then two blinks, awake after 3 s
static const uint32_t BEH_IDLE_MS        = 4000;   // calm this long, then look around
static const uint32_t BEH_SEARCH_MS      = 4000;   // look around this long, then calm again
static const uint32_t BEH_HAPPY_MS       = 2000;   // happy reaction to "Charlie"
static const uint32_t BEH_AWAKE_BLUE     = 0x3C78FF;

static BehaviorState g_beh_state = BEH_WAKE;
static unsigned long g_beh_since = 0;
static bool g_beh_wake_blinking = false;

static const char* const BEH_NAMES[] = {"wake", "idle", "search", "happy"};

static void beh_enter(BehaviorState s) {
  g_beh_state = s;
  g_beh_since = millis();
  switch (s) {
    case BEH_WAKE:   eyes_set_mood(MOOD_SLEEPY); g_beh_wake_blinking = false; break;
    case BEH_IDLE:   eyes_set_mood(MOOD_CALM); break;
    case BEH_SEARCH: eyes_set_mood(MOOD_SEARCHING); break;   // TODO(Sara): motion_set_mode(MODE_FOLLOW)
    case BEH_HAPPY:  eyes_set_mood(MOOD_HAPPY); break;       // TODO(Sara): motion_set_mode(MODE_COME)
                                                             // TODO(Wiam): audio_bark(2)
  }
  char buf[64];
  snprintf(buf, sizeof buf, "{\"type\":\"robot.behavior\",\"state\":\"%s\"}", BEH_NAMES[s]);
  comms_send(buf);
}

void behavior_begin() { beh_enter(BEH_WAKE); }

void behavior_tick() {
  if (mic_called()) { beh_enter(BEH_HAPPY); return; }     // "Charlie" wins in every state

  unsigned long t = millis() - g_beh_since;
  switch (g_beh_state) {
    case BEH_WAKE:
      if (t >= BEH_WAKE_MS) { beh_enter(BEH_IDLE); return; }
      if (t >= BEH_WAKE_SLEEPY_MS && !g_beh_wake_blinking) {   // eyes open: two quick blue blinks
        eyes_set(BEH_AWAKE_BLUE, BEH_AWAKE_BLUE, PAT_BLINK, 500);
        g_beh_wake_blinking = true;
      }
      return;
    case BEH_HAPPY:
      if (t >= BEH_HAPPY_MS) beh_enter(BEH_IDLE);
      return;
    case BEH_IDLE:
      if (t >= BEH_IDLE_MS) { beh_enter(BEH_SEARCH); return; }
      break;
    case BEH_SEARCH:
      if (t >= BEH_SEARCH_MS) { beh_enter(BEH_IDLE); return; }
      break;
  }

  // IDLE / SEARCH: white "listening" eyes while someone speaks, otherwise the state's mood
  EyeMood base = (g_beh_state == BEH_IDLE) ? MOOD_CALM : MOOD_SEARCHING;
  EyeMood want = mic_talking() ? MOOD_LISTENING : base;
  if (eyes_mood() != want) eyes_set_mood(want);
}

BehaviorState behavior_state() { return g_beh_state; }
const char* behavior_state_name(BehaviorState s) { return s <= BEH_HAPPY ? BEH_NAMES[s] : "?"; }
