// Host test: g++ -std=c++11 -I.. ../mic.cpp test_mic.cpp -o /tmp/test_mic && /tmp/test_mic
#include "../mic.h"
#include <stdio.h>
#include <string.h>

static unsigned long now_ms = 1000;
static int level = 50;
static bool playing = false;
static int heard = 0, sounds = 0;
unsigned long millis() { return now_ms; }
void mic_hw_begin() {}
int16_t mic_hw_level() { return (int16_t)level; }
bool audio_is_playing() { return playing; }
void comms_send(const char* j) {
  if (strstr(j, "\"robot.heard\"")) heard++;
  if (strstr(j, "\"robot.sound\"")) sounds++;
}

static int fails = 0;
#define CHECK(c) do { if (!(c)) { printf("FAIL line %d: %s\n", __LINE__, #c); fails++; } } while (0)
static int calls = 0;   // mic_called() is consumed every step, like the real loop does
static void run(int ms, int lvl) {
  level = lvl;
  for (int i = 0; i < ms; i += 10) { now_ms += 10; mic_tick(); if (mic_called()) calls++; }
}
static void say_word(int lvl = 1500) { run(250, lvl); run(100, 60); run(300, lvl); }  // "Char" .. "lie"

int main() {
  mic_begin();

  // silence: nothing heard, robot.sound at ~5 Hz
  run(2000, 50);
  CHECK(calls == 0 && !mic_talking() && !mic_loud());
  int s0 = sounds; run(1000, 50); CHECK(sounds - s0 >= 4 && sounds - s0 <= 6);

  // one word with a syllable gap -> exactly one call, only after the quiet that follows it
  run(100, 1500); CHECK(mic_loud() && mic_talking() && mic_level() > 0.3f);
  run(150, 1500); run(100, 60); run(300, 1500);
  run(200, 50);  CHECK(calls == 0 && mic_talking());          // still waiting for quiet
  run(800, 50);  CHECK(calls == 1 && heard == 1 && !mic_talking());
  CHECK(mic_last_call_ms() >= 600 && mic_last_call_ms() <= 750);
  CHECK(!mic_called());                                       // consumed once

  // clap: too short -> ignored
  run(2000, 50); run(80, 5000); run(1000, 50);
  CHECK(calls == 1);

  // sentence: words with short pauses merge into one long sound -> ignored
  for (int k = 0; k < 6; k++) { run(400, 1500); run(120, 50); }
  run(1000, 50);
  CHECK(calls == 1);

  // own speaker playing (and 1 s after) -> ignored
  run(2000, 50);
  playing = true;  run(600, 1500);
  playing = false; run(500, 1500); run(1500, 50);
  CHECK(calls == 1);
  say_word(); run(1000, 50);                                  // after the mute: heard again
  CHECK(calls == 2);

  // cooldown: a second word right after a call is ignored, a later one counts
  run(300, 50); say_word(); run(1000, 50);
  CHECK(calls == 2);
  run(1500, 50); say_word(); run(1000, 50);
  CHECK(calls == 3);

  // quiet word in a quiet room still counts; a tiny bump does not
  run(3000, 50); say_word(260); run(1000, 50);
  CHECK(calls == 4);
  run(2000, 50); say_word(120); run(1000, 50);
  CHECK(calls == 4);

  // constant new noise (fan) becomes the background instead of locking the detector
  run(6000, 900); run(1000, 900);
  CHECK(calls == 4 && !mic_talking());
  say_word(4000); run(1000, 900);                             // a word over the fan still counts
  CHECK(calls == 5);

  if (fails) { printf("%d FAILED\n", fails); return 1; }
  printf("mic: all tests passed\n");
  return 0;
}
