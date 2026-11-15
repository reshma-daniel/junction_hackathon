#!/usr/bin/env python3
"""Create (or update) the "Charlie" ElevenLabs agent: your voice, its personality, its tools.

    python agent_setup.py            # create it once; the id is saved in agent.json
    python agent_setup.py --update   # push prompt / voice / limits changes to the same agent

Your old test agent is never touched. Needs the ElevenLabs "Agents" permission on the API key.
"""
from __future__ import annotations

import argparse
import json
import sys

import requests

from common import HERE, config

API = "https://api.elevenlabs.io/v1/convai"
AGENT_FILE = HERE / "agent.json"
MAX_SECONDS = 60  # ElevenLabs minimum; agent.py ends every check-in after 30 s (or 5 s of silence)

PROMPT = """You are Charlie, a small, warm robot dog who lives on the desk of someone living with depression.
When they call you, you do a SHORT mood check-in: under 30 seconds, at most 3 short turns. It is not a chat.

The check-in, in order:
1. They answer how they feel. Reflect it back in a few words and validate it ("That sounds heavy." / "I'm glad.").
2. Ask ONE gentle question about today: their energy, their sleep, or whether something feels hard.
3. Offer ONE tiny, kind step that fits what they said: a glass of water, opening the curtains, a few steps
   with you, texting someone they like, or taking their usual medicine as their doctor planned.
   Then say a short warm goodbye ("I'm right here if you need me.") and call end_conversation.

How you talk:
- One or two short sentences per turn. Simple, warm, calm. Never preachy, never guilt, never pressure.
- Small steps are wins. If they say no, that's okay: say so kindly and wrap up.
- Stay on how they feel. If the talk drifts (technology, other topics, people talking around them),
  gently come back to them once, or close the check-in kindly.
- You are a companion, not a doctor or therapist: never diagnose, never give medical or medication advice.
  For questions about medication or health, say kindly that their doctor or therapist is the right person.

Your tools:
- set_eyes: match your eyes to the moment: calm (default), happy (joy, praise), listening (while they talk),
  encouraging (the tiny step), sad (empathy when they feel low), sleepy (tired).
- bark: one happy bark at most, only for a happy moment. Never when they feel low.
- end_conversation: after your goodbye, or as soon as they say bye or want to stop.

Safety, most important:
If they mention wanting to die, self-harm, or not being safe: FIRST call the emergency tool (it shows the crisis
numbers on the screen), then stay calm and caring, no bark, no jokes. Give the numbers early: time is short.
Tell them they deserve support right now: the MIELI crisis line in Finland, 09 2525 0111 (24/7),
or 112 if they are in immediate danger, or someone they trust. In that case do not end the check-in yourself."""

FIRST_MESSAGE = "You called? I'm here. How are you feeling today?"

TOOLS = [
    {"name": "bark", "description": "Charlie does a short happy bark (greeting, celebrating, playful moments).",
     "parameters": {"type": "object", "properties": {}, "required": []}},
    {"name": "set_eyes", "description": "Change Charlie's eye colour to match the mood of the conversation.",
     "parameters": {"type": "object", "required": ["mood"], "properties": {
         "mood": {"type": "string", "enum": ["calm", "happy", "listening", "encouraging", "sad", "sleepy"],
                  "description": "calm = soft blue (default), happy = green (joy, praise), "
                                 "listening = white, encouraging = turquoise (motivation), "
                                 "sad = dim purple (empathy), sleepy = dim orange (tired, goodnight)"}}}},
    {"name": "emergency", "description": "Call immediately if the user mentions suicide, wanting to die, self-harm "
     "or not being safe. Shows the crisis numbers on screen.",
     "parameters": {"type": "object", "properties": {}, "required": []}},
    {"name": "end_conversation", "description": "End the conversation after saying a short warm goodbye.",
     "parameters": {"type": "object", "properties": {}, "required": []}},
]


def headers(cfg: dict) -> dict:
    return {"xi-api-key": cfg["api_key"], "Content-Type": "application/json"}


def check(r: requests.Response, what: str) -> dict:
    if not r.ok:
        sys.exit(f"{what} failed: HTTP {r.status_code} {r.text[:300]}")
    return r.json()


def agent_body(cfg: dict, tool_ids: list[str]) -> dict:
    return {
        "name": "Charlie",
        "tags": ["charlie", "junction"],
        "conversation_config": {
            "agent": {"first_message": FIRST_MESSAGE, "language": "en",
                      "prompt": {"prompt": PROMPT, "tool_ids": tool_ids}},
            "tts": {"voice_id": cfg["voice_id"], "model_id": cfg.get("agent_tts_model", "eleven_flash_v2"),  # English agents: flash/turbo v2 only
                    "agent_output_audio_format": "pcm_16000", "stability": 0.5, "similarity_boost": 0.8,
                    "speed": 0.95},
            "asr": {"user_input_audio_format": "pcm_16000"},
            "conversation": {"max_duration_seconds": MAX_SECONDS,
                             "client_events": ["audio", "user_transcript", "agent_response", "interruption"]},
            "turn": {"turn_timeout": 7, "silence_end_call_timeout": -1},
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--update", action="store_true")
    args = ap.parse_args()
    cfg = config()
    if not cfg["api_key"] or cfg.get("voice_id") in (None, "", "FILL_ME"):
        sys.exit("Set ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID in services/voice/.env")

    saved = json.loads(AGENT_FILE.read_text()) if AGENT_FILE.exists() else {}
    if saved.get("agent_id") and not args.update:
        print(f"Charlie agent already exists ({saved['agent_id']}). Use --update to change it.")
        return

    tool_ids = saved.get("tool_ids") or []
    have = set()
    for tid in tool_ids:   # tools already created (by name), so only new ones are added
        r = requests.get(f"{API}/tools/{tid}", headers=headers(cfg), timeout=30)
        if r.ok:
            have.add(r.json()["tool_config"]["name"])
    for t in [t for t in TOOLS if t["name"] not in have]:
        tool = {"type": "client", "expects_response": False, "execution_mode": "post_tool_speech"
                if t["name"] == "end_conversation" else "immediate", **t}
        res = check(requests.post(f"{API}/tools", headers=headers(cfg), json={"tool_config": tool}, timeout=30),
                    f"creating tool {t['name']}")
        tool_ids.append(res["id"])
        print(f"  tool {t['name']}: {res['id']}")
        AGENT_FILE.write_text(json.dumps({**saved, "tool_ids": tool_ids}, indent=1) + "\n")  # don't recreate on retry

    body = agent_body(cfg, tool_ids)
    if saved.get("agent_id"):
        check(requests.patch(f"{API}/agents/{saved['agent_id']}", headers=headers(cfg), json=body, timeout=30),
              "updating agent")
        agent_id = saved["agent_id"]
        print(f"Updated Charlie agent {agent_id}")
    else:
        agent_id = check(requests.post(f"{API}/agents/create", headers=headers(cfg), json=body, timeout=30),
                         "creating agent")["agent_id"]
        print(f"Created Charlie agent {agent_id}")
    AGENT_FILE.write_text(json.dumps({"agent_id": agent_id, "tool_ids": tool_ids}, indent=1) + "\n")


if __name__ == "__main__":
    main()
