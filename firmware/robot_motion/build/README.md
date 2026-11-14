# robot_motion

Generated firmware for **Atech 14-Port Board** (`14port`).

## Modules

- **DC Motor** (`dc_motor`) as `m1` on `port_1`
- **DC Motor** (`dc_motor`) as `m6` on `port_6`
- **DC Motor** (`dc_motor`) as `m9` on `port_9`
- **DC Motor** (`dc_motor`) as `m14` on `port_14`
- **Distance Sensor (VL53L5CX 8x8 ToF)** (`distance_sensor`) as `distance_sensor` on `port_11`

## Build & flash

This folder is generated. Change `project.yaml` one level up and run, from there:

```bash
atech build .
atech upload .
```

It is also a plain PlatformIO project (`pio run`, `pio run -t upload`), but
anything edited here is overwritten by the next `atech build`.
