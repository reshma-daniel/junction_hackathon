# Robot board port map (fill in during M0)

Atech board: 12 ports (1-7, 9-11, 13-14); port 8 = USB-C, port 12 = reset. Double-width modules take two ports.

| Module | Port(s) | Position on robot | Owner | Notes |
|---|---|---|---|---|
| DC Motor front-left | 14 | top-left in photo (USB-C end = front) | Sara | + speed pushes it BACKWARD: flip sign |
| DC Motor front-right | 6 | top-right | Sara | + speed = forward |
| DC Motor rear-left | 9 | bottom-left | Sara | + speed pushes it BACKWARD: flip sign |
| DC Motor rear-right | 1 | bottom-right | Sara | + speed = forward |
| Speaker | ? | | Wiam | double-width |
| Microphone | ? | | Reshma | |
| LED Grid LEFT eye | ? | | Reshma | |
| LED Grid RIGHT eye | ? | | Reshma | |
| Distance — front-left | ? | | Reshma | obstacles |
| Distance — front-right | ? | | Reshma | obstacles |
| Distance — pill dock | ? | | Wanhui | points at pill compartment |

Photo shows 3 distance sensors: two stacked on one side and one on the bottom edge. Decide which is the pill dock and which two face forward.
Motor wiring: confirm which side is forward and the sign of +speed for left/right (Sara).

Tested 2026-11-14 (Sara): forward = toward the USB-C end. Right motors (1, 6) +speed = forward; left motors (9, 14) +speed = backward, so left sign = -1.
Needs a power bank: USB from the laptop alone did not run the motors.
