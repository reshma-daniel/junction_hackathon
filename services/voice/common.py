"""Shared helpers for the voice service: paths, config, .env, WAV files, audio clean-up."""
from __future__ import annotations

import hashlib
import json
import os
import wave
from array import array
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
CACHE = HERE / "library"  # committed to git: render once, share with the team
MANIFEST = CACHE / "manifest.json"
SAMPLE_RATE = 16000  # Atech speaker_play_pcm expects 16 kHz mono signed 16-bit


def load_env() -> None:
    """Read KEY=VALUE lines from services/voice/.env or the repo's .env (never committed)."""
    for path in (HERE / ".env", REPO / ".env"):
        if not path.exists():
            continue
        for raw in path.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def config() -> dict:
    """The `elevenlabs:` section of shared/config.yaml, with env overrides."""
    load_env()
    cfg = yaml.safe_load((REPO / "shared" / "config.yaml").read_text()).get("elevenlabs", {})
    env_voice = os.getenv("ELEVENLABS_VOICE_ID")
    if env_voice:
        cfg["voice_id"] = env_voice
    cfg["api_key"] = os.getenv(cfg.get("api_key_env", "ELEVENLABS_API_KEY"), "")
    return cfg


def load_yaml(name: str) -> dict:
    return yaml.safe_load((HERE / name).read_text()) or {}


def short_hash(*parts) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:8]


# ---------- WAV in / out (16 kHz mono s16) ----------

def write_wav(path: Path, pcm: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm)


def read_wav(path: Path) -> bytes:
    with wave.open(str(path), "rb") as w:
        if w.getnchannels() != 1 or w.getsampwidth() != 2 or w.getframerate() != SAMPLE_RATE:
            raise ValueError(f"{path.name}: expected 16 kHz mono 16-bit WAV")
        return w.readframes(w.getnframes())


# ---------- clean-up so clips sound good on a small speaker ----------

def clean_pcm(pcm: bytes, peak: float = 0.89, silence: int = 300, fade_ms: int = 15) -> bytes:
    """Trim silence at both ends, normalise the loudest sample to `peak` (about -1 dBFS),
    and fade the edges so there is no click. Pure Python: clips are short."""
    s = array("h")
    s.frombytes(pcm[: len(pcm) // 2 * 2])
    if not s:
        return b""
    start = next((i for i, v in enumerate(s) if abs(v) > silence), 0)
    end = next((i for i in range(len(s) - 1, -1, -1) if abs(s[i]) > silence), len(s) - 1)
    pad = SAMPLE_RATE // 50  # keep 20 ms around the sound
    s = s[max(0, start - pad): min(len(s), end + pad + 1)]
    loudest = max(abs(v) for v in s) or 1
    gain = peak * 32767 / loudest
    fade = min(len(s) // 2, SAMPLE_RATE * fade_ms // 1000)
    out = array("h", bytes(len(s) * 2))
    for i, v in enumerate(s):
        g = gain
        if i < fade:
            g *= i / fade
        elif i >= len(s) - fade:
            g *= (len(s) - 1 - i) / fade
        out[i] = max(-32768, min(32767, int(v * g)))
    return out.tobytes()


def read_manifest() -> dict:
    if not MANIFEST.exists():
        raise SystemExit("No clips yet. Run `python render.py` first (or git pull the library).")
    return json.loads(MANIFEST.read_text())
