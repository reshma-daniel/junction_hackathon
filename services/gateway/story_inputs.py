"""Route SDK events using the Board connections already owned by run_story.py.

Never opens a second serial connection; voice, motion and eyes share Charlie.lock.
"""
from services.activity.motion import decode_motion
from services.medication.dock import decode_dock


class StoryInputs:
    def __init__(self, story, walking):
        self.story, self.walking = story, walking

    def wearable(self, event):
        if event.key != "wearable_motion":
            return
        sample = decode_motion(event.value)
        if sample is None:
            return
        self.walking.on_motion(sample)
        self.story.on_motion(sample.energy, moving=sample.moving)

    def robot(self, event):
        if event.key == "wearable_ble":
            self.walking.position.update(event.value)
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
            self.story.on_called()
        elif event.key == "robot_behavior":
            value = event.value if isinstance(event.value, dict) else {}
            self.story.robot_behavior = value.get("state") or self.story.robot_behavior
            if value.get("state") == "wake" and self.story.phase not in ("new", "starting"):
                self.story.log("!!! Charlie restarted; waiting for fresh sensor data")
                self.walking.stop()
