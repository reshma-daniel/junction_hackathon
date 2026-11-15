"""Where the audio goes. Every link plays 16 kHz mono PCM and can be stopped between chunks.

- AtechUsbLink: straight to the robot's speaker over USB (what worked in the first test).
- BusLink:      emits `robot.audio_out` messages for the gateway (when Wanhui's gateway owns the port).
- LaptopLink:   plays on the laptop speakers (test phrases without the robot).
- PrintLink:    plays nothing, just waits the right time (tests).
"""
from __future__ import annotations

import base64
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from common import SAMPLE_RATE, write_wav

# 2048 bytes = 1024 samples = 64 ms -> 2732 base64 chars (speaker_play_pcm limit is ~3000).
CHUNK_BYTES = 2048


def chunks(pcm: bytes, size: int = CHUNK_BYTES):
    for i in range(0, len(pcm), size):
        yield pcm[i:i + size]


def seconds(pcm: bytes) -> float:
    return len(pcm) / (2 * SAMPLE_RATE)


class Link:
    def play(self, pcm: bytes, stop: threading.Event) -> bool:
        """Play and return True, or return False if `stop` was set before the end."""
        raise NotImplementedError

    def set_volume(self, volume: float) -> None:
        pass

    def close(self) -> None:
        pass


class AtechUsbLink(Link):
    """Each chunk is one `speaker_play_pcm` action. The board acknowledges a chunk once it has
    been handed to the speaker, so waiting for the ack paces the stream by itself."""

    def __init__(self, port: str | None = None, volume: float = 0.4, instance: str = "speaker",
                 board=None, lock: threading.Lock | None = None):
        """Pass `board` (an open atech Board) and its `lock` to share the gateway's USB connection
        instead of opening the port again (only one program can hold it)."""
        self.owns_board = board is None
        if board is None:
            from atech import Board  # only needed for this link
            board = Board.connect(port=port) if port else Board.connect()
            board.__enter__()
        self.board = board
        self.lock = lock or threading.Lock()
        self.action = f"{instance}_play_pcm"
        self.instance = instance
        self.set_volume(volume)

    def set_volume(self, volume: float) -> None:
        with self.lock:
            self.board.call(f"{self.instance}_set_volume", round(volume, 2))

    def play(self, pcm: bytes, stop: threading.Event) -> bool:
        for c in chunks(pcm):
            with self.lock:  # other commands (drive, eyes) slip in between chunks
                if stop.is_set():
                    self.board.call(f"{self.instance}_stop", "")
                    return False
                try:
                    self.board.call(self.action, base64.b64encode(c).decode("ascii"), timeout=5.0)
                except Exception as e:  # one chunk not acknowledged: skip it, keep talking
                    print(f"! speaker chunk skipped ({type(e).__name__})", file=sys.stderr, flush=True)
        return True

    def close(self) -> None:
        if self.owns_board:
            self.board.__exit__(None, None, None)


class BusLink(Link):
    """For the integrated system: `send(msg)` hands messages to the gateway, which turns each
    `robot.audio_out {seq,last,pcm_b64}` into the Atech action `speaker_play_pcm <pcm_b64>`.
    We pace by time (slightly faster than real time) so the robot never runs dry."""

    def __init__(self, send, lead: float = 0.9):
        self.send = send
        self.lead = lead
        self.seq = 0

    def play(self, pcm: bytes, stop: threading.Event) -> bool:
        parts = list(chunks(pcm))
        t0 = time.monotonic()
        played = 0.0
        for i, c in enumerate(parts):
            if stop.is_set():
                return False
            self.seq += 1
            self.send({"type": "robot.audio_out", "ts": time.time(), "seq": self.seq,
                       "last": i == len(parts) - 1, "pcm_b64": base64.b64encode(c).decode("ascii")})
            played += seconds(c)
            wait = t0 + played * self.lead - time.monotonic()
            if wait > 0 and i >= 1:  # send the first two chunks at once as a cushion
                time.sleep(wait)
        return True


class LaptopLink(Link):
    def __init__(self):
        self.player = "afplay" if sys.platform == "darwin" else "aplay"

    def play(self, pcm: bytes, stop: threading.Event) -> bool:
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "clip.wav"
            write_wav(path, pcm)
            proc = subprocess.Popen([self.player, str(path)])
            while proc.poll() is None:
                if stop.wait(0.02):
                    proc.terminate()
                    return False
        return True


class LaptopStreamLink(Link):
    """Laptop speakers without gaps between chunks (needed for live conversation)."""

    def __init__(self):
        import sounddevice as sd
        self.stream = sd.RawOutputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=1024)
        self.stream.start()

    def play(self, pcm: bytes, stop: threading.Event) -> bool:
        for c in chunks(pcm):
            if stop.is_set():
                return False
            self.stream.write(c)  # blocks until the sound card takes it: real-time pacing
        return True

    def close(self) -> None:
        self.stream.stop()
        self.stream.close()


class PrintLink(Link):
    def __init__(self, speed: float = 1.0):
        self.speed = speed

    def play(self, pcm: bytes, stop: threading.Event) -> bool:
        n = sum(1 for _ in chunks(pcm))
        print(f"  [print link] {seconds(pcm):.2f} s, {n} chunks", file=sys.stderr)
        return not stop.wait(seconds(pcm) * self.speed)


def make_link(kind: str, port: str | None = None, volume: float = 0.4) -> Link:
    if kind == "usb":
        return AtechUsbLink(port, volume)
    if kind == "laptop":
        try:
            return LaptopStreamLink()
        except Exception:  # no sounddevice / no output device: one file per clip with afplay
            return LaptopLink()
    if kind == "print":
        return PrintLink()
    if kind == "bus":
        import json
        return BusLink(lambda m: print(json.dumps(m, separators=(",", ":")), flush=True))
    raise ValueError(f"unknown link {kind!r} (usb | laptop | print | bus)")
