// Wearable application for project.yaml; Atech creates the IMU and USB transport.
#include <Arduino.h>
#include <Preferences.h>
#include <esp_system.h>
#include "atech_helpers.h"
#include "icm40608.h"

extern ICM40608 icm40608_imu;

// Wearable acceleration stream: every imuPeriodMs this board prints
// {"type":"imu","payload":{"ax":..,"ay":..,"az":..}} (g). (debug only). Board frame: +X right edge, +Y top edge, +Z out of the face.
static bool imuOk = false;
static bool imuStreamOn = false;  // raw stream off by default: only motion events are sent
static uint32_t imuPeriodMs = 100;   // 10 samples per second
static EveryTimer imuTimer;

// ---- wearable.motion reporter (team-shared format) ----
// Every 20 ms (50 Hz) the acceleration magnitude |a| (g) is read and |(|a| - 1 g)|
// is accumulated. Once per second: energy = mean of those deviations over the
// window, moving = energy > moveThreshG, and one line is sent:
//   {"type":"wearable.motion","payload":{"energy":0.0123,"moving":false}}
// MOVE_THRESHOLD_G mirrors move_threshold_g in src/shared/config.yaml; keep them equal.
#define MOVE_THRESHOLD_G 0.05f
static float moveThreshG = MOVE_THRESHOLD_G;  // adjustable with: thresh <g>
static double winSum = 0.0;
static uint32_t winN = 0;
static float lastEnergy = NAN;
// State-change reporting: energy is computed every second ON THE BOARD; a
// wearable.motion line is sent only when the debounced moving flag flips
// (and once at boot when the first state is confirmed).
static uint32_t moveHoldS = 2;       // seconds above threshold before "moving"
static uint32_t stillHoldS = 5;      // seconds below threshold before "still"
static int reportedMoving = -1;      // -1 unknown, 0 still, 1 moving
static uint32_t aboveRun = 0, belowRun = 0;
static bool verbose = false;         // "verbose on" prints every 1 s window (debug)
static Preferences prefs;
static EveryTimer sampleTimer;
static EveryTimer reportTimer;
// calibration: "calib sit" / "calib walk" average energy over 10 windows
static int calibMode = 0;            // 0 none, 1 sit, 2 walk
static int calibLeft = 0;
static double calibSum = 0.0;
static int calibCount = 0;
static float sitEnergy = NAN, walkEnergy = NAN;

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


static void printHelp() {
  Serial.println("{\"type\":\"help\",\"payload\":{\"commands\":[\"thresh 0.05\",\"calib sit\",\"calib walk\",\"status\",\"move_hold 2\",\"still_hold 5\",\"verbose on|off\",\"stream on|off\",\"rate 100\",\"accel\",\"motion\",\"motion true|false\",\"help\"]}}");
}


static void printError(const char* action, const char* msg) {
  Serial.printf("{\"type\":\"error\",\"payload\":{\"action\":\"%s\",\"message\":\"%s\"}}\n", action, msg);
}

static void sendAccel() {
  if (!imuOk || !icm40608_imu.isConnected()) {
    Serial.println("{\"type\":\"imu\",\"payload\":{\"ax\":null,\"ay\":null,\"az\":null,\"ok\":false}}");
    return;
  }
  float ax, ay, az;
  icm40608_imu.readAll(&ax, &ay, &az, nullptr, nullptr, nullptr, nullptr);
  if (isnan(ax) || isnan(ay) || isnan(az)) {
    Serial.println("{\"type\":\"imu\",\"payload\":{\"ax\":null,\"ay\":null,\"az\":null,\"ok\":false}}");
    return;
  }
  Serial.printf("{\"type\":\"imu\",\"payload\":{\"ax\":%.3f,\"ay\":%.3f,\"az\":%.3f}}\n", ax, ay, az);
}

static void printStatus();
static void printStatus() {
  Serial.printf("{\"type\":\"wearable.status\",\"payload\":{\"move_threshold_g\":%.4f,\"sit_energy\":", moveThreshG);
  if (isnan(sitEnergy)) Serial.print("null"); else Serial.printf("%.4f", sitEnergy);
  Serial.print(",\"walk_energy\":");
  if (isnan(walkEnergy)) Serial.print("null"); else Serial.printf("%.4f", walkEnergy);
  Serial.print(",\"energy\":");
  if (isnan(lastEnergy)) Serial.print("null"); else Serial.printf("%.4f", lastEnergy);
  Serial.printf(",\"moving\":%s,\"move_hold_s\":%u,\"still_hold_s\":%u,\"verbose\":%s,\"calibrating\":%s",
                reportedMoving < 0 ? "null" : (reportedMoving ? "true" : "false"),
                (unsigned)moveHoldS, (unsigned)stillHoldS, verbose ? "true" : "false",
                calibMode == 1 ? "\"sit\"" : (calibMode == 2 ? "\"walk\"" : "null"));
  Serial.printf(",\"sensor_ok\":%s}}\n", imuOk ? "true" : "false");
}

static void sampleAccel() {
  if (!imuOk) return;
  float ax, ay, az;
  icm40608_imu.readAll(&ax, &ay, &az, nullptr, nullptr, nullptr, nullptr);
  if (isnan(ax) || isnan(ay) || isnan(az)) return;
  float mag = sqrtf(ax * ax + ay * ay + az * az);
  winSum += fabsf(mag - 1.0f);
  winN++;
}

static void finishCalib() {
  float avg = (float)(calibSum / calibCount);
  if (calibMode == 1) sitEnergy = avg; else walkEnergy = avg;
  calibMode = 0;
  if (!isnan(sitEnergy) && !isnan(walkEnergy)) {
    if (walkEnergy > sitEnergy) {
      moveThreshG = (sitEnergy + walkEnergy) * 0.5f;
      prefs.putFloat("thresh", moveThreshG);
      Serial.printf("{\"type\":\"wearable.calib\",\"payload\":{\"sit_energy\":%.4f,\"walk_energy\":%.4f,"
                    "\"move_threshold_g\":%.4f,\"yaml\":\"move_threshold_g: %.4f\"}}\n",
                    sitEnergy, walkEnergy, moveThreshG, moveThreshG);
      return;
    }
    printError("calib", "walking energy was not above sitting energy; threshold unchanged");
  }
  printStatus();
}

static void sendMotionLine(float energy, bool moving) {
  Serial.printf("{\"type\":\"wearable.motion\",\"payload\":{\"energy\":%.4f,\"moving\":%s}}\n",
                energy, moving ? "true" : "false");
}

static void reportMotion() {
  if (winN == 0) {
    lastEnergy = NAN;
    if (verbose) Serial.println("{\"type\":\"wearable.energy\",\"payload\":{\"energy\":null,\"above\":null}}");
    return;
  }
  lastEnergy = (float)(winSum / winN);
  winSum = 0.0; winN = 0;
  bool above = lastEnergy > moveThreshG;
  if (above) { aboveRun++; belowRun = 0; } else { belowRun++; aboveRun = 0; }
  int next = reportedMoving;
  if (aboveRun >= moveHoldS) next = 1;
  else if (belowRun >= stillHoldS) next = 0;
  if (next != reportedMoving) {
    reportedMoving = next;
    sendMotionLine(lastEnergy, next == 1);
  } else if (verbose) {
    Serial.printf("{\"type\":\"wearable.energy\",\"payload\":{\"energy\":%.4f,\"above\":%s}}\n",
                  lastEnergy, above ? "true" : "false");
  }
  // Integrated story consumes one SDK event each second. Keep the original
  // change-only wearable.motion line for the standalone USB test bridge.
  Serial.printf("{\"type\":\"event\",\"payload\":{\"event_type\":\"sensor\",\"key\":\"wearable_motion\",\"value\":{\"energy\":%.4f,\"moving\":", lastEnergy);
  if (reportedMoving < 0) Serial.print("null"); else Serial.print(reportedMoving ? "true" : "false");
  Serial.println("}}}");
  if (calibMode) {
    calibSum += lastEnergy; calibCount++;
    if (--calibLeft <= 0) finishCalib();
  }
}


static void handle(const char* action, const char* value) {
  if (strcmp(action, "stream") == 0) {
    if (strcmp(value, "on") == 0 || strcmp(value, "1") == 0 || strcmp(value, "true") == 0) imuStreamOn = true;
    else if (strcmp(value, "off") == 0 || strcmp(value, "0") == 0 || strcmp(value, "false") == 0) imuStreamOn = false;
    else { printError("stream", "expected on or off"); return; }
    Serial.printf("{\"type\":\"stream\",\"payload\":{\"on\":%s,\"rate_ms\":%u,\"sensor_ok\":%s}}\n",
                  imuStreamOn ? "true" : "false", (unsigned)imuPeriodMs, imuOk ? "true" : "false");
  } else if (strcmp(action, "rate") == 0) {
    long v = atol(value);
    if (v >= 20 && v <= 5000) {
      imuPeriodMs = (uint32_t)v;
      Serial.printf("{\"type\":\"stream\",\"payload\":{\"on\":%s,\"rate_ms\":%u,\"sensor_ok\":%s}}\n",
                    imuStreamOn ? "true" : "false", (unsigned)imuPeriodMs, imuOk ? "true" : "false");
    } else printError("rate", "expected milliseconds between samples, 20-5000");
  } else if (strcmp(action, "accel") == 0) {
    sendAccel();
  } else if (strcmp(action, "status") == 0) {
    printStatus();
  } else if (strcmp(action, "thresh") == 0) {
    float v = atof(value);
    if (v > 0.0f && v <= 2.0f) { moveThreshG = v; prefs.putFloat("thresh", v); printStatus(); }
    else printError("thresh", "expected g above 0, up to 2");
  } else if (strcmp(action, "calib") == 0) {
    if (strcmp(value, "sit") == 0) calibMode = 1;
    else if (strcmp(value, "walk") == 0) calibMode = 2;
    else { printError("calib", "expected sit or walk"); return; }
    calibLeft = 10; calibSum = 0.0; calibCount = 0;
    Serial.printf("{\"type\":\"wearable.calib\",\"payload\":{\"recording\":\"%s\",\"seconds\":10}}\n", value);
  } else if (strcmp(action, "move_hold") == 0 || strcmp(action, "still_hold") == 0) {
    long v = atol(value);
    if (v < 1 || v > 120) { printError(action, "expected seconds, 1-120"); return; }
    if (action[0] == 'm') { moveHoldS = v; prefs.putUInt("mhold", v); }
    else { stillHoldS = v; prefs.putUInt("shold", v); }
    printStatus();
  } else if (strcmp(action, "verbose") == 0) {
    verbose = (strcmp(value, "on") == 0 || strcmp(value, "1") == 0 || strcmp(value, "true") == 0);
    printStatus();
  } else if (strcmp(action, "motion") == 0) {
    // Test send: one wearable.motion line now, in exactly the team format.
    // No value = the current energy and state; "true"/"false" forces moving for a link test
    // (the board's own state is not changed).
    float e = isnan(lastEnergy) ? 0.0f : lastEnergy;
    bool m;
    if (strcmp(value, "true") == 0 || strcmp(value, "1") == 0 || strcmp(value, "on") == 0) m = true;
    else if (strcmp(value, "false") == 0 || strcmp(value, "0") == 0 || strcmp(value, "off") == 0) m = false;
    else if (value[0] == 0) {
      if (isnan(lastEnergy)) { printError("motion", "no energy measured yet; wait a second or check the sensor"); return; }
      m = reportedMoving < 0 ? (lastEnergy > moveThreshG) : (reportedMoving == 1);
    } else { printError("motion", "expected nothing, true or false"); return; }
    sendMotionLine(e, m);
  } else if (strcmp(action, "help") == 0) {
    printHelp();
  } else {
    printError(action, "unknown command; send help");
  }
}

void wearable_setup() {
  icm40608_imu.setMountRotation(270);
  imuOk = icm40608_imu.isConnected();
  prefs.begin("wearable", false);
  moveThreshG = prefs.getFloat("thresh", MOVE_THRESHOLD_G);
  moveHoldS = prefs.getUInt("mhold", moveHoldS);
  stillHoldS = prefs.getUInt("shold", stillHoldS);
  if (!imuOk) printError("begin", "orientation sensor did not answer; check it is on port 11");


  Serial.printf("{\"type\":\"boot\",\"payload\":{\"reset_reason\":\"%s\",\"free_heap\":%u,"
                "\"modules\":[{\"instance\":\"icm40608_imu\",\"module\":\"icm40608_imu\",\"ok\":%s,\"detectable\":false}]}}\n",
                resetReasonStr(), (unsigned)ESP.getFreeHeap(), imuOk ? "true" : "false");
}

void wearable_tick() {
  if (sampleTimer.ready(20)) sampleAccel();
  if (reportTimer.ready(1000)) reportMotion();
  if (imuStreamOn && imuTimer.ready(imuPeriodMs)) sendAccel();
  delay(1);
}
