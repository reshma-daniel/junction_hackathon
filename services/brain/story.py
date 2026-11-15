"""Charlie's story: wake, wait for "Charlie", then watch the pill and the user's movement.

Pure logic, no hardware: it decides WHAT Charlie does and WHEN; an `act` object does it.
`run_story.py` connects it to the real boards; `test_story.py` tests it with a fake clock.

  start            sleepy (yellow) eyes + yawn + greeting
  wait for call    user says "Charlie"  -> happy eyes + happy speech
  then the clock starts (t0 = when the greeting ended):
    X seconds after t0   pleading eyes + pill request; asks again every `repeat_s` while ignored
                         pill taken (dock sensor, port 7, stops seeing it) -> happy eyes + happy speech
    Y seconds without movement (wearable)  pleading eyes + "Follow me" line, THEN the robot drives off
                         (walk_s seconds, with the existing front obstacle clamp on port 11):
                         IMU/RSSI selects approach, lead and return directions.
                         The robot never drives while it speaks (the speaker blocks its motor loop).
                         Walk time (`follow_window_s`, starts with the walk): at its end
                         the user moved at all -> happy eyes + praise;
                         the user never moved  -> sad eyes + a gentle back-off line.
                         Then the Y window restarts.

After `max_reasks` unanswered asks Charlie backs off gently (never nags forever).
A pill nobody takes ends with sad eyes and a gentle back-off line (never guilt).

One topic at a time: while Charlie is asking about the pill (until it is taken, or Charlie gives up) it never
asks about walking, and while a walk ask is going on (ask, walk, praise) it never asks about the pill.
After either one ends Charlie stays quiet for `gap_s` (break) before the next ask. The pill goes first when
both are due. A finished pill episode starts the movement window afresh, so "Follow me" never comes right
after the pill.
"""
from __future__ import annotations

import queue
import threading
import time
from typing import Callable, Optional


class Story:
    def __init__(self, act, x: float, y: float, repeat_s: float = 5.0, max_reasks: int = 3, walk_s: float = 10.0,
                 motion_energy: float = 0.05, dock_near_mm: int = 40, dock_hold: int = 2, gap_s: float = 8.0,
                 follow_window_s: float = 10.0,
                 pill_approach_s: float = 0.0,
                 clock: Callable[[], float] = time.monotonic, log: Callable[[str], None] = print):
        self.act, self.x, self.y = act, x, y
        self.repeat_s, self.max_reasks, self.walk_s = repeat_s, max_reasks, walk_s
        self.gap_s = gap_s
        self.follow_window_s = follow_window_s  # walk time: the user has this long after "Follow me" to move
        self.pill_approach_s = max(0.0, pill_approach_s)
        self.motion_energy, self.dock_near_mm, self.dock_hold = motion_energy, dock_near_mm, dock_hold
        self.clock, self.log = clock, log
        self.lock = threading.RLock()
        self.jobs: "queue.Queue[Callable[[], None]]" = queue.Queue()
        self.pending = 0                      # jobs queued or running: timers wait while Charlie acts
        self.gen = 0                          # bumped on restart: actions from before are dropped
        self.on_mark: Callable[[str, str], None] = lambda kind, label: None   # events for the panel's clock
        self.last_energy: Optional[float] = None   # live wearable reading (panel)
        self.last_dock_mm: Optional[int] = None    # live dock reading (panel)
        self.robot_behavior: Optional[str] = None  # robot's own state: wake / idle / search / happy / express
        self.paused = False
        self._paused_at = 0.0
        self._reset_state()

    def _reset_state(self) -> None:
        self.following = False                # inside the walk time
        self.follow_until = 0.0
        self._after_resume: list = []         # next steps that finished during a pause run on Resume
        self.moved_in_window = False
        self.topic: Optional[str] = None      # None | "pill" | "move": what Charlie is asking about right now
        self.quiet_until = 0.0                # break after a topic ends: no new ask before this
        self.phase = "new"                    # new -> starting -> wait_call -> run
        self.t0 = 0.0
        # pill
        self.pill = "wait"                    # wait -> asking -> done | gave_up
        self.pill_attempt = 0
        self.pill_next = 0.0
        self.dock_present: Optional[bool] = None   # None = not known yet
        self._dock_votes = 0
        self.pill_delivered = False
        self.pill_forward_s = 0.0
        self.pill_motion_phase: Optional[str] = None
        self.pill_motion_remaining = 0.0
        self.pill_motion_started: Optional[float] = None
        # movement
        self.last_move = 0.0
        self.move_asks = 0
        self.move_quiet = False
        self.user_moving_until = 0.0          # wearable showed movement until this time
        # robot walk after the "Follow me" line
        self.walking = False
        self._walk_pending = False
        self._walk_encouraging = False
        self._invitation_open = False
        self._invitation_responded = False
        self.walk_until = 0.0
        self.walk_fast = False
        self.called_at: Optional[float] = None
        self.pill_done_at: Optional[float] = None
        self.walk_result: Optional[str] = None     # "praise" | "sad" for the last walk time

    # ---------- panel controls: settings, restart, pause ----------
    SETTINGS = ("x", "y", "repeat_s", "max_reasks", "walk_s", "follow_window_s", "gap_s",
                "motion_energy", "dock_near_mm")

    def settings(self) -> dict:
        return {k: getattr(self, k) for k in self.SETTINGS}

    def set_settings(self, new: dict) -> list:
        """Change timings and thresholds while the story runs. Returns what changed."""
        changed = []
        with self.lock:
            for k in self.SETTINGS:
                if k not in new:
                    continue
                try:
                    v = int(new[k]) if k in ("max_reasks", "dock_near_mm") else float(new[k])
                except (TypeError, ValueError):
                    continue
                if k == "dock_near_mm" and not 5 <= v <= 500:
                    continue
                if v < 0 or v == getattr(self, k):
                    continue
                setattr(self, k, v)
                changed.append(f"{k}={v:g}")
        if changed:
            self.log("Settings: " + ", ".join(changed))
        return changed

    def restart(self) -> None:
        """Start the story again from the wake-up (panel "Restart"). Queued actions are dropped."""
        with self.lock:
            self.gen += 1
            while True:
                try:
                    self.jobs.get_nowait()
                    self.pending -= 1
                except queue.Empty:
                    break
            was_walking = self.walking
            was_delivering = self.pill_motion_phase is not None
            self._reset_state()
            self.paused = False
        if was_walking:
            try:
                self.act.walk_stop()
            except Exception:
                pass
        if was_delivering:
            try:
                self.act.pill_stop()
            except Exception as e:
                self.log(f"! pill stop failed: {e}")
        self.log("Story restarted")
        self.begin()

    def pause(self) -> None:
        with self.lock:
            if self.paused:
                return
            self.paused, self._paused_at = True, self.clock()
        self._stop_walk()
        self._pause_pill_motion()
        self.log("Paused")

    def resume(self) -> None:
        """Timers continue where they stopped: every deadline moves on by the paused time."""
        with self.lock:
            if not self.paused:
                return
            d = self.clock() - self._paused_at
            self.paused = False
            for k in ("t0", "pill_next", "last_move", "quiet_until", "follow_until", "user_moving_until"):
                v = getattr(self, k)
                if v not in (0.0, float("inf")):
                    setattr(self, k, v + d)
            pending_walk = self._walk_pending
            self._walk_pending = False
        self.log("Resumed")
        waiting, self._after_resume = self._after_resume, []
        for step in waiting:
            step()
        if pending_walk:
            self._begin_walk()

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
            if self.paused:            # Pause holds everything: queued speech waits until Resume
                time.sleep(0.1)
                continue
            self.run_one_job(block=True)

    def _say(self, emotion: str, then: Optional[Callable[[], None]] = None, **kw) -> None:
        gen = self.gen

        def job():
            if gen != self.gen:                            # queued before a restart: drop it
                return
            try:
                self._stop_walk()                          # never speak while driving
                self._pause_pill_motion()
                self.act.express(emotion, **kw)
            finally:
                if then and gen == self.gen:               # the story goes on even if the robot missed a sound
                    if self.paused:                        # paused meanwhile: the next step waits for Resume
                        self._after_resume.append(then)
                    else:
                        then()
        self._enqueue(job)

    # ---------- story steps ----------
    def begin(self) -> None:
        """Program start: sleepy eyes, yawn, greeting; then wait for "Charlie"."""
        with self.lock:
            self.phase = "starting"
        self.log("Charlie wakes up (sleepy eyes, yawn, greeting)")
        self.on_mark("wake", "wake-up")
        self._say("wake", mood="sleepy", then=self._wait_for_call)

    def _wait_for_call(self) -> None:
        with self.lock:
            self.phase = "wait_call"
        self.log('Waiting for someone to call "Charlie"')

    def on_called(self) -> None:
        """The user said "Charlie"."""
        if self.paused:
            self.log('Heard "Charlie" while paused: ignored')
            return
        with self.lock:
            if self.phase in ("new", "starting"):
                return                                    # still waking up: not listening yet
            first = self.phase == "wait_call"
            if first:
                self.phase = "calling"
        self.log('Heard "Charlie": happy eyes + greeting')
        self.called_at = self.clock()
        self.on_mark("call", '"Charlie!"')
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
        self.last_dock_mm = mm
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

    def on_dock(self, removed: bool, mm: int | None = None) -> None:
        """Already-debounced coverage state. Initial empty dock is not a pickup."""
        if mm is not None:
            self.last_dock_mm = mm
        present = not removed
        with self.lock:
            before = self.dock_present
            self.dock_present = present
        if before is True and removed:
            self.on_pill_removed()
        elif before is not True and present:
            self.log("Dock sensor: pill on the sensor")

    def on_pill_removed(self) -> None:
        with self.lock:
            if self.pill in ("done",):
                return
            was = self.pill
            self.pill = "done"
            self._pause_pill_motion()
            self.pill_motion_phase = None
            self.pill_motion_remaining = 0.0
        if was == "wait":
            self.log("Pill removed before it was due: nothing to ask")
            return
        self.log("Pill taken: happy eyes + thank you")
        self.pill_done_at = self.clock()
        self.on_mark("pill", "pill taken")
        self._say("reward", task="pill", then=self._return_after_pill)

    def on_motion(self, energy: float, moving: bool | None = None) -> None:
        """Wearable, once per second. energy >= threshold counts as moving."""
        self.last_energy = energy
        if not (moving if moving is not None else energy >= self.motion_energy):
            return
        now = self.clock()
        with self.lock:
            self.user_moving_until = now + 2.0
            if self._invitation_open:
                # An early response belongs to the upcoming walk. Enqueuing a
                # reward here would stop that walk immediately after speech.
                self._invitation_responded = True
                return
            if self.following:                            # judged at the end of the walk time
                self.moved_in_window = True
                return
            self.last_move = now
            reminded = self.phase == "run" and self.move_asks > 0
            self.move_asks = 0
            self.move_quiet = False
        if reminded:                                      # moved after being asked: happy eyes + praise
            self.log("User moves after a reminder: happy eyes + praise")
            self._say("reward", task="walk", then=lambda: self._end_topic("move"))

    # ---------- the clock ----------
    def tick(self) -> None:
        with self.lock:
            if self.phase != "run" or self.paused:
                return
            now = self.clock()
            if self.pill_motion_phase is not None:
                self._tick_pill_motion(now)
                return
            if self.walking:
                self._walk_tick(now)
                return
            if self.following:                            # walk time still running (robot already stopped)
                if now >= self.follow_until and not self.pending:
                    self._judge_walk()
                return
            if self.pending:
                return
            if now < self.quiet_until:                    # break between two topics
                return
            # the pill first: a pill episode blocks walk asks until it ends
            if self.topic in (None, "pill"):
                if self.pill == "wait" and now >= self.t0 + self.x:
                    self.pill = "asking"
                    self.topic = "pill"
                    if self.dock_present is False:
                        self.log("! the dock sensor sees no pill: put the pill on port 7 (and take it off to finish)")
                    self._ask_pill(now)
                    return
                if self.pill == "asking":
                    if now >= self.pill_next:
                        self._ask_pill(now)
                    return                                # still waiting for the pill: no walk asks
            # walking only when nothing else is going on
            if self.topic is None and not self.move_quiet and now - self.last_move >= self.y:
                self.topic = "move"
                self._ask_move(now)

    def _end_topic(self, kind: str) -> None:
        """A pill or walk episode is over: take a break before the next ask."""
        with self.lock:
            now = self.clock()
            if self.topic in (None, kind):
                self.topic = None
            self.quiet_until = max(self.quiet_until, now + self.gap_s)
            if kind == "pill" and not self.walking:
                self.last_move = now                      # fresh movement window after the pill
        self.log(f"{'Pill' if kind == 'pill' else 'Walk'} episode over: {self.gap_s:g} s break before the next ask")

    def _ask_pill(self, now: float) -> None:
        self.pill_attempt += 1
        n = self.pill_attempt
        if n > self.max_reasks:
            self.pill = "gave_up"
            self.log("Pill: not taken, backing off gently: sad eyes + sad speech")
            self.pill_done_at = self.clock()
            self.on_mark("pill_missed", "pill not taken")
            self._say("sad", then=lambda: self._end_topic("pill"))
            return
        self.log(f"Pill request {n}: pleading eyes + speech")
        self.on_mark("nudge", f"pill ask {n}")
        self.pill_next = float("inf")                     # re-armed when the speech has finished
        self._say("pleading", attempt=n, then=self._after_pill_prompt)

    def _after_pill_prompt(self) -> None:
        with self.lock:
            if self.pill != "asking":
                return
            if not self.pill_delivered and self.pill_approach_s > 0:
                self.pill_motion_phase = "approach"
                self.pill_motion_remaining = self.pill_approach_s
                self.pill_motion_started = None
                self.log(f"Delivering pill: approach for {self.pill_approach_s:g} s")
                return
        self._arm_pill_repeat()

    def _pause_pill_motion(self) -> None:
        with self.lock:
            if self.pill_motion_started is None:
                return
            elapsed = min(self.pill_motion_remaining, max(0.0, self.clock() - self.pill_motion_started))
            if self.pill_motion_phase == "approach":
                self.pill_forward_s += elapsed
            self.pill_motion_remaining = max(0.0, self.pill_motion_remaining - elapsed)
            self.pill_motion_started = None
        try:
            self.act.pill_stop()
        except Exception as e:
            self.log(f"! pill stop failed: {e}")

    def _return_after_pill(self) -> None:
        with self.lock:
            if self.pill_forward_s > 0:
                self.pill_motion_phase = "return"
                self.pill_motion_remaining = self.pill_forward_s
                self.pill_motion_started = None
                self.log(f"Pill taken: reverse for {self.pill_forward_s:g} s to approximate the starting position")
                return
        self._end_topic("pill")

    def _tick_pill_motion(self, now: float) -> None:
        if self.pending:
            self._pause_pill_motion()
            return
        if self.pill_motion_started is None and self.pill_motion_remaining > 0:
            try:
                self.act.pill_drive(1 if self.pill_motion_phase == "approach" else -1)
            except Exception as e:
                self.log(f"! pill drive failed: {e}")
                try:
                    self.act.pill_stop()
                except Exception:
                    pass
                leg = self.pill_motion_phase
                self.pill_motion_phase = None
                self.pill_motion_remaining = 0.0
                self.pill_delivered = True
                if leg == "return":
                    self.pill_forward_s = 0.0
                    self._end_topic("pill")
                else:
                    self._arm_pill_repeat()
                return
            self.pill_motion_started = now
        if (self.pill_motion_started is not None
                and now - self.pill_motion_started < self.pill_motion_remaining):
            return
        leg = self.pill_motion_phase
        self._pause_pill_motion()
        self.pill_motion_phase = None
        if leg == "approach":
            self.pill_delivered = True
            self._arm_pill_repeat()
            self.log("Pill delivery arrived: waiting for pickup")
        else:
            self.pill_forward_s = 0.0
            self._end_topic("pill")

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
            self._say("encouraging", attempt=n, then=lambda: self._end_topic("move"))
            return
        self.log(f"No movement for {self.y:g} s, reminder {n}: pleading eyes + encouraging speech")
        self.on_mark("walk_start", f'"Follow me" {n}')
        self._invitation_open = True
        self._invitation_responded = False
        self.last_move = float("inf")                     # re-armed when the speech has finished
        self._say("encouraging", mood="pleading", attempt=n, then=self._begin_walk)

    def _restart_move_window(self) -> None:
        with self.lock:
            if self.last_move == float("inf"):
                self.last_move = self.clock()

    # ---------- the robot walks after "Follow me" ----------
    def _begin_walk(self) -> None:
        with self.lock:
            if self.paused:
                self._walk_pending = True
                return
            now = self.clock()
            self.walking = True
            self.walk_until = now + self.walk_s
            self.walk_fast = now < self.user_moving_until
            self.last_move = float("inf")
            self.following = True
            self.moved_in_window = self._invitation_responded or self.walk_fast
            self._invitation_open = False
            self._invitation_responded = False
            self.follow_until = now + self.follow_window_s
        self.log(f"Robot walk episode: {self.walk_s:g} s (user {'moving' if self.walk_fast else 'still'}); "
                 f"walk time {self.follow_window_s:g} s for the user to move")
        self._drive(fast=self.walk_fast)

    def _drive(self, fast: bool) -> None:
        try:
            self.act.walk(fast=fast)
        except Exception as e:                            # robot missed a command: keep the story going
            self.log(f"! drive command failed: {e}")

    def _walk_tick(self, now: float) -> None:
        if self._walk_encouraging:
            return
        if now >= self.walk_until:
            self._stop_walk()
            return
        if getattr(self.act, "walk_needs_encouragement", lambda: False)():
            self._encourage_return()
            return
        fast = now < self.user_moving_until
        if fast != self.walk_fast:
            self.walk_fast = fast
            self.log(f"User {'moves' if fast else 'stopped'}: updating walk input")
            self._drive(fast=fast)

    def _encourage_return(self) -> None:
        """At close RSSI, encourage once, then wait for wearable movement."""
        self._walk_encouraging = True
        gen = self.gen
        self.log("RSSI close threshold reached: stop, encourage once, then wait for IMU moving=true")

        def job():
            if gen != self.gen or not self.walking or self.paused:
                if gen == self.gen:
                    self._walk_encouraging = False
                return
            began = self.clock()
            try:
                self.act.walk_hold()
                self.act.express("encouraging", mood="encouraging", attempt=1)
            finally:
                with self.lock:
                    if gen == self.gen:
                        self._walk_encouraging = False
                        if self.walking and not self.paused:
                            duration = max(0.0, self.clock() - began)
                            self.walk_until += duration
                            self.follow_until += duration
                            self.act.walk_resume()
        self._enqueue(job)

    def _judge_walk(self) -> None:
        """End of the walk time: praise if the user moved at all, else sad eyes + a gentle back-off line."""
        self.following = False
        self.last_move = float("inf")                     # re-armed after the reaction

        def after():
            self._restart_move_window()
            self._end_topic("move")
        if self.moved_in_window:
            self.move_asks = 0
            self.log("The user moved during the walk time: happy eyes + praise")
            self.walk_result = "praise"
            self.on_mark("walk", "walk: praise")
            self._say("reward", task="walk", then=after)
            return
        if self.move_asks >= self.max_reasks:
            self.move_quiet = True                        # no more walk asks until the user moves
            self.log("User didn't move during the walk time, last ask: sad eyes + sad speech, then quiet")
        else:
            self.log("User didn't move during the walk time: sad eyes + sad speech")
        self.walk_result = "sad"
        self.on_mark("walk_sad", "walk: no movement (sad)")
        self._say("encouraging", mood="sad", attempt=self.max_reasks + 1, then=after)

    def _stop_walk(self) -> None:
        """Stop the motors if the robot is walking."""
        with self.lock:
            if not self.walking:
                return
            self.walking = False
        self.log("Robot stops")
        try:
            self.act.walk_stop()
        except Exception as e:
            self.log(f"! stop command failed: {e}")
