# services/medication — Owner: Reshma

Input: `robot.dock` (`reach` edge = pill taken). Output: `med.taken`, `med.late`, `med.missed`.

- Debounce: one reach within a few minutes = one dose.
- Learn usual time: median of last N dose times (cold start: use config `med_usual_time`).
- `late` = now > usual + `med_late_after_s` and no dose today; re-emit at intervals (brain limits re-asks).
- `missed` = no dose by end of day window. Store in SQLite table `doses`.
- Demo mode: set a usual time ~1 min ahead so the late flow appears quickly.
- Tests with synthetic reach events.
