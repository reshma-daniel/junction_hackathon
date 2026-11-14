# services/voice — Owner: Wiam

Kaamos's voice: warm phrases, dog sounds, 5 reactions, and its name as a wake word.

- **A library rendered once.** Every clip is generated with ElevenLabs a single time and saved in
  `library/`, which **is committed to git**. Teammates just `git pull`: nobody spends credits again.
  `render.py` only renders clips that are missing, so running it twice costs nothing.
- **Hears its name offline.** "Kaamos" is detected locally (Vosk), free, nothing sent to the cloud.

```
phrases.yaml ─┐                           ┌─► robot speaker (USB: speaker_play_pcm chunks)
sfx.yaml ─────┼─► render.py ─► library/ ─► voice.py ─┤
reactions.yaml┘  (ElevenLabs, once)        (+ reactions.py)   └─► events: voice.done, voice.reacting, ...
laptop mic ─► wake.py (Vosk, offline) ─► voice.wake {word:"kaamos"}  (muted while Kaamos makes sound)
```

## The 5 reactions
| Reaction | When (brain state) | What Kaamos does | Eyes |
|---|---|---|---|
| `wake_up` | start of day / leaving sleep (→ IDLE) | yawn, "Good morning! I'm awake…" | calm, pulse |
| `called` | `voice.wake` → COME_TO_USER | chirp, happy yips, "You called? I'm here!" | happy, blink |
| `encourage` | PROMPT_WALK, re-asks | escalates, see below | prompt |
| `pill` | PROMPT_PILL, re-asks | escalates, see below | prompt |
| `reward` | PRAISE (`task`: walk / pill / other) | excited spin, praise for that task, chime | success, wink |

**Escalation** (`encourage`, `pill`): the brain sends `attempt` (1 = first reminder) and optionally
`late_s`. Level = the higher of the two (late thresholds: 0 / 30 / 60 s in the demo profile, 0 / 15 / 30 min
in production). After `max_reasks` (shared/config.yaml) Kaamos gently backs off, never guilt.

| attempt | encourage | pill |
|---|---|---|
| 1 | happy yips + "Follow me, let's walk a little!" | knock + "Knock knock! It's time for your medicine." |
| 2 | curious whine + "No rush. Just a few steps together?" | begging whine + gentle reminder |
| 3 | woof woof + "Pretty please? Just to the window and back!" | knock knock + whine + "Please take your medicine?" |
| 4+ | soft sigh + "That's okay. We can try again later." | soft sigh + "Okay. I'll remind you a little later." |

Edit the steps in `reactions.yaml` and the words in `phrases.yaml`; then `python render.py` renders only
the new lines.

## Setup (once)
```bash
cd services/voice
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # ELEVENLABS_API_KEY + ELEVENLABS_VOICE_ID (only needed to render)
python render.py --dry-run    # what is missing ("0 to render" = library complete)
python render.py              # render the missing clips, then commit library/
```

## Try it (robot on USB)
```bash
python voice.py react pill --attempt 2   # one reaction at one level
python voice.py react reward --task walk
python voice.py reactions                # every reaction and level, once
python voice.py charlie                  # say "Kaamos" -> `called` reaction
python voice.py say walk_prompt          # a single phrase  |  sound yawn  |  bark 2  |  list
```
`--link laptop` plays on the laptop, `--port /dev/cu.usbmodemXXXX` picks the board, `--volume 0.5` (1.0 distorts).

## For the brain (Reshma)
`python voice.py serve --listen` takes one JSON message per line on stdin and prints events on stdout.
From Python: `Voice(make_link("usb")).reactions.play("pill", attempt=2)`, or `reactions.plan(...)` to
see the level and eyes without playing.

| In | Out |
|---|---|
| `{"type":"voice.react","reaction":"pill","attempt":2,"late_s":40}` | `voice.reacting {reaction, level, eyes}` at the start (set the eyes from it), `voice.reaction_done {reaction, level, completed}` at the end |
| `{"type":"voice.react","reaction":"reward","task":"walk"}` | same |
| `{"type":"voice.say","intent":"walk_prompt"}` | `voice.done {intent, completed}` |
| `{"type":"robot.bark","count":2}` / `{"type":"robot.say_clip","clip":"yawn"}` | plays it |
| `{"type":"voice.stop"}` | cuts the current sound and drops the queue |
| (with `--listen`) someone says "Kaamos" | `voice.wake {word:"kaamos", confidence}` |

`voice.react`, `voice.reacting` and `voice.reaction_done` are new: add them to docs/MESSAGES.md once the team agrees.

## USB and the gateway (Wanhui)
Nothing changes in Wanhui's protocol: the gateway already plans a USB fallback (JSON lines, 115200).
The only rule is that **one program at a time can open the robot's USB port**:
- **Now:** voice.py opens the port itself (`--link usb`). Fine while the gateway isn't running.
- **When everything runs together:** the gateway holds the port, so it shares its connection:
  `AtechUsbLink(board=gateway_board, lock=gateway_lock)`. Audio chunks and drive/eye commands then take
  turns on the same cable (a command waits at most about 64 ms while Kaamos speaks).
- **If the gateway runs as a separate program:** use `BusLink(send)`. It emits `robot.audio_out`, and the
  gateway forwards each one as the Atech action `speaker_play_pcm` (it already converts every team
  message into an Atech action, so this is one more line).

## Firmware
No custom code: the Atech `speaker` module's built-in `speaker_play_pcm` action plays our chunks.
The robot's `project.yaml` just needs `{id: speaker, instance: speaker, ports: [N, N+1]}`.
All sounds come from the laptop library, so barks work with no Wi-Fi. The microSD idea is only
needed if the robot goes wireless and streaming stutters.

## Files
| File | What it does |
|---|---|
| `phrases.yaml` | every line Kaamos says, per intent, with an emotion |
| `sfx.yaml` | prompts for barks, knocks, whines, yawns, chimes |
| `reactions.yaml` | the 5 reactions: steps, escalation levels, eyes |
| `render.py` | ElevenLabs once (v3 + emotion tag, fallback model; Sound Effects API), cleans audio, checks every reaction's clips exist |
| `library/` | the rendered clips + `manifest.json` (committed) |
| `voice.py` | plays phrases/sounds (never the same variant twice in a row), mutes the mic while speaking, CLI + `serve` |
| `reactions.py` | picks the level and plays a reaction |
| `links.py` | where audio goes: robot USB (own or shared board), gateway bus, laptop, nowhere (tests) |
| `wake.py` | offline "Kaamos" detection (Vosk listens for sound-alikes like "commas", "commerce"; "Charlie" still works) |

## Privacy
Mic audio never leaves the laptop: the wake word is detected locally and nothing is stored.
