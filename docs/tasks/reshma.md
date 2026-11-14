# Reshma — Eyes, microphone, obstacles + all leftovers (brain & integration)

**Goal:** Charlie looks alive, hears, senses obstacles, and has a brain that ties everyone's parts into the demo.

## Part A — Robot sensing/expressing (firmware)
1. **Eyes (`eyes.*`)**: two LED Grids (3x3 NeoPixel) as eyes. `eyes_set(left,right,pattern,period)` with patterns solid / blink / pulse / wink. Idle: slow random blinking in blue. Draw an eye shape (e.g. centre pixel or small cluster) not a full flood. Colours in MESSAGES.md.
2. **Obstacles (`range.*`)**: front-left and front-right distance sensors (8x8 ToF) → `range_get() -> {left_mm,right_mm,min_mm,bearing,blocked}`; `bearing` from where the nearest object sits across the grid; `blocked` when `min_mm < obstacle_stop_mm`. Send `robot.range`. **Push a stub returning fixed values on day 1 so Sara can build against it.**
3. **Microphone (`mic.*`)**: level → `robot.sound {level,loud}`; on `loud` record a ≤ 3 s clip, send `robot.audio` chunks (Wiam does speech-to-text). Avoid triggering on its own speaker (ignore mic while audio is playing).
4. **`main.*` integrator**: setup + loop calling every module's `tick()`.

## Part B — Laptop logic (all "leftover" tasks)
5. **`services/brain/`**: state machine from docs/ARCHITECTURE.md (IDLE, PROMPT_WALK, LEAD_WALK, PRAISE, FOLLOW_USER, PROMPT_PILL, COME_TO_USER). Inputs: `activity.*`, `med.*`, `voice.wake`, `wearable.motion`, `rel.estimate`, `robot.range`. Outputs: `robot.mode`, `robot.eyes`, `robot.bark`, `voice.say`. Rules: max re-asks, pill > walk priority, "Charlie" interrupts everything except speech in progress, quiet hours. Log episodes to SQLite.
6. **`services/activity/`**: from `wearable.motion` → `activity.still_too_long` (demo 60 s), `activity.moving_again`, daily active-minutes baseline, `activity.decline` vs 7-day mean.
7. **`services/medication/`**: from `robot.dock reach` → `med.taken`; learn usual time (median of last N days; demo override in config); emit `med.late` / `med.missed`.
8. **`tools/simulator/`** (do early; unblocks everyone): fake wearable + fake robot using the same JSON, scripted scenarios, terminal view of eyes/mode/speech, time-speed flag.
9. **`shared/`**: keep protocol.py and config.yaml in sync with MESSAGES.md. Run the integration tests and the demo rehearsals; own the README "how to run".

## Priority order (so the demo survives if time is short)
1. Stub `range_get()` + simulator skeleton (unblock others) → 2. eyes → 3. brain (walk flow) → 4. real obstacle sensing → 5. activity + medication → 6. mic/"Charlie" → 7. decline detection, SQLite episode log, polish.
If overloaded, hand the simulator or activity/medication to Sara (free after printing).

## Done when
Eyes change colour/pattern on `robot.eyes`; blocked flag flips when you put a hand in front; the full demo script in docs/PLAN.md runs twice in a row.
