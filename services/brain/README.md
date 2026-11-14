# services/brain — Owner: Reshma

The personality: subscribes to all events, runs the state machine from docs/ARCHITECTURE.md.

- States: IDLE, PROMPT_WALK, LEAD_WALK, PRAISE, FOLLOW_USER, PROMPT_PILL, COME_TO_USER.
- Inputs: `activity.*`, `med.*`, `voice.wake`, `wearable.motion` (to verify the user is moving), `robot.range/state`.
- Outputs: `robot.mode`, `robot.eyes`, `robot.bark`, `voice.say`.
- Rules: max re-asks (config), never interrupt a prompt in progress, quiet hours, pill > walk priority,
  a "Charlie" call interrupts everything except an ongoing speech line.
- Logs every episode (trigger, prompts, outcome) to SQLite `kaamos.db` table `episodes` – useful for the therapist-facing story.
- Pure logic, no I/O inside the state machine, so it is unit-testable with the simulator.
