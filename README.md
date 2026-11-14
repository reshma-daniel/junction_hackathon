# Kaamos

A desk companion dog-robot for people living with depression. It passively notices
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
