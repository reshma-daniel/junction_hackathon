# services/position — Owner: Wanhui
Produces `rel.estimate` / `rel.lost` (see docs/MESSAGES.md and docs/tasks/wanhui.md).
Method order: WiFi RSSI -> BLE/ESP-NOW RSSI -> ToF fallback from `robot.range`. Coarse near/mid/far is enough for the demo.


Implemented: `rssi.py` tracks the first fresh BLE RSSI per process, current freshness, the 20% power-drop return threshold and -80 dBm close reference. It reports signal strength, never invented distance or bearing.
