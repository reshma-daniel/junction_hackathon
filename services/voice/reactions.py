"""Kaamos's reactions (reactions.yaml): wake_up, called, encourage, pill, reward.

    from voice import Voice; from links import make_link; from reactions import Reactions
    r = Reactions(Voice(make_link("usb")))
    r.plan("pill", attempt=2)        # what would happen: level, eyes, steps (plays nothing)
    r.play("pill", attempt=2)        # play it on the robot
    r.play("reward", task="walk")

Escalation: level = max(attempt, level from late_s), capped at the highest level.
attempt > max_reasks (shared/config.yaml) -> the gentle `give_up` reaction.
"""
from __future__ import annotations

import time

import yaml

from common import REPO, load_yaml


class Reactions:
    def __init__(self, voice=None):
        self.voice = voice
        data = load_yaml("reactions.yaml")
        self.reactions: dict = data["reactions"]
        shared = yaml.safe_load((REPO / "shared" / "config.yaml").read_text())
        profile = shared.get("profile", "demo")
        self.max_reasks = int(shared.get(profile, {}).get("max_reasks", 3))
        self.late_steps = data.get("escalate_late_s", {}).get(profile, [0, 30, 60])

    def names(self) -> list[str]:
        return list(self.reactions)

    def plan(self, name: str, attempt: int = 1, late_s: float | None = None, task: str | None = None) -> dict:
        """Decide what to do, without playing anything (useful for the brain and for tests)."""
        if name not in self.reactions:
            raise KeyError(f"unknown reaction {name!r}; known: {', '.join(self.reactions)}")
        r = self.reactions[name]
        level = None
        block = r
        if "levels" in r:
            if attempt > self.max_reasks and "give_up" in r:
                level, block = "give_up", r["give_up"]
            else:
                by_time = sum(1 for t in self.late_steps if late_s is not None and late_s >= t)
                top = max(int(k) for k in r["levels"])
                level = max(1, min(top, max(attempt, by_time)))
                block = r["levels"].get(level) or r["levels"][str(level)]
        task_name = task if task in ("walk", "pill") else "general"
        steps = []
        for step in block.get("steps", []):
            step = dict(step)
            if "say" in step:
                step["say"] = step["say"].format(task=task_name)
            steps.append(step)
        return {"reaction": name, "level": level, "eyes": block.get("eyes", r.get("eyes")), "steps": steps}

    def play(self, name: str, attempt: int = 1, late_s: float | None = None, task: str | None = None) -> dict:
        p = self.plan(name, attempt, late_s, task)
        v = self.voice
        v.emit({"type": "voice.reacting", "ts": time.time(), **{k: p[k] for k in ("reaction", "level", "eyes")}})
        for step in p["steps"]:
            if "pause" in step:
                time.sleep(float(step["pause"]))
            elif "sound" in step:
                v.sound(step["sound"], int(step.get("count", 1)))
            elif "say" in step:
                v.say(step["say"], quiet=True)
            if v.stopped():  # voice.stop arrived: abandon the rest of the reaction
                break
        v.emit({"type": "voice.reaction_done", "ts": time.time(), "reaction": name,
                "level": p["level"], "completed": not v.stopped()})
        return p
