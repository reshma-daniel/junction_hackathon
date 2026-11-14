#!/usr/bin/env python3
"""Pre-render every phrase (phrases.yaml) and sound (sfx.yaml) into library/ as 16 kHz WAV.
library/ is committed to git, so each clip is generated once for the whole team.

    python render.py            # render only what is missing (re-runs cost 0 credits)
    python render.py --dry-run  # show what would be rendered, call nothing
    python render.py --force    # render everything again

Speech uses eleven_multilingual_v2 by default (your voice as you designed it); the emotion sets
how expressive each line is. Set render_model: eleven_v3 in shared/config.yaml for v3 + emotion tags. Sounds use the Sound Effects API.
"""
from __future__ import annotations

import argparse
import json
import sys

import requests

from common import CACHE, MANIFEST, clean_pcm, config, load_yaml, short_hash, write_wav

API = "https://api.elevenlabs.io/v1"
EXPRESSIVE_MODEL = "eleven_v3"
EMOTION_TAGS = {
    "warm": "[warmly]", "excited": "[excited]", "happy": "[happily]", "playful": "[playfully]",
    "soft": "[softly]", "calm": "[calmly]", "curious": "[curious]",
}
PRONOUNCE = {"Kaamos": "Kah-moss"}  # spelled the way we want ElevenLabs to say it


def spoken(text: str) -> str:
    for word, sound_like in PRONOUNCE.items():
        text = text.replace(word, sound_like)
    return text


# Model used to render speech. eleven_multilingual_v2 = how your voice sounded in the first test.
# Set render_model: eleven_v3 in shared/config.yaml (elevenlabs:) to try v3 with emotion tags instead.
DEFAULT_MODEL = "eleven_multilingual_v2"
STYLE = {"excited": 0.35, "happy": 0.35, "playful": 0.35, "warm": 0.2, "curious": 0.2, "soft": 0.05, "calm": 0.05}


def tts(cfg: dict, text: str, emotion: str | None) -> tuple[bytes, str]:
    """Return (raw 16 kHz PCM, model used)."""
    url = f"{API}/text-to-speech/{cfg['voice_id']}"
    headers = {"xi-api-key": cfg["api_key"], "Content-Type": "application/json"}
    model = cfg.get("render_model", DEFAULT_MODEL)
    text = spoken(text)
    if model == EXPRESSIVE_MODEL:  # v3 understands [excited] etc.; other models would read the tag aloud
        body = {"text": f"{EMOTION_TAGS.get(emotion or '', '')} {text}".strip(), "model_id": model,
                "voice_settings": {"stability": 0.5}}  # v3 accepts 0 / 0.5 / 1
    else:  # emotion -> a little more or less expressiveness
        body = {"text": text, "model_id": model, "voice_settings": {
            "stability": 0.5, "similarity_boost": 0.8, "style": STYLE.get(emotion or "", 0.2), "speed": 0.95}}
    r = requests.post(url, params={"output_format": "pcm_16000"}, headers=headers, timeout=60, json=body)
    if not (r.ok and r.content):
        raise RuntimeError(f"{model}: HTTP {r.status_code} {r.text[:200]}")
    return r.content, model


def sound(cfg: dict, prompt: str, duration: float) -> bytes:
    r = requests.post(f"{API}/sound-generation", params={"output_format": "pcm_16000"}, timeout=90,
                      headers={"xi-api-key": cfg["api_key"], "Content-Type": "application/json"},
                      json={"text": prompt, "duration_seconds": duration, "prompt_influence": 0.6})
    if not r.ok or not r.content:
        raise RuntimeError(f"sound-generation: HTTP {r.status_code} {r.text[:200]}")
    return r.content


def plan(cfg: dict) -> list[dict]:
    """Every clip we want, with a file name that changes when its text/voice/prompt changes."""
    jobs = []
    for intent, entry in load_yaml("phrases.yaml").items():
        for v in entry.get("variants", []):
            v = {"text": v} if isinstance(v, str) else v
            emotion = v.get("emotion", entry.get("emotion"))
            h = short_hash(v["text"], emotion, cfg.get("voice_id"), cfg.get("render_model", DEFAULT_MODEL))
            jobs.append({"kind": "tts", "group": intent, "text": v["text"], "emotion": emotion,
                         "file": f"tts/{intent}__{h}.wav"})
    for name, entry in load_yaml("sfx.yaml").items():
        for i in range(int(entry.get("variants", 1))):
            h = short_hash(entry["prompt"], entry.get("duration"), i)
            jobs.append({"kind": "sfx", "group": name, "prompt": entry["prompt"],
                         "duration": float(entry.get("duration", 1.0)), "file": f"sfx/{name}__{h}.wav"})
    return jobs


def check_reactions() -> list[str]:
    """Every sound / phrase that reactions.yaml uses must exist in sfx.yaml / phrases.yaml."""
    phrases, sounds = load_yaml("phrases.yaml"), load_yaml("sfx.yaml")
    problems = []
    for name, r in load_yaml("reactions.yaml").get("reactions", {}).items():
        blocks = [r] + list((r.get("levels") or {}).values()) + ([r["give_up"]] if "give_up" in r else [])
        for b in blocks:
            for step in b.get("steps", []) or []:
                if "sound" in step and step["sound"] not in sounds:
                    problems.append(f"{name}: sound {step['sound']!r} is not in sfx.yaml")
                say = step.get("say", "")
                for intent in ([say.format(task=t) for t in ("walk", "pill", "general")] if "{task}" in say else [say] if say else []):
                    if intent not in phrases:
                        problems.append(f"{name}: phrase {intent!r} is not in phrases.yaml")
    return problems


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--only", help="render only this intent / sound name")
    args = ap.parse_args()

    for problem in check_reactions():
        print(f"! reactions.yaml: {problem}", file=sys.stderr)
    cfg = config()
    jobs = plan(cfg)
    todo = [j for j in jobs if (args.force or not (CACHE / j["file"]).exists())
            and (not args.only or j["group"] == args.only)]
    n_tts = sum(j["kind"] == "tts" for j in todo)
    print(f"{len(jobs)} clips in total, {len(todo)} to render ({n_tts} speech, {len(todo) - n_tts} sounds).")

    if todo and not args.dry_run:
        if not cfg["api_key"]:
            sys.exit("ELEVENLABS_API_KEY is not set (put it in services/voice/.env).")
        if n_tts and (not cfg.get("voice_id") or cfg["voice_id"] == "FILL_ME"):
            sys.exit("No voice id: set ELEVENLABS_VOICE_ID in .env or voice_id in shared/config.yaml.")

    failed = 0
    for j in todo:
        label = j.get("text") or j["prompt"][:60]
        print(f"  {'[dry]' if args.dry_run else '->'} {j['group']:<18} {label}")
        if args.dry_run:
            continue
        try:
            if j["kind"] == "tts":
                pcm, model = tts(cfg, j["text"], j["emotion"])
                j["model"] = model
            else:
                pcm = sound(cfg, j["prompt"], j["duration"])
            write_wav(CACHE / j["file"], clean_pcm(pcm))
        except Exception as e:  # keep going: one bad clip should not stop the rest
            failed += 1
            print(f"    ! failed: {e}", file=sys.stderr)

    # Manifest = what exists on disk, grouped for voice.py.
    manifest: dict = {"tts": {}, "sfx": {}}
    for j in jobs:
        if (CACHE / j["file"]).exists():
            manifest[j["kind"]].setdefault(j["group"], []).append(
                {"file": j["file"], "text": j.get("text"), "emotion": j.get("emotion")})
    if not args.dry_run:
        # Delete clips whose line was removed or changed (e.g. a sentence you edited), so they never play.
        wanted = {j["file"] for j in jobs}
        for old in list(CACHE.glob("tts/*.wav")) + list(CACHE.glob("sfx/*.wav")):
            if old.relative_to(CACHE).as_posix() not in wanted:
                old.unlink()
                print(f"  removed old clip {old.name}")
        CACHE.mkdir(exist_ok=True)
        MANIFEST.write_text(json.dumps(manifest, indent=1))
        ready = sum(len(v) for k in manifest.values() for v in k.values())
        print(f"Done. {ready}/{len(jobs)} clips ready in {CACHE}. Commit library/ so nobody renders them again" + (f", {failed} failed" if failed else ""))


if __name__ == "__main__":
    main()
