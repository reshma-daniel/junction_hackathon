"""Live conversation with Charlie (ElevenLabs agent, your voice), for at most ~60 seconds (a short mood check-in).

    python voice.py chat                 # happy bark, then talk (robot speaker over USB)
    python voice.py chat --link laptop   # same, on the laptop speakers
    python voice.py charlie --chat       # say "Charlie" -> bark -> conversation

Mic = laptop mic (muted while Charlie speaks, so it never hears itself).
Charlie's voice goes to the same place as the clips (robot USB or laptop).
Tools the agent can use: bark, set_eyes (-> robot.eyes event), end_conversation.
No internet / no agent: falls back to the pre-rendered `called` reaction.
"""
from __future__ import annotations

import array
import json
import re
import queue
import sys
import threading
import time

from common import HERE, config

AGENT_FILE = HERE / "agent.json"
sys.path.insert(0, str(HERE.parents[1]))
from shared.protocol import MOODS  # noqa: E402  eye moods: docs/MESSAGES.md
CHECKIN_LIMIT_S = 30   # a check-in ends after 30 s (Charlie finishes its sentence first) ...
SILENCE_END_S = 5      # ... or after 5 s with nobody talking
# In an emergency (the agent calls its `emergency` tool, or the user's words say so) the panel shows the crisis
# numbers in red and the silence stop is off, but the 30 s maximum stays.
EMERGENCY_WORDS = re.compile(r"kill(ing)? myself|suicid|want(ed)? to die|wanna die|end my life|end it all|"
                             r"self[- ]?harm|hurt(ing)? myself|cut(ting)? myself|(not|don't|do not) feel safe|"
                             r"not safe|no reason to live|better off dead|can'?t go on|cannot go on", re.I)
SPEECH_PEAK = 1200     # laptop mic peak above this = someone is talking (quiet room ~600-800)
_active: dict = {}  # the conversation in progress, so end_chat() can stop it from another thread


def clear_emergency() -> None:
    """The emergency is handled (banner dismissed): the normal 30 s / 5 s limits apply again."""
    state = _active.get("state")
    if state is not None:
        state["emergency"] = False


def end_chat() -> bool:
    """End the live conversation in progress (e.g. a Pause button). True if one was running."""
    conv = _active.pop("conv", None)
    if conv is None:
        return False
    try:
        conv.end_session()
    except Exception:
        pass
    return True


def agent_id() -> str | None:
    import os
    if AGENT_FILE.exists():
        return json.loads(AGENT_FILE.read_text()).get("agent_id")
    return os.getenv("CHARLIE_AGENT_ID") or os.getenv("CHARLIE_AGENT_ID")  # old name still accepted


def _audio_interface_class():
    from elevenlabs.conversational_ai.conversation import AudioInterface

    class CharlieAudio(AudioInterface):
        """Laptop mic in; agent audio out through the Voice's link (robot or laptop)."""

        def __init__(self, voice, mic_device=None):
            self.voice = voice
            self.last_voice = time.monotonic()   # last time the user's voice was loud enough (silence stop)
            self.mic_device = mic_device
            self.q: queue.Queue[bytes] = queue.Queue()
            self.running = False

        def start(self, input_callback):
            import sounddevice as sd
            self.running = True

            def on_mic(data, frames, t, status):
                # While Charlie is speaking, send silence: it never hears (or interrupts) itself.
                pcm = bytes(data)
                if not self.voice.mic_muted() and self.q.empty():
                    samples = array.array("h", pcm)
                    if samples and max(max(samples), -min(samples)) > SPEECH_PEAK:
                        self.last_voice = time.monotonic()
                input_callback(bytes(len(pcm)) if self.voice.mic_muted() or not self.q.empty() else pcm)

            self.mic = sd.RawInputStream(samplerate=16000, channels=1, dtype="int16", blocksize=4000,
                                         device=self.mic_device, callback=on_mic)
            self.mic.start()
            self.player = threading.Thread(target=self._play_loop, daemon=True)
            self.player.start()

        def _play_loop(self):
            while self.running:
                try:
                    chunk = self.q.get(timeout=0.1)
                except queue.Empty:
                    continue
                try:
                    self.voice._play(chunk)
                except Exception as e:   # never let one bad chunk kill Charlie's voice for the whole chat
                    print(f"! chat audio chunk failed ({e})", file=sys.stderr, flush=True)

        def output(self, audio: bytes):
            self.q.put(audio)

        def interrupt(self):
            while not self.q.empty():
                self.q.get_nowait()
            self.voice.stop()

        def stop(self):
            self.running = False
            self.interrupt()
            try:
                self.mic.stop()
                self.mic.close()
            except Exception:
                pass

    return CharlieAudio


def chat(voice, mic_device=None, bark_first: bool = True) -> str | None:
    """Run one conversation. Returns the conversation id, or None if it fell back."""
    if bark_first:
        voice.sound("happy_bark")
    aid = agent_id()
    cfg = config()
    try:
        from elevenlabs.client import ElevenLabs
        from elevenlabs.conversational_ai.conversation import ClientTools, Conversation
        if not aid:
            raise RuntimeError("no agent yet: run `python agent_setup.py`")

        tools = ClientTools()
        conv_box: dict = {}
        state = {"emergency": False, "last_user": time.monotonic()}
        _active["state"] = state

        def raise_emergency(why: str):
            if not state["emergency"]:
                state["emergency"] = True
                print(f"!!! EMERGENCY ({why}): crisis numbers shown; MIELI 09 2525 0111 / 112", file=sys.stderr, flush=True)
                voice.emit({"type": "voice.emergency", "ts": time.time(), "why": why})

        def emergency(params):
            raise_emergency("Charlie heard the user is not safe")
            return "emergency noted: the crisis numbers are shown on the screen"

        def on_user(text: str):
            state["last_user"] = time.monotonic()
            print(f"You:    {text}", file=sys.stderr, flush=True)
            if EMERGENCY_WORDS.search(text or ""):
                raise_emergency("the user's words")

        def bark(params):
            voice.sound("bark")
            return "barked"

        def set_eyes(params):
            mood = params.get("mood", "calm")
            if mood not in MOODS:
                mood = "calm"
            colour, pattern, period = MOODS[mood]
            eyes = {"type": "robot.eyes", "ts": time.time(), "left": colour, "right": colour,
                    "pattern": pattern, "mood": mood}
            if period:
                eyes["period_ms"] = period
            voice.emit(eyes)
            return f"eyes {mood}"

        def end_conversation(params):
            def later():
                while voice.mic_muted():  # let the goodbye finish playing
                    time.sleep(0.1)
                conv_box["conv"].end_session()
            threading.Thread(target=later, daemon=True).start()
            return "ending"

        tools.register("bark", bark)
        tools.register("set_eyes", set_eyes)
        tools.register("end_conversation", end_conversation)
        tools.register("emergency", emergency)

        audio = _audio_interface_class()(voice, mic_device)
        conv = Conversation(
            ElevenLabs(api_key=cfg["api_key"]), aid, requires_auth=True,
            audio_interface=audio, client_tools=tools,
            callback_agent_response=lambda t: print(f"Charlie: {t}", file=sys.stderr, flush=True),
            callback_user_transcript=on_user,
        )
        conv_box["conv"] = _active["conv"] = conv
        voice.emit({"type": "voice.chat_started", "ts": time.time()})
        conv.start_session()
        done = threading.Event()

        def watchdog():   # 30 s limit and 5 s silence, both lifted in an emergency
            start = time.monotonic()
            last = start + 3   # the first "How are you feeling?" needs a moment to arrive
            quiet_since = None
            while not done.wait(0.2):
                now = time.monotonic()
                if state["emergency"]:
                    last = now   # emergency: no 5 s silence stop (let them speak), but still 30 s max
                talking = voice.mic_muted() or not audio.q.empty()   # Charlie is speaking
                if talking:
                    last = now
                    quiet_since = None
                elif quiet_since is None:
                    quiet_since = now
                finished = quiet_since is not None and now - quiet_since >= 1.2   # its sentence is over
                last = max(last, audio.last_voice, state["last_user"])
                over = now - start >= CHECKIN_LIMIT_S
                if (over and (finished or now - start >= CHECKIN_LIMIT_S + 10)) or now - last >= SILENCE_END_S:
                    print(f"(check-in ends: {'30 s' if over else '5 s of silence'})", file=sys.stderr, flush=True)
                    try:
                        conv.end_session()
                    except Exception:
                        pass
                    return
        threading.Thread(target=watchdog, daemon=True).start()
        cid = conv.wait_for_session_end()
        done.set()
        _active.pop("state", None)
        _active.pop("conv", None)
        voice.emit({"type": "voice.chat_done", "ts": time.time(), "conversation_id": cid})
        return cid
    except KeyboardInterrupt:
        try:
            conv_box["conv"].end_session()
        except Exception:
            pass
        return None
    except Exception as e:  # offline, no permission, no agent: stay friendly with the cached reaction
        print(f"! live chat unavailable ({e}); playing the pre-rendered greeting", file=sys.stderr)
        voice.say("greeting_charlie")
        return None
