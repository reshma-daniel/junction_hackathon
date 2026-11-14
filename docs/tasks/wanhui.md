# Wanhui — Communication, positions, wearable, pill dock

**Goal:** all boards talk to the laptop reliably; the system knows roughly where the user is relative to the robot; we detect user movement and pill removal.

## Tasks
1. **Connectivity first (M0, the whole team depends on it):**
   - Get both boards (robot + wearable) talking JSON to the laptop via Atech WebSocket gateway (or USB serial fallback).
   - Answer OPEN_QUESTIONS #1: can two boards share one project, or do we need two project IDs? Fill ids in shared/config.yaml.
   - **`services/gateway/` (laptop):** connect to both boards, publish incoming JSON on an in-process bus, `send_to_robot(msg)`, auto-reconnect + `--sim` mode (talks to Reshma's simulator).
   - **`comms.*` robot firmware:** parse incoming JSON, dispatch to handler functions of the other people (see firmware/robot/README.md), `send()`, 2 s watchdog flag, `robot.ack`.
2. **Wearable firmware (`firmware/wearable/`):** Orientation Sensor → compute `energy` per second (mean abs deviation of accel magnitude from 1 g) → `wearable.motion {energy,moving}` at 1 Hz. Tune the `moving` threshold on walking vs sitting; put it in shared/config.yaml. Power via USB-C bank.
3. **Pill dock (`dock.*` on robot):** distance sensor aimed at the pill compartment. Report `robot.dock {mm,present,reach}`; `reach` = the pill/lid was removed (distance jumps) or a hand enters — debounce so one pick-up = one event. Calibrate with real pills.
4. **Relative position (`services/position/` laptop, new folder, plus any firmware support):** produce `rel.estimate {distance_m, bearing, method, confidence}`. Try in this order and stop at the first that works well enough:
   a. **WiFi RSSI** of both boards as seen by the router/laptop (if the gateway exposes it) → distance trend (coarse: near / mid / far).
   b. **Direct BLE/ESP-NOW** RSSI between the two ESP32-S3s, if Atech's toolchain allows custom radio code.
   c. **Fallback:** no wireless position; robot uses its distance sensors (Reshma's `range`) to find the person. Emit `rel.estimate` with `method:"tof"` from `robot.range` so the brain has the same interface either way.
   Time-box this to a few hours: coarse "near/far" is enough for the demo.

## You consume
`robot.*` commands (dispatch), `robot.range` (fallback position).
## You produce
`wearable.hello`, `wearable.motion`, `robot.hello`, `robot.dock`, `robot.ack`, `rel.estimate`, `rel.lost`.

## Done when
Laptop log shows motion at 1 Hz and a dock reach event on each pill pick-up; reconnects after unplugging WiFi; `rel.estimate` distinguishes "next to robot" from "other side of room" (or the ToF fallback is wired in).

## Dependencies
Others cannot test on real hardware until gateway + `comms` work: do that FIRST and announce when done.
