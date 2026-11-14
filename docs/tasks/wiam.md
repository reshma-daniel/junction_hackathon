# Wiam — Speaker & ElevenLabs

**Goal:** Kaamos speaks warmly and clearly through its small speaker, and understands when someone calls "Charlie".

## Tasks
1. **ElevenLabs setup:** API key via env `ELEVENLABS_API_KEY` (never commit), choose a warm voice, set `voice_id` in shared/config.yaml.
2. **`services/voice/` (laptop, Python):**
   - `voice.say {intent, text?, emotion}` → pick a phrase from `phrases.yaml` (several variants per intent, avoid repeats) → ElevenLabs TTS → PCM 16 kHz mono → chunks → `robot.audio_out {seq,last,pcm_b64}`. Emit `voice.done` at the end.
   - Pre-render and cache common phrases at startup (`cache/`, git-ignored): fast + survives bad WiFi.
   - **STT:** receive `robot.audio` clips (from Reshma's mic), reassemble, ElevenLabs speech-to-text, delete the audio after. Fuzzy-match "charlie" (charlie/charly/chali/…) → `voice.wake {word,confidence}`.
3. **`audio.*` robot firmware:** `audio_play_chunk(seq,pcm,last)` buffering so playback has no gaps; `audio_bark(n)` local woof sound (no cloud, instant) for `robot.bark`; optional `audio_play_clip(id)` from microSD for `robot.say_clip`.
4. **Phrase library** (short, warm, no guilt, varied) for intents: `walk_prompt` ("Follow me, let's walk a little!"), `walk_reask`, `walk_praise`, `pill_prompt`, `pill_reask`, `pill_praise`, `greeting_charlie`, `gentle_checkin`, `low_battery`.
5. **Test intelligibility** through the actual speaker (volume, speed, voice stability).

## You consume
`voice.say` (brain) · `robot.audio` (from Reshma/Wanhui comms) · `robot.bark`, `robot.audio_out`, `robot.say_clip`.
## You produce
`robot.audio_out`, `voice.done`, `voice.wake`.

## Done when
`voice.say walk_prompt` is audible and clear within ~2 s; shouting "Charlie" from 2 m produces `voice.wake` within ~2 s; bark works with no WiFi.

## Risk (report by M1)
Audio streamed over JSON may stutter. If so, fallback = pre-rendered clips on the robot's SD card triggered by `robot.say_clip`. Tell the team which one we use.
