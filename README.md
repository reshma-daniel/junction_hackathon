# Kaamos

A desk companion dog-robot, called **Charlie**, for people living with depression. It passively notices
behaviour (movement, medication) and responds with gentle spoken encouragement.
Built on the Atech kit (ESP32-S3 modules) + a laptop "brain" + ElevenLabs voice.

## Read in this order
1. [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) – how the pieces fit
2. [docs/PLAN.md](docs/PLAN.md) – who builds what, milestones, demo; then your sheet in [docs/tasks/](docs/tasks/)
3. [docs/MESSAGES.md](docs/MESSAGES.md) – the JSON contract everyone codes against
4. [docs/OPEN_QUESTIONS.md](docs/OPEN_QUESTIONS.md) – things to verify on real hardware early

## Layout
```
kaamos/
  docs/                 plan, architecture, message contract
  shared/               config.yaml + protocol.py (single source of truth)
  firmware/wearable/    Atech board on the user's wrist  (IMU)
  firmware/robot/       Atech board in the dog           (motors, ToF, LEDs, speaker, mic)
  services/gateway/     WebSocket bridge to Atech boards (Wanhui)
  services/position/    relative robot<->user position (Wanhui)
  services/brain/       state machine / orchestrator (the "personality")
  services/activity/    movement baseline + sedentary/decline detection
  services/medication/  dose-time learning + missed/late detection
  services/voice/       ElevenLabs TTS + STT, wake word "Charlie"
  tools/simulator/      fake wearable/robot so software works without hardware
```

## Rules of the road
- Everyone codes against `docs/MESSAGES.md`. Change it only via a quick team agreement.
- Every service must run against the simulator, so nobody blocks on hardware.
- Demo thresholds live in `shared/config.yaml` (stillness = 60 s for now).

## Integrated board firmware and story runner

The full robot image is **`firmware/robot_main/project.yaml`**; the wearable image
is **`firmware/wearable/project.yaml`**. Flash both before running the story.
`robot_link_test` is a standalone bench image and does not contain eyes/voice/dock.

The existing entry point includes IMU + BLE/RSSI walking and pill-dock coverage
now; do not run the standalone bridge alongside it:

```bash
python services/brain/run_story.py --robot-port COM5 --wearable-port COM8 --panel
```

Replace COM ports with your actual device paths on macOS/Linux. Use `--no-drive`
for the first full-system check. Build/flash commands, module ports, service
responsibilities, calibration and tests are in [the integration guide](docs/INTEGRATION_WANHUI.md).
