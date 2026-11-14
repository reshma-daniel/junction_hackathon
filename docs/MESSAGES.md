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
| `robot.eyes` | `left`, `right` (`#rrggbb`), `pattern`: `solid` \| `blink` \| `pulse` \| `wink`, `period_ms` (opt) | Reshma |
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

## Eye colours (brain chooses, Reshma renders)
blue `#2f6fff` idle · yellow `#ffc83d` prompting · green `#2fd06b` success · red `#ff4d4d` concern/error (sparingly) ·
cyan `#27d3e6` walking · white `#ffffff` listening · purple `#9b5de5` happy/Charlie.
