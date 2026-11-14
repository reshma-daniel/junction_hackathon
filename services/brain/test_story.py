"""Tests for the story with a fake clock and a fake Charlie. Run: python -m pytest services/brain -q
(or: python services/brain/test_story.py)"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from story import Story  # noqa: E402


class Fake:
    def __init__(self):
        self.t = 0.0
        self.calls = []
        self.moves = []          # robot driving: ("walk", fast) / ("stop",)

    def walk(self, fast=False):
        self.moves.append((round(self.t, 1), "walk", fast))

    def walk_stop(self):
        self.moves.append((round(self.t, 1), "stop"))

    def express(self, emotion, mood=None, **kw):
        self.calls.append((round(self.t, 1), emotion, mood, kw))

    def names(self):
        return [(c[1], c[2]) for c in self.calls]


def make(x=10, y=7, walk_s=2, **kw):
    f = Fake()
    s = Story(f, x=x, y=y, walk_s=walk_s, clock=lambda: f.t, log=lambda m: None, **kw)
    return f, s


def run(f, s, seconds, step=0.5):
    end = f.t + seconds
    while f.t < end:
        f.t += step
        s.tick()
        s.drain()


def awake_and_called(f, s):
    s.begin(); s.drain()
    s.on_called(); s.drain()          # t0 = now


def test_start_is_sleepy_yawn_then_waits_for_charlie():
    f, s = make()
    s.begin(); s.drain()
    assert f.names() == [("wake", "sleepy")]
    assert s.phase == "wait_call"
    run(f, s, 60)                      # no call: nothing else happens, no timers
    assert len(f.calls) == 1


def test_charlie_call_gives_happy_then_starts_clock():
    f, s = make()
    s.begin(); s.drain()
    s.on_called(); s.drain()
    assert f.names()[-1] == ("called", None)
    assert s.phase == "run"


def test_call_before_wake_is_ignored():
    f, s = make()
    s.on_called(); s.drain()
    assert f.calls == []


def test_pill_asked_after_x_and_repeats_every_5s():
    f, s = make(x=10, y=1000)
    awake_and_called(f, s)
    t0 = f.t
    run(f, s, 9)
    assert [c for c in f.calls if c[1] == "pleading"] == []
    run(f, s, 22)
    asks = [c for c in f.calls if c[1] == "pleading"]
    assert [a[3]["attempt"] for a in asks] == [1, 2, 3]
    assert 10 <= asks[0][0] - t0 <= 10.6
    assert 4.9 <= asks[1][0] - asks[0][0] <= 5.6
    assert f.calls[-1][1] == "sad"     # 4th time: gentle back-off, no more asking
    n = len(f.calls)
    run(f, s, 30)
    assert len(f.calls) == n


def test_pill_taken_gives_happy_and_stops_asking():
    f, s = make(x=10, y=1000)
    awake_and_called(f, s)
    s.on_distance(5)                   # pill on the sensor
    run(f, s, 11)                      # first request is out
    s.on_distance(32767); s.on_distance(32767)   # sensor sees nothing for 1 s: pill removed
    s.drain()
    assert f.calls[-1][1:2] == ("reward",) and f.calls[-1][3] == {"task": "pill"}
    n = len(f.calls)
    run(f, s, 30)
    assert len(f.calls) == n


def test_dock_flicker_does_not_count():
    f, s = make(x=1, y=1000)
    awake_and_called(f, s)
    s.on_distance(5)
    run(f, s, 2)
    s.on_distance(32767); s.on_distance(5)       # one odd reading
    s.drain()
    assert all(c[1] != "reward" for c in f.calls)


def test_idle_user_is_reminded_after_y_with_pleading_eyes():
    f, s = make(x=1000, y=7)
    awake_and_called(f, s)
    t0 = f.t
    run(f, s, 6)
    assert all(c[1] != "encouraging" for c in f.calls)
    run(f, s, 2)
    c = [c for c in f.calls if c[1] == "encouraging"][0]
    assert c[2] == "pleading" and 7 <= c[0] - t0 <= 7.6
    run(f, s, 9)                       # 2 s walk, then the window restarts: a second reminder 7 s later
    assert len([c for c in f.calls if c[1] == "encouraging"]) == 2


def test_movement_keeps_charlie_quiet():
    f, s = make(x=1000, y=7)
    awake_and_called(f, s)
    for _ in range(40):                # moving every 2 s for 80 s
        run(f, s, 2)
        s.on_motion(0.3)
    assert all(c[1] != "encouraging" for c in f.calls)


def test_weak_motion_does_not_count():
    f, s = make(x=1000, y=7)
    awake_and_called(f, s)
    for _ in range(5):
        run(f, s, 2)
        s.on_motion(0.01)              # sitting: sensor noise
    assert any(c[1] == "encouraging" for c in f.calls)


def test_backs_off_after_max_reasks_until_user_moves():
    f, s = make(x=1000, y=2, max_reasks=2)
    awake_and_called(f, s)
    run(f, s, 30)
    enc = [c for c in f.calls if c[1] == "encouraging"]
    assert len(enc) == 3 and enc[-1][2] is None       # 2 reminders + calm back-off
    s.on_motion(0.5)
    run(f, s, 3)
    assert len([c for c in f.calls if c[1] == "encouraging"]) == 4   # asks again after moving then idling


def test_moving_after_a_reminder_gives_happy_once():
    f, s = make(x=1000, y=2)
    awake_and_called(f, s)
    run(f, s, 3)                                   # reminder 1 went out, robot is walking
    s.on_motion(0.5)                               # user moves: praise waits until the robot stopped
    assert all(c[1] != "reward" for c in f.calls)
    run(f, s, 3); s.drain()
    rewards = [c for c in f.calls if c[1] == "reward"]
    assert len(rewards) == 1 and rewards[0][3] == {"task": "walk"}
    stops = [m for m in f.moves if m[1] == "stop"]
    assert stops and stops[0][0] <= rewards[0][0]      # robot stopped before it spoke
    s.on_motion(0.5); s.on_motion(0.5); s.drain()      # still moving: no second praise
    assert len([c for c in f.calls if c[1] == "reward"]) == 1


def test_moving_after_backoff_gives_happy():
    f, s = make(x=1000, y=2, max_reasks=2)
    awake_and_called(f, s)
    run(f, s, 20)
    s.on_motion(0.5); s.drain()
    assert f.calls[-1][1] == "reward"


def test_moving_without_a_reminder_stays_quiet():
    f, s = make(x=1000, y=7)
    awake_and_called(f, s)
    run(f, s, 2)
    s.on_motion(0.5); s.drain()
    assert all(c[1] != "reward" for c in f.calls)


def test_robot_walks_after_follow_me_and_stops():
    f, s = make(x=1000, y=3, walk_s=4)
    awake_and_called(f, s)
    t0 = f.t
    run(f, s, 3.5)
    assert f.moves[0][1:] == ("walk", False)          # slow: user is idle
    assert f.calls[-1][1] == "encouraging"            # the line came first
    run(f, s, 5)
    assert f.moves[-1][1] == "stop"
    assert 6.5 <= f.moves[-1][0] - t0 <= 7.6          # 3 s idle + 4 s walk


def test_robot_goes_faster_when_user_moves_and_slower_when_they_stop():
    f, s = make(x=1000, y=3, walk_s=10)
    awake_and_called(f, s)
    run(f, s, 3.5)
    s.on_motion(0.4)
    run(f, s, 0.5)
    assert f.moves[-1][1:] == ("walk", True)
    run(f, s, 3)                                      # no more movement for > 2 s
    assert f.moves[-1][1:] == ("walk", False)


def test_robot_never_drives_while_speaking():
    f, s = make(x=1000, y=3, walk_s=30)
    awake_and_called(f, s)
    run(f, s, 5)
    assert f.moves[-1][1] == "walk"
    s.on_called(); s.drain()                          # "Charlie" in the middle of the walk
    assert f.moves[-1][1] == "stop" and f.calls[-1][1] == "called"


def test_pill_taken_stops_the_robot_first():
    f, s = make(x=1000, y=3, walk_s=30)
    awake_and_called(f, s)
    s.on_distance(5)
    run(f, s, 5)
    s.pill = "asking"
    s.on_pill_removed(); s.drain()
    assert f.moves[-1][1] == "stop" and f.calls[-1][1] == "reward"


def test_timers_wait_while_charlie_speaks():
    f, s = make(x=1, y=1)
    awake_and_called(f, s)
    run(f, s, 1.5)
    s.pending = 1                      # Charlie is talking
    n = len(f.calls)
    run(f, s, 10)
    assert len(f.calls) == n


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
