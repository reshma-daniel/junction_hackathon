"""Integration contract tests, with no board, cloud, microphone or audio access."""
import math
from pathlib import Path
import sys
import threading
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).parent))
from services.activity.motion import MotionSample, decode_motion
from services.position.rssi import RssiPosition
from services.medication.dock import decode_dock
from services.brain.walking import RssiWalk
from services.gateway.story_inputs import StoryInputs
from run_story import WalkingCharlie
import run_story
from story import Story


class Clock:
    t = 0.0
    def __call__(self):
        return self.t


def setup_walk():
    clock = Clock()
    pos = RssiPosition(clock=clock)
    walk = RssiWalk(pos, clock=clock)
    return clock, pos, walk


def feed(pos, rssi, detected=True, age=0):
    pos.update({"detected": detected, "rssi_smoothed_dbm": rssi, "age_ms": age})


def test_rssi_baseline_is_per_run_and_not_fixed_close_reference():
    clock, pos, walk = setup_walk()
    feed(pos, -92)
    feed(pos, -80)
    assert pos.initial == -92
    assert pos.snapshot()["return_below_dbm"] == pytest.approx(-92.9691, abs=0.0001)
    walk.on_motion(MotionSample(.01, False))
    assert walk.tick() == 0  # IMU alone cannot start the robot outside Story.
    walk.start()
    assert walk.tick() == 255
    walk.on_motion(MotionSample(.2, True))
    assert walk.tick() == 0
    clock.t = .21
    assert walk.tick() == -255
    feed(pos, -92.96)
    assert walk.tick() == -255
    feed(pos, -92.98)
    assert walk.tick() == 0 and walk.phase == "return"
    clock.t = .42
    assert walk.tick() == 255
    feed(pos, -80.01)
    assert walk.tick() == 255
    feed(pos, -80)
    assert walk.tick() == 0 and walk.phase == "lead"
    clock.t = .63
    assert walk.tick() == -255
    assert pos.initial == -92


def test_still_cannot_return_or_interrupt_return_and_duplicates_do_not_flip():
    clock, pos, walk = setup_walk()
    feed(pos, -85)
    walk.on_motion(MotionSample(.2, True)); walk.start()
    assert walk.tick() == -255
    walk.on_motion(MotionSample(.01, False))
    assert walk.tick() == -255
    feed(pos, -87)
    assert walk.tick() == 0
    clock.t = .21
    walk.on_motion(MotionSample(.2, True))
    assert walk.tick() == 255 and walk.phase == "return"
    walk.on_motion(MotionSample(.2, True))
    assert walk.tick() == 255


def test_sensor_loss_stops_even_when_laptop_still_running():
    clock, pos, walk = setup_walk()
    feed(pos, -90); walk.on_motion(MotionSample(.01, False)); walk.start()
    assert walk.tick() == 255
    clock.t = 3
    assert walk.tick() == 0
    feed(pos, -89)
    assert walk.tick() == 0  # Fresh BLE alone cannot mask stale wearable data.
    walk.on_motion(MotionSample(.01, False))
    assert walk.tick() == 255
    feed(pos, -89, detected=False)
    assert walk.tick() == 0
    walk.stop(); feed(pos, -89);walk.on_motion(MotionSample(.2, True))
    assert walk.tick() == 0 and not walk.enabled


@pytest.mark.parametrize("value", [None, [], {"energy": True}, {"energy": math.nan},
                                  {"energy": -1}, {"energy": .1, "moving": "false"}])
def test_bad_motion_is_ignored(value):
    assert decode_motion(value) is None


def test_sdk_motion_unknown_state_and_legacy_format():
    assert decode_motion({"energy": .2, "moving": True}) == MotionSample(.2, True)
    assert decode_motion({"energy": .2, "moving": None}) == MotionSample(.2, None)
    assert decode_motion({"energy": .2}) == MotionSample(.2, None)


def test_bad_or_stale_rssi_cannot_capture_baseline():
    clock, pos, walk = setup_walk()
    for value in [{"detected": True, "rssi_smoothed_dbm": math.nan, "age_ms": 0},
                  {"detected": True, "rssi_smoothed_dbm": -90, "age_ms": 3000},
                  {"detected": True, "rssi_smoothed_dbm": -90, "age_ms": -1}]:
        assert not pos.update(value)
    assert pos.initial is None


class BoardFake:
    def __init__(self): self.calls = []
    def call(self, action, value="", **kw): self.calls.append((action, value))


def charlie_fake(walk):
    charlie = object.__new__(WalkingCharlie)
    charlie.board = BoardFake(); charlie.lock = threading.Lock()
    charlie.navigation = walk; charlie._driving = False
    charlie._closed = threading.Event()
    charlie.slow = 60; charlie.fast = 255
    return charlie


def test_story_shares_board_and_stop_cannot_be_undone_by_next_tick():
    clock, pos, walk = setup_walk()
    feed(pos, -90);walk.on_motion(MotionSample(.01, False))
    charlie = charlie_fake(walk)
    charlie.walk();charlie.drive_tick()
    assert ("robot_drive", "255,255") in charlie.board.calls
    charlie.walk_stop()
    count = len(charlie.board.calls)
    charlie.drive_tick()
    assert len(charlie.board.calls) == count
    assert ("robot_mode", "stop") in charlie.board.calls
    assert not walk.enabled


@pytest.mark.parametrize("action", ["pause", "restart", "speak", "deadline"])
def test_story_pause_restart_speech_and_walk_deadline_stop_navigation(action):
    clock, pos, walk = setup_walk()
    feed(pos, -90); walk.on_motion(MotionSample(.01, False))
    charlie = charlie_fake(walk)
    spoke = []
    def express(*args, **kwargs):
        assert not walk.enabled
        spoke.append(args)
    charlie.express = express
    story = Story(charlie, x=1000, y=10, walk_s=1, clock=clock, log=lambda m: None)
    story.phase = "run"
    story._begin_walk(); charlie.drive_tick()
    assert walk.enabled
    if action == "pause":
        story.pause()
    elif action == "restart":
        story.restart(); story.drain()
    elif action == "speak":
        story._say("called"); story.drain()
    else:
        clock.t = 1.1; story.tick()
    assert not walk.enabled and not story.walking
    count = len(charlie.board.calls)
    charlie.drive_tick()
    assert len(charlie.board.calls) == count


def test_pause_during_invitation_does_not_start_wheels_when_speech_finishes():
    clock, pos, walk = setup_walk()
    feed(pos, -90); walk.on_motion(MotionSample(.01, False))
    charlie = charlie_fake(walk)
    story = Story(charlie, x=1000, y=10, clock=clock, log=lambda m: None)
    story.phase = "run"
    story.pause()
    story._begin_walk()  # Invitation's completion callback, while paused.
    charlie.drive_tick()
    assert not walk.enabled and not story.walking and not charlie.board.calls
    story.resume()
    charlie.drive_tick()
    assert walk.enabled and story.walking
    assert ("robot_drive", "255,255") in charlie.board.calls


def test_initial_empty_dock_and_repeated_removed_events_never_reward_twice():
    clock, pos, walk = setup_walk()
    story = Story(None, x=10, y=10, clock=clock, log=lambda m: None)
    inputs = StoryInputs(story, walk)
    def dock(removed):
        inputs.robot(SimpleNamespace(key="robot_dock", value={"valid": True, "removed": removed, "mm": 8}))
    story.pill = "asking"
    dock(True)
    assert story.pill == "asking" and not story.pending
    dock(False);dock(True)
    assert story.pill == "done" and story.pending == 1
    dock(True)
    assert story.pending == 1


def test_partial_hand_or_invalid_sensor_cannot_trigger_pill_reward():
    clock, pos, walk = setup_walk()
    story = Story(None, x=10, y=10, clock=clock, log=lambda m: None)
    inputs = StoryInputs(story, walk)
    story.pill = "asking";story.dock_present = True
    inputs.robot(SimpleNamespace(key="distance_sensor_min_distance", value=32767))
    inputs.robot(SimpleNamespace(key="robot_dock", value={"valid": False, "removed": True}))
    assert story.pill == "asking" and story.dock_present is True
    assert decode_dock({"valid": True, "removed": "true"}) is None


def test_validated_motion_routes_to_both_story_and_navigation():
    clock, pos, walk = setup_walk()
    story = Story(None, x=10, y=10, clock=clock, log=lambda m: None)
    inputs = StoryInputs(story, walk)
    inputs.wearable(SimpleNamespace(key="wearable_motion", value={"energy": .3, "moving": False}))
    assert walk.moving is False and story.last_energy == .3 and story.user_moving_until == 0
    inputs.wearable(SimpleNamespace(key="wearable_motion", value={"energy": .1, "moving": True}))
    assert walk.moving is True and story.user_moving_until == 2


def test_existing_cli_opens_each_board_once_and_stops_on_exit(monkeypatch):
    import atech
    class FakeBoard(BoardFake):
        closed = False
        def close(self): self.closed = True
    robot, wearable = FakeBoard(), FakeBoard()
    connects = []
    def connect(port=None):
        connects.append(port)
        return {"COM5": robot, "COM8": wearable}[port]
    class NoThread:
        def __init__(self, *args, **kwargs): pass
        def start(self): pass
    def interrupt(_): raise KeyboardInterrupt
    monkeypatch.setattr(atech.Board, "connect", connect)
    monkeypatch.setattr(run_story.threading, "Thread", NoThread)
    monkeypatch.setattr(run_story.time, "sleep", interrupt)
    monkeypatch.setattr(sys, "argv", ["run_story.py", "--robot-port", "COM5",
                                     "--wearable-port", "COM8", "--no-drive"])
    run_story.main()
    assert connects == ["COM5", "COM8"]
    assert robot.closed and wearable.closed
    assert ("robot_mode", "stop") in robot.calls
    assert not any(key == "robot_drive" for key, value in robot.calls)
    assert ("dock_near", "10") in robot.calls


def test_incompatible_firmware_cleanup_preserves_original_startup_error(monkeypatch):
    import atech
    class OldFirmware(BoardFake):
        closed = False
        def call(self, action, value="", **kwargs):
            if action == "speaker_set_volume":
                raise RuntimeError("speaker startup rejected")
            if action == "robot_mode":
                raise RuntimeError("shutdown stop rejected")
        def close(self): self.closed = True
    board = OldFirmware()
    monkeypatch.setattr(atech.Board, "connect", lambda port=None: board)
    monkeypatch.setattr(sys, "argv", ["run_story.py", "--robot-port", "COM5", "--no-drive"])
    with pytest.raises(RuntimeError, match="speaker startup rejected"):
        run_story.main()
    assert board.closed
