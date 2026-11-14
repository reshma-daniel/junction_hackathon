"""Charlie's story: wake, wait for "Charlie", then watch the pill and the user's movement.

Pure logic, no hardware: it decides WHAT Charlie does and WHEN; an `act` object does it.
`run_story.py` connects it to the real boards; `test_story.py` tests it with a fake clock.

  start            sleepy (yellow) eyes + yawn + greeting
  wait for call    user says "Charlie"  -> happy eyes + happy speech
  then the clock starts (t0 = when the greeting ended):
    X seconds after t0   pleading eyes + pill request; asks again every `repeat_s` while ignored
                         pill taken (dock sensor, port 7, stops seeing it) -> happy eyes + happy speech
    Y seconds without movement (wearable)  pleading eyes + "Follow me" line, THEN the robot drives off
                         (walk_s seconds, avoiding obstacles with the front sensor on port 11):
                         slowly while the user sits, faster while the wearable shows the user moving.
                         The robot never drives while it speaks (the speaker blocks its motor loop).
                         User moved during the walk -> happy eyes + praise when it stops.
                         Then the Y window restarts.

After `max_reasks` unanswered asks Charlie backs off gently (never nags forever).
"""
from __future__ import annotations

import queue
import threading
import time
from typing import Callable, Optional


class Story:
    def __init__(self, act, x: float, y: float, repeat_s: float = 5.0, max_reasks: int = 3, walk_s: float = 10.0,
                 motion_energy: float = 0.05, dock_near_mm: int = 40, dock_hold: int = 2,
                 clock: Callable[[], float] = time.monotonic, log: Callable[[str], None] = print):
        self.act, self.x, self.y = act, x, y
        self.repeat_s, self.max_reasks, self.walk_s = repeat_s, max_reasks, walk_s
        self.motion_energy, self.dock_near_mm, self.dock_hold = motion_energy, dock_near_mm, dock_hold
        self.clock, self.log = clock, log
        self.lock = threading.RLock()
        self.jobs: "queue.Queue[Callable[[], None]]" = queue.Queue()
        self.pending = 0                      # jobs queued or running: timers wait while Charlie acts
        self.phase = "new"                    # new -> starting -> wait_call -> run
        self.t0 = 0.0
        # pill
        self.pill = "wait"                    # wait -> asking -> done | gave_up
        self.pill_attempt = 0
        self.pill_next = 0.0
        self.dock_present: Optional[bool] = None   # None = not known yet
        self._dock_votes = 0
        # movement
        self.last_move = 0.0
        self.move_asks = 0
        self.move_quiet = False
        self.user_moving_until = 0.0          # wearable showed movement until this time
        # robot walk after the "Follow me" line
        self.walking = False
        self.walk_until = 0.0
        self.walk_fast = False
        self.moved_during_walk = False

    # ---------- job queue: one action at a time, in order ----------
    def _enqueue(self, fn: Callable[[], None]) -> None:
        with self.lock:
            self.pending += 1
        self.jobs.put(fn)

    def run_one_job(self, block: bool = False) -> bool:
        try:
            fn = self.jobs.get(block=block, timeout=0.2 if block else None)
        except queue.Empty:
            return False
        try:
            fn()
        except Exception as e:  # a failed sound must not stop the story
            self.log(f"! action failed: {e}")
        finally:
            with self.lock:
                self.pending -= 1
        return True

    def drain(self) -> None:
        while self.run_one_job():
            pass

    def worker(self) -> None:
        while True:
            self.run_one_job(block=True)

    def _say(self, emotion: str, then: Optional[Callable[[], None]] = None, **kw) -> None:
        def job():
            self._stop_walk()                              # never speak while driving
            self.act.express(emotion, **kw)
            if then:
                then()
        self._enqueue(job)

    # ---------- story steps ----------
    def begin(self) -> None:
        """Program start: sleepy eyes, yawn, greeting; then wait for "Charlie"."""
        with self.lock:
            self.phase = "starting"
        self.log("Charlie wakes up (sleepy eyes, yawn, greeting)")
        self._say("wake", mood="sleepy", then=self._wait_for_call)

    def _wait_for_call(self) -> None:
        with self.lock:
            self.phase = "wait_call"
        self.log('Waiting for someone to call "Charlie"')

    def on_called(self) -> None:
        """The user said "Charlie"."""
        with self.lock:
            if self.phase in ("new", "starting"):
                return                                    # still waking up: not listening yet
            first = self.phase == "wait_call"
            if first:
                self.phase = "calling"
        self.log('Heard "Charlie": happy eyes + greeting')
        self._say("called", then=self._start_monitoring if first else None)

    def _start_monitoring(self) -> None:
        with self.lock:
            now = self.clock()
            self.t0 = self.last_move = now
            self.phase = "run"
        self.log(f"Monitoring starts: pill request in X={self.x:g} s, movement window Y={self.y:g} s")

    # ---------- sensor inputs ----------
    def on_distance(self, mm: int) -> None:
        """Dock sensor (port 7), one reading every 0.5 s. Pill present = something right on the sensor."""
        present = mm < self.dock_near_mm
        with self.lock:
            if self.dock_present is None:
                self.dock_present, self._dock_votes = present, 0
                self.log(f"Dock sensor: {'pill on the sensor' if present else 'nothing on the sensor'} ({mm} mm)")
                return
            if present == self.dock_present:
                self._dock_votes = 0
                return
            self._dock_votes += 1
            if self._dock_votes < self.dock_hold:         # must hold for a moment: ignore flicker
                return
            self.dock_present, self._dock_votes = present, 0
        if not present:
            self.on_pill_removed()
        else:
            self.log("Dock sensor: pill back on the sensor")

    def on_pill_removed(self) -> None:
        with self.lock:
            if self.pill in ("done",):
                return
            was = self.pill
            self.pill = "done"
        if was == "wait":
            self.log("Pill removed before it was due: nothing to ask")
            return
        self.log("Pill taken: happy eyes + thank you")
        self._say("reward", task="pill")

    def on_motion(self, energy: float) -> None:
        """Wearable, once per second. energy >= threshold counts as moving."""
        if energy < self.motion_energy:
            return
        now = self.clock()
        with self.lock:
            self.user_moving_until = now + 2.0
            if self.walking:                              # praise comes when the robot has stopped
                self.moved_during_walk = True
                return
            self.last_move = now
            reminded = self.phase == "run" and self.move_asks > 0
            self.move_asks = 0
            self.move_quiet = False
        if reminded:                                      # moved after being asked: happy eyes + praise
            self.log("User moves after a reminder: happy eyes + praise")
            self._say("reward", task="walk")

    # ---------- the clock ----------
    def tick(self) -> None:
        with self.lock:
            if self.phase != "run":
                return
            now = self.clock()
            if self.walking:
                self._walk_tick(now)
                return
            if self.pending:
                return
            if self.pill == "wait" and now >= self.t0 + self.x:
                self.pill = "asking"
                if self.dock_present is False:
                    self.log("! the dock sensor sees no pill: put the pill on port 7 (and take it off to finish)")
                self._ask_pill(now)
            elif self.pill == "asking" and now >= self.pill_next:
                self._ask_pill(now)
            elif not self.move_quiet and now - self.last_move >= self.y:
                self._ask_move(now)

    def _ask_pill(self, now: float) -> None:
        self.pill_attempt += 1
        n = self.pill_attempt
        if n > self.max_reasks:
            self.pill = "gave_up"
            self.log("Pill: no answer, backing off gently")
            self._say("sad")
            return
        self.log(f"Pill request {n}: pleading eyes + speech")
        self.pill_next = float("inf")                     # re-armed when the speech has finished
        self._say("pleading", attempt=n, then=self._arm_pill_repeat)

    def _arm_pill_repeat(self) -> None:
        with self.lock:
            if self.pill == "asking":
                self.pill_next = self.clock() + self.repeat_s

    def _ask_move(self, now: float) -> None:
        self.move_asks += 1
        n = self.move_asks
        if n > self.max_reasks:
            self.move_quiet = True                        # stay quiet until the user moves
            self.log("Movement: no answer, backing off gently")
            self._say("encouraging", attempt=n)
            return
        self.log(f"No movement for {self.y:g} s, reminder {n}: pleading eyes + encouraging speech")
        self.last_move = float("inf")                     # re-armed when the speech has finished
        self._say("encouraging", mood="pleading", attempt=n, then=self._begin_walk)

    def _restart_move_window(self) -> None:
        with self.lock:
            if self.last_move == float("inf"):
                self.last_move = self.clock()

    # ---------- the robot walks after "Follow me" ----------
    def _begin_walk(self) -> None:
        with self.lock:
            now = self.clock()
            self.walking, self.moved_during_walk = True, False
            self.walk_until = now + self.walk_s
            self.walk_fast = now < self.user_moving_until
            self.last_move = float("inf")
        self.log(f"Robot walks for {self.walk_s:g} s ({'fast' if self.walk_fast else 'slow'})")
        self.act.walk(fast=self.walk_fast)

    def _walk_tick(self, now: float) -> None:
        fast = now < self.user_moving_until
        if fast != self.walk_fast:
            self.walk_fast = fast
            self.log(f"User {'moves' if fast else 'stopped'}: robot goes {'faster' if fast else 'slower'}")
            self.act.walk(fast=fast)
        if now >= self.walk_until:
            moved = self._stop_walk()
            self.last_move = now
            if moved:
                self.move_asks = 0
                self.log("The user moved during the walk: happy eyes + praise")
                self.last_move = float("inf")
                self._say("reward", task="walk", then=self._restart_move_window)

    def _stop_walk(self) -> bool:
        """Stop the motors if the robot is walking. Returns whether the user moved during the walk."""
        with self.lock:
            if not self.walking:
                return False
            self.walking = False
            moved = self.moved_during_walk
            if self.last_move == float("inf"):
                self.last_move = self.clock()
        self.log("Robot stops")
        self.act.walk_stop()
        return moved
