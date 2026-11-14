#!/usr/bin/env python3
"""Kaamos voice: plays library phrases, sounds and reactions on the robot, and hears "Kaamos".

Try it (robot on USB):
    python voice.py preview walk_prompt     # FREE: read the sentences aloud with the Mac's voice (no render)
    python voice.py list                    # what is in the library
    python voice.py playall --link laptop   # every variant of every phrase and sound, labelled
    python voice.py react pill --attempt 2  # a reaction: wake_up | called | encourage | pill | reward
    python voice.py react reward --task walk
    python voice.py reactions               # every reaction and level once
    python voice.py say walk_prompt         # one phrase (a different variant each time)
    python voice.py sound yawn              # one sound
    python voice.py bark 2                  # woof woof
    python voice.py demo                    # every phrase and sound once
    python voice.py charlie                 # say "Kaamos" -> the `called` reaction
    python voice.py chat                    # live conversation with the Kaamos agent (max ~90 s)
    python voice.py charlie --chat          # say "Kaamos" -> bark -> live conversation
    python voice.py serve --listen          # for the brain: JSON in on stdin, events out on stdout

Add --link laptop to hear it on the laptop instead of the robot, --port to pick the USB port.
"""
from __future__ import annotations

import argparse
import json
import queue
import random
import sys
import threading
import time

from common import CACHE, REPO, config, read_manifest, read_wav, short_hash, write_wav, clean_pcm
from links import Link, make_link

sys.path.insert(0, str(REPO))
from shared.protocol import msg  # noqa: E402

MUTE_TAIL_S = 0.3  # keep the mic muted this long after the robot stops making sound


class Voice:
    def __init__(self, link: Link, emit=None):
        self.link = link
        self.emit = emit or (lambda m: print(json.dumps(m), flush=True))
        self.manifest = read_manifest()
        self._last: dict[str, str] = {}      # group -> last file played (avoid repeats)
        self._lock = threading.Lock()        # one sound at a time
        self._stop = threading.Event()
        self._speaking = threading.Event()
        self._quiet_since = 0.0

    # ---- for the wake word: is the robot making sound right now (or just was)? ----
    def mic_muted(self) -> bool:
        return self._speaking.is_set() or time.monotonic() - self._quiet_since < MUTE_TAIL_S

    def stop(self) -> None:
        self._stop.set()

    def stopped(self) -> bool:
        """True if voice.stop cut the last clip."""
        return self._stop.is_set()

    # ---- what the brain asks for ----
    def say(self, intent: str, text: str | None = None, emotion: str | None = None, quiet: bool = False) -> bool:
        if text:
            pcm = self._live_text(text, intent)
        else:
            pcm = self._pick("tts", intent)
        if pcm is None:
            print(f"! no clip for intent {intent!r}", file=sys.stderr)
            return False
        done = self._play(pcm)
        if not quiet:
            self.emit(msg("voice.done", intent=intent, completed=done))
        return done

    def sound(self, name: str, count: int = 1, gap: float = 0.12) -> bool:
        for i in range(max(1, count)):
            pcm = self._pick("sfx", name)
            if pcm is None:
                print(f"! no sound {name!r}", file=sys.stderr)
                return False
            if not self._play(pcm):
                return False
            if i < count - 1:
                time.sleep(gap)
        return True

    def bark(self, count: int = 1) -> bool:
        return self.sound("bark", count)

    def handle(self, m: dict) -> None:
        """One message from the brain (MESSAGES.md names)."""
        t = m.get("type")
        if t == "voice.say":
            self.say(m.get("intent", ""), m.get("text"), m.get("emotion"))
        elif t == "robot.bark":
            self.bark(int(m.get("count", 1)))
        elif t == "robot.say_clip":
            clip = m.get("clip", "")
            self.say(clip) if clip in self.manifest["tts"] else self.sound(clip)
        elif t == "voice.sound":  # extra: any sound from sfx.yaml
            self.sound(m.get("name", ""), int(m.get("count", 1)))
        elif t == "voice.react":  # one of the 5 reactions (reactions.yaml)
            self.reactions.play(m.get("reaction", ""), int(m.get("attempt", 1)), m.get("late_s"), m.get("task"))
        elif t == "voice.chat":  # live conversation with the agent (falls back to `called` offline)
            from agent import chat
            chat(self)
        elif t == "voice.stop":
            self.stop()

    @property
    def reactions(self):
        if not hasattr(self, "_reactions"):
            from reactions import Reactions
            self._reactions = Reactions(self)
        return self._reactions

    # ---- internals ----
    def _pick(self, kind: str, group: str) -> bytes | None:
        options = self.manifest.get(kind, {}).get(group, [])
        if not options:
            return None
        fresh = [o for o in options if o["file"] != self._last.get(group)] or options
        choice = random.choice(fresh)
        self._last[group] = choice["file"]
        return read_wav(CACHE / choice["file"])

    def _play(self, pcm: bytes) -> bool:
        with self._lock:
            self._stop.clear()
            self._speaking.set()
            try:
                return self.link.play(pcm, self._stop)
            finally:
                self._speaking.clear()
                self._quiet_since = time.monotonic()

    def _live_text(self, text: str, intent: str) -> bytes | None:
        """Free text from the brain: render once with the fast model, then it is cached too."""
        path = CACHE / "live" / f"{short_hash(text)}.wav"
        if path.exists():
            return read_wav(path)
        try:
            import requests
            cfg = config()
            r = requests.post(f"https://api.elevenlabs.io/v1/text-to-speech/{cfg['voice_id']}",
                              params={"output_format": "pcm_16000"}, timeout=20,
                              headers={"xi-api-key": cfg["api_key"]},
                              json={"text": text, "model_id": cfg.get("tts_model", "eleven_flash_v2_5")})
            r.raise_for_status()
            pcm = clean_pcm(r.content)
            write_wav(path, pcm)
            return pcm
        except Exception as e:  # no internet / no credits: fall back to a cached line
            print(f"! live TTS failed ({e}); using a cached {intent!r} line", file=sys.stderr)
            return self._pick("tts", intent)


# ---------------- command line ----------------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["preview", "playall", "list", "chat", "react", "reactions", "say", "text", "sound", "bark", "demo", "charlie", "serve"])
    ap.add_argument("arg", nargs="?", help="reaction / intent / text / sound name / bark count")
    ap.add_argument("--attempt", type=int, default=1, help="react: reminder number (1 = first)")
    ap.add_argument("--late", type=float, help="react: seconds late (escalates too)")
    ap.add_argument("--task", help="react reward: walk | pill | other")
    ap.add_argument("--link", default="usb", help="usb (robot) | laptop | print | bus")
    ap.add_argument("--port", help="robot USB port, e.g. /dev/cu.usbmodem1101 (default: first board)")
    ap.add_argument("--volume", type=float, default=0.4, help="robot speaker volume 0..1 (1.0 clips)")
    ap.add_argument("--listen", action="store_true", help="serve: also listen for 'Kaamos'")
    ap.add_argument("--chat", action="store_true", help="charlie: start a live conversation instead of the reaction")
    ap.add_argument("--mic", help="microphone device name/number for the wake word (default: system)")
    args = ap.parse_args()

    if args.command == "preview":  # free check of the wording: macOS voice, no ElevenLabs, no render
        import subprocess
        from common import load_yaml
        phrases = load_yaml("phrases.yaml")
        for intent, entry in phrases.items():
            if args.arg and intent != args.arg:
                continue
            print(f"{intent}  ({entry.get('emotion', '')})")
            for v in entry.get("variants", []):
                text = v if isinstance(v, str) else v["text"]
                print(f"   - {text}")
                if sys.platform == "darwin":
                    subprocess.run(["say", "-v", "Samantha", "-r", "175", text.replace("Kaamos", "Kah-moss")])
        return

    if args.command == "list":
        man = read_manifest()
        for kind, title in (("tts", "Phrases (voice.say <intent>)"), ("sfx", "Sounds (voice.sound <name>)")):
            print(title)
            for group, clips in man[kind].items():
                print(f"  {group:<20} {len(clips)} variant(s)  e.g. {clips[0].get('text') or ''}")
        return

    voice = Voice(make_link(args.link, args.port, args.volume))
    try:
        if args.command == "chat":
            from agent import chat
            chat(voice, mic_device=args.mic)
        elif args.command == "react":
            voice.reactions.play(args.arg or "called", args.attempt, args.late, args.task)
        elif args.command == "reactions":  # play every reaction, every level, once
            r = voice.reactions
            for name in r.names():
                n = len(r.reactions[name].get("levels") or {}) + ("give_up" in r.reactions[name])
                for attempt in range(1, max(1, n) + 1):
                    print(f"> {name}" + (f" attempt {attempt}" if n else ""), file=sys.stderr)
                    r.play(name, attempt=attempt, task="walk" if name == "reward" else None)
                    time.sleep(0.6)
        elif args.command == "playall":  # every single clip, with its text, to review the library
            for kind in ([args.arg] if args.arg in ("tts", "sfx") else ["tts", "sfx"]):  # playall sfx = sounds only
                for group, clips in voice.manifest[kind].items():
                    for i, c in enumerate(clips, 1):
                        print(f"[{kind}] {group} {i}/{len(clips)}: {c.get('text') or ''}", flush=True)
                        voice._play(read_wav(CACHE / c["file"]))
                        time.sleep(0.5)
        elif args.command == "say":
            voice.say(args.arg or "walk_prompt")
        elif args.command == "text":
            voice.say("gentle_checkin", text=args.arg or "Hello, I'm Kaamos.")
        elif args.command == "sound":
            voice.sound(args.arg or "bark")
        elif args.command == "bark":
            voice.bark(int(args.arg or 1))
        elif args.command == "demo":
            for intent in voice.manifest["tts"]:
                print(f"> {intent}", file=sys.stderr)
                voice.say(intent)
                time.sleep(0.4)
            for name in voice.manifest["sfx"]:
                print(f"> {name}", file=sys.stderr)
                voice.sound(name)
                time.sleep(0.4)
        elif args.command == "charlie":
            from wake import WakeListener

            busy = threading.Lock()

            def on_wake(word, conf):
                voice.emit(msg("voice.wake", word=word, confidence=conf))
                if not busy.acquire(blocking=False):  # already chatting: ignore
                    return
                try:
                    if args.chat:
                        from agent import chat
                        chat(voice, mic_device=args.mic)
                    else:
                        voice.reactions.play("called")
                finally:
                    busy.release()
            print("Listening... say 'Kaamos' (Ctrl+C to quit)", file=sys.stderr)
            WakeListener(on_wake, is_muted=voice.mic_muted, device=args.mic).run()
        elif args.command == "serve":
            if args.listen:
                from wake import WakeListener
                wl = WakeListener(lambda w, c: voice.emit(msg("voice.wake", word=w, confidence=c)),
                                  is_muted=voice.mic_muted, device=args.mic)
                threading.Thread(target=wl.run, daemon=True).start()
            # One worker plays messages in order; stdin stays free so voice.stop works mid-sentence.
            jobs: queue.Queue[dict] = queue.Queue()

            def worker():
                while True:
                    m = jobs.get()
                    try:
                        voice.handle(m)
                    except Exception as e:  # a bad message must not kill the voice
                        print(f"! {m.get('type')}: {e}", file=sys.stderr)
                    finally:
                        jobs.task_done()
            threading.Thread(target=worker, daemon=True).start()
            print("Ready: one JSON message per line, e.g. "
                  '{"type":"voice.say","intent":"walk_prompt"}', file=sys.stderr)
            for line in sys.stdin:
                line = line.strip()
                if not line:
                    continue
                try:
                    m = json.loads(line)
                except json.JSONDecodeError:
                    print(f"! not JSON: {line[:80]}", file=sys.stderr)
                    continue
                if m.get("type") == "voice.stop":  # drop what is queued and cut the current clip
                    while not jobs.empty():
                        jobs.get_nowait()
                        jobs.task_done()
                    voice.stop()
                else:
                    jobs.put(m)
            jobs.join()  # stdin closed: let queued clips finish
    except KeyboardInterrupt:
        pass
    finally:
        voice.link.close()


if __name__ == "__main__":
    main()
