// Host test: g++ -std=c++11 -I.. ../behavior.cpp ../eyes.cpp test_behavior.cpp -o /tmp/test_behavior && /tmp/test_behavior
#include "../behavior.h"
#include "../eyes.h"
#include "../mic.h"
#include <stdio.h>

static unsigned long now_ms = 1000;
static bool fake_called = false, fake_talking = false;
unsigned long millis() { return now_ms; }
void eyes_hw_begin() {}
void eyes_hw_show(const uint32_t*, const uint32_t*) {}
bool mic_called() { bool c = fake_called; fake_called = false; return c; }
bool mic_talking() { return fake_talking; }
void comms_send(const char*) {}

static int fails = 0;
#define CHECK(c) do { if (!(c)) { printf("FAIL line %d: %s\n", __LINE__, #c); fails++; } } while (0)
static void run(int ms) { for (int i = 0; i < ms; i += 10) { now_ms += 10; behavior_tick(); eyes_tick(); } }

int main() {
  eyes_begin(); behavior_begin();

  // wake: sleepy 2 s, then blinking blue, idle at 3 s
  CHECK(behavior_state() == BEH_WAKE && eyes_mood() == MOOD_SLEEPY);
  run(2500); CHECK(behavior_state() == BEH_WAKE && eyes_mood() == MOOD_COUNT);
  run(600);  CHECK(behavior_state() == BEH_IDLE && eyes_mood() == MOOD_CALM);

  // nothing happens: idle 4 s -> search 4 s -> idle -> search ...
  run(3800); CHECK(behavior_state() == BEH_IDLE);
  run(300);  CHECK(behavior_state() == BEH_SEARCH && eyes_mood() == MOOD_SEARCHING);
  run(4000); CHECK(behavior_state() == BEH_IDLE && eyes_mood() == MOOD_CALM);
  run(4100); CHECK(behavior_state() == BEH_SEARCH);

  // "Charlie" during search -> happy 2 s -> idle, idle timer starts again
  fake_called = true; run(10);
  CHECK(behavior_state() == BEH_HAPPY && eyes_mood() == MOOD_HAPPY);
  run(2100);  CHECK(behavior_state() == BEH_IDLE && eyes_mood() == MOOD_CALM);
  run(3000); CHECK(behavior_state() == BEH_IDLE);
  run(1100); CHECK(behavior_state() == BEH_SEARCH);

  // speaking -> listening eyes, back to the state's mood after
  run(4100); CHECK(behavior_state() == BEH_IDLE);
  fake_talking = true;  run(50); CHECK(eyes_mood() == MOOD_LISTENING && behavior_state() == BEH_IDLE);
  fake_talking = false; run(50); CHECK(eyes_mood() == MOOD_CALM);

  // "Charlie" during wake-up also works
  behavior_begin(); run(500);
  fake_called = true; run(10); CHECK(behavior_state() == BEH_HAPPY);

  // laptop speaks the "called" phrase: happy held for the whole phrase (longer than 2 s), then idle
  behavior_begin(); run(3100); CHECK(behavior_state() == BEH_IDLE);
  fake_called = true; run(500); CHECK(behavior_state() == BEH_HAPPY);
  behavior_express(MOOD_HAPPY); run(10);
  CHECK(behavior_state() == BEH_EXPRESS && eyes_mood() == MOOD_HAPPY);
  run(3500); CHECK(behavior_state() == BEH_EXPRESS && eyes_mood() == MOOD_HAPPY);
  behavior_express_done(); run(10);
  CHECK(behavior_state() == BEH_IDLE && eyes_mood() == MOOD_CALM);

  // other emotions: mood held while speaking, no idle/search switching meanwhile
  behavior_express(MOOD_PLEADING); run(6000);
  CHECK(behavior_state() == BEH_EXPRESS && eyes_mood() == MOOD_PLEADING);
  fake_talking = true; run(50); CHECK(eyes_mood() == MOOD_PLEADING);   // no listening overlay
  fake_talking = false;
  behavior_express_done(); run(10); CHECK(behavior_state() == BEH_IDLE);

  // laptop never says done: back to idle after 15 s
  behavior_express(MOOD_SAD); run(14900); CHECK(behavior_state() == BEH_EXPRESS);
  run(200); CHECK(behavior_state() == BEH_IDLE && eyes_mood() == MOOD_CALM);


  if (fails) { printf("%d FAILED\n", fails); return 1; }
  printf("behavior: all tests passed\n");
  return 0;
}
