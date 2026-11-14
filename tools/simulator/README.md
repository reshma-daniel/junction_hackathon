# tools/simulator — Owner: Reshma (ship first!)

Fake wearable + fake robot so everyone can develop without hardware.

- Plays scripted scenarios: `sit_still`, `walk`, `pill_taken`, `pill_late`, `charlie_call`.
- Speaks the same JSON as docs/MESSAGES.md over the same gateway interface (`--sim`).
- Tiny terminal UI: shows robot eye colours, current mode, spoken lines; keys to trigger events (m = move, s = still, p = reach pill dock, c = "Charlie").
- Time-scaling flag (`--speed 10`) to run the 60 s/45 s demo thresholds quickly.
