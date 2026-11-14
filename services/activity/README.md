# services/activity — Owner: Reshma

Input: `wearable.motion` @1 Hz. Output: `activity.still_too_long`, `activity.moving_again`, `activity.decline`.

- Still timer: reset whenever `moving` true; fire at `still_threshold_s` (demo 60 s), re-fire only after the brain acknowledges or cooldown.
- Daily aggregate: active minutes per day (SQLite `kaamos.db`, table `activity_daily`).
- Baseline: rolling 7-day mean; `decline` when today's/last N days' value is `decline_pct` below.
- Ignore sleeping hours (quiet hours) so night stillness doesn't trigger.
- Tests: feed synthetic streams; no hardware needed.
