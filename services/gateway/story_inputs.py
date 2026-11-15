"""Route SDK events using the Board connections already owned by run_story.py.

Never opens a second serial connection; voice, motion and eyes share Charlie.lock.
"""
from services.activity.motion import decode_motion
from services.medication.dock import decode_dock


class StoryInputs:
    def __init__(self, story, walking, telemetry=lambda kind, value: None):
        self.story, self.walking = story, walking
        self.telemetry = telemetry
        self._last_moving = None
        self.hear_calls = lambda: True   # run_story/panel: robot mic on or off for "Charlie" calls

    def wearable(self, event):
        if event.key != "wearable_motion":
            return
        sample = decode_motion(event.value)
        if sample is None:
            return
        self.telemetry("wearable_motion", {"energy": sample.energy, "moving": sample.moving})
        if sample.moving is not None and sample.moving != self._last_moving:
            self.story.log(f"IMU moving={sample.moving}, energy={sample.energy:.4f}")
            self._last_moving = sample.moving
        self.walking.on_motion(sample)
        self.story.on_motion(sample.energy, moving=sample.moving)

    def robot(self, event):
        if event.key == "wearable_ble":
            self.walking.position.update(event.value)
            self.telemetry("wearable_ble", {"sample": event.value, **self.walking.position.snapshot()})
        elif event.key == "robot_state":
            # mode, motors-active flag, front min/left/right distances; this
            # distinguishes an intended return from the firmware obstacle clamp.
            self.telemetry("robot_state", event.value)
        elif event.key == "robot_dock":
            sample = decode_dock(event.value)
            if sample is not None:
                self.story.on_dock(sample.removed, sample.mm)
        elif event.key == "distance_sensor_min_distance":
            # Raw values remain useful for the panel, but never bypass the
            # coverage/hysteresis detector by rewarding a hand passing the sensor.
            if isinstance(event.value, int) and not isinstance(event.value, bool):
                self.story.last_dock_mm = event.value
        elif event.key == "robot_heard":
            if self.hear_calls():
                self.story.on_called()
            else:
                self.story.log("Robot mic heard a call: ignored (robot mic switched off)")
        elif event.key == "robot_behavior":
            value = event.value if isinstance(event.value, dict) else {}
            self.story.robot_behavior = value.get("state") or self.story.robot_behavior
            if value.get("state") == "wake" and self.story.phase not in ("new", "starting"):
                self.story.log("!!! Charlie restarted; waiting for fresh sensor data")
                self.walking.stop()
