// Host test: g++ -std=c++11 -I.. ../eyes.cpp test_eyes.cpp -o /tmp/test_eyes && /tmp/test_eyes
#include "../eyes.h"
#include <stdio.h>
#include <string.h>

static unsigned long now_ms = 1000;
static uint32_t L[9], R[9];
static int shows = 0;
unsigned long millis() { return now_ms; }
void eyes_hw_begin() {}
void eyes_hw_show(const uint32_t l[9], const uint32_t r[9]) {
  memcpy(L, l, sizeof(L)); memcpy(R, r, sizeof(R)); shows++;
}

static int fails = 0;
#define CHECK(c) do { if (!(c)) { printf("FAIL line %d: %s\n", __LINE__, #c); fails++; } } while (0)
static void run(int ms) { for (int i = 0; i < ms; i += 10) { now_ms += 10; eyes_tick(); } }
static int R8(uint32_t c) { return (c >> 16) & 0xFF; }
static int G8(uint32_t c) { return (c >> 8) & 0xFF; }
static int B8(uint32_t c) { return c & 0xFF; }
static int lit(const uint32_t* px) { int n = 0; for (int i = 0; i < 9; i++) n += px[i] != 0; return n; }
static int peak(const uint32_t* px) {
  int m = 0;
  for (int i = 0; i < 9; i++) { int v = R8(px[i]) > G8(px[i]) ? R8(px[i]) : G8(px[i]); if (B8(px[i]) > v) v = B8(px[i]); if (v > m) m = v; }
  return m;
}

int main() {
  eyes_begin(); eyes_tick();
  CHECK(eyes_mood() == MOOD_CALM);

  // calm: soft blue, whole eye, slow blink 1.5 s on / 1.5 s off
  CHECK(lit(L) == 9 && lit(R) == 9);
  CHECK(B8(L[4]) > R8(L[4]) && B8(L[4]) > G8(L[4]));
  run(1000); CHECK(lit(L) == 9);                               // t=1.0 s on
  run(700);  CHECK(lit(L) == 0 && lit(R) == 0);                // t=1.7 s off

  // same mood again does not restart the animation (a restart would turn it back on)
  eyes_set_mood(MOOD_CALM); run(30); CHECK(lit(L) == 0);
  run(1400); CHECK(lit(L) == 9);                               // t=3.1 s next cycle, on

  // listening: bright white, steady, no redraws while nothing changes
  eyes_set_mood(MOOD_LISTENING); run(50);
  CHECK(L[0] == 0xFFFFFF && R[8] == 0xFFFFFF && lit(L) == 9);
  int s = shows; run(1000); CHECK(shows == s);

  // happy: green, very fast blink (0.1 s on / 0.1 s off), then calm after 2 s
  eyes_set_mood(MOOD_HAPPY); run(50);
  CHECK(eyes_mood() == MOOD_HAPPY);
  CHECK(lit(L) == 9 && G8(L[4]) > R8(L[4]) && G8(L[4]) > B8(L[4]));   // t=0.05 on
  run(100); CHECK(lit(L) == 0);                                        // t=0.15 off
  run(100); CHECK(lit(L) == 9);                                        // t=0.25 on
  run(1900); CHECK(eyes_mood() == MOOD_CALM);

  // pleading: warm amber, blink once a second (0.5 s on / 0.5 s off)
  eyes_set_mood(MOOD_PLEADING); run(100);
  CHECK(lit(L) == 9 && R8(L[4]) > G8(L[4]) && G8(L[4]) > B8(L[4]));   // t=0.1 on
  run(500); CHECK(lit(L) == 0);                                        // t=0.6 off
  run(500); CHECK(lit(L) == 9);                                        // t=1.1 on again

  // encouraging: turquoise, steady with two quick blinks every 2 s
  eyes_set_mood(MOOD_ENCOURAGING);
  run(50);  CHECK(lit(L) == 0);                                // blink 1
  run(100); CHECK(lit(L) == 9);
  run(100); CHECK(lit(L) == 0);                                // blink 2
  run(400); CHECK(lit(L) == 9 && G8(L[0]) > R8(L[0]) && B8(L[0]) > R8(L[0]));
  run(1000); CHECK(lit(L) == 9);
  run(400); CHECK(lit(L) == 0);                                // next period, blink 1

  // sad: dim purple, slow glow, never off, never brighter than ~60 %
  eyes_set_mood(MOOD_SAD);
  int sad_max = 0, sad_min = 255;
  for (int k = 0; k < 70; k++) {
    run(100);
    if (peak(L) > sad_max) sad_max = peak(L);
    if (peak(L) < sad_min) sad_min = peak(L);
  }
  CHECK(sad_min > 0 && sad_max <= 0xC8 * 61 / 100 && sad_max > sad_min * 4);
  CHECK(B8(L[4]) > G8(L[4]) && R8(L[4]) > G8(L[4]));

  // sleepy: dim orange, only the middle row
  eyes_set_mood(MOOD_SLEEPY); run(50);
  CHECK(lit(L) == 3 && L[3] && L[4] && L[5] && lit(R) == 3);
  CHECK(R8(L[4]) > G8(L[4]) && B8(L[4]) == 0 && R8(L[4]) < 0x80);

  // searching: one pale-blue column sweeping across both eyes and back
  eyes_set_mood(MOOD_SEARCHING); run(10);
  CHECK(lit(L) == 3 && lit(R) == 0 && L[0] && L[3] && L[6]);  // left eye, column 0
  run(900); CHECK(lit(L) == 0 && lit(R) == 3 && R[0]);        // t=0.91 s right eye, column 0
  run(600); CHECK(lit(R) == 3 && R[2]);                        // t=1.51 s right eye, column 2 (far end)
  run(600); CHECK(lit(R) == 3 && R[0]);                        // t=2.11 s coming back

  // names
  CHECK(eyes_set_mood_name("sad") && eyes_mood() == MOOD_SAD);
  CHECK(!eyes_set_mood_name("angry") && eyes_mood() == MOOD_SAD);
  EyePattern p; CHECK(eyes_pattern_from_name("sweep", &p) && p == PAT_SWEEP);
  CHECK(strcmp(eyes_mood_name(MOOD_ENCOURAGING), "encouraging") == 0);

  // raw robot.eyes: different colour per eye
  eyes_set(0xFF0000, 0x0000FF, PAT_SOLID, 0); run(50);
  CHECK(L[4] == 0xFF0000 && R[4] == 0x0000FF && eyes_mood() == MOOD_COUNT);

  if (fails) { printf("%d FAILED\n", fails); return 1; }
  printf("eyes: all tests passed\n");
  return 0;
}
