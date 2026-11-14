#!/usr/bin/env python3
"""Charlie demo runner: the whole 3-minute demo with the real voice, no brain or sensors needed.

    python tools/demo/run_demo.py                 # robot speaker over USB
    python tools/demo/run_demo.py --link laptop   # laptop speakers
    python tools/demo/run_demo.py --fast          # short timers, for rehearsing
    python tools/demo/run_demo.py --listen        # also hear "Charlie" on the mic

Then open http://localhost:8765 : buttons stand in for the sensors (wearable moving, pill dock,
"Charlie!"), the page shows Charlie's state and eye colour. Keyboard works on the page too.

Flow (timers from shared/config.yaml, demo profile):
  sitting still for still_threshold_s -> `encourage` (1, 2, 3, then back off), every walk_check_s
  "User walks" while prompting       -> `reward` (walk)
  "Pill time"                        -> `pill` (1, 2, 3, then back off), "Pill taken" -> `reward` (pill)
  "Charlie!"                          -> bark + live conversation (or the `called` reaction)
"""
from __future__ import annotations

import argparse
import json
import queue
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services" / "voice"))
from links import make_link  # noqa: E402
from voice import Voice  # noqa: E402

PAGE = Path(__file__).with_name("panel.html")
from shared.protocol import COLORS, MOODS  # noqa: E402  eye moods: docs/MESSAGES.md


class Demo:
    def __init__(self, voice: Voice, fast: bool, chat: bool):
        shared = yaml.safe_load((REPO / "shared" / "config.yaml").read_text())
        p = shared.get(shared.get("profile", "demo"), {})
        self.still_s = 10 if fast else float(p.get("still_threshold_s", 60))
        self.check_s = 8 if fast else float(p.get("walk_check_s", 20))
        self.max_reasks = int(p.get("max_reasks", 3))
        self.voice, self.chat = voice, chat
        self.lock = threading.RLock()
        self.jobs: queue.Queue = queue.Queue()
        self.busy = False
        self.log: list[str] = []
        self.eyes = {"color": COLORS["calm"], "pattern": MOODS["calm"][1], "name": "calm"}
        self.reset()
        voice.emit = self.on_voice_event
        threading.Thread(target=self._worker, daemon=True).start()
        threading.Thread(target=self._ticker, daemon=True).start()

    # ---------- state ----------
    def reset(self):
        with self.lock:
            self.task = None          # None | "walk" | "pill"
            self.attempt = 0
            self.still_since = time.monotonic()
            self.next_check = None    # when to re-ask (set after a reaction finishes)
            self.skip_pending = False # "next step" pressed while Charlie was talking
            self.note("Reset: Charlie is idle, the user is sitting.")

    def note(self, text: str):
        stamp = time.strftime("%H:%M:%S")
        with self.lock:
            self.log = ([f"{stamp}  {text}"] + self.log)[:14]
        print(f"{stamp}  {text}", flush=True)

    def on_voice_event(self, m: dict):
        t = m.get("type")
        if t == "voice.reacting" and m.get("eyes"):
            name = m["eyes"].get("color", "calm")
            self.eyes = {"color": COLORS.get(name, name), "pattern": m["eyes"].get("pattern", "solid"), "name": name}
            lvl = f" level {m['level']}" if m.get("level") else ""
            self.note(f"Charlie reacts: {m['reaction']}{lvl}")
        elif t == "robot.eyes":
            self.eyes = {"color": m.get("left", COLORS["calm"]), "pattern": m.get("pattern", "solid"), "name": "chat"}
        elif t in ("voice.chat_started", "voice.chat_done"):
            self.note("Live conversation " + ("started" if t.endswith("started") else "ended"))

    def snapshot(self) -> dict:
        now = time.monotonic()
        with self.lock:
            if self.task:
                left = None if self.next_check is None else max(0, self.next_check - now)
                status = f"Asking ({self.task}), reminder {self.attempt}"
                timer = "" if left is None else f"next reminder in {left:.0f} s"
            else:
                status = "Idle, user sitting"
                timer = f"walk prompt in {max(0, self.still_s - (now - self.still_since)):.0f} s"
            return {"status": "Charlie is talking..." if self.busy else status, "timer": timer,
                    "eyes": self.eyes, "log": self.log, "busy": self.busy}

    # ---------- audio jobs (one at a time, in order) ----------
    def do(self, label: str, fn, after=None):
        self.jobs.put((label, fn, after))

    def _worker(self):
        while True:
            label, fn, after = self.jobs.get()
            self.busy = True
            try:
                fn()
            except Exception as e:
                self.note(f"! {label} failed: {e}")
            finally:
                self.busy = False
                if after:
                    after()

    def _arm_check(self):
        with self.lock:
            if self.task:
                self.next_check = time.monotonic() + (0 if self.skip_pending else self.check_s)
            self.skip_pending = False

    def _remind(self):
        """Play the reminder for the current task at the current attempt."""
        task, attempt = self.task, self.attempt
        reaction = "encourage" if task == "walk" else "pill"
        if attempt > self.max_reasks:  # back off gently, then stop asking
            self.do("give up", lambda: self.voice.reactions.play(reaction, attempt=attempt))
            with self.lock:
                self.task, self.next_check, self.still_since = None, None, time.monotonic()
            self.note(f"Backing off from {task}: no more reminders for now")
        else:
            self.do(reaction, lambda: self.voice.reactions.play(reaction, attempt=attempt), after=self._arm_check)

    def _ticker(self):
        while True:
            time.sleep(0.2)
            if self.busy or not self.jobs.empty():
                continue  # never interrupt Charlie; timers wait while it talks
            now = time.monotonic()
            with self.lock:
                if self.task is None and now - self.still_since >= self.still_s:
                    self.note(f"User sat still for {self.still_s:.0f} s")
                    self.task, self.attempt = "walk", 1
                    self._remind()
                elif self.task and self.next_check is not None and now >= self.next_check:
                    self.next_check = None
                    self.attempt += 1
                    self.note(f"No reaction from the user: reminder {self.attempt}")
                    self._remind()

    # ---------- what the buttons do ----------
    def event(self, name: str):
        with self.lock:
            if name == "moved":
                if self.task == "walk":
                    self.note("Wearable: user is walking")
                    self.task, self.next_check = None, None
                    self.do("reward", lambda: self.voice.reactions.play("reward", task="walk"))
                else:
                    self.note("Wearable: user moved (still timer restarts)")
                self.still_since = time.monotonic()
            elif name == "pill_due":
                self.note("Pill time (demo-scaled: it's late now)")
                self.task, self.attempt, self.next_check = "pill", 1, None
                self._remind()
            elif name == "pill_taken":
                self.note("Pill dock: hand reached in, pill taken")
                was_pill = self.task == "pill"
                self.task, self.next_check, self.still_since = None, None, time.monotonic()
                self.do("reward", lambda: self.voice.reactions.play("reward", task="pill" if was_pill else None))
            elif name == "charlie":
                self.note('Someone said "Charlie"')
                if self.chat:
                    from agent import chat
                    self.do("chat", lambda: chat(self.voice))
                else:
                    self.do("called", lambda: self.voice.reactions.play("called"))
            elif name == "wake_up":
                self.do("wake_up", lambda: self.voice.reactions.play("wake_up"))
            elif name == "skip":
                if self.task and self.next_check is not None:
                    self.next_check = time.monotonic()
                elif self.task:  # Charlie is still talking: apply as soon as it finishes
                    self.skip_pending = True
                else:
                    self.still_since = time.monotonic() - self.still_s
                self.note("Skip: next step now")
            elif name == "stop":
                while not self.jobs.empty():
                    self.jobs.get_nowait()
                self.voice.stop()
                self.note("Stop: sound cut")
            elif name == "reset":
                while not self.jobs.empty():
                    self.jobs.get_nowait()
                self.voice.stop()
                self.eyes = {"color": COLORS["calm"], "pattern": MOODS["calm"][1], "name": "calm"}
                self.reset()


def serve(demo: Demo, port: int):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # keep the console for the demo log
            pass

        def _send(self, code, body: bytes, ctype: str):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/state":
                self._send(200, json.dumps(demo.snapshot()).encode(), "application/json")
            else:
                self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")

        def do_POST(self):
            if self.path.startswith("/event/"):
                demo.event(self.path.split("/event/", 1)[1])
                self._send(200, b"{}", "application/json")
            else:
                self._send(404, b"{}", "application/json")

    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--link", default="usb", help="usb (robot) | laptop | print")
    ap.add_argument("--port", help="robot USB port (default: first board)")
    ap.add_argument("--volume", type=float, default=0.4)
    ap.add_argument("--fast", action="store_true", help="short timers (10 s still, 8 s between reminders)")
    ap.add_argument("--no-chat", action="store_true", help='"Charlie" plays the called reaction, no live chat')
    ap.add_argument("--listen", action="store_true", help='also detect "Charlie" on the microphone')
    ap.add_argument("--http", type=int, default=8765)
    args = ap.parse_args()

    voice = Voice(make_link(args.link, args.port, args.volume))
    demo = Demo(voice, args.fast, chat=not args.no_chat)
    if args.listen:
        from wake import WakeListener
        wl = WakeListener(lambda w, c: demo.event("charlie"), is_muted=lambda: voice.mic_muted() or demo.busy)
        threading.Thread(target=wl.run, daemon=True).start()
    print(f"Demo panel: http://localhost:{args.http}   (Ctrl+C to quit)", flush=True)
    try:
        serve(demo, args.http)
    except KeyboardInterrupt:
        pass
    finally:
        voice.link.close()


if __name__ == "__main__":
    main()
