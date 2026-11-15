"""Normalize the firmware's debounced pill coverage state."""
from dataclasses import dataclass


@dataclass(frozen=True)
class DockSample:
    removed: bool
    mm: int | None


def decode_dock(value) -> DockSample | None:
    if not isinstance(value, dict) or value.get("valid") is not True:
        return None
    removed = value.get("removed")
    if not isinstance(removed, bool):
        return None
    mm = value.get("mm")
    if mm is not None and (isinstance(mm, bool) or not isinstance(mm, int) or mm < 0):
        return None
    return DockSample(removed, mm)
