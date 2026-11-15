#ifndef KAAMOS_DOCK_HW_CPP_INCLUDED
#define KAAMOS_DOCK_HW_CPP_INCLUDED
#include <Arduino.h>
#include "dock.cpp"

// SDK initializes distance_sensor on port 7. Do not initialize Wire again:
// front obstacle sensor uses Wire1 and both eyes already occupy other ports.
static PillDock dockDetector;
static uint32_t dockLastCheck = 0, dockLastReport = 0;
static int dockClose = 0, dockZones = 0, dockMin = -1;
static bool dockValid = false;

static void dock_report() {
  Serial.print("{\"type\":\"event\",\"payload\":{\"event_type\":\"sensor\",\"key\":\"robot_dock\",\"value\":{\"valid\":");
  Serial.print(dockValid && dockDetector.state >= 0 ? "true" : "false");
  Serial.print(",\"removed\":");
  if (dockDetector.state < 0) Serial.print("null"); else Serial.print(dockDetector.state == 0 ? "true" : "false");
  Serial.printf(",\"mm\":%d,\"close_zones\":%d,\"zones\":%d,\"near_mm\":%d,\"cover_pct\":%d,\"open_pct\":%d,\"hold_ms\":%lu}}}\n",
                dockMin, dockClose, dockZones, dockDetector.nearMm, dockDetector.coverPct,
                dockDetector.openPct, (unsigned long)dockDetector.holdMs);
}
static void dock_begin() { dockLastCheck = dockLastReport = millis(); }
static void dock_tick() {
  uint32_t now = millis();
  bool changed = false;
  if (uint32_t(now - dockLastCheck) >= 20) {
    dockLastCheck = now;
    dockValid = distance_sensor_ok && distance_sensor.isReady();
    if (dockValid) {
      int16_t grid[64]; distance_sensor.getDistanceGrid(grid);
      dockZones = distance_sensor.zoneCount(); dockClose = 0;
      int valid = 0; dockMin = 32767;
      for (int i = 0; i < dockZones; ++i) {
        int d = grid[i];
        if (d <= 0) continue;
        ++valid; if (d < dockMin) dockMin = d;
        if (d <= dockDetector.nearMm) ++dockClose;
      }
      dockValid = valid * 2 >= dockZones && dockZones > 0;
      changed = dockDetector.update(dockClose, dockZones, valid, now);
    } else dockDetector.candidate = -1;
  }
  if (changed || uint32_t(now - dockLastReport) >= 1000) {
    dockLastReport = now; dock_report();
  }
}
static bool dock_action(const String& action, const String& value) {
  if (action == "dock_status") { dock_report(); return true; }
  char* end = nullptr;
  long number = strtol(value.c_str(), &end, 10);
  bool valid = value.length() && end && !*end;
  if (!valid) return false;
  bool changed = true;
  if (action == "dock_near" && number >= 5 && number <= 500) dockDetector.nearMm = number;
  else if (action == "dock_cover" && number > dockDetector.openPct && number <= 100) dockDetector.coverPct = number;
  else if (action == "dock_open" && number >= 0 && number < dockDetector.coverPct) dockDetector.openPct = number;
  else if (action == "dock_hold" && number >= 0 && number <= 10000) dockDetector.holdMs = number;
  else changed = false;
  if (changed) { dockDetector.candidate = -1; dock_report(); }
  return changed;
}
#endif
