// mic.* — owner: Reshma. Microphone (I2S MEMS, ports 2+3): sound level + "Charlie" call detection.
// Contract: docs/MESSAGES.md (robot.sound).
//
// How a call is detected (option A, on the board, no laptop):
//   a sound that rises clearly above the background noise, lasts like one spoken word
//   (0.25 .. 1.2 s, short gaps between syllables allowed) and is followed by quiet.
//   Claps/knocks (too short) and sentences/music (too long) are ignored.
//   Any short word counts. Later: the laptop (Wiam's speech-to-text) confirms it was "Charlie".
//
// The mic ignores everything while the robot's own speaker plays and for 1 s after.
#pragma once
#include <stdint.h>

// ---- Main API ---------------------------------------------------------------
void mic_begin();            // call once in setup
void mic_tick();             // call every loop; non-blocking (works every 20 ms)

float mic_level();           // current sound level 0..1 (robot.sound "level")
bool  mic_loud();            // sound clearly above background right now (robot.sound "loud")
bool  mic_talking();         // a sound is in progress (use for "listening" eyes)
bool  mic_called();          // true ONCE per detected call, then false until the next one
uint16_t mic_last_call_ms(); // length of the last detected call word, for logs

// ---- Interfaces mic needs from other owners -----------------------------------
bool audio_is_playing();                 // Wiam: true while the speaker plays (mic is muted)
void comms_send(const char* json_line);  // Wanhui: send one JSON object

// ---- Hardware layer (mic_hw.cpp) ------------------------------------------------
// Only place that touches the Atech microphone API.
void    mic_hw_begin();
int16_t mic_hw_level();      // RMS sound level, 0..32767
