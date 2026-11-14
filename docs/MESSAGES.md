# Message contract (v1)

Transport: one JSON object per message (WebSocket via Atech gateway, or one line over USB serial, 115200 baud).
Every message: `type` (string) and `ts` (unix seconds; boards without a clock may omit, the gateway stamps it).
Names are `source.event`. Keep payloads small (ESP32). Unknown fields must be ignored; unknown types logged, not crashed on.

## Wearable → laptop  (owner: Wanhui)
| type | fields | rate |
|---|---|---|
| `wearable.hello` | `fw` | on connect |
| `wearable.motion` | `energy` (float g; 0 = still), `moving` (bool) | 1 Hz |

## Robot → laptop
| type | fields | owner | rate |
|---|---|---|---|
| `robot.hello` | `fw`, `ports_ok` (bool) | Wanhui | on connect |
| `robot.dock` | `mm`, `present` (bool: pills/lid in place), `reach` (bool: true once when a hand removes the pill) | Wanhui | 2 Hz + on change |
| `robot.range` | `left_mm`, `right_mm`, `min_mm`, `bearing` (-1 left … +1 right, nearest object), `blocked` (bool, min_mm < stop threshold) | Reshma | 5 Hz while driving, else 1 Hz |
| `robot.sound` | `level` (0..1), `loud` (bool) | Reshma | 5 Hz |
| `robot.audio` | `seq`, `last`, `pcm_b64` (16 kHz mono s16) | Reshma (capture) / Wanhui (send) | after `loud`, ≤ 3 s clip |
| `robot.state` | `mode`, `driving`, `battery` (opt) | Sara | 1 Hz |
| `robot.ack` | `id`, `ok`, `err` (opt) | Wanhui | per command that has `id` |

## Laptop → robot
| type | fields | handled by |
|---|---|---|
| `robot.mode` | `mode`: `idle` \| `walk` \| `follow` \| `come` \| `stop`, `id` (opt) | Sara |
| `robot.drive` | `left`, `right` (-255..255; 4 motors = 2 sides) | Sara |
| `robot.eyes` | `left`, `right` (`#rrggbb`), `pattern`: `solid` \| `blink` \| `breathe` \| `pulse` \| `sparkle` \| `double_blink` \| `glow` \| `half` \| `sweep`, `period_ms` (opt) | Reshma |
| `robot.bark` | `count` | Wiam |
| `robot.audio_out` | `seq`, `last`, `pcm_b64` | Wiam |
| `robot.say_clip` | `clip` (id of a pre-stored clip on the SD card) | Wiam (fallback if streaming is too laggy) |

**Robot mode semantics (Sara implements, uses Reshma's range data):**
`walk` = go forward, avoid obstacles · `follow` = steer toward the user, keep ~400 mm · `come` = approach user then stop ·
`stop` = motors off. Watchdog: no laptop message for 2 s → motors off, eyes red-dim.

## Relative position between boards (owner: Wanhui)
Laptop-internal event, produced by the position module from whatever method works (see wanhui.md):
| type | fields |
|---|---|
| `rel.estimate` | `distance_m` (float), `bearing` (-1..+1 or null), `method` (`rssi` \| `ble` \| `espnow` \| `tof`), `confidence` (0..1) |
| `rel.lost` | `seconds` (no estimate for this long) |

## Laptop-internal events (brain ↔ services)
| type | fields | producer |
|---|---|---|
| `activity.still_too_long` | `seconds` | Reshma |
| `activity.moving_again` | – | Reshma |
| `activity.decline` | `pct_drop`, `days` | Reshma |
| `med.taken` | `minutes_from_usual` | Reshma |
| `med.late` | `minutes_late` | Reshma |
| `med.missed` | – | Reshma |
| `voice.say` (brain→voice) | `intent`, `text` (opt), `emotion` | consumer: Wiam |
| `voice.done` | `intent` | Wiam |
| `voice.wake` | `word` ("charlie"), `confidence` | Wiam (STT text match) |

Audio format both ways: PCM 16-bit mono 16 kHz. Wiam confirms what the Speaker module accepts and reports back to the team.

## Eye moods (brain chooses, Reshma renders)
Source of truth: `MOODS` in firmware/robot/eyes.cpp. Both eyes show the same mood.

| mood | when | colour | pattern | period_ms | how it moves |
|---|---|---|---|---|---|
| `calm` | idle | soft blue `#3c78ff` | `blink` | 3000 | slow blink: 1.5 s on, 1.5 s off |
| `listening` | while you talk | bright white `#ffffff` | `solid` | – | steady |
| `happy` | heard you ("Charlie"), pill taken | green `#1eff3c` | `blink` | 200 | very fast blink for 2 s, then back to calm |
| `pleading` | pill reminder, lost you on a walk | warm amber `#ff8c00` | `blink` | 1000 | blink once a second |
| `encouraging` | on a walk | turquoise `#28e0d0` | `double_blink` | 2000 | steady, quick double blink every 2 s |
| `sad` | pill missed, couldn't find you | dim purple `#7828c8` | `glow` | 6000 | very slow, faint glow (8–60 %) |
| `sleepy` | quiet hours, waking up | dim orange `#401900` | `half` | – | only the middle row lit |
| `searching` | looking for you | pale blue `#96c8ff` | `sweep` | 3000 | column sweeping left eye → right eye → back |

LED Grid brightness is capped at 51/255 by the module; colours are scaled by it.
