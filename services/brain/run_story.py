"""Run Charlie's story on the real boards. Owner: Reshma.

    python services/brain/run_story.py --x 10 --y 7 --robot-port COM8 --wearable-port COM9

  x  seconds after the "Charlie" greeting when Charlie asks for the pill (asks again every 5 s)
  y  movement window in seconds: no movement from the wearable for y s -> Charlie asks you to move,
     then the robot DRIVES for --walk-s seconds with IMU/RSSI direction control (--no-drive = wheels off)

Boards: robot = firmware/robot_main (eyes, mic, speaker, dock distance sensor on port 7)
        wearable = firmware/wearable (IMU). `atech ports` lists the ports.
--listen: hear "Charlie" on the laptop mic too (offline).
Keyboard stand-ins while rehearsing (type a key + Enter):  c = "Charlie"   p = pill taken   m = user moved
Story logic and the table of what happens when: services/brain/story.py
"""
from __future__ import annotations

import argparse
import sys
import threading
import time
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "services" / "brain"))
from express import Charlie  # noqa: E402  (eyes + Wiam's voice on one USB cable)
from story import Story  # noqa: E402
from services.gateway.story_inputs import StoryInputs
from services.gateway.telemetry import RunTelemetry
from services.position.rssi import RssiPosition
from services.brain.walking import RssiWalk


class WalkingCharlie(Charlie):
    """Charlie + the wheels. The robot firmware (robot_main) stops its motors if it hears nothing from the
    laptop for 2 s, so a ping goes out every half second. Speeds are 0..255 before the motors' minimum PWM."""

    def __init__(self, board, volume: float, slow: int, fast: int, navigation=None):
        super().__init__(board, volume=volume)
        self.slow, self.fast = slow, fast
        self.navigation = navigation
        self._closed = threading.Event()
        self._driving = False
        self._walk_held = False
        self._pill_speed = 0
        self._stop_pending = False
        self.telemetry = lambda kind, value: None
        self._nav_last_report = 0.0
        self._nav_last_phase = None
        threading.Thread(target=self._ping, daemon=True).start()

    def _ping(self) -> None:
        while not self._closed.wait(0.5):
            try:
                self._robot("robot_ping", "")
            except Exception:
                pass

    def walk(self, fast: bool = False) -> None:
        # Story calls this only after the invitation finishes. No second still
        # timer: story.y already owns the idle/reminder interval.
        if not self._driving:
            self._robot("robot_express", "encouraging")
            self._driving = True
        if self.navigation:
            with self.lock:
                self.navigation.start()
        else:
            self._robot("robot_speed", str(self.fast if fast else self.slow))
            self._robot("robot_mode", "walk")

    def drive_tick(self) -> None:
        with self.lock:
            if self._stop_pending:
                self.board.call("robot_mode", "stop", timeout=1)
                self._stop_pending = False
                return
            if self._pill_speed:
                self.board.call("robot_drive", f"{self._pill_speed},{self._pill_speed}", timeout=1)
                return
            if not self.navigation or self._walk_held:
                return
            if not self._driving:
                return
            speed = self.navigation.tick()
            # Existing robot_main remains sole hardware owner, including its
            # obstacle clamp, motor mapping and two-second communication watchdog.
            self.board.call("robot_drive", f"{speed},{speed}", timeout=1)
            snapshot = self.navigation.snapshot()
            marker = (snapshot["phase"], snapshot["blocked"])
            now = time.monotonic()
            if marker != self._nav_last_phase or now - self._nav_last_report >= 2:
                def dbm(value):
                    return "unknown" if value is None else f"{value:.2f}"
                print(f"NAV phase={snapshot['phase']} speed={speed} "
                      f"RSSI={dbm(snapshot['rssi_dbm'])} initial={dbm(snapshot['initial_rssi_dbm'])} "
                      f"return_at<={dbm(snapshot['return_below_dbm'])} "
                      f"close_at>={snapshot['close_rssi_dbm']:g} "
                      f"blocked={snapshot['blocked'] or 'none'}", flush=True)
                self._nav_last_phase, self._nav_last_report = marker, now
                self.telemetry("navigation", snapshot)

    def walk_stop(self) -> None:
        with self.lock:
            if self.navigation:
                self.navigation.stop()
            self._walk_held = False
            self._stop_pending = True
            self.board.call("robot_mode", "stop")
            self._stop_pending = False
            was_driving, self._driving = self._driving, False
            if was_driving:
                self.board.call("robot_express", "done")

    def pill_drive(self, direction: int) -> None:
        with self.lock:
            self._pill_speed = 0
            speed = self.fast if direction > 0 else -self.fast
            self.board.call("robot_drive", f"{speed},{speed}", timeout=1)
            self._pill_speed = speed

    def pill_stop(self) -> None:
        with self.lock:
            self._pill_speed = 0
            self._stop_pending = True
            self.board.call("robot_mode", "stop", timeout=1)
            self._stop_pending = False

    def walk_needs_encouragement(self) -> bool:
        return bool(self.navigation and self.navigation.phase == "encourage")

    def walk_hold(self) -> None:
        with self.lock:
            self._walk_held = True
            self._stop_pending = True
            self.board.call("robot_mode", "stop", timeout=1)
            self._stop_pending = False

    def walk_resume(self) -> None:
        with self.lock:
            if self.navigation:
                self.navigation.resume_after_encouragement()
            self._walk_held = False

    def close(self) -> None:
        self._closed.set()
        self._pill_speed = 0
        self.walk_stop()


def load_defaults() -> dict:
    cfg = yaml.safe_load((REPO / "shared" / "config.yaml").read_text())
    return {**cfg.get(cfg.get("profile", "demo"), {}), **cfg.get("story", {}),
            "walking": cfg.get("walking", {}), "dock": cfg.get("dock", {})}


def _keep_listening(name: str, story: Story, listen) -> None:
    """Run a listener forever: an error (unplugged cable, odd message) is logged and listening starts again."""
    while True:
        try:
            listen()
        except Exception as e:
            story.log(f"! {name} listener: {e} (trying again)")
            time.sleep(1.0)


def robot_events(board, story: Story, inputs: StoryInputs) -> None:
    def listen():
        for event in board.events():
            inputs.robot(event)
    _keep_listening("robot", story, listen)


def wearable_events(board, story: Story, inputs: StoryInputs) -> None:
    def listen():
        for event in board.events():
            inputs.wearable(event)
    _keep_listening("wearable", story, listen)


def keyboard(story: Story) -> None:
    keys = {"c": story.on_called, "p": story.on_pill_removed, "m": lambda: story.on_motion(1.0)}
    for line in sys.stdin:
        fn = keys.get(line.strip().lower()[:1])
        if fn:
            fn()


def main() -> None:
    d = load_defaults()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--x", type=float, default=d.get("x_pill_after_s", 10), help="seconds until the pill request")
    ap.add_argument("--y", type=float, default=d.get("y_idle_window_s", 7), help="idle window for movement, seconds")
    ap.add_argument("--repeat", type=float, default=d.get("pill_repeat_s", 5), help="seconds between pill requests")
    ap.add_argument("--max-reasks", type=int, default=d.get("max_reasks", 3))
    ap.add_argument("--walk-s", type=float, default=d.get("walk_s", 30), help="how long the robot drives after 'Follow me'")
    ap.add_argument("--gap", type=float, default=d.get("topic_gap_s", 8),
                    help="break in seconds between a pill episode and a walk ask (and the other way round)")
    ap.add_argument("--follow", type=float, default=d.get("follow_window_s", 30),
                    help="walk time: seconds after 'Follow me' for the user to move; no movement at all -> sad")
    ap.add_argument("--slow", type=int, default=d.get("speed_slow", 60), help="still speed in legacy-drive mode only (0-255)")
    ap.add_argument("--fast", type=int, default=d.get("speed_fast", 255), help="common PWM in RSSI mode; moving speed in legacy mode (0-255)")
    ap.add_argument("--legacy-drive", action="store_true", help="use the previous slow/fast walk mode without BLE control")
    ap.add_argument("--no-drive", action="store_true", help="never move the wheels (speech and eyes only)")
    ap.add_argument("--robot-port", help="robot USB port, e.g. COM8 (default: first board found)")
    ap.add_argument("--wearable-port", help="wearable USB port; leave out to run without the wearable")
    ap.add_argument("--volume", type=float, default=d.get("volume", 0.1))
    ap.add_argument("--listen", action="store_true",
                    help='also hear "Charlie" on the laptop microphone (offline, Vosk); muted while Charlie speaks')
    ap.add_argument("--mic", help="laptop microphone device name/number for --listen (default: system)")
    ap.add_argument("--panel", action="store_true",
                    help="set up and run the story from Wiam's demo panel in the browser (Story mode)")
    ap.add_argument("--panel-port", type=int, default=8766,
                    help="panel web page port (default 8766; Wiam's own day demo uses 8765)")
    args = ap.parse_args()
    if args.robot_port and args.robot_port == args.wearable_port:
        ap.error("robot and wearable must use different serial ports")

    from atech import Board
    robot = Board.connect(port=args.robot_port) if args.robot_port else Board.connect()
    wearable = None
    charlie = None
    telemetry = None
    try:
        telemetry = RunTelemetry(REPO / "logs")
        print(f"Telemetry log: {telemetry.path}", flush=True)
        telemetry.record("settings", {"walk_s": args.walk_s, "follow_s": args.follow,
                                      "robot_port": args.robot_port, "wearable_port": args.wearable_port,
                                      "no_drive": args.no_drive, "walking": d["walking"]})
        wearable = Board.connect(port=args.wearable_port) if args.wearable_port else None
        if wearable is None:
            print("No wearable: RSSI walking stays stopped; 'm' only rehearses story reactions.", flush=True)
        wc = d["walking"]
        position = RssiPosition(close_dbm=wc.get("close_rssi_dbm", -80),
                                power_drop=wc.get("return_power_drop", 0.20),
                                stale_s=wc.get("rssi_stale_s", 3))
        navigation = RssiWalk(position, pwm=args.fast,
                              motion_stale_s=wc.get("motion_stale_s", 3),
                              reversal_s=wc.get("reversal_pause_s", 0.2))
        charlie = WalkingCharlie(robot, args.volume, args.slow, args.fast,
                                  navigation=None if args.legacy_drive else navigation)
        charlie.telemetry = telemetry.record
        for key, default in (("near_mm", d.get("dock_near_mm", 10)), ("cover_pct", 30), ("open_pct", 0), ("hold_ms", 100)):
            action = {"near_mm": "dock_near", "cover_pct": "dock_cover", "open_pct": "dock_open", "hold_ms": "dock_hold"}[key]
            charlie._robot(action, str(default if key == "near_mm" else d["dock"].get(key, default)))
        print("Firmware: robot=firmware/robot_main; wearable=firmware/wearable; standalone bridge is not needed.", flush=True)
        drive = {"on": not args.no_drive, "volume": args.volume}
        mics = {"mic_robot": True, "mic_laptop": bool(args.listen)}   # which mic may start a "Charlie" call
        dock_near = {"mm": d.get("dock_near_mm", 10)}
        real_walk, real_stop, real_pill_drive = charlie.walk, charlie.walk_stop, charlie.pill_drive

        def walk(fast: bool = False) -> None:            # wheels can be switched off (--no-drive / panel)
            if drive["on"]:
                real_walk(fast)
        charlie.walk = walk

        def pill_drive(direction: int) -> None:
            if drive["on"]:
                real_pill_drive(direction)
        charlie.pill_drive = pill_drive

        def runner_get() -> dict:
            return {"speed_slow": charlie.slow, "speed_fast": charlie.fast, "drive": drive["on"], **mics,
                    "mic_laptop_available": bool(args.listen),
                    "volume": drive["volume"], "navigation": navigation.snapshot()}

        def runner_set(new: dict) -> list:
            changed = []
            for key, attr in (("speed_slow", "slow"), ("speed_fast", "fast")):
                if key in new:
                    try:
                        v = max(0, min(255, int(float(new[key]))))
                    except (TypeError, ValueError):
                        continue
                    if v != getattr(charlie, attr):
                        setattr(charlie, attr, v)
                        if attr == "fast":
                            navigation.pwm = v
                        changed.append(f"{key}={v}")
            if "drive" in new and bool(new["drive"]) != drive["on"]:
                drive["on"] = bool(new["drive"])
                changed.append("wheels " + ("on" if drive["on"] else "off"))
                if not drive["on"]:
                    charlie.pill_stop()
                    real_stop()
            for key, name in (("mic_robot", "robot mic"), ("mic_laptop", "laptop mic")):
                if key in new and bool(new[key]) != mics[key]:
                    if key == "mic_laptop" and not args.listen:
                        continue  # the laptop mic only exists when started with --listen
                    mics[key] = bool(new[key])
                    changed.append(f"{name} {'on' if mics[key] else 'off'}")
            if "dock_near_mm" in new:
                try:
                    near = int(new["dock_near_mm"])
                    if 5 <= near <= 500 and near != dock_near["mm"]:
                        charlie._robot("dock_near", str(near))
                        dock_near["mm"] = near
                        changed.append(f"dock near={near} mm")
                except (TypeError, ValueError):
                    pass
            if "volume" in new:
                try:
                    v = max(0.0, min(1.0, float(new["volume"])))
                    if v != drive["volume"]:
                        charlie.voice.link.set_volume(v)
                        drive["volume"] = v
                        changed.append(f"volume={v:g}")
                except (TypeError, ValueError):
                    pass
            return changed

        def story_log(message):
            print(f"{time.strftime('%H:%M:%S')}  {message}", flush=True)
            telemetry.record("story", message)

        story = Story(charlie, x=args.x, y=args.y, repeat_s=args.repeat, max_reasks=args.max_reasks, walk_s=args.walk_s,
                      gap_s=args.gap, follow_window_s=args.follow,
                      pill_approach_s=d.get("pill_approach_s", 2.5),
                      motion_energy=d.get("motion_energy_moving", 0.05), dock_near_mm=d.get("dock_near_mm", 10),
                      log=story_log)
        inputs = StoryInputs(story, navigation, telemetry=telemetry.record)
        inputs.hear_calls = lambda: mics["mic_robot"]
        if args.panel:
            from story_panel import StoryPanel, serve
            panel = StoryPanel(story, charlie, runner_get, runner_set, day_s=d.get("panel_day_s", 180),
                               start_at=d.get("panel_start_at", "08:00"))
            threading.Thread(target=serve, args=(panel, args.panel_port), daemon=True).start()
        for fn, a in ((story.worker, ()), (robot_events, (robot, story, inputs)), (keyboard, (story,))):
            threading.Thread(target=fn, args=a, daemon=True).start()
        if wearable:
            threading.Thread(target=wearable_events, args=(wearable, story, inputs), daemon=True).start()
        if args.listen:  # Wiam: the laptop mic hears the word "Charlie" (the robot mic only hears loudness)
            sys.path.insert(0, str(REPO / "services" / "voice"))
            from wake import WakeListener

            def heard(word, confidence):
                if not mics["mic_laptop"]:
                    return  # switched off in the panel
                story_log(f'Laptop mic heard "{word}" ({confidence:.2f})')
                story.on_called()
            wake = WakeListener(heard, is_muted=charlie.voice.mic_muted, device=args.mic)
            threading.Thread(target=_keep_listening, args=("laptop mic", story, wake.run), daemon=True).start()
            print('Laptop mic: listening for "Charlie".', flush=True)
        if args.panel:
            print(f"Panel: open http://localhost:{args.panel_port} and press 'Start the story' "
                  "(Ctrl+C here to stop).", flush=True)
        else:
            story.begin()
            print(f'Story running: x={args.x:g} s, y={args.y:g} s. Say "Charlie" (Ctrl+C to stop).', flush=True)
        while True:
            time.sleep(0.2)
            try:
                story.tick()
                charlie.drive_tick()
            except Exception as e:                        # never let one bad moment end the story
                story.log(f"! story step failed: {e} (going on)")
    except KeyboardInterrupt:
        print("\nbye")
    finally:
        try:
            try:
                if charlie:
                    charlie.close()
                else:
                    robot.call("robot_mode", "stop", timeout=1)
            except Exception as e:
                print(f"! shutdown stop not acknowledged: {e}", flush=True)
        finally:
            robot.close()
            if wearable:
                wearable.close()
            if telemetry:
                telemetry.close()


if __name__ == "__main__":
    main()
