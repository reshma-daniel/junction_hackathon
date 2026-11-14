# Sara — Wheels, chassis, motors

**Goal:** a sturdy dog-shaped body that drives smoothly, and a motion layer the rest of the team commands with simple modes.

## Tasks
1. **3D printing: files are ready in `/Users/sara/junction/3d/`, just print these (nothing to design):**
   | File | Qty | What it is |
   |---|---|---|
   | `wheel_1.stl` … `wheel_4.stl` | 4 | the four wheels (one per motor) |
   | `plate_4x8_big_holes.stl` | 1 | big base plate (4x8 grid) for the board/modules |
   | `plate_2x8_solid.stl` | 1 | smaller solid plate (2x8 grid) |
   | `dog_nuzzle_4x8.stl` | 1 | the dog muzzle/snout |
   | `dog_ear_left_3cm.stl`, `dog_ear_right_3cm.stl` | 1 each | ears, 3 cm |
   Print wheels first (needed for driving tests), then plates, then nuzzle and ears. After printing, check the wheels fit the motor shafts and that the nuzzle does not block the distance sensors' view (tell Reshma if it does).
2. **Motors:** wire/configure 4 DC motors as left side / right side. Verify forward sign and top speed; add a minimum PWM so it actually moves.
3. **`motion.*` firmware** (see firmware/robot/README.md):
   - `motion_drive(left,right)` -255..255, ramped (no jerk).
   - `motion_set_mode(mode)`:
     - `walk`: forward; if `range_get().blocked` → stop, turn toward the freer side (`left_mm` vs `right_mm`), continue.
     - `follow`: steer using `range_get().bearing` of the nearest object at 300–1200 mm; keep ~400 mm. (Optional: use `rel.estimate` forwarded by the laptop as `robot.drive` commands.)
     - `come`: like follow, stop at ~400 mm, then `idle`.
     - `stop`/`idle`: motors off.
   - Safety: obstacle < `obstacle_stop_mm` always stops forward motion, whatever the mode; watchdog (no laptop message 2 s) → stop.
   - Emit `robot.state` at 1 Hz.
4. **Power:** check 4 motors don't brown-out the ESP32 (separate supply/capacitor if resets).

## You consume
`robot.mode`, `robot.drive` (from laptop) · `range_get()` (from Reshma's `range.*`).
## You produce
`robot.state`.

## Done when
From the laptop: `robot.mode walk` crosses a room and goes around a box; `follow` tracks a hand/leg; unplugging WiFi stops the robot within 2 s.

## Dependencies
Needs Reshma's `range_get()` stub early (she should push a version returning fixed numbers on day 1). Tell Wanhui which port the dock sensor mount uses.

## After your tasks are done
Free capacity goes to Reshma: ask for the simulator (`tools/simulator`) or activity/medication logic.
