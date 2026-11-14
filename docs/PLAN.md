# Team plan

Contract between everyone: [MESSAGES.md](MESSAGES.md). Personal task sheets: [tasks/](tasks/).

| Person | Owns | Task sheet |
|---|---|---|
| **Sara** | Wheels, 4 DC motors, drive firmware, power, and printing the ready-made STLs (4 wheels, 2 plates, nuzzle, 2 ears) | [tasks/sara.md](tasks/sara.md) |
| **Wiam** | Speaker + ElevenLabs (TTS, STT, phrases, audio streaming, wake-word text matching) | [tasks/wiam.md](tasks/wiam.md) |
| **Wanhui** | Board-to-board link & relative position, gateway, user wearable (IMU), pill-dock detection | [tasks/wanhui.md](tasks/wanhui.md) |
| **Reshma** | Eyes (2 LED grids), microphone, distance sensors/obstacles **+ every leftover**: brain/state machine, activity & medication logic, simulator, integration, demo | [tasks/reshma.md](tasks/reshma.md) |

## The one-firmware problem
The robot is ONE board, so Sara, Wiam, Wanhui and Reshma all add code to ONE robot firmware.
Rule: **one source file per person, a tiny shared interface, one integrator** (see
[firmware/robot/README.md](../firmware/robot/README.md)). Wanhui owns `comms` (the JSON in/out dispatcher),
so nobody else parses JSON; everyone just implements the handler functions listed in their task sheet.

## Hardware map (from the photo)
Robot board: 4x DC Motor (corners) · Speaker (big square) · Microphone · 2x LED Grid (eyes) · 3x Distance Sensor · USB-C (port 8).
Wearable board (separate kit): Orientation Sensor (IMU) + power bank.
Fill in real port numbers in [firmware/robot/PORTS.md](../firmware/robot/PORTS.md) in the first hour.

## Milestones
1. **M0 (hour 1):** read MESSAGES.md together, fix it; everyone installs Atech tooling and uploads hello-world;
   fill PORTS.md; decide WiFi/project-ID setup (OPEN_QUESTIONS #1).
2. **M1 (each alone):** Sara wheels drive on `robot.drive` · Reshma eyes + obstacle readout · Wiam speaks a phrase through
   the speaker · Wanhui wearable `wearable.motion` + `robot.dock` reach arrive at the laptop · Reshma simulator running.
3. **M2:** still 60 s → "Follow me" → robot walks and avoids an obstacle.
4. **M3:** user not moving → robot returns/follows & re-asks; pill late → follow → ask → dock reach → praise; "Charlie" → comes, woof woof.
5. **M4:** tune, rehearse, demo twice in a row.

## Demo script (≈3 min)
1. User sits still 60 s → eyes blue→yellow → "Hey, let's stretch our legs. Follow me!" → robot walks around an obstacle.
2. User stays still → robot comes back, asks again → user walks → eyes green, praise.
3. Pill time passes (demo-scaled) → robot approaches user: "Time for your medicine." → hand at dock → green, praise.
4. Say "Charlie!" → robot comes closer, woof woof, eyes blink.

## Risks to check early
See [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md). Biggest: relative position between boards (Wanhui), audio over WiFi (Wiam), 4 motors brown-out (Sara).
Reshma carries the most scope: if she falls behind, the first things to hand back are the simulator and the activity/medication baselines (Sara is free once the chassis is printed).
