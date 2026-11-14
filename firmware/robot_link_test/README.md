# Robot RSSI-guided approach and lead demo

Atech 14port board, motors on 1, 6, 9, 14. Wearable BLE beacon and IMU/USB bridge
remain the input sources. RSSI controls reversals along a pre-aligned line; it cannot
find the user's direction and does not provide obstacle avoidance.

User-calibrated direction: motor 1 counterclockwise rotation means forward,
as viewed during calibration. Positive PWM was confirmed to be the opposite
direction. Logical forward therefore sends negative PWM to motors 1/6 and
positive PWM to 9/14. Logical speed stays positive for approach and negative for
leading; only the hardware output mapping is inverted.

## States

Each normal bridge Run sends `session_start`, stops any old activity and captures
one fresh smoothed RSSI before departure as `initial_rssi_dbm`. This measured
baseline remains unchanged throughout that run, including subsequent lead phases.
A new Run/`session_start` resets it. For example, a -92 dBm initial measurement
means return at <= -93.54902 dBm, not relative to the fixed -80 reference.


- Boot / idle: stopped. An initial `moving:true` alone does not start driving.
- First `moving:false`: wait 10 continuous seconds; duplicate false reports do
  not reset the timer. True cancels this initial wait.
- After the first wait with fresh BLE data: approach
  at fixed PWM +255. RSSI no longer changes speed.
- After departure, a true transition reverses into `lead` at PWM -255. Capture
  `lead_initial_rssi_dbm` from the session's measured `initial_rssi_dbm`.
  The -80 dBm constant is only a close-range reference, not a return threshold.
- After departure, false reports do not change travel direction. Return from
  lead is triggered only by the RSSI threshold below. A false-to-true transition
  while already leading does not reset the RSSI reference.
- In lead, a received-power drop of 30% from the leading baseline switches back
  to approach on the next loop. Since RSSI is logarithmic, this is a drop of
  `10*log10(1/0.7) = 1.54902 dB`, applied to the smoothed reading: return at <= measured run baseline minus 1.54902 dB. This small
  threshold may react to radio fluctuations; tune `RETURN_DROP_DB` if needed.
- After an RSSI-triggered return, robot stays in `return` until smoothed RSSI
  reaches -80 dBm or stronger, then automatically reverses into lead. No new IMU
  event is needed. IMU changes do not prematurely interrupt return travel.
- The measured run baseline stays fixed through every return/lead cycle.
  Already-close readings (>= -80 dBm) cannot trigger a return; this prevents
  overlapping thresholds from causing immediate repeated reversals if a run
  started with an unusually strong initial signal.
- There is no normal `wait_user` stop after initial departure. Each direction
  reversal still stops for 200 ms, then applies the fixed +255 or -255 output.
- BLE data stale for 3 seconds: stop until fresh readings return. Bridge
  heartbeat/motion missing for 3 seconds: stop/disarm and require a new motion
  message; the next cycle starts with the initial ten-second wait.
- Explicit `stop` cancels the cycle and resets both RSSI baselines.

`status`/one-second `link_status` telemetry reports signed `speed`, `target`,
`phase`, `armed`, `initial_rssi_dbm` and `lead_initial_rssi_dbm`. A heartbeat
cannot restart a disarmed robot. IMU moving/still debounce remains unchanged:
"immediate" means when robot receives the classified state, not instant raw
accelerometer movement detection.

## BLE telemetry

`ble_scanner.cpp` scans asynchronously. Every second `wearable_ble` reports the
shared service UUID, detected flag, raw/smoothed RSSI, age and packet count.
Display detection expires at 5 seconds; motor control requires age <3 seconds.
No BLE connection is required. Wearable advertises every 100–150 ms.

Only one program can own the robot USB port. Stop bridge before using:

```bash
source .venv/bin/activate
atech monitor --port /dev/cu.usbmodem101 --key wearable_ble
```

Build/upload from the repository root (raise wheels for motion tests):

```bash
source .venv/bin/activate
atech build firmware/robot_link_test
atech upload firmware/robot_link_test --port /dev/cu.usbmodem101
```

Run existing wearable bridge to supply actual motion states and heartbeats.
Host state-machine tests:

```bash
clang++ -std=c++11 -I firmware/robot_link_test firmware/robot_link_test/test_motion_wait.cpp -o /tmp/test_motion_wait
/tmp/test_motion_wait
```
