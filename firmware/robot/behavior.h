// behavior.* — owner: Reshma. The robot's own small personality (works without the laptop).
//
//   power on -> WAKE (3 s) -> IDLE (4 s) <-> SEARCH (4 s)   ... forever, when nothing happens
//   "Charlie" (mic_called) in any state -> HAPPY (2 s) -> IDLE
//   while someone is speaking in IDLE/SEARCH the eyes show "listening" (white)
//   laptop speaks a phrase -> EXPRESS: hold that mood until the laptop says "done" (max 15 s) -> IDLE
//
// Uses eyes.* and mic.*. Later hooks (marked TODO in behavior.cpp): motion (Sara), bark (Wiam).
#pragma once
#include <stdint.h>

#include "eyes.h"

enum BehaviorState : uint8_t { BEH_WAKE = 0, BEH_IDLE, BEH_SEARCH, BEH_HAPPY, BEH_EXPRESS };

void behavior_begin();          // call once in setup, after eyes_begin() and mic_begin()
void behavior_tick();           // call every loop, after mic_tick() and before eyes_tick()
void behavior_express(EyeMood mood);   // laptop starts a phrase: hold this mood (max 15 s)
void behavior_express_done();          // laptop finished the phrase: back to idle
BehaviorState behavior_state();
const char* behavior_state_name(BehaviorState s);
