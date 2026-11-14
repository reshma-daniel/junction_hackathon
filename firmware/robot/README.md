# firmware/robot — one board, four contributors

Hardware: 4x DC Motor · Speaker · Microphone · 2x LED Grid (eyes) · 3x Distance Sensor. See [PORTS.md](PORTS.md).

## File ownership (one file each; don't edit others')
| File | Owner | Exposes |
|---|---|---|
| `comms.*` | Wanhui | WebSocket/serial JSON in/out, dispatches to handlers, `send(json)`, 2 s watchdog flag |
| `motion.*` | Sara | `motion_set_mode(mode)`, `motion_drive(left,right)`, `motion_tick()`, `motion_stop()` |
| `eyes.*` | Reshma | `eyes_set(left,right,pattern,period)`, `eyes_tick()` (idle blinking animation) |
| `range.*` | Reshma | `range_get() -> Range{left_mm,right_mm,min_mm,bearing,blocked}`, `range_tick()` |
| `mic.*` | Reshma | `mic_level()`, `mic_loud()`, `mic_clip_start()/next_chunk()` |
| `dock.*` | Wanhui | `dock_get() -> {mm,present,reach}` |
| `audio.*` | Wiam | `audio_play_chunk(seq,pcm,last)`, `audio_play_clip(id)`, `audio_bark(n)` |
| `main.*` | Reshma (integrator) | setup + loop calling every `*_tick()`; no logic of its own |

## Rules
- Loop is non-blocking: no `delay()` longer than a few ms; every module has a `*_tick()`.
- Message names/fields exactly as in docs/MESSAGES.md.
- Motion reads obstacles ONLY via `range_get()`; eyes are driven ONLY via `eyes_set()`.
- If the Atech toolchain makes one-file-per-person awkward, use separate blocks/sections per owner and merge in git often (small commits, pull before push).
- Tooling: https://atech.dev/editor or `pip install atech` (`atech validate/build/upload`); needs desktop Chromium + USB-C data cable. First build downloads ~2.4 GB.
