# services/medication — Owner: Reshma

Input: `robot.dock` (`reach` edge = pill taken). Output: `med.taken`, `med.late`, `med.missed`.

- Debounce: one reach within a few minutes = one dose.
- Learn usual time: median of last N dose times (cold start: use config `med_usual_time`).
- `late` = now > usual + `med_late_after_s` and no dose today; re-emit at intervals (brain limits re-asks).
- `missed` = no dose by end of day window. Store in SQLite table `doses`.
- Demo mode: set a usual time ~1 min ahead so the late flow appears quickly.
- Tests with synthetic reach events.


Implemented story path: `dock.py` validates the debounced `robot_dock` events. Firmware coverage/hold detection runs on robot port 7; Story rewards only a confirmed present-to-removed transition, not initial emptiness or raw distance flicker.
