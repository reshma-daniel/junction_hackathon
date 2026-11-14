#!/usr/bin/env python3
"""Local wake word ("Kaamos") with Vosk: offline, free, no credits.

Vosk runs in *grammar mode*: it may only choose between our name's sound-alikes and "something else",
which makes it fast and hard to fool. The small English model (~40 MB) downloads by itself
on first run into ~/.cache/vosk.

    python wake.py                 # laptop mic, prints voice.wake events
    python wake.py --list-mics     # pick a mic, then --mic <number or name>

Audio from the robot's mic (`robot.audio` clips) can be pushed in with WakeListener.feed().
"""
from __future__ import annotations

import argparse
import json
import queue
import sys
import time

SAMPLE_RATE = 16000
# "Kaamos" is not an English word, so Vosk cannot know it. These are what it hears instead
# (tested on 5 voices x 4 phrasings: 20/20 detected). Don't add "calm as"/"calm": they fire on
# "stay calm and...". "charlie" still works as a backup name.
ALIASES = ["commas", "commerce", "comas", "calm us", "come us", "charlie"]
NAME = "kaamos"


class WakeListener:
    def __init__(self, on_wake, is_muted=lambda: False, device=None, min_conf: float = 0.6,
                 cooldown_s: float = 2.0, model_path: str | None = None):
        from vosk import KaldiRecognizer, Model, SetLogLevel
        SetLogLevel(-1)
        model = Model(model_path) if model_path else Model(lang="en-us")
        self.rec = KaldiRecognizer(model, SAMPLE_RATE, json.dumps(ALIASES + ["[unk]"]))
        self.rec.SetWords(True)
        self.on_wake = on_wake
        self.is_muted = is_muted
        self.device = int(device) if device and str(device).isdigit() else device
        self.min_conf = min_conf
        self.cooldown_s = cooldown_s
        self._last_fire = 0.0
        self._was_muted = False
        self._q: queue.Queue[bytes] = queue.Queue()

    def feed(self, pcm: bytes) -> None:
        """Push 16 kHz mono s16 audio (laptop mic or a robot.audio clip)."""
        if self.is_muted():          # robot is talking: ignore what the mic hears
            self._was_muted = True
            return
        if self._was_muted:          # forget half-heard words from while we were muted
            self.rec.Reset()
            self._was_muted = False
        if self.rec.AcceptWaveform(pcm):
            self._check(json.loads(self.rec.Result()))

    def _check(self, result: dict) -> None:
        """Fire when an alias appears as consecutive words, each heard confidently enough."""
        words = result.get("result", [])
        tokens = [w.get("word") for w in words]
        for alias in ALIASES:
            parts = alias.split()
            for i in range(len(tokens) - len(parts) + 1):
                if tokens[i:i + len(parts)] != parts:
                    continue
                conf = min(float(w.get("conf", 0)) for w in words[i:i + len(parts)])
                if conf < self.min_conf:
                    continue
                now = time.monotonic()
                if now - self._last_fire >= self.cooldown_s:
                    self._last_fire = now
                    self.on_wake(NAME, round(conf, 2))
                return

    def run(self) -> None:
        """Listen on the laptop microphone until Ctrl+C."""
        import sounddevice as sd

        def cb(data, frames, t, status):
            self._q.put(bytes(data))

        with sd.RawInputStream(samplerate=SAMPLE_RATE, blocksize=4000, dtype="int16",
                               channels=1, device=self.device, callback=cb):
            while True:
                self.feed(self._q.get())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mic", help="input device number or name")
    ap.add_argument("--list-mics", action="store_true")
    ap.add_argument("--min-conf", type=float, default=0.6)
    args = ap.parse_args()
    if args.list_mics:
        import sounddevice as sd
        print(sd.query_devices())
        return
    print("Listening... say 'Kaamos' (Ctrl+C to quit)", file=sys.stderr)
    wl = WakeListener(lambda w, c: print(json.dumps({"type": "voice.wake", "ts": time.time(),
                                                     "word": w, "confidence": c}), flush=True),
                      device=args.mic, min_conf=args.min_conf)
    try:
        wl.run()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
