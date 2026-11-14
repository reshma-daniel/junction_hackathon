# services/voice — Owner: Wiam

ElevenLabs for all speech.

## Out: `voice.say {intent, text?, emotion}`
1. Look up phrase in `phrases.yaml` (several variants per intent; pick one not used recently).
2. ElevenLabs TTS -> PCM 16 kHz mono -> chunk -> `robot.audio_out`. Emit `voice.done` at the end.
3. Pre-render + cache common phrases at startup (`cache/`, git-ignored) for speed and offline resilience.

## In: `robot.audio` clips
1. Reassemble clip -> ElevenLabs STT -> text.
2. Fuzzy-match wake word "charlie" (charlie/charly/chali...) -> emit `voice.wake`.
3. Do not store audio; delete after transcription.

## Intents to write phrases for
`walk_prompt` ("Follow me, let's walk a little!"), `walk_reask`, `walk_praise`, `pill_prompt`, `pill_reask`,
`pill_praise`, `greeting_charlie`, `gentle_checkin` (activity decline). Warm, short, no guilt, no pressure.

## Env
`ELEVENLABS_API_KEY` in your shell / `.env` (never commit).
