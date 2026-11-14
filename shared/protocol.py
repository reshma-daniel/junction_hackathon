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

# Eye moods: keep in sync with the "Eye moods" table in docs/MESSAGES.md and MOODS in firmware/robot/eyes.cpp.
# mood -> (colour, pattern, period_ms or None)
MOODS = {
    "calm":        ("#3c78ff", "blink", 3000),         # idle: slow blink
    "listening":   ("#ffffff", "solid", None),         # while you talk
    "happy":       ("#1eff3c", "blink", 200),          # "Charlie" / pill taken: fast blink 2 s, then calm
    "pleading":    ("#ff8c00", "blink", 1000),         # pill reminder, lost you on a walk
    "encouraging": ("#28e0d0", "double_blink", 2000),  # on a walk
    "sad":         ("#7828c8", "glow", 6000),          # pill missed, couldn't find you
    "sleepy":      ("#401900", "half", None),          # quiet hours, waking up
    "searching":   ("#96c8ff", "sweep", 3000),         # looking for you
}
COLORS = {mood: spec[0] for mood, spec in MOODS.items()}


def msg(type_: str, **fields) -> dict:
    return {"type": type_, "ts": fields.pop("ts", time.time()), **fields}


def dumps(m: dict) -> str:
    return json.dumps(m, separators=(",", ":"))
