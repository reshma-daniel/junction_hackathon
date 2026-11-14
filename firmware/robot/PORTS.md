# Robot board port map (fill in during M0)

Atech board: 12 ports (1-7, 9-11, 13-14); port 8 = USB-C, port 12 = reset. Double-width modules take two ports.

| Module | Port(s) | Position on robot | Owner | Notes |
|---|---|---|---|---|
| DC Motor front-left | ? | | Sara | |
| DC Motor front-right | ? | | Sara | |
| DC Motor rear-left | ? | | Sara | |
| DC Motor rear-right | ? | | Sara | |
| Speaker | ? | | Wiam | double-width |
| Microphone | 2, 3 | | Reshma | double-width (I2S), instance `microphone` |
| LED Grid LEFT eye | 13 | | Reshma | instance `eye_left`; if eyes look swapped, swap 13/10 in robot_eyes/project.yaml |
| LED Grid RIGHT eye | 10 | | Reshma | instance `eye_right` |
| Distance — front-left | ? | | Reshma | obstacles |
| Distance — front-right | ? | | Reshma | obstacles |
| Distance — pill dock | ? | | Wanhui | points at pill compartment |

Photo shows 3 distance sensors: two stacked on one side and one on the bottom edge. Decide which is the pill dock and which two face forward.
Motor wiring: confirm which side is forward and the sign of +speed for left/right (Sara).
