#!/usr/bin/env python3
"""Charlie demo runner: one day with Charlie on a fast clock, with the real voice.

    python tools/demo/run_demo.py                 # 1 day = 3 minutes, sound in the panel (browser tab)
    python tools/demo/run_demo.py --fast          # 1 day = 2 minutes
    python tools/demo/run_demo.py --link usb      # sound on the robot speaker over USB
    python tools/demo/run_demo.py --listen        # also hear "Charlie" on the laptop mic
    gateway | python tools/demo/run_demo.py --stdin   # real sensors: team JSON messages, one per line

Open http://localhost:8765 and click Start. Every setting is in real-life time (wake-up 08:00, pill 09:00,
move after 45 min...). Only the clock speed differs between the demo and real life ("real time").
The clock stops while Charlie talks, so one sentence never skips half an hour.

  08:00  wake-up call: yawn + good morning (Charlie sleeps from bedtime until then)
  09:00  pill: dock not opened today -> `pill` reminder 1, 2, 3, then a gentle back-off (missed)
  day    no movement on the wearable for 45 min -> `encourage` 1, 2, 3, then back off
         a walk counts once the user has walked "walk goal" (15 min); a short stop (< 3 min) is fine,
         a shorter walk still gets a gentle "that's a win"
  22:00  bedtime: Charlie goes quiet until the next morning
The dial keeps the last 24 h of marks: wake-up, pill taken / missed, walks, reminders.

Sensors: the panel buttons stand in for them. Real messages (docs/MESSAGES.md) by POST /msg or --stdin:
  {"type":"wearable.motion","moving":true}   {"type":"robot.dock","reach":true}
  {"type":"voice.wake"} or {"type":"robot.heard","kind":"call"}
"""
from __future__ import annotations

import argparse
import base64
import json
import queue
import re
import sys
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services" / "voice"))
sys.path.insert(0, str(REPO))
from links import Link, make_link, seconds  # noqa: E402
from voice import Voice  # noqa: E402
from shared.protocol import COLORS, MOODS  # noqa: E402  eye moods: docs/MESSAGES.md

PAGE = Path(__file__).with_name("panel.html")
DAY = 86400
HHMM = re.compile(r"([01]?\d|2[0-3]):([0-5]\d)")
LIMITS = {"day_s": (60, DAY), "still_s": (60, 43200), "reask_s": (60, 43200), "walk_goal_s": (60, 7200)}
WALK_GRACE_S = 3 * 60     # clock seconds a walk may pause (traffic light, door) before it ends
SHORT_WALK_MIN_S = 60     # a walk shorter than the goal but at least this long still gets a gentle praise
NAMES = {"day_s": "1 day lasts", "still_s": "move after", "reask_s": "remind again after", "walk_goal_s": "walk goal",
         "wake_at": "wake-up", "sleep_at": "bedtime", "pill_at": "pill"}


class PanelLink(Link):
    """Charlie's sound plays in the panel: each clip is handed to the browser (GET /audio), which
    queues it without gaps. Here we wait the clip's real length, so 'talking' stays right."""

    def __init__(self):
        self.cond = threading.Condition()
        self.clips: list[tuple[int, bytes]] = []
        self.seq = 0
        self.stops = 0  # bumped on stop: the browser cuts what it has queued

    def play(self, pcm: bytes, stop: threading.Event) -> bool:
        with self.cond:
            self.seq += 1
            self.clips = (self.clips + [(self.seq, pcm)])[-200:]
            self.cond.notify_all()
        if stop.wait(seconds(pcm)):
            with self.cond:
                self.stops += 1
                self.cond.notify_all()
            return False
        return True

    def poll(self, after: int, wait_s: float = 1.0) -> dict:
        """Clips newer than `after` (waits up to wait_s for one, so the browser hears it at once)."""
        with self.cond:
            self.cond.wait_for(lambda: self.seq > after, timeout=wait_s)
            new = [{"seq": s, "pcm": base64.b64encode(p).decode()} for s, p in self.clips if s > after]
            return {"seq": self.seq, "stops": self.stops, "clips": new}


def tod_of(hhmm) -> int | None:
    """'09:00' -> seconds since midnight (None if not a valid time)."""
    m = HHMM.fullmatch(str(hhmm).strip())
    return int(m[1]) * 3600 + int(m[2]) * 60 if m else None


def clock(sec: float) -> str:
    sec = int(sec) % DAY
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}"


def dur(sec: float) -> str:
    """Clock durations: 30 s | 45 min | 2 h 05 min."""
    sec = max(0, int(round(sec)))
    if sec < 60:
        return f"{sec} s"
    if sec < 3600:
        return f"{round(sec / 60)} min"
    return f"{sec // 3600} h {sec % 3600 // 60:02d} min"


class Demo:
    def __init__(self, voice: Voice, fast: bool, chat: bool):
        shared = yaml.safe_load((REPO / "shared" / "config.yaml").read_text())
        c = shared.get("demo_clock") or {}
        p = shared.get(shared.get("profile", "demo"), {})
        self.settings = {
            "day_s": 120.0 if fast else float(c.get("day_s", 180)),   # real seconds per clock day
            "wake_at": clock(tod_of(c.get("wake_at", "08:00")) or 8 * 3600),
            "sleep_at": clock(tod_of(c.get("sleep_at", "22:00")) or 22 * 3600),
            "pill_at": clock(tod_of(c.get("pill_at", "09:00")) or 9 * 3600),
            "still_s": float(c.get("move_after_min", 45)) * 60,       # clock seconds
            "reask_s": float(c.get("remind_again_min", 20)) * 60,     # clock seconds
            "walk_goal_s": float(c.get("walk_goal_min", 15)) * 60,    # clock seconds of walking = a walk
        }
        self.backoff_s = float(c.get("walk_backoff_min", 120)) * 60  # after giving up: quiet this long
        self.max_reasks = int(p.get("max_reasks", 3))
        self.motion_g = float(p.get("motion_energy_moving", 0.05))
        self.voice, self.chat = voice, chat
        self.lock = threading.RLock()
        self.jobs: queue.Queue = queue.Queue()
        self.busy = False
        self.current = None             # label of the job playing now ("chat", "wake_up", ...)
        self.queued: list[str] = []     # labels waiting their turn
        self.log: list[str] = []
        self.reset()
        voice.emit = self.on_voice_event
        threading.Thread(target=self._worker, daemon=True).start()
        threading.Thread(target=self._ticker, daemon=True).start()

    # ---------- the clock ----------
    def _t(self, key: str) -> int:
        return tod_of(self.settings[key])

    def tod(self) -> float:
        return self.sim % DAY

    def day(self) -> int:
        return int(self.sim // DAY)

    def until(self, key: str) -> float:
        """Clock seconds until the next `key` time (wake_at, pill_at...)."""
        return (self._t(key) - self.tod()) % DAY

    def both(self, clock_s: float) -> str:
        """'45 min (6 s)': clock time, and the real wait when the clock runs fast."""
        return dur(clock_s) if self.realtime else f"{dur(clock_s)} ({dur(clock_s / self.speed)})"

    def _daytime(self, tod: float) -> bool:
        return self._t("wake_at") <= tod < self._t("sleep_at")

    def _jump(self, target: float):
        """Move the clock forward without counting the skipped time as sitting still."""
        delta = max(0.0, target - self.sim)
        self.sim += delta
        self.still_since += delta
        if self.next_check is not None:
            self.next_check += delta

    # ---------- state ----------
    def reset(self):
        with self.lock:
            s = self.settings
            self.speed = DAY / s["day_s"]
            self.realtime = s["day_s"] >= DAY
            if self.realtime:  # the real clock: what the product does at home
                n = datetime.now()
                self.sim = float(n.hour * 3600 + n.minute * 60 + n.second)
            else:              # demo: start a little before the wake-up call
                self.sim = float((self._t("wake_at") - 20 * 60) % DAY)
            tod = self.tod()
            self.awake = self._daytime(tod)
            self.wake_day = 0 if self.awake else -1               # day of the last wake-up call
            self.sleep_day = 0 if tod >= self._t("sleep_at") else -1
            self.pill_day = -1                                    # day the pill was taken or missed
            self.pill_taken_at = None
            self.awake_at = clock(tod) if self.awake else None
            self.task = None            # None | "walk" | "pill": the reminder in progress
            self.attempt = 0
            self.next_check = None      # clock time of the next reminder (set after one finishes)
            self.skip_pending = False   # "next step" pressed while Charlie was talking
            self.paused = False
            self.still_since = self.sim # clock time the user last moved
            self.walk_quiet_until = 0.0 # after a walk back-off: no walk reminder before this clock time
            self.moving = False         # last wearable reading (or the Start / Stop walking button)
            self.walk_open = False      # a walk in progress (may be briefly paused)
            self.walked = 0.0           # clock seconds walked in this walk, before the current stretch
            self.walk_seg = None        # clock time the current stretch of walking started
            self.walk_stop_at = None    # clock time the user stopped (the walk ends after WALK_GRACE_S)
            self.marks: list[dict] = []
            self.eyes = self._mood_eyes("calm" if self.awake else "sleepy")
            self.last_tick = time.monotonic()
            where = "Charlie is awake" if self.awake else f"Charlie sleeps until {s['wake_at']}"
            self.note(f"New day: the clock shows {clock(tod)}, {where}")

    def note(self, text: str):
        stamp = clock(self.sim) if hasattr(self, "sim") else "--:--"
        with self.lock:
            self.log = ([f"{stamp}  {text}"] + self.log)[:18]
        print(f"{time.strftime('%H:%M:%S')}  [{stamp}]  {text}", flush=True)

    def mark(self, kind: str, label: str):
        self.marks = (self.marks + [{"sim": self.sim, "t": self.tod(), "kind": kind, "label": label}])[-80:]

    def set_settings(self, new: dict):
        changed, restart = [], False
        with self.lock:
            s = self.settings
            times = {k: s[k] for k in ("wake_at", "sleep_at", "pill_at")}
            for key in times:
                t = tod_of(new.get(key, ""))
                if t is not None:
                    times[key] = clock(t)
            if tod_of(times["wake_at"]) >= tod_of(times["sleep_at"]):
                self.note("Settings ignored: the wake-up must be before bedtime")
            else:
                for key, v in times.items():
                    if v != s[key]:
                        s[key] = v
                        changed.append(f"{NAMES[key]} {v}")
            for key, (lo, hi) in LIMITS.items():
                if key not in new:
                    continue
                try:
                    v = min(hi, max(lo, float(new[key])))
                except (TypeError, ValueError):
                    continue
                if v == s[key]:
                    continue
                if key == "day_s":
                    restart = (v >= DAY) != self.realtime  # switching to / from the real clock
                    self.speed = DAY / v
                    changed.append("1 day lasts " + ("24 h (real time)" if v >= DAY else dur(v)))
                else:
                    changed.append(f"{NAMES[key]} {dur(v)}")
                s[key] = v
        if changed:
            self.note("Settings: " + ", ".join(changed))
        if restart:
            self._silence()
            self.reset()

    @staticmethod
    def _mood_eyes(name: str, pattern: str | None = None) -> dict:
        colour, mood_pattern, period = MOODS.get(name, (COLORS.get(name, name), "solid", None))
        return {"color": colour, "pattern": pattern or mood_pattern, "period_ms": period, "name": name}

    def on_voice_event(self, m: dict):
        t = m.get("type")
        if t == "voice.reacting" and m.get("eyes"):
            self.eyes = self._mood_eyes(m["eyes"].get("color", "calm"), m["eyes"].get("pattern"))
            lvl = f" level {m['level']}" if m.get("level") else ""
            self.note(f"Charlie reacts: {m['reaction']}{lvl}")
        elif t == "robot.eyes":
            self.eyes = {"color": m.get("left", COLORS["calm"]), "pattern": m.get("pattern", "solid"),
                         "period_ms": m.get("period_ms"), "name": m.get("mood", "chat")}
        elif t in ("voice.chat_started", "voice.chat_done"):
            self.note("Live conversation " + ("started" if t.endswith("started") else "ended"))

    def snapshot(self) -> dict:
        with self.lock:
            s, tod, day = self.settings, self.tod(), self.day()
            talking = self.busy or not self.jobs.empty()
            nxt = None if self.next_check is None else f"next reminder in {self.both(self.next_check - self.sim)}"
            reminder = lambda: f"reminder {self.attempt} of {self.max_reasks}" + (f", {nxt}" if nxt else "")
            wake_t, sleep_t, pill_t = self._t("wake_at"), self._t("sleep_at"), self._t("pill_at")
            # 0 · wake-up / bedtime
            if not self.awake:
                night = (wake_t - sleep_t) % DAY or DAY
                wake = {"state": "", "text": "Asleep",
                        "detail": f"wake-up call at {s['wake_at']}, in {self.both(self.until('wake_at'))}",
                        "progress": 1 - self.until("wake_at") / night}
            else:
                wake = {"state": "ok", "text": f"Awake since {self.awake_at}",
                        "detail": f"bedtime at {s['sleep_at']}, in {self.both(self.until('sleep_at'))}",
                        "progress": ((tod - wake_t) % DAY) / ((sleep_t - wake_t) % DAY or DAY)}
            # 1 · pill
            if self.task == "pill":
                pill = {"state": "due", "text": f"Due since {s['pill_at']}, not taken", "detail": reminder(),
                        "progress": 1}
            elif self.pill_day == day and self.pill_taken_at:
                pill = {"state": "ok", "text": f"Taken at {self.pill_taken_at}",
                        "detail": f"next dose tomorrow at {s['pill_at']}", "progress": 1}
            elif self.pill_day == day:
                pill = {"state": "", "text": "Missed today", "detail": f"next dose tomorrow at {s['pill_at']}",
                        "progress": 0}
            else:
                span = (pill_t - wake_t) % DAY or DAY
                pill = {"state": "waiting", "text": f"Next dose at {s['pill_at']}",
                        "detail": f"in {self.both(self.until('pill_at'))}",
                        "progress": max(0, min(1, ((tod - wake_t) % DAY) / span)) if self.awake else 0}
            # 2 · movement
            still = self.sim - self.still_since
            if not self.awake:
                move = {"state": "", "text": "Resting", "detail": "no movement reminders at night", "progress": 0}
            elif self.walk_open:
                goal, done = s["walk_goal_s"], self._walked()
                if self.moving:
                    detail = f"{self.both(goal - done)} to go, Charlie follows along"
                else:
                    detail = f"stopped: the walk ends in {self.both(WALK_GRACE_S - (self.sim - self.walk_stop_at))} unless you move again"
                move = {"state": "ok", "text": f"Walking {dur(done)} / {dur(goal)}", "detail": detail,
                        "progress": done / goal}
            elif self.task == "walk":
                move = {"state": "due", "text": f"Still for {dur(still)}", "detail": reminder(), "progress": 1}
            elif self.moving:
                move = {"state": "ok", "text": "Moving", "detail": "the still timer stays at 0", "progress": 0}
            else:
                left = max(s["still_s"] - still, self.walk_quiet_until - self.sim)
                detail = (f"Charlie backed off: next check at {clock(self.walk_quiet_until)}"
                          if self.walk_quiet_until > self.sim else
                          f"walk reminder in {self.both(left)}" if left > 0 else
                          "walk reminder waits for the pill" if self.task == "pill" else "walk reminder now")
                move = {"state": "waiting", "text": f"Still for {dur(still)}", "detail": detail,
                        "progress": min(1, still / s["still_s"])}
            labels = {"chat": "live conversation", "wake_up": "wake-up", "called": '"Charlie!"', "reward": "reward",
                      "encourage": "walk reminder", "pill": "pill reminder", "back off": "back off"}
            if self.paused:
                status = "Paused: press Resume to continue"
            elif self.current == "chat":
                status = "Live conversation (ends on \"bye\", silence or 90 s)"
            elif self.busy:
                status = "Charlie is talking (the clock waits)"
            elif not self.awake:
                status = "Charlie is asleep"
            elif self.task:
                status = "Reminding: " + ("take the pill" if self.task == "pill" else "move a little")
            else:
                status = "Awake, keeping an eye on things"
            if self.queued and not self.paused:
                status += "  ·  next: " + ", ".join(labels.get(q, q) for q in self.queued)
            dial = {"tod": tod, "day": day + 1, "time": clock(tod), "speed": self.speed, "realtime": self.realtime,
                    "running": not self.paused and (self.realtime or not talking),
                    "wake": wake_t, "sleep": sleep_t, "pill": pill_t,
                    "marks": [{"t": m["t"], "kind": m["kind"], "label": m["label"]}
                              for m in self.marks if self.sim - m["sim"] < DAY - 60]}
            return {"status": status, "eyes": self.eyes, "log": self.log, "busy": self.busy,
                    "paused": self.paused, "walking": self.moving, "settings": s, "clock": dial, "wake": wake, "pill": pill, "move": move}

    # ---------- audio jobs (one at a time, in order) ----------
    def do(self, label: str, fn, after=None):
        with self.lock:
            if label == self.current or label in self.queued:  # pressed twice: once is enough
                state = "playing now" if label == self.current else "waiting its turn"
                self.note(f"{label.replace('_', ' ')} is already {state}: press ignored")
                return
            self.queued.append(label)
        self.jobs.put((label, fn, after))

    def _clear_jobs(self):
        while not self.jobs.empty():
            self.jobs.get_nowait()
        self.queued.clear()

    def _worker(self):
        while True:
            label, fn, after = self.jobs.get()
            with self.lock:
                if label in self.queued:
                    self.queued.remove(label)
                self.current = label
            self.busy = True
            try:
                fn()
            except Exception as e:
                self.note(f"! {label} failed: {e}")
            finally:
                with self.lock:
                    if self.task != "walk":  # the still timer starts again once Charlie stops talking
                        self.still_since = max(self.still_since, self.sim)
                self.busy, self.current = False, None
                if after:
                    after()

    def _arm_check(self):
        with self.lock:
            if self.task:
                self.next_check = self.sim + (0 if self.skip_pending else self.settings["reask_s"])
            self.skip_pending = False

    def _remind(self):
        """Queue the reminder for the current task at the current attempt (lock held)."""
        task, attempt = self.task, self.attempt
        reaction = "encourage" if task == "walk" else "pill"
        if attempt > self.max_reasks:  # back off gently, then stop asking
            self.do("back off", lambda: self.voice.reactions.play(reaction, attempt=attempt))
            self.task, self.next_check = None, None
            if task == "pill":
                self.pill_day, self.still_since = self.day(), self.sim
                self.mark("pill_missed", "pill missed")
                self.note(f"Dose missed: Charlie backs off until tomorrow {self.settings['pill_at']}")
            else:
                self.still_since = self.sim
                self.walk_quiet_until = self.sim + self.backoff_s
                self.note(f"Charlie backs off: no walk reminder before {clock(self.walk_quiet_until)}")
        else:
            self.mark("nudge", f"{'pill' if task == 'pill' else 'walk'} reminder {attempt}")
            self.do(reaction, lambda: self.voice.reactions.play(reaction, attempt=attempt), after=self._arm_check)

    def _wake(self, source: str):
        """Wake-up call (lock held): yawn + good morning. Movement is counted from now."""
        first = not self.awake
        self.awake, self.wake_day = True, self.day()
        if first:
            self.awake_at = clock(self.tod())
            self.still_since = self.sim
            self.mark("wake", "wake-up")
        self.note(f"Wake-up call ({source})")
        self.do("wake_up", lambda: self.voice.reactions.play("wake_up"))

    def _walked(self) -> float:
        return self.walked + (self.sim - self.walk_seg if self.moving and self.walk_seg is not None else 0.0)

    def _end_walk(self, complete: bool):
        """Walk goal reached, or stopped too long (lock held). Any real walk gets a kind word."""
        walked = self._walked()
        if self.moving:
            self.walked, self.walk_seg = walked, self.sim
        self.walk_open, self.walk_stop_at = False, None
        self.still_since = self.sim
        if self.task == "walk":
            self.task, self.next_check = None, None
        if complete:
            self.mark("walk", f"walk done ({dur(walked)})")
            self.note(f"Walk done: {dur(walked)} with Charlie")
            self.do("reward", lambda: self.voice.reactions.play("reward", task="walk"))
        elif walked >= SHORT_WALK_MIN_S:
            self.mark("walk_short", f"short walk ({dur(walked)})")
            self.note(f"Short walk: {dur(walked)} of {dur(self.settings['walk_goal_s'])}, still a win")
            self.do("reward", lambda: self.voice.reactions.play("reward"))  # general praise, never guilt
        else:
            self.note(f"Walk too short to count ({dur(walked)})")

    def _ticker(self):
        while True:
            time.sleep(0.1)
            with self.lock:
                now = time.monotonic()
                dt, self.last_tick = now - self.last_tick, now
                talking = self.busy or not self.jobs.empty()
                if not self.paused and (self.realtime or not talking):
                    self.sim += dt * self.speed  # demo: the clock waits while Charlie talks
                if not self.paused and not talking:
                    self._step()

    def _step(self):
        """What the clock time asks for now (lock held, Charlie silent)."""
        s, tod, day = self.settings, self.tod(), self.day()
        wake_t, sleep_t, pill_t = self._t("wake_at"), self._t("sleep_at"), self._t("pill_at")
        if self.awake and tod >= sleep_t and self.sleep_day != day:
            if self.pill_day != day and tod >= pill_t:
                self.pill_day = day
                self.mark("pill_missed", "pill missed")
            self.task, self.next_check, self.awake, self.sleep_day = None, None, False, day
            self.eyes = self._mood_eyes("sleepy")
            self.mark("sleep", "bedtime")
            self.note(f"Bedtime: Charlie goes to sleep until {s['wake_at']}")
        elif not self.awake:
            if wake_t <= tod < sleep_t and self.wake_day != day:
                self._wake("clock")
        elif self.walk_open and self.moving and self._walked() >= s["walk_goal_s"]:
            self._end_walk(complete=True)
        elif self.walk_open and not self.moving and self.sim - self.walk_stop_at >= WALK_GRACE_S:
            self._end_walk(complete=False)
        elif self.task != "pill" and self.pill_day != day and tod >= pill_t:
            if self.task == "walk":
                self.note("Pill time: the walk reminder waits")
            self.note("Pill time, and the dock has not been opened today")
            self.task, self.attempt, self.next_check = "pill", 1, None
            self._remind()
        elif (self.task is None and not self.moving and self.sim - self.still_since >= s["still_s"]
              and self.sim >= self.walk_quiet_until):
            self.note(f"No movement for {dur(self.sim - self.still_since)}")
            self.task, self.attempt = "walk", 1
            self._remind()
        elif self.task and self.next_check is not None and self.sim >= self.next_check:
            self.next_check = None
            self.attempt += 1
            what = "Pill still not taken" if self.task == "pill" else "Still not moving"
            self.note(f"{what}: reminder {self.attempt}")
            self._remind()

    # ---------- real sensors (docs/MESSAGES.md) ----------
    def on_message(self, m: dict):
        t = m.get("type", "")
        if t == "wearable.motion":
            moving = bool(m.get("moving")) or float(m.get("energy") or 0) > self.motion_g
            with self.lock:
                if moving == self.moving:
                    if moving:
                        self.still_since = self.sim
                    return
            self.event("walk_start" if moving else "walk_stop", source="wearable")
        elif t == "robot.dock" and m.get("reach"):
            self.event("pill_taken", source="dock")
        elif t == "voice.wake" or (t == "robot.heard" and m.get("kind", "call") == "call"):
            self.event("charlie", source="mic")

    # ---------- what the buttons (and sensors) do ----------
    def event(self, name: str, source: str = "button"):
        with self.lock:
            day = self.day()
            if name == "moved":  # the Move button: start or stop walking
                name = "walk_stop" if self.moving else "walk_start"
            if name == "walk_start" and not self.moving:
                self.moving, self.walk_seg = True, self.sim
                self.still_since, self.walk_quiet_until = self.sim, 0.0
                if self.task == "walk":  # the reminder worked: stop asking
                    self.task, self.next_check = None, None
                if self.walk_open:
                    self.note(f"Walking again ({source})")
                else:
                    self.walk_open, self.walked = True, 0.0
                    self.mark("walk_start", "walk started")
                    self.note(f"Walk started ({source}): goal {dur(self.settings['walk_goal_s'])}")
                    self.do("bark", lambda: self.voice.sound("happy_bark"))  # Charlie comes along
            elif name == "walk_stop" and self.moving:
                self.moving = False
                self.still_since = self.sim
                if self.walk_open:
                    self.walked += self.sim - self.walk_seg
                    self.walk_seg, self.walk_stop_at = None, self.sim
                    self.note(f"Stopped walking ({source}) after {dur(self.walked)}")
            elif name == "pill_taken":
                early = self.task != "pill"
                self.note(f"Dock opened ({source}): pill taken" + (" before the reminder" if early else ""))
                if self.task == "pill":
                    self.task, self.next_check = None, None
                self.pill_day, self.pill_taken_at = day, clock(self.tod())
                self.still_since = max(self.still_since, self.sim)  # no walk nag right after the praise
                self.mark("pill", "pill taken")
                self.do("reward", lambda: self.voice.reactions.play("reward", task="pill"))
            elif name == "pill_due":
                if not self.awake:
                    self.note("Charlie is asleep: wake it up first (W)")
                    return
                self.pill_day, self.pill_taken_at = -1, None
                if self.tod() < self._t("pill_at"):
                    self._jump(day * DAY + self._t("pill_at"))
                else:
                    self._jump(self.sim)
                self.note("Pill time now (clock moved forward)")
            elif name == "charlie":
                self.note(f'Someone said "Charlie" ({source})')
                if self.chat:
                    from agent import chat
                    self.do("chat", lambda: chat(self.voice))
                else:
                    self.do("called", lambda: self.voice.reactions.play("called"))
            elif name == "wake_up":
                self._wake(source)
            elif name == "skip":
                if not self.awake:  # skip the night
                    w = self._t("wake_at")
                    self._jump(day * DAY + w if self.tod() < w else (day + 1) * DAY + w)
                    self.note("Skip: straight to the morning")
                elif self.task and self.next_check is not None:
                    self.next_check = self.sim
                    self.note("Skip: next reminder now")
                elif self.task:  # Charlie is still talking: apply as soon as it finishes
                    self.skip_pending = True
                    self.note("Skip: next reminder right after this one")
                else:
                    self.still_since = self.sim - self.settings["still_s"]
                    self.note("Skip: walk reminder now")
            elif name == "pause":
                if not self.paused:
                    self._silence()
                    if self.task:  # keep the reminder where it was; after Resume, wait one full interval
                        self.next_check = self.sim + self.settings["reask_s"]
                    self.skip_pending = False
                    self.paused = True
                    self.eyes = self._mood_eyes("calm" if self.awake else "sleepy")
                    self.note("Paused: Charlie stops, the clock stops")
                else:
                    self.paused = False
                    self.last_tick = time.monotonic()
                    self.note("Resumed")
            elif name in ("stop", "reset"):
                self._silence()
                if name == "stop":
                    self.note("Stop: sound cut")
                else:
                    self.reset()

    def _silence(self):
        """Drop what is waiting, cut what is playing, end a live conversation."""
        self._clear_jobs()
        self.voice.stop()
        try:
            from agent import end_chat
            end_chat()
        except Exception:
            pass


def serve(demo: Demo, port: int):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # keep the console for the demo log
            pass

        def _send(self, code, body: bytes, ctype: str = "application/json"):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self):
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n) or b"{}")

        def do_GET(self):
            if self.path == "/state":
                self._send(200, json.dumps(demo.snapshot()).encode())
            elif self.path.startswith("/audio"):
                link = demo.voice.link
                if not isinstance(link, PanelLink):
                    return self._send(200, b'{"panel": false}')
                after = int(parse_qs(urlparse(self.path).query).get("after", ["0"])[0])
                self._send(200, json.dumps({"panel": True, **link.poll(after)}).encode())
            else:
                self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")

        def do_POST(self):
            try:
                if self.path.startswith("/event/"):
                    demo.event(self.path.split("/event/", 1)[1])
                elif self.path == "/settings":
                    demo.set_settings(self._json())
                elif self.path == "/msg":
                    body = self._json()
                    for m in body if isinstance(body, list) else [body]:
                        demo.on_message(m)
                else:
                    return self._send(404, b"{}")
                self._send(200, b"{}")
            except (ValueError, TypeError, AttributeError) as e:
                self._send(400, json.dumps({"error": str(e)}).encode())

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    server.serve_forever()


def read_stdin(demo: Demo):
    """Team messages, one JSON object per line (e.g. piped from the gateway)."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            demo.on_message(json.loads(line))
        except (ValueError, TypeError, AttributeError):
            print(f"(ignored, not a JSON message: {line[:60]})", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--link", default="panel", help="panel (browser tab) | usb (robot) | laptop | print")
    ap.add_argument("--port", help="robot USB port (default: first board)")
    ap.add_argument("--volume", type=float, default=0.4)
    ap.add_argument("--fast", action="store_true", help="1 day = 2 minutes (default 3)")
    ap.add_argument("--no-chat", action="store_true", help='"Charlie" plays the called reaction, no live chat')
    ap.add_argument("--listen", action="store_true", help='also detect "Charlie" on the microphone')
    ap.add_argument("--stdin", action="store_true", help="read sensor messages (JSON lines) from stdin")
    ap.add_argument("--http", type=int, default=8765)
    args = ap.parse_args()

    voice = Voice(PanelLink() if args.link == "panel" else make_link(args.link, args.port, args.volume))
    demo = Demo(voice, args.fast, chat=not args.no_chat)
    if args.listen:
        from wake import WakeListener
        wl = WakeListener(lambda w, c: demo.event("charlie", source="mic"),
                          is_muted=lambda: voice.mic_muted() or demo.busy)
        threading.Thread(target=wl.run, daemon=True).start()
    if args.stdin:
        threading.Thread(target=read_stdin, args=(demo,), daemon=True).start()
    print(f"Demo panel: http://localhost:{args.http}   (Ctrl+C here to quit)", flush=True)
    try:
        serve(demo, args.http)
    except KeyboardInterrupt:
        pass
    finally:
        voice.link.close()


if __name__ == "__main__":
    main()
