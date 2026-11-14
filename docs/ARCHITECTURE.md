# Architecture

## Key constraint from Atech
Per atech.dev/llms.txt: boards **cannot talk to each other directly**. Over WiFi a
WebSocket gateway relays JSON between a board and *your code*; over USB it is
115200-baud serial, one JSON object per line. So we need a **brain on a laptop**
that both boards talk to. The "wearable ↔ robot" link is wearable → brain → robot.

```
 ┌────────────────┐   JSON/WS    ┌───────────────────────────────┐   JSON/WS   ┌──────────────────────┐
 │ WEARABLE board │ ───────────► │ LAPTOP "BRAIN" (Python)       │ ◄────────── │ ROBOT board (dog)    │
 │ Orientation/IMU│              │  gateway ─ brain (state mach.)│ ──────────► │ 2x DC Motor          │
 └────────────────┘              │  activity   medication        │             │ Distance (ToF 8x8) x2│
                                 │  voice ◄──► ElevenLabs cloud  │             │   front=obstacles    │
                                 └───────────────────────────────┘             │   dock =pill reach   │
                                                                               │ LED Grid (eyes)      │
                                                                               │ Speaker, Microphone  │
                                                                               └──────────────────────┘
```

## Hardware (modules from the Atech catalogue)
| Board | Modules | Purpose |
|---|---|---|
| Wearable | Orientation Sensor (6-axis IMU) | motion energy, still/active |
| Robot | 4x DC Motor | walk / turn (left side + right side) |
| Robot | 2x Distance Sensor (front-left/right) | obstacle avoidance, locate person ahead |
| Robot | Distance Sensor (pill dock) | detects pill removal / hand reaching |
| Robot | 2x LED Grid (3x3 NeoPixel) | one per eye, colour = mood |
| Robot | Speaker | play ElevenLabs audio, bark |
| Robot | Microphone | hear "Charlie" |
| Optional | Camera | stretch goal: person following |

Port budget is fine (12 ports; double-width modules take two). Note: wearable needs
a USB-C power bank, since it is a full ESP32 board.

## Services (all Python 3.10+, asyncio, on the laptop)
- **gateway**: one WebSocket client per board; normalises messages onto an internal
  event bus (in-process asyncio queues, or Redis later if needed).
- **activity**: consumes `wearable.motion`, emits `activity.still_too_long`,
  `activity.decline`. Learns daily baseline (SQLite).
- **medication**: consumes `robot.dock`, learns usual dose time, emits
  `med.taken`, `med.late`, `med.missed`.
- **voice**: ElevenLabs TTS (text → audio → robot speaker), STT (mic clip → text),
  wake-word "Charlie" by STT keyword match. Emits `voice.wake`.
- **brain**: subscribes to all events, owns the robot state machine, picks phrases and
  LED moods, sends `robot.drive` / `robot.eyes` / `voice.say`.

## Brain state machine
```
IDLE ──still_too_long──► PROMPT_WALK ─"Follow me"─► LEAD_WALK ─user moving?─► PRAISE ─► IDLE
                              ▲                          │ no movement for N s
                              └──── re-ask, follow user ◄┘ (escalate up to K times)
IDLE ──med.late──► FOLLOW_USER ─► PROMPT_PILL ─► (med.taken → PRAISE) | (give up → log, notify)
any  ──voice.wake("Charlie")──► COME_TO_USER ─► BARK + blink ─► IDLE
```
LED moods (full table in MESSAGES.md): calm=soft blue slow blink, listening=white, happy=green
fast blink, pleading=amber 1 Hz blink, encouraging=turquoise double blink, sad=dim purple slow glow,
sleepy=dim orange middle row, searching=pale blue sweep.

## Safety / tone (depression context)
Warm, never guilt-tripping. Max re-asks per episode (e.g. 3) then back off. Quiet hours.
Not a medical device; log events, don't diagnose. Raise a human-contact escalation
hook (therapist/caregiver) as a future item, not in MVP.
