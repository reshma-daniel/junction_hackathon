"""Live conversation with Kaamos (ElevenLabs agent, your voice), for at most ~90 seconds.

    python voice.py chat                 # happy bark, then talk (robot speaker over USB)
    python voice.py chat --link laptop   # same, on the laptop speakers
    python voice.py charlie --chat       # say "Kaamos" -> bark -> conversation

Mic = laptop mic (muted while Kaamos speaks, so it never hears itself).
Kaamos's voice goes to the same place as the clips (robot USB or laptop).
Tools the agent can use: bark, set_eyes (-> robot.eyes event), end_conversation.
No internet / no agent: falls back to the pre-rendered `called` reaction.
"""
from __future__ import annotations

import json
import queue
import sys
import threading
import time

from common import HERE, config

AGENT_FILE = HERE / "agent.json"
EYES = {"calm": "#2f6fff", "happy": "#9b5de5", "success": "#2fd06b", "listen": "#ffffff"}
LOCAL_LIMIT_S = 95  # safety net on top of the agent's own 90 s limit


def agent_id() -> str | None:
    import os
    if AGENT_FILE.exists():
        return json.loads(AGENT_FILE.read_text()).get("agent_id")
    return os.getenv("KAAMOS_AGENT_ID")


def _audio_interface_class():
    from elevenlabs.conversational_ai.conversation import AudioInterface

    class KaamosAudio(AudioInterface):
        """Laptop mic in; agent audio out through the Voice's link (robot or laptop)."""

        def __init__(self, voice, mic_device=None):
            self.voice = voice
            self.mic_device = mic_device
            self.q: queue.Queue[bytes] = queue.Queue()
            self.running = False

        def start(self, input_callback):
            import sounddevice as sd
            self.running = True

            def on_mic(data, frames, t, status):
                # While Kaamos is speaking, send silence: it never hears (or interrupts) itself.
                pcm = bytes(data)
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
                self.voice._play(chunk)

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

    return KaamosAudio


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

        def bark(params):
            voice.sound("bark")
            return "barked"

        def set_eyes(params):
            mood = params.get("mood", "calm")
            voice.emit({"type": "robot.eyes", "ts": time.time(), "left": EYES.get(mood, EYES["calm"]),
                        "right": EYES.get(mood, EYES["calm"]), "pattern": "solid"})
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

        conv = Conversation(
            ElevenLabs(api_key=cfg["api_key"]), aid, requires_auth=True,
            audio_interface=_audio_interface_class()(voice, mic_device), client_tools=tools,
            callback_agent_response=lambda t: print(f"Kaamos: {t}", file=sys.stderr, flush=True),
            callback_user_transcript=lambda t: print(f"You:    {t}", file=sys.stderr, flush=True),
        )
        conv_box["conv"] = conv
        voice.emit({"type": "voice.chat_started", "ts": time.time()})
        conv.start_session()
        timer = threading.Timer(LOCAL_LIMIT_S, conv.end_session)
        timer.daemon = True
        timer.start()
        cid = conv.wait_for_session_end()
        timer.cancel()
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
