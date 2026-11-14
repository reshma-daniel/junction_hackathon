# Demo runner — Owner: Wiam

A whole day with Charlie on a fast 24-hour clock, with Charlie's real voice.

```bash
python tools/demo/run_demo.py              # 1 day = 3 minutes (1 hour = 7.5 s)
python tools/demo/run_demo.py --fast       # 1 day = 2 minutes
python tools/demo/run_demo.py --link usb   # Charlie's voice on the robot speaker instead of the tab
```
Open http://localhost:8765 and click **Start the day** (browsers only play sound after a click).

**Every setting is a real-life time** (wake-up 08:00, pill 09:00, move after 45 min). Only the clock speed
changes between the demo and the product: pick "24 h (real time)" and the same code runs on the real clock.
The clock **waits while Charlie talks**, so a sentence never skips half an hour.

## The day
| Clock time | What happens | Sensor (button) |
|---|---|---|
| until 08:00 | Charlie sleeps (sleepy eyes, no reminders) | **Wake up now** (W) |
| 08:00 | wake-up call: yawn + good morning | |
| 09:00 | the head sensor has not seen a hand today → `pill` reminder 1, 2, 3 (every 20 min), then a gentle back-off: pill missed | **Take the pill** (T) = `robot.dock reach` → `reward` |
| all day | no movement for 45 min → `encourage` 1, 2, 3, then back off and stay quiet 2 h | **Start / Stop walking** (M) = `wearable.motion` `moving` true / false |
| a walk | starts with a happy bark; done after the **walk goal** (15 min of walking, stops under 3 min allowed) → `reward` (walk). Ended early but ≥ 1 min → gentle "that's a win" (general praise), never guilt | |
| 22:00 | bedtime: Charlie goes quiet until the next morning (a pill not taken by then = missed) | |

- **One reminder at a time:** the pill goes first, the walk waits.
- **The dial** shows night and day, the planned times on the rim (wake-up, pill, bedtime) and, on the ring,
  what happened in the last 24 h: wake-up, pill taken / missed, moves, reminders. After one run, the
  whole day is on one circle.
- **Pause** (Q, X or Space) silences Charlie at once, ends a live conversation and stops the clock.
- **Next step now** (S) skips the night, or the wait for the next reminder. **Pill time now** (P) moves the
  clock to the pill time. **New day** (R) starts again just before the wake-up. Pressing a button twice
  does not queue it twice.
- Defaults: `demo_clock` in `shared/config.yaml` (`day_s`, `wake_at`, `pill_at`, `sleep_at`,
  `move_after_min`, `remind_again_min`, `walk_backoff_min`, `walk_goal_min`). The panel changes them live.

## Real sensors
The buttons stand in for the sensors. Real sensors send the team messages (docs/MESSAGES.md):
```bash
gateway | python tools/demo/run_demo.py --stdin      # one JSON message per line
curl -X POST localhost:8765/msg -d '{"type":"robot.dock","reach":true}'
curl -X POST localhost:8765/msg -d '{"type":"wearable.motion","energy":0.3,"moving":true}'
```
`voice.wake` or `robot.heard {kind:"call"}` count as "Charlie!". `--listen` also hears it on the laptop mic.

## Next version
- **Head pat = awake.** The distance sensor that checks the pill sits on top of Charlie's head: a hand close
  to it in the morning means the user is up and petting the dog. The wake-up call can then end (or
  celebrate) on a pat, not only at a time. Same message as the pill: `robot.dock` (`mm`, `reach`).

## Limits (MVP)
- The head sensor knows a hand came close, not that the pill was swallowed.
- One pill per day; several doses a day is for the next version.
- The panel shows the eyes; sending them to the robot is Reshma's `services/brain/express.py`.
