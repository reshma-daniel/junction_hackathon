# Wearable motion firmware and bridge

For the full system, use `services/brain/run_story.py`, not the standalone bridge.
The firmware now also emits standard SDK `wearable_motion` events every second.
See [integration guide](../../docs/INTEGRATION_WANHUI.md).

## BLE beacon (additional feature)

The wearable also advertises `KaamosWearable` with project-specific service UUID
`bf8a82d0-418f-4a40-9f84-e969e54cf731` every 100–150 ms. The shared identifier
is in `firmware/shared/ble_identity.cpp`; advertising is in `ble_beacon.cpp`.
This is a connectionless beacon. IMU output, calibration and USB commands retain
their existing behavior. Robot uses the UUID, not the name, to filter broadcasts.
The UUID identifies this project beacon and is not an authentication mechanism.

## Current mode: USB

Wearable port 11301 → Python bridge → robot port 101. No Wi-Fi required.
Running with no arguments enables motor control from wearable data. Use `--monitor-only` to display data without controlling motors.

```bash
.venv/bin/python firmware/wearable/bridge.py
```

VS Code launch configurations explicitly select these USB ports. Verify port
assignments after reconnecting. `--cloud` is an optional legacy path and requires
separate cloud-enabled board firmware.

Atech 14port board, orientation sensor on port 11. `project.yaml` supplies the
SDK sensor and USB host transport; `wearable.cpp` implements the application.
No downloaded Studio transport, Wi-Fi or pin headers are required.

## Build

From the repository root:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r firmware/wearable/requirements.txt
.venv/bin/python firmware/wearable/build_usb.py
```

Alternatively, activate `.venv` and run `atech build firmware/wearable`.
Both commands regenerate `firmware/wearable/build/` and compile only.
Keep the default output directory: the C++ include is relative to `build/src/`.
Edit the source, never generated files. Select `.venv/bin/python` for Python;
open `firmware/wearable/build/` with PlatformIO for C++ SDK indexing.

## Behavior

- Sample acceleration at 50 Hz; compute mean `abs(|a| - 1g)` each second.
- Default threshold: 0.05 g; report moving after 2 consecutive moving windows,
  still after 5 still windows. Emit `wearable.motion` at the first confirmed
  state and every state change, rather than continuously.
- Preserve the original 270-degree mounting rotation, calibration commands,
  raw acceleration stream, status, and persistent threshold/hold settings.
- USB actions: `status`, `calib sit`, `calib walk`, `thresh 0.05`, `move_hold 2`,
  `still_hold 5`, `verbose on`, `stream on`, `rate 100`, `accel`, `motion true`,
  `motion false`, `help`. With `atech send`, action and value are separate args.
- `motion true` sends a test event without changing the detected state.

## Communication test

After flashing the wearable project and `firmware/robot_link_test` to their
respective boards, run from the repository root:

```bash
.venv/bin/python firmware/wearable/bridge.py --wearable-port /dev/cu.usbmodem11301 --robot-port /dev/cu.usbmodem101
```

Recheck port assignments after reconnecting. The bridge receives wearable USB
JSON, validates the motion payload and sends `wearable_motion` to the robot.
The bridge starts a new robot session and records the first fresh BLE RSSI.
The robot then waits for 10 seconds of `moving:false`,
then approaches at fixed PWM 255. The ten-second wait is only for the first departure. `moving:true` reverses into leading;
weakening BLE signal alone triggers a forward return; still reports after departure do not reverse direction. See
`firmware/robot_link_test/README.md` for thresholds and recovery behavior.
The bridge continues forwarding motion states and connection heartbeats unchanged.
Lift the wheels and supply motor power for testing.
`ROBOT ACK` confirms the firmware handled the message; observe the wheels to
verify the physical output. With `--monitor-only`, the bridge only logs events.
Close serial monitors before running the bridge: one process per serial port.

Without port arguments, USB ports 11301 and 101 are used by default; --cloud explicitly selects cloud transport.
