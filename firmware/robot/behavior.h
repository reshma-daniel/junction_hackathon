// behavior.* — owner: Reshma. The robot's own small personality (works without the laptop).
//
//   power on -> WAKE (3 s) -> IDLE (4 s) <-> SEARCH (4 s)   ... forever, when nothing happens
//   "Charlie" (mic_called) in any state -> HAPPY (2 s) -> IDLE
//   while someone is speaking in IDLE/SEARCH the eyes show "listening" (white)
//
// Uses eyes.* and mic.*. Later hooks (marked TODO in behavior.cpp): motion (Sara), bark (Wiam).
#pragma once
#include <stdint.h>

enum BehaviorState : uint8_t { BEH_WAKE = 0, BEH_IDLE, BEH_SEARCH, BEH_HAPPY };

void behavior_begin();          // call once in setup, after eyes_begin() and mic_begin()
void behavior_tick();           // call every loop, after mic_tick() and before eyes_tick()
BehaviorState behavior_state();
const char* behavior_state_name(BehaviorState s);
