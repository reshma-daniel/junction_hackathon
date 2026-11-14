# services/position — Owner: Wanhui
Produces `rel.estimate` / `rel.lost` (see docs/MESSAGES.md and docs/tasks/wanhui.md).
Method order: WiFi RSSI -> BLE/ESP-NOW RSSI -> ToF fallback from `robot.range`. Coarse near/mid/far is enough for the demo.
