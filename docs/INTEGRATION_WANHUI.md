# Integrated IMU, RSSI walking and pill dock

The normal system entry point stays `services/brain/run_story.py`. It owns one
connection to each board; eyes, voice and wheel commands share Charlie's lock.
Do not run `firmware/wearable/bridge.py` or a serial monitor at the same time.
That script and `robot_link_test` remain standalone bench tools.

## The two firmware projects

| Board | Build and flash project | Included application code |
| --- | --- | --- |
| Robot | `firmware/robot_main/project.yaml` | existing eyes/mic/behavior/motion/speaker, plus `firmware/robot/ble_scanner.cpp` and `dock_hw.cpp` |
| Wearable | `firmware/wearable/project.yaml` | `wearable.cpp`, `ble_beacon.cpp` |

Do not flash `robot_link_test` for the full story: it lacks the other robot
modules. The old `pill_dock.ino` is a reference, not another firmware to upload.
Its coverage algorithm now lives in `firmware/robot/dock.cpp`. The integrated
dock sensor stays on port **7**. Port **13** is an eye; front obstacle sensor
stays on port **11**. Wearable's IMU is on its separate board's port **11**.

## Build and run

Install Python 3.12 and the story requirements in your chosen environment:

```bash
python -m pip install -r services/brain/requirements.txt
atech build firmware/robot_main
atech build firmware/wearable
```

Windows (use the actual two COM ports):

```powershell
atech upload firmware/robot_main --port COM5
atech upload firmware/wearable --port COM8
C:\Python312\python.exe services\brain\run_story.py --robot-port COM5 --wearable-port COM8 --panel
```

Mac, from an activated repo `.venv` (recheck port numbers after reconnecting):

```bash
atech upload firmware/robot_main --port /dev/cu.usbmodem101
atech upload firmware/wearable --port /dev/cu.usbmodem11301
python services/brain/run_story.py --robot-port /dev/cu.usbmodem101 --wearable-port /dev/cu.usbmodem11301 --panel --no-drive
```

Start with `--no-drive` to verify the complete story, BLE, IMU and dock without
wheel motion; the existing panel can enable wheels. Supply motor power and raise
the wheels for initial motion tests. Remove `--no-drive` for a normal run.
Cached voice assets continue working as before; live voice features still use
the existing `services/voice/requirements.txt` and their account configuration.

## Ownership and data flow

| Layer | File | Responsibility |
| --- | --- | --- |
| firmware | `firmware/wearable/wearable.cpp` | 50 Hz sampling, 1 Hz energy, calibrated/debounced moving flag, existing USB commands |
| firmware | `firmware/wearable/ble_beacon.cpp` | broadcast the shared BLE UUID |
| firmware | `firmware/robot/ble_scanner.cpp` | report `wearable_ble` RSSI, no motor decisions |
| firmware | `firmware/robot/dock.cpp`, `dock_hw.cpp` | coverage hysteresis and hold time, report `robot_dock` |
| gateway | `services/gateway/story_inputs.py` | dispatch events from the existing Board objects; never open another port |
| activity | `services/activity/motion.py` | validate energy/moving samples |
| position | `services/position/rssi.py` | first fresh per-run RSSI reference, freshness and return/close thresholds |
| medication | `services/medication/dock.py` | validate the debounced dock state |
| brain | `services/brain/walking.py` | pure walking state machine, only active when Story starts a walk |
| brain | `services/brain/run_story.py` | wire services together, send existing `robot_drive` commands |

The IMU now additionally emits standard SDK `wearable_motion` events every
second, with `energy` and `moving` (null until the initial debounce completes).
Original change-only `wearable.motion` log lines are retained for the bench
bridge. The integrated runner consumes the SDK events, not log lines.

## Behavior in the story

- The existing pill-first ordering, invitation speech, eye animations,
  `--walk-s` deadline, praise/sad result, panel pause/restart and no-drive switch
  remain in charge. RSSI navigation never moves the robot during the greeting,
  a pill episode, speech or a pause.
- `story.y_idle_window_s` defaults to 10. The story's still interval is the
  initial delay; there is no additional ten-second delay after the invitation.
- During an allowed walk, still means approach (+255); a moving transition
  selects lead (-255). Still reports after departure do not reverse direction.
- Returning is based on smoothed RSSI dropping 20% in received power from the
  first measured per-process baseline (0.9691 dB). On return, reaching -80 dBm
  or stronger resumes lead automatically. The baseline is not reset on a turn.
- The firmware's motor sign mapping matches the calibrated bench version
  (logical forward: negative on 1/6, positive on 9/14). Its obstacle clamp,
  ramp and two-second hardware watchdog are retained. RSSI cannot determine
  bearing; use an aligned demonstration route.
- Stale BLE or wearable samples stop navigation even while laptop pings continue.
  An explicit stop, story deadline, pause, restart, speech or process exit stops
  wheel commands. Reverse changes retain a 200 ms dwell.
- `--legacy-drive` restores the old slow/fast autonomous walk mode; IMU and pill
  dock still use the integrated events. In RSSI mode `--fast` is the common PWM;
  the panel's slow setting is only used by legacy mode.

## Pill dock

The near-zone boundary defaults to 10 mm (`story.dock_near_mm`), covered means
at least 60% of zones, open means 0%, and the candidate must persist 100 ms.
Intermediate coverage or invalid grids reset the candidate without inventing
a pickup. Runtime `dock_near`, `dock_cover`, `dock_open`, `dock_hold`,
`dock_status` actions permit calibration. Other parameters are under `dock:`.

The runner uses confirmed covered→open transitions for the existing pill reward.
An initially empty dock, duplicate reports or the raw min-distance event alone
cannot count as taking a pill. The raw distance remains available on the panel.

## Tests

```bash
python -m pip install -r services/brain/requirements-dev.txt
python -m pytest services/brain -q
clang++ -std=c++11 firmware/robot/test/test_dock.cpp -o /tmp/test_dock
/tmp/test_dock
```

Compiler and unit tests do not replace checking the actual modules/ports,
voice playback, sensor coverage, obstacle behavior and motor power on hardware.
