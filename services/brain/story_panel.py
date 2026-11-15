"""Wiam's demo panel (tools/demo/panel.html) in Story mode: set up and run Charlie's story from the browser.
Owner: Reshma. Started by `run_story.py --panel`; open http://localhost:8766.

The story keeps its own timings in seconds (exactly as tested). The 24-hour dial only *shows* Charlie's day:
it starts at the wake-up time when the story starts and runs at the chosen speed (1 day = 3 min: 1 s = 8 min),
with every story event marked on the ring.
"""
from __future__ import annotations

import json
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from shared.protocol import MOODS  # noqa: E402

PAGE = REPO / "tools" / "demo" / "panel.html"
CONFIG = REPO / "shared" / "config.yaml"
DAY = 86400
ROBOT_EYES = {"wake": "sleepy", "idle": "calm", "search": "searching", "happy": "happy"}
SAYING = {"wake": "yawn + good morning", "called": "“You called? I’m here!”", "pleading": "pill reminder",
          "reward": "praise", "sad": "pill back-off (sad)"}
# story setting -> key in shared/config.yaml `story:`
SAVE_KEYS = {"x": "x_pill_after_s", "y": "y_idle_window_s", "repeat_s": "pill_repeat_s", "max_reasks": "max_reasks",
             "walk_s": "walk_s", "follow_window_s": "follow_window_s", "gap_s": "topic_gap_s",
             "motion_energy": "motion_energy_moving", "dock_near_mm": "dock_near_mm",
             "speed_slow": "speed_slow", "speed_fast": "speed_fast", "volume": "volume",
             "day_s": "panel_day_s", "start_at": "panel_start_at"}


def tod_of(hhmm: str) -> int | None:
    m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", str(hhmm or ""))
    return None if not m else (int(m.group(1)) % 24) * 3600 + int(m.group(2)) * 60


def hhmm(t: float) -> str:
    t = int(t) % DAY
    return f"{t // 3600:02d}:{t % 3600 // 60:02d}"


class StoryPanel:
    def __init__(self, story, charlie, runner_get: Callable[[], dict], runner_set: Callable[[dict], list],
                 day_s: float = 180, start_at: str = "08:00", sleep_at: str = "22:00"):
        self.story, self.charlie = story, charlie
        self.runner_get, self.runner_set = runner_get, runner_set
        self.day_s = float(day_s)
        self.start_at = start_at if tod_of(start_at) is not None else "08:00"
        self.clock_start = tod_of(self.start_at)   # the running clock's start (the setting applies on restart)
        self.sleep_tod = tod_of(sleep_at) or 22 * 3600
        self.lock = threading.Lock()
        self.lines: list[str] = []
        self.marks: list[dict] = []
        self.started = False
        self.t_start = story.clock()
        self.paused_total = 0.0
        self.paused_since: float | None = None
        log = story.log

        def both(m: str) -> None:              # terminal + panel log
            log(m)
            with self.lock:
                self.lines.insert(0, f"{hhmm(self.tod())}  {m}")
                del self.lines[80:]
        story.log = both
        story.on_mark = self._mark

    # ---------- the display clock ----------
    @property
    def speed(self) -> float:
        return DAY / self.day_s

    def _elapsed(self, at: float | None = None) -> float:
        now = self.story.clock() if at is None else at
        paused = self.paused_total + ((now - self.paused_since) if self.paused_since is not None else 0.0)
        return max(0.0, now - self.t_start - paused)

    def tod(self, at: float | None = None) -> float:
        return self.clock_start + self._elapsed(at) * self.speed

    def _when(self, kind: str) -> str:
        """Clock time of the last event of this kind, as it was when it happened."""
        with self.lock:
            t = next((m["t"] for m in reversed(self.marks) if m["kind"] == kind), None)
        return "–" if t is None else hhmm(t)

    def _mark(self, kind: str, label: str) -> None:
        with self.lock:
            self.marks.append({"t": self.tod() % DAY, "kind": kind, "label": label})
            del self.marks[:-60]

    # ---------- buttons ----------
    def event(self, name: str) -> None:
        s = self.story
        if name == "reset":
            with self.lock:
                self.lines, self.marks = [], []
                self.t_start, self.paused_total, self.paused_since = s.clock(), 0.0, None
                self.clock_start = tod_of(self.start_at)
                self.started = True
            s.restart()
        elif name == "pause":
            if s.paused:
                with self.lock:
                    if self.paused_since is not None:
                        self.paused_total += s.clock() - self.paused_since
                    self.paused_since = None
                s.resume()
            else:
                with self.lock:
                    self.paused_since = s.clock()
                s.pause()
        elif name == "charlie":
            s.log('Button: "Charlie!"')
            s.on_called()
        elif name == "pill_taken":
            s.log("Button: pill taken")
            s.on_pill_removed()
        elif name == "moved":
            s.log("Button: user moved")
            s.on_motion(max(1.0, s.motion_energy))
        elif name == "save":
            self.save()
        else:
            s.log(f"(button {name} is not used in Story mode)")

    # ---------- settings ----------
    def settings(self) -> dict:
        return {**self.story.settings(), **self.runner_get(), "day_s": self.day_s, "start_at": self.start_at}

    def set_settings(self, new: dict) -> None:
        self.story.set_settings(new)
        changed = self.runner_set(new)
        if "day_s" in new:
            try:
                v = min(DAY, max(30.0, float(new["day_s"])))
                if v != self.day_s:
                    with self.lock:                  # keep the hand where it is, change only its speed
                        tod_now = self.tod()
                        self.day_s = v
                        self.t_start = self.story.clock() - (tod_now - self.clock_start) / self.speed \
                            - self.paused_total - ((self.story.clock() - self.paused_since)
                                                   if self.paused_since is not None else 0.0)
                    changed.append(f"1 day lasts {v:g} s")
            except (TypeError, ValueError):
                pass
        if tod_of(new.get("start_at", "")) is not None and new["start_at"] != self.start_at:
            self.start_at = hhmm(tod_of(new["start_at"]))
            changed.append(f"story starts at {self.start_at} (from the next restart)")
        if changed:
            self.story.log("Settings: " + ", ".join(changed))

    def save(self) -> None:
        """Write the current settings into shared/config.yaml `story:` (comments kept)."""
        values = self.settings()
        text = CONFIG.read_text(encoding="utf-8")
        nl = "\r\n" if "\r\n" in text else "\n"
        lines = text.split(nl)
        try:
            start = next(i for i, l in enumerate(lines) if re.match(r"^story:\s*$", l))
        except StopIteration:
            self.story.log("! Save failed: no `story:` section in shared/config.yaml")
            return
        end = start + 1
        while end < len(lines) and (lines[end].startswith("  ") or not lines[end].strip()):
            end += 1
        while end > start + 1 and not lines[end - 1].strip():
            end -= 1
        done = set()
        for i in range(start + 1, end):
            m = re.match(r"^(  )(\w+)(:\s*)([^#]*?)(\s*#.*)?$", lines[i])
            if not m:
                continue
            for key, cfg_key in SAVE_KEYS.items():
                if m.group(2) == cfg_key and key in values:
                    v = values[key]
                    val = f'"{v}"' if isinstance(v, str) else (f"{v:g}" if isinstance(v, float) else str(v).lower())
                    pad = max(1, len(m.group(4)) + len(m.group(3)) - len(val) - 1) if m.group(5) else 0
                    lines[i] = f"  {cfg_key}: {val}" + (" " * pad + m.group(5).lstrip() if m.group(5) else "")
                    done.add(key)
        extra = []
        for key, cfg_key in SAVE_KEYS.items():
            if key in values and key not in done:
                v = values[key]
                val = f'"{v}"' if isinstance(v, str) else (f"{v:g}" if isinstance(v, float) else str(v).lower())
                extra.append(f"  {cfg_key}: {val}")
        lines[end:end] = extra
        CONFIG.write_text(nl.join(lines), encoding="utf-8", newline="")
        self.story.log("Saved as default in shared/config.yaml (story:)")

    # ---------- what the page shows ----------
    def _eyes(self) -> dict:
        playing = self.charlie.now_playing
        if playing:
            name = playing["mood"]
        else:
            name = ROBOT_EYES.get(self.story.robot_behavior or "", "calm")
        colour, pattern, period = MOODS.get(name, MOODS["calm"])
        return {"color": colour, "pattern": pattern, "period_ms": period, "name": name}

    def snapshot(self) -> dict:
        s, now = self.story, self.story.clock()
        playing = self.charlie.now_playing
        left = lambda t: max(0.0, t - now)
        with s.lock:
            phase, topic, pill = s.phase, s.topic, s.pill
            # status line
            if not self.started:
                status = "Press “Start the story”"
            elif s.paused:
                status = "Paused: press Resume to continue"
            elif playing:
                e = playing["emotion"]
                if e == "encouraging":
                    say = "back-off (sad)" if playing["mood"] == "sad" else "“Follow me!”"
                else:
                    say = SAYING.get(e, e)
                status = f"Charlie is talking: {say}"
            elif phase in ("new", "starting"):
                status = "Charlie is waking up"
            elif phase in ("wait_call", "calling"):
                status = "Waiting for someone to say “Charlie!”"
            elif s.walking:
                status = "Charlie walks ahead: follow it!"
            elif s.following:
                status = f"Walk time: {left(s.follow_until):.0f} s left to move"
            elif topic == "pill":
                status = "Asking about the pill"
            elif now < s.quiet_until:
                status = f"Break: {left(s.quiet_until):.0f} s before the next ask"
            else:
                status = "Keeping an eye on things"
            # 0 · Charlie
            if phase in ("new", "starting"):
                wake = {"state": "", "text": "Waking up", "detail": "sleepy eyes, yawn, good morning", "progress": 0.3}
            elif phase in ("wait_call", "calling"):
                wake = {"state": "due", "text": "Waiting for “Charlie!”",
                        "detail": "say Charlie near the robot, or press the button", "progress": 0.6}
            else:
                at = self._when("call")
                wake = {"state": "ok", "text": f"Called at {at}", "detail": "the timers run from the greeting",
                        "progress": 1}
            # 1 · pill
            dock = "dock sensor: " + ("–" if s.last_dock_mm is None else
                                      f"{s.last_dock_mm} mm ({'pill on it' if s.last_dock_mm < s.dock_near_mm else 'empty'})")
            if pill == "done":
                pill_card = {"state": "ok", "text": f"Taken at {self._when('pill')}",
                             "detail": dock, "progress": 1}
            elif pill == "gave_up":
                pill_card = {"state": "", "text": "Not taken (sad)", "detail": dock, "progress": 0}
            elif pill == "asking":
                nxt = "" if s.pill_next == float("inf") else f", next ask in {left(s.pill_next):.0f} s"
                pill_card = {"state": "due", "text": f"Ask {s.pill_attempt} of {s.max_reasks}",
                             "detail": f"take the pill off the dock{nxt} · {dock}", "progress": 1}
            elif phase == "run":
                due = s.t0 + s.x
                if now < due:
                    pill_card = {"state": "waiting", "text": f"Pill ask in {left(due):.0f} s", "detail": dock,
                                 "progress": max(0.0, min(1.0, (now - s.t0) / s.x)) if s.x else 1}
                else:
                    why = "the walk" if topic == "move" else "the break"
                    pill_card = {"state": "waiting", "text": "Due: waits for " + why, "detail": dock, "progress": 1}
            else:
                pill_card = {"state": "", "text": "Starts after “Charlie!”",
                             "detail": f"asked {s.x:g} s after the greeting · {dock}", "progress": 0}
            # 2 · movement
            wear = "wearable: " + ("–" if s.last_energy is None else
                                   f"{s.last_energy:.2f} (moving at ≥ {s.motion_energy:g})")
            moving = now < s.user_moving_until
            if s.following:
                total = s.follow_window_s or 1
                move = {"state": "ok" if s.moved_in_window else "due",
                        "text": f"Walk time: {left(s.follow_until):.0f} s left",
                        "detail": ("you moved ✓" if s.moved_in_window else "not moved yet") + f" · {wear}",
                        "progress": 1 - left(s.follow_until) / total}
            elif phase != "run":
                move = {"state": "", "text": "Starts after “Charlie!”", "detail": wear, "progress": 0}
            elif s.move_quiet:
                move = {"state": "", "text": "Charlie backed off", "detail": f"it waits until you move · {wear}",
                        "progress": 0}
            elif moving:
                move = {"state": "ok", "text": "Moving", "detail": wear, "progress": 0}
            elif topic == "pill":
                move = {"state": "waiting", "text": "Waits for the pill", "detail": wear, "progress": 0}
            else:
                still = 0.0 if s.last_move == float("inf") else now - s.last_move
                ask_in = max(s.y - still, s.quiet_until - now)
                last = {"praise": "last walk: praised", "sad": "last walk: no movement (sad)"}.get(s.walk_result, "")
                move = {"state": "waiting", "text": f"Still for {still:.0f} s",
                        "detail": (f"“Follow me” in {ask_in:.0f} s" if ask_in > 0 else "“Follow me” now")
                                  + (f" · {last}" if last else "") + f" · {wear}",
                        "progress": min(1.0, still / s.y) if s.y else 1}
            pill_tod = (self.tod() + (s.t0 + s.x - now) * self.speed) if phase == "run" else self.clock_start
            walking = s.walking
        elapsed_tod = self.tod()
        with self.lock:
            clock = {"tod": elapsed_tod % DAY, "day": 1 + int(elapsed_tod // DAY), "time": hhmm(elapsed_tod),
                     "speed": self.speed, "realtime": self.day_s >= DAY,
                     "running": self.started and not s.paused,
                     "wake": self.clock_start % DAY, "sleep": self.sleep_tod, "pill": pill_tod % DAY,
                     "marks": list(self.marks)}
            log = list(self.lines)
        st = self.settings()
        legacy = {"day_s": self.day_s, "wake_at": self.start_at, "sleep_at": hhmm(self.sleep_tod),
                  "pill_at": hhmm(pill_tod), "still_s": s.y * self.speed, "reask_s": s.repeat_s * self.speed,
                  "walk_goal_s": s.follow_window_s * self.speed}
        return {"mode": "story", "started": self.started, "status": status, "eyes": self._eyes(), "log": log,
                "busy": bool(playing), "paused": s.paused, "walking": walking, "settings": legacy,
                "story_settings": st, "clock": clock, "wake": wake, "pill": pill_card, "move": move}


def serve(panel: StoryPanel, port: int = 8766) -> None:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
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
                self._send(200, json.dumps(panel.snapshot()).encode())
            elif self.path.startswith("/audio"):
                self._send(200, b'{"panel": false}')        # Charlie's voice plays on the robot speaker
            else:
                self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")

        def do_POST(self):
            try:
                if self.path.startswith("/event/"):
                    panel.event(self.path.split("/event/", 1)[1])
                elif self.path == "/settings":
                    panel.set_settings(self._json())
                else:
                    return self._send(404, b"{}")
                self._send(200, b"{}")
            except (ValueError, TypeError, AttributeError) as e:
                self._send(400, json.dumps({"error": str(e)}).encode())

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    server.serve_forever()
