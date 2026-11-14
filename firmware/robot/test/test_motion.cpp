// Host test: g++ -std=c++11 -I.. ../motion.cpp test_motion.cpp -o /tmp/test_motion && /tmp/test_motion
#include "../motion.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned long now_ms = 1000;
static Range fake = {2000, 2000, 2000, 0.0f, false};
static bool wd = false;
static int out_l, out_r, states;
unsigned long millis() { return now_ms; }
Range range_get() { fake.blocked = fake.min_mm < 250; return fake; }
bool comms_watchdog_tripped() { return wd; }
void comms_send(const char* j) { if (strstr(j, "robot.state")) states++; }
void motion_hw_write(int l, int r) { out_l = l; out_r = r; }

static int fails = 0;
#define CHECK(c) do { if (!(c)) { printf("FAIL line %d: %s\n", __LINE__, #c); fails++; } } while (0)
static void run(int ms) { for (int i = 0; i < ms; i += 20) { now_ms += 20; motion_tick(); } }

int main() {
  motion_tick();
  // ramp: no jump, min PWM applied
  motion_drive(200, 200); now_ms += 20; motion_tick();
  CHECK(out_l > 0 && out_l < 200);
  run(1000); CHECK(out_l == 170 + 200 * (255 - 170) / 255);
  motion_drive(5, 5); run(2000); CHECK(out_l >= 170);        // small cmd still moves
  // safety in manual mode: obstacle kills forward motion
  motion_drive(200, 200); run(500);
  fake.min_mm = 200; run(100); CHECK(out_l == 0 && out_r == 0);
  fake.min_mm = 2000; fake.left_mm = fake.right_mm = 2000;
  // walk: forward, blocked -> turn to freer (left) side, then continue
  motion_set_mode_name("walk"); run(1000); CHECK(out_l > 0 && out_r > 0);
  fake.min_mm = 150; fake.left_mm = 900; fake.right_mm = 100; run(200);
  CHECK(out_l < 0 && out_r > 0);                              // left turn
  fake.min_mm = 1500; fake.left_mm = fake.right_mm = 1500; run(1500);
  CHECK(out_l > 0 && out_r > 0);                              // resumed forward
  // follow: far target -> forward, bearing right -> left wheel faster
  motion_set_mode_name("follow"); fake.min_mm = 800; fake.bearing = 0.5f; run(1500);
  CHECK(out_l > out_r && out_r > 0);
  fake.min_mm = 400; fake.bearing = 0; run(1500); CHECK(out_l == 0 && out_r == 0);
  fake.min_mm = 2500; run(500); CHECK(out_l == 0 && out_r == 0);   // out of window
  // come: arrives then idle
  motion_set_mode_name("come"); fake.min_mm = 410; run(1500); CHECK(motion_mode() == MODE_IDLE);
  // watchdog
  motion_set_mode_name("walk"); fake.min_mm = 2000; run(500); CHECK(motion_driving());
  wd = true; run(40); CHECK(!motion_driving() && out_l == 0 && out_r == 0);
  wd = false;
  // stop + state
  motion_set_mode_name("stop"); run(100); CHECK(out_l == 0 && out_r == 0);
  CHECK(states >= 5);
  CHECK(!motion_set_mode_name("dance"));
  printf(fails ? "%d FAILED\n" : "all motion tests passed\n", fails);
  return fails != 0;
}
