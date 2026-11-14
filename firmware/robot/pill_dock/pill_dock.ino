#include <Arduino.h>
#include "transport.h"           // host link (USB)
#include "esp_system.h"
#include "pins.h"
#include "modules/shared/atech_helpers.h"
#include "modules/distance/vl53l5cx.h"

VL53L5CX_Sensor vl53l5cx_distance(Wire);  // the core's Wire

// ---- pill detector: a paper ball resting on the sensor window ----
// The ball covers most of the sensor's field of view at a few millimetres, so
// "covered" = at least coverPct % of the zones (default 60 %) see
// something closer than nearMm. "uncovered" = no zone does (openPct, default 0 %).
// Anything in between is ignored: the current state is kept. A new state must
// also hold, unbroken, for holdMs before it is announced, so a hand passing
// over or a ball half-placed never prints. Nothing is printed while the state
// stays the same.
static int  nearMm = 10;              // adjustable with: near <mm>
static int  coverPct = 60;            // adjustable with: cover <percent>
static int  openPct = 0;              // adjustable with: open <percent>
static int  holdMs = 100;             // adjustable with: hold <ms>
static int  candidate = -1;          // state seen but not yet held long enough
static uint32_t candidateSince = 0;
static bool sensorOk = false;
static int  stateKnown = -1;          // -1 unknown, 0 removed, 1 on sensor

static int  lastClose = 0, lastZones = 0, lastMin = 32767;

static EveryTimer checkTimer;

static const char* resetReasonStr() {
  switch (esp_reset_reason()) {
    case ESP_RST_POWERON:   return "POWERON";
    case ESP_RST_EXT:       return "EXT";
    case ESP_RST_SW:        return "SOFTWARE";
    case ESP_RST_PANIC:     return "PANIC";
    case ESP_RST_INT_WDT:   return "INT_WDT";
    case ESP_RST_TASK_WDT:  return "TASK_WDT";
    case ESP_RST_WDT:       return "WDT";
    case ESP_RST_BROWNOUT:  return "BROWNOUT";
    case ESP_RST_DEEPSLEEP: return "DEEPSLEEP";
    default:                return "UNKNOWN";
  }
}

// Print human-readable status and standard JSON report.
// JSON contains only one state parameter: removed.
static void announce(int s) {
  // text output just for test
  // if (s == 1) {
  //   Serial.println("Pill not removed yet");
  // } else {
  //   Serial.println("Pill removed");
  // }

  Serial.printf(
    "{\"type\":\"robot.dock\",\"payload\":{\"removed\":%s}}\n",
    s == 0 ? "true" : "false"
  );
}

static void printStatus() {
  const char* st = stateKnown == 1 ? "on_sensor" : (stateKnown == 0 ? "removed" : "unknown");
  Serial.printf("{\"type\":\"status\",\"payload\":{\"state\":\"%s\",\"ready\":%s,\"close_zones\":%d,"
                "\"zones\":%d,\"nearest_mm\":%d,\"near_mm\":%d,\"cover_pct\":%d,\"open_pct\":%d,\"hold_ms\":%d}}\n",
                st, vl53l5cx_distance.isReady() ? "true" : "false",
                lastClose, lastZones, lastMin == 32767 ? -1 : lastMin, nearMm, coverPct, openPct, holdMs);
}

static void printHelp() {
  Serial.println("{\"type\":\"help\",\"payload\":{\"commands\":[\"status\",\"near 10\",\"cover 60\",\"open 0\",\"hold 100\",\"help\"]}}");
}

static void printError(const char* action, const char* msg) {
  Serial.printf("{\"type\":\"error\",\"payload\":{\"action\":\"%s\",\"message\":\"%s\"}}\n", action, msg);
}

static void handle(const char* action, const char* value) {
  if (strcmp(action, "status") == 0) {
    printStatus();
  } else if (strcmp(action, "near") == 0) {
    int v = atoi(value);
    if (v >= 5 && v <= 500) { nearMm = v; printStatus(); }
    else printError("near", "expected a distance in mm, 5-500");
  } else if (strcmp(action, "cover") == 0) {
    int v = atoi(value);
    if (v > openPct && v <= 100) { coverPct = v; printStatus(); }
    else printError("cover", "expected a percent above open, up to 100");
  } else if (strcmp(action, "open") == 0) {
    int v = atoi(value);
    if (*value && v >= 0 && v < coverPct) { openPct = v; printStatus(); }
    else printError("open", "expected a percent from 0, below cover");
  } else if (strcmp(action, "hold") == 0) {
    int v = atoi(value);
    if (v >= 0 && v <= 10000) { holdMs = v; printStatus(); }
    else printError("hold", "expected milliseconds, 0-10000");
  } else if (strcmp(action, "help") == 0) {
    printHelp();
  } else {
    printError(action, "unknown command; send help");
  }
}

static void checkSensor() {
  if (!sensorOk || !vl53l5cx_distance.isReady()) return;
  int zones = vl53l5cx_distance.zoneCount();
  int close = 0;
  for (int i = 0; i < zones; i++) {
    int16_t d = vl53l5cx_distance.getDistance(i);
    if (d > 0 && d < nearMm) close++;
  }
  lastClose = close; lastZones = zones;
  lastMin = vl53l5cx_distance.getMinDistance();

  if (zones <= 0) return;
  int pct = close * 100 / zones;
  int raw;
  if (pct >= coverPct) raw = 1;               // fully covered
  else if (pct <= openPct) raw = 0;           // fully open
  else { candidate = -1; return; }            // in between: ignore, keep state

  if (raw == stateKnown) { candidate = -1; return; }
  uint32_t now = millis();
  if (raw != candidate) { candidate = raw; candidateSince = now; }
  if ((uint32_t)(now - candidateSince) >= (uint32_t)holdMs) {
    stateKnown = raw;                         // held long enough: report once
    candidate = -1;
    announce(stateKnown);
  }
}

void setup() {
  Serial.setRxBufferSize(8192);
  Serial.begin(115200);
  Serial.setTxTimeoutMs(0);
  p2p_transport_setup();
  Wire.begin(PIN_VL53L5CX_DISTANCE_SDA, PIN_VL53L5CX_DISTANCE_SCL);
  Wire.setClock(400000);
  sensorOk = vl53l5cx_distance.begin();

  // 4x4 zones: plenty to tell "covered" from "open", and faster than 8x8.
  if (sensorOk) vl53l5cx_distance.setGridMode(VL53L5CX_Sensor::GRID_4X4);
  else printError("begin", "distance sensor did not start; check it is on port 13");

  Serial.printf("{\"type\":\"boot\",\"payload\":{\"reset_reason\":\"%s\",\"free_heap\":%u,"
                "\"modules\":[{\"instance\":\"vl53l5cx_distance\",\"module\":\"vl53l5cx_distance\",\"ok\":%s,\"detectable\":false}]}}\n",
                resetReasonStr(), (unsigned)ESP.getFreeHeap(), sensorOk ? "true" : "false");
}

void loop() {
  p2p_transport_loop();

  P2PCommand cmd;
  while (p2p_next_command(&cmd)) {
    char action[sizeof(cmd.action)];
    strncpy(action, cmd.action, sizeof(action)); action[sizeof(action) - 1] = 0;
    const char* value = cmd.value;
    char* sp = strpbrk(action, " \t:=(");
    if (sp && cmd.value[0] == 0) { *sp = 0; value = sp + 1; while (*value == ' ') value++; }
    handle(action, value);
  }

  if (!checkTimer.ready(5)) { delay(1); return; }
  checkSensor();
}