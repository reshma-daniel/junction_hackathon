"""Diagnostic logging must help explain behavior without changing control."""
import json
from types import SimpleNamespace

from services.gateway.telemetry import RunTelemetry
from services.gateway.story_inputs import StoryInputs
from services.position.rssi import RssiPosition
from services.brain.walking import RssiWalk


def test_journal_preserves_motion_rssi_and_physical_robot_feedback(tmp_path):
    journal = RunTelemetry(tmp_path)
    walk = RssiWalk(RssiPosition())
    story = SimpleNamespace(log=lambda m: None, on_motion=lambda *a, **kw: None)
    inputs = StoryInputs(story, walk, telemetry=journal.record)
    inputs.wearable(SimpleNamespace(key="wearable_motion", value={"energy": .2, "moving": True}))
    inputs.robot(SimpleNamespace(key="wearable_ble", value={"detected": True,
                 "rssi_smoothed_dbm": -90, "age_ms": 0}))
    inputs.robot(SimpleNamespace(key="robot_state", value="manual,0,77,77,1800"))
    journal.close()
    rows = [json.loads(s) for s in journal.path.read_text().splitlines()]
    assert [r["kind"] for r in rows] == ["wearable_motion", "wearable_ble", "robot_state"]
    assert rows[1]["value"]["initial_rssi_dbm"] == -90
    assert rows[2]["value"] == "manual,0,77,77,1800"
    assert all(r["elapsed_s"] >= 0 and r["ts"] for r in rows)


def test_unwritable_log_directory_does_not_break_control(tmp_path):
    blocked = tmp_path / "file"
    blocked.write_text("not a directory")
    journal = RunTelemetry(blocked)
    journal.record("navigation", {"speed": 0})
    journal.close()


def test_bad_record_does_not_prevent_later_records(tmp_path):
    journal = RunTelemetry(tmp_path)
    journal.record("bad", float("nan"))
    journal.record("good", {"speed": 0})
    journal.close()
    rows = [json.loads(s) for s in journal.path.read_text().splitlines()]
    assert len(rows) == 1 and rows[0]["kind"] == "good"
