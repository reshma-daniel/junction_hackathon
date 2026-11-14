// audio_hw.cpp — owner: Reshma (for the mic). The robot's speaker: Atech `speaker` module,
// instance `speaker`, ports 4+5. Wiam's laptop code plays sound through the module's built-in
// actions (speaker_play_pcm / speaker_set_volume / speaker_stop), so there is no custom audio firmware.
//
// audio_is_playing() tells mic.* to ignore what it hears while the robot itself makes sound.
// Catch: speaker_play_pcm BLOCKS the loop until each ~64 ms chunk has played, so when our code
// runs again that chunk is already over and speaker.isPlaying() can be false. A loop pass that took
// much longer than normal therefore also counts as "playing". mic.* adds 1 s of quiet after that.
#include "mic.h"

#ifdef ARDUINO
#include <Arduino.h>
#endif

static const unsigned long AUDIO_FROZEN_MS = 45;   // normal mic steps are ~20-30 ms apart

bool audio_is_playing() {
  static unsigned long last = 0;
  unsigned long now = millis();
  bool frozen = last != 0 && now - last > AUDIO_FROZEN_MS;
  last = now;
  return speaker.isPlaying() || frozen;
}
