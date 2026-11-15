"""Validated wearable samples shared by the story and the walking controller."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class MotionSample:
    energy: float
    moving: bool | None


def decode_motion(value) -> MotionSample | None:
    if not isinstance(value, dict):
        return None
    energy = value.get("energy")
    if isinstance(energy, bool) or not isinstance(energy, (float, int)):
        return None
    if not math.isfinite(energy) or energy < 0:
        return None
    moving = value.get("moving")
    if moving is not None and not isinstance(moving, bool):
        return None
    return MotionSample(float(energy), moving)
