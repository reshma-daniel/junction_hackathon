# firmware/wearable  — Owner: Wanhui

Atech board + **Orientation Sensor** worn on the wrist/body.

## Job
- Read accel/gyro, compute `energy` once per second (mean absolute deviation of accel magnitude from 1 g).
- Send `wearable.motion {energy, moving}` at 1 Hz (see docs/MESSAGES.md). Send `wearable.hello` on connect.
- Reconnect automatically on WiFi loss.

## How
- Fastest path: describe it in https://atech.dev/editor, or `pip install atech`, `atech new`, `atech validate/build/upload`.
- Programming needs desktop Chromium + USB-C data cable (Web Serial). First build downloads ~2.4 GB compiler: do this at home on good WiFi.
- Atech also has an MCP connector (https://atech.dev/mcp) your coding agent can use.

## Done when
Walking vs sitting gives clearly different `energy`; tuned `motion_energy_moving` goes into shared/config.yaml.
