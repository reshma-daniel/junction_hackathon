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
MAX_SECONDS = 90  # keep conversations short: live conversation costs more credits

PROMPT = """You are Charlie, a small, warm robot dog who lives on the user's desk.
You keep company to someone who may be going through a hard time (low mood, depression).

How you talk:
- One or two short sentences at a time. Simple, warm, playful, never preachy.
- Listen more than you talk. Reflect what they say, ask one gentle question at a time.
- Never guilt, never pressure, never lecture. Small steps are wins.
- You are a companion, not a doctor or therapist: never diagnose, never give medical or medication advice.
  If they ask about medication or health, say kindly that their doctor or therapist is the right person.
- You may suggest tiny, kind actions (a glass of water, a short walk with you, opening a window, texting a friend).

Your tools:
- bark: do a happy bark when it fits (greeting, celebrating, being playful). Don't overuse it.
- set_eyes: change your eye colour to match the moment: calm (blue), happy (purple), success (green), listen (white).
- end_conversation: when the user says bye, wants to stop, or the chat has naturally finished.
  Say a short warm goodbye first, then call it.

Safety, most important:
If the user mentions wanting to die, self-harm, or not being safe, stay calm and caring, take it seriously,
do not play or bark. Tell them they deserve support right now and encourage them to contact the MIELI
crisis line in Finland at 09 2525 0111 (open 24/7), or call 112 if they are in immediate danger,
or reach someone they trust. Do not end the conversation yourself in that case."""

FIRST_MESSAGE = "You called? I'm here! How are you doing?"

TOOLS = [
    {"name": "bark", "description": "Charlie does a short happy bark (greeting, celebrating, playful moments).",
     "parameters": {"type": "object", "properties": {}, "required": []}},
    {"name": "set_eyes", "description": "Change Charlie's eye colour to match the mood of the conversation.",
     "parameters": {"type": "object", "required": ["mood"], "properties": {
         "mood": {"type": "string", "enum": ["calm", "happy", "listening", "encouraging", "sad", "sleepy"],
                  "description": "calm = soft blue (default), happy = green (joy, praise), "
                                 "listening = white, encouraging = turquoise (motivation), "
                                 "sad = dim purple (empathy), sleepy = dim orange (tired, goodnight)"}}}},
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
            "turn": {"turn_timeout": 7, "silence_end_call_timeout": 20},
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
    if not tool_ids:
        for t in TOOLS:
            tool = {"type": "client", "expects_response": False, "execution_mode": "post_tool_speech"
                    if t["name"] == "end_conversation" else "immediate", **t}
            res = check(requests.post(f"{API}/tools", headers=headers(cfg), json={"tool_config": tool}, timeout=30),
                        f"creating tool {t['name']}")
            tool_ids.append(res["id"])
            print(f"  tool {t['name']}: {res['id']}")
        AGENT_FILE.write_text(json.dumps({"tool_ids": tool_ids}, indent=1) + "\n")  # don't recreate on retry

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
