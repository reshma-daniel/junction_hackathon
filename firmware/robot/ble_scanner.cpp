#ifndef KAAMOS_BLE_SCANNER_CPP_INCLUDED
#define KAAMOS_BLE_SCANNER_CPP_INCLUDED
#include <Arduino.h>
#include <BLEDevice.h>
#include <BLEScan.h>
#include "../shared/ble_identity.cpp"

// Bluetooth callbacks run on a different task. Keep serial output in loop().
static portMUX_TYPE bleSampleMux = portMUX_INITIALIZER_UNLOCKED;
static bool bleSeen = false;
static int bleRssi = 0;
static uint32_t bleLastSeen = 0;
static uint32_t bleSamples = 0;
static float bleSmoothed = 0;
static uint32_t bleLastReport = 0;

class WearableBeaconCallbacks : public BLEAdvertisedDeviceCallbacks {
  void onResult(BLEAdvertisedDevice device) override {
    if (!device.haveServiceUUID() ||
        !device.isAdvertisingService(BLEUUID(WEARABLE_BLE_UUID))) return;
    const uint32_t now = millis();
    const int rssi = device.getRSSI();
    portENTER_CRITICAL(&bleSampleMux);
    if (!bleSeen || uint32_t(now - bleLastSeen) > 5000) bleSmoothed = rssi;
    else bleSmoothed = 0.75f * bleSmoothed + 0.25f * rssi;
    bleSeen = true;
    bleRssi = rssi;
    bleLastSeen = now;
    ++bleSamples;
    portEXIT_CRITICAL(&bleSampleMux);
  }
};
static WearableBeaconCallbacks wearableBeaconCallbacks;

static bool robot_ble_rssi(float& smoothed) {
  portENTER_CRITICAL(&bleSampleMux);
  bool seen = bleSeen;
  uint32_t lastSeen = bleLastSeen;
  smoothed = bleSmoothed;
  portEXIT_CRITICAL(&bleSampleMux);
  // Motor control uses a stricter freshness bound than the display.
  return seen && uint32_t(millis() - lastSeen) < 3000;
}

static void robot_ble_begin() {
  BLEDevice::init("KaamosRobot");
  BLEScan* scanner = BLEDevice::getScan();
  // Receive duplicate advertisements for continuously updated RSSI. The SDK
  // does not accumulate scan results when callbacks + duplicates are enabled.
  scanner->setAdvertisedDeviceCallbacks(&wearableBeaconCallbacks, true);
  scanner->setActiveScan(false);
  scanner->setInterval(100);
  scanner->setWindow(50);
  // Callback overload starts scanning asynchronously. Zero = continuous scan.
  bool started = scanner->start(0, static_cast<void (*)(BLEScanResults)>(nullptr), false);
  Serial.printf("{\"type\":\"robot.ble\",\"payload\":{\"scanning\":%s}}\n", started ? "true" : "false");
}

static void robot_ble_tick() {
  if (uint32_t(millis() - bleLastReport) < 1000) return;
  bleLastReport = millis();
  portENTER_CRITICAL(&bleSampleMux);
  bool seen = bleSeen;
  int rssi = bleRssi;
  float smoothed = bleSmoothed;
  uint32_t lastSeen = bleLastSeen;
  uint32_t samples = bleSamples;
  portEXIT_CRITICAL(&bleSampleMux);
  uint32_t age = uint32_t(millis() - lastSeen);
  bool detected = seen && age <= 5000;
  Serial.printf("{\"type\":\"event\",\"payload\":{\"event_type\":\"sensor\",\"key\":\"wearable_ble\",\"value\":{\"id\":\"%s\",\"detected\":%s,\"rssi_dbm\":", WEARABLE_BLE_UUID, detected ? "true" : "false");
  if (detected) Serial.printf("%d,\"rssi_smoothed_dbm\":%.1f", rssi, smoothed);
  else Serial.print("null,\"rssi_smoothed_dbm\":null");
  Serial.print(",\"age_ms\":");
  if (seen) Serial.printf("%lu", (unsigned long)age); else Serial.print("null");
  Serial.printf(",\"samples\":%lu}}}\n", (unsigned long)samples);
}

#endif
