"""Shared message names and helpers. Owner: P4. Keep in sync with docs/MESSAGES.md."""
from __future__ import annotations
import json
import time

# Wearable -> brain
WEARABLE_MOTION = "wearable.motion"
WEARABLE_HELLO = "wearable.hello"

# Robot -> brain
ROBOT_DOCK = "robot.dock"
ROBOT_RANGE = "robot.range"
ROBOT_AUDIO = "robot.audio"
ROBOT_SOUND = "robot.sound"
ROBOT_ACK = "robot.ack"
ROBOT_STATE = "robot.state"
ROBOT_HELLO = "robot.hello"

# Brain -> robot
ROBOT_DRIVE = "robot.drive"
ROBOT_MODE = "robot.mode"        # idle | walk | follow | come | stop
ROBOT_EYES = "robot.eyes"       # left/right colour + pattern
ROBOT_BARK = "robot.bark"
ROBOT_AUDIO_OUT = "robot.audio_out"
ROBOT_SAY_CLIP = "robot.say_clip"

REL_ESTIMATE = "rel.estimate"
REL_LOST = "rel.lost"

# Internal events
ACTIVITY_STILL = "activity.still_too_long"
ACTIVITY_MOVING = "activity.moving_again"
ACTIVITY_DECLINE = "activity.decline"
MED_TAKEN = "med.taken"
MED_LATE = "med.late"
MED_MISSED = "med.missed"
VOICE_SAY = "voice.say"
VOICE_WAKE = "voice.wake"
VOICE_DONE = "voice.done"

COLORS = {
    "calm": "#2f6fff", "prompt": "#ffc83d", "success": "#2fd06b",
    "concern": "#ff4d4d", "walk": "#27d3e6", "listen": "#ffffff", "happy": "#9b5de5",
}


def msg(type_: str, **fields) -> dict:
    return {"type": type_, "ts": fields.pop("ts", time.time()), **fields}


def dumps(m: dict) -> str:
    return json.dumps(m, separators=(",", ":"))
