#ifndef KAAMOS_BLE_BEACON_CPP_INCLUDED
#define KAAMOS_BLE_BEACON_CPP_INCLUDED
#include <BLEDevice.h>
#include <BLEAdvertising.h>
#include "../shared/ble_identity.cpp"

static void wearable_ble_begin() {
  BLEDevice::init(WEARABLE_BLE_NAME);
  BLEAdvertisementData advertisement;
  advertisement.setFlags(0x06);
  advertisement.setCompleteServices(BLEUUID(WEARABLE_BLE_UUID));
  BLEAdvertisementData response;
  response.setName(WEARABLE_BLE_NAME);
  BLEAdvertising* advertising = BLEDevice::getAdvertising();
  advertising->setAdvertisementType(ADV_TYPE_SCAN_IND);
  advertising->setAdvertisementData(advertisement);
  advertising->setScanResponseData(response);
  // 0.625 ms units: advertise every 100–150 ms. No BLE connection needed.
  advertising->setMinInterval(160);
  advertising->setMaxInterval(240);
  advertising->start();
  Serial.printf("{\"type\":\"wearable.ble\",\"payload\":{\"advertising\":true,\"id\":\"%s\"}}\n", WEARABLE_BLE_UUID);
}

#endif
