"""Timed pill delivery and encouragement handoff, with a fake clock and motors."""
import pytest

from story import Story
from test_integration import Clock, charlie_fake, feed, setup_walk
from services.activity.motion import MotionSample
from run_story import load_defaults
import run_story
import sys


class DeliveryAct:
    def __init__(self, clock):
        self.clock, self.speed = clock, 0
        self.events = []
    def express(self, emotion, **kwargs):
        assert self.speed == 0, "never play a phrase while delivering"
        self.events.append((self.clock(), "say", emotion))
    def pill_drive(self, direction):
        self.speed = direction
        self.events.append((self.clock(), "drive", direction))
    def pill_stop(self):
        self.speed = 0
        self.events.append((self.clock(), "stop", 0))
    def walk_stop(self): pass


def delivering():
    clock = Clock(); act = DeliveryAct(clock)
    story = Story(act, x=0, y=1000, pill_approach_s=2.5, clock=clock, log=lambda m: None)
    story.phase = "run"
    story.tick()
    assert act.speed == 0 and story.pending == 1
    story.drain()
    assert act.speed == 0 and story.pill_motion_phase == "approach"
    story.tick()
    assert act.speed == 1
    return clock, act, story


def test_requested_runner_defaults():
    d = load_defaults()
    assert d["volume"] == .1 and d["walk_s"] == 30 and d["follow_window_s"] == 30
    assert d["pill_approach_s"] == 2.5


def test_pill_prompt_approach_pickup_praise_then_reverse_same_duration():
    clock, act, story = delivering()
    clock.t = 2.49; story.tick(); assert act.speed == 1
    clock.t = 2.5; story.tick()
    assert act.speed == 0 and story.pill_forward_s == 2.5 and story.pill_delivered
    story.on_pill_removed()
    assert act.speed == 0
    story.drain()
    assert act.events[-1][1:] == ("say", "reward") and act.speed == 0
    assert story.pill_motion_phase == "return"
    story.tick(); assert act.speed == -1
    clock.t = 4.99; story.tick(); assert act.speed == -1
    clock.t = 5; story.tick()
    assert act.speed == 0 and story.pill_motion_phase is None and story.topic is None


def test_early_pickup_stops_immediately_and_only_reverses_driven_time():
    clock, act, story = delivering()
    clock.t = .7
    story.on_pill_removed()
    assert act.speed == 0 and story.pill_forward_s == .7
    story.drain(); story.tick()
    assert act.speed == -1
    clock.t = 1.41; story.tick()
    assert act.speed == 0 and story.topic is None


def test_duplicate_pickup_does_not_queue_another_reward_or_departure():
    clock, act, story = delivering()
    clock.t = 1; story.on_pill_removed(); story.on_pill_removed()
    assert story.pending == 1
    story.drain(); story.tick()
    assert len([e for e in act.events if e[1:] == ("say", "reward")]) == 1
    assert len([e for e in act.events if e[1:] == ("drive", -1)]) == 1


def test_repeat_pill_prompt_does_not_drive_closer_again():
    clock, act, story = delivering()
    clock.t = 2.5; story.tick()
    clock.t = story.pill_next; story.tick();story.drain();story.tick()
    assert act.speed == 0
    assert len([e for e in act.events if e[1:] == ("drive", 1)]) == 1


@pytest.mark.parametrize("leg", ["approach", "return"])
def test_pause_suspends_motion_and_excludes_paused_time(leg):
    clock, act, story = delivering()
    if leg == "return":
        clock.t = 2.5;story.tick();story.on_pill_removed();story.drain();story.tick()
    began = clock.t
    clock.t += 1;story.pause()
    assert act.speed == 0 and story.pill_motion_remaining == 1.5
    clock.t += 10;story.tick();assert act.speed == 0
    story.resume();story.tick();assert act.speed == (1 if leg == "approach" else -1)
    clock.t += 1.5;story.tick();assert act.speed == 0
    if leg == "approach": assert story.pill_forward_s == 2.5


def test_pause_while_prompt_finishes_defers_delivery_until_resume():
    clock = Clock();act = DeliveryAct(clock)
    story = Story(act, x=0, y=1000, pill_approach_s=2.5, clock=clock, log=lambda m: None)
    story.phase = "run";story.tick();story.pause();story.drain();story.tick()
    assert act.speed == 0
    story.resume();story.tick();assert act.speed == 1


def test_restart_cancels_delivery_and_stale_reward_return_callback():
    clock, act, story = delivering()
    clock.t = .7;story.on_pill_removed();story.restart();story.drain()
    assert act.speed == 0 and story.pill_motion_phase is None
    assert not any(e[1:] == ("drive", -1) for e in act.events)


def test_interruption_speaks_stopped_and_resumes_remaining_delivery():
    clock, act, story = delivering()
    clock.t = 1;story.on_called();story.drain()
    assert act.speed == 0 and story.pill_motion_remaining == 1.5
    story.tick();assert act.speed == 1
    clock.t = 2.5;story.tick();assert act.speed == 0 and story.pill_forward_s == 2.5


def test_return_drive_failure_does_not_leave_story_stuck_in_pill_topic():
    clock, act, story = delivering()
    clock.t = .7;story.on_pill_removed();story.drain()
    def fail(_): raise RuntimeError("serial unavailable")
    act.pill_drive = fail
    story.tick()
    assert act.speed == 0 and story.topic is None and story.pill_motion_phase is None


def returned_walk():
    clock, pos, walk = setup_walk()
    charlie = charlie_fake(walk)
    story = Story(charlie, x=1000, y=10, walk_s=30, follow_window_s=30,
                  clock=clock, log=lambda m: None)
    story.phase = "run"
    feed(pos, -90);walk.on_motion(MotionSample(.2, True));story._begin_walk();charlie.drive_tick()
    clock.t = 1;feed(pos, -92);walk.on_motion(MotionSample(.01, False));charlie.drive_tick()
    clock.t = 1.21;charlie.drive_tick();assert walk.output == 255
    clock.t = 2;feed(pos, -80);charlie.drive_tick()
    assert walk.phase == "encourage" and walk.output == 0
    return clock, pos, walk, charlie, story


def test_close_return_encourages_once_waits_for_motion_and_extends_walk():
    clock, pos, walk, charlie, story = returned_walk()
    phrases = []
    def express(emotion, **kw):
        assert charlie._walk_held and walk.output == 0
        n = len(charlie.board.calls);charlie.drive_tick()
        assert len(charlie.board.calls) == n
        phrases.append((emotion, kw));clock.t += 2
    charlie.express = express
    story.tick();story.tick();assert story.pending == 1
    story.drain()
    assert phrases == [("encouraging", {"mood": "encouraging", "attempt": 1})]
    assert walk.phase == "wait_for_user" and not charlie._walk_held
    assert story.walk_until == 32 and story.follow_until == 32
    for i in range(10):
        clock.t += .21
        feed(pos, -79 if i % 2 else -85)  # RSSI fluctuations cannot restart approach.
        walk.on_motion(MotionSample(.01, False));charlie.drive_tick()
        story.tick();story.drain()
        assert walk.phase == "wait_for_user" and walk.output == 0
        assert len(phrases) == 1
    clock.t += .21;feed(pos, -80);walk.on_motion(MotionSample(.2, True));charlie.drive_tick()
    assert walk.output == -255
    story.tick();story.drain();assert len(phrases) == 1


@pytest.mark.parametrize("interrupt", ["pause", "restart"])
def test_pause_or_restart_during_return_prompt_never_resumes_wheels(interrupt):
    clock, pos, walk, charlie, story = returned_walk()
    def express(emotion, **kw):
        if emotion == "encouraging":
            getattr(story, interrupt)()
            clock.t += 2
    charlie.express = express
    story.tick();story.drain();charlie.drive_tick()
    assert not walk.enabled and not story.walking and walk.output == 0


def test_failed_stop_is_retried_before_any_other_motion_command():
    clock, pos, walk = setup_walk();charlie = charlie_fake(walk)
    charlie.pill_drive(1)
    real_call = charlie.board.call
    def fail(*args, **kwargs): raise RuntimeError("no ack")
    charlie.board.call = fail
    with pytest.raises(RuntimeError): charlie.pill_stop()
    assert charlie._pill_speed == 0 and charlie._stop_pending
    charlie.board.call = real_call;charlie.drive_tick()
    assert not charlie._stop_pending and charlie.board.calls[-1] == ("robot_mode", "stop")


def test_no_drive_cli_gates_both_pill_directions(monkeypatch, tmp_path):
    import atech
    factory = run_story.RunTelemetry
    monkeypatch.setattr(run_story, "RunTelemetry", lambda directory: factory(tmp_path))
    from test_integration import BoardFake
    class FakeBoard(BoardFake):
        def close(self): pass
    robot, wearable = FakeBoard(), FakeBoard()
    class NoThread:
        def __init__(self, *a, **kw): pass
        def start(self): pass
    class PillProbe:
        def __init__(self, act, **kw): self.act = act
        def worker(self): pass
        def begin(self):
            self.act.pill_drive(1); self.act.pill_stop()
            self.act.pill_drive(-1); self.act.pill_stop()
    def interrupt(_): raise KeyboardInterrupt
    monkeypatch.setattr(atech.Board, "connect", lambda port=None: robot if port == "COM5" else wearable)
    monkeypatch.setattr(run_story.threading, "Thread", NoThread)
    monkeypatch.setattr(run_story, "Story", PillProbe)
    monkeypatch.setattr(run_story.time, "sleep", interrupt)
    monkeypatch.setattr(sys, "argv", ["run_story.py", "--robot-port", "COM5", "--wearable-port", "COM8", "--no-drive"])
    run_story.main()
    assert not any(key == "robot_drive" for key, value in robot.calls)
