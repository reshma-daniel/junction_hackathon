"""Run Charlie's story on the real boards. Owner: Reshma.

    python services/brain/run_story.py --x 10 --y 7 --robot-port COM8 --wearable-port COM9

  x  seconds after the "Charlie" greeting when Charlie asks for the pill (asks again every 5 s)
  y  movement window in seconds: no movement from the wearable for y s -> Charlie asks you to move,
     then the robot DRIVES for --walk-s seconds: slowly while you sit, faster while you move (--no-drive = wheels off)

Boards: robot = firmware/robot_main (eyes, mic, speaker, dock distance sensor on port 7)
        wearable = firmware/wearable (IMU). `atech ports` lists the ports.
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
sys.path.insert(0, str(REPO / "services" / "brain"))
from express import Charlie  # noqa: E402  (eyes + Wiam's voice on one USB cable)
from story import Story  # noqa: E402


class WalkingCharlie(Charlie):
    """Charlie + the wheels. The robot firmware (robot_main) stops its motors if it hears nothing from the
    laptop for 2 s, so a ping goes out every second. Speeds are 0..255 before the motors' minimum PWM."""

    def __init__(self, board, volume: float, slow: int, fast: int):
        super().__init__(board, volume=volume)
        self.slow, self.fast = slow, fast
        self._driving = False
        threading.Thread(target=self._ping, daemon=True).start()

    def _ping(self) -> None:
        while True:
            time.sleep(1.0)
            try:
                self._robot("robot_ping", "")
            except Exception:
                pass

    def walk(self, fast: bool = False) -> None:
        self._robot("robot_speed", str(self.fast if fast else self.slow))
        if not self._driving:
            self._driving = True
            self._robot("robot_express", "encouraging")      # eyes while walking
        self._robot("robot_mode", "walk")                    # drives forward, turns away from obstacles

    def walk_stop(self) -> None:
        self._robot("robot_mode", "stop")
        if self._driving:
            self._driving = False
            self._robot("robot_express", "done")


def load_defaults() -> dict:
    cfg = yaml.safe_load((REPO / "shared" / "config.yaml").read_text())
    return {**cfg.get(cfg.get("profile", "demo"), {}), **cfg.get("story", {})}


def _keep_listening(name: str, story: Story, listen) -> None:
    """Run a listener forever: an error (unplugged cable, odd message) is logged and listening starts again."""
    while True:
        try:
            listen()
        except Exception as e:
            story.log(f"! {name} listener: {e} (trying again)")
            time.sleep(1.0)


def robot_events(board, story: Story) -> None:
    def listen():
        for ev in board.events(keys=["robot_heard", "distance_sensor_min_distance", "robot_behavior"]):
            if ev.key == "robot_heard":
                story.on_called()
            elif ev.key == "robot_behavior":
                v = ev.value if isinstance(ev.value, dict) else {}
                story.robot_behavior = v.get("state") or story.robot_behavior   # robot's own eyes (panel)
                if v.get("state") == "wake" and story.phase not in ("new", "starting"):
                    story.log("!!! Charlie restarted (power dip or USB?): the story goes on")
            else:
                try:
                    story.on_distance(int(ev.value))
                except (TypeError, ValueError):
                    pass
    _keep_listening("robot", story, listen)


def wearable_events(board, story: Story) -> None:
    def listen():
        for ev in board.events(keys=["wearable_motion"]):
            v = ev.value if isinstance(ev.value, dict) else {}
            if "energy" in v:
                story.on_motion(float(v["energy"]))
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
    ap.add_argument("--walk-s", type=float, default=d.get("walk_s", 10), help="how long the robot drives after 'Follow me'")
    ap.add_argument("--gap", type=float, default=d.get("topic_gap_s", 8),
                    help="break in seconds between a pill episode and a walk ask (and the other way round)")
    ap.add_argument("--follow", type=float, default=d.get("follow_window_s", 10),
                    help="walk time: seconds after 'Follow me' for the user to move; no movement at all -> sad")
    ap.add_argument("--slow", type=int, default=d.get("speed_slow", 60), help="walk speed while the user is still (0-255)")
    ap.add_argument("--fast", type=int, default=d.get("speed_fast", 220), help="walk speed while the user moves (0-255)")
    ap.add_argument("--no-drive", action="store_true", help="never move the wheels (speech and eyes only)")
    ap.add_argument("--robot-port", help="robot USB port, e.g. COM8 (default: first board found)")
    ap.add_argument("--wearable-port", help="wearable USB port; leave out to run without the wearable")
    ap.add_argument("--volume", type=float, default=d.get("volume", 0.4))
    ap.add_argument("--panel", action="store_true",
                    help="set up and run the story from Wiam's demo panel in the browser (Story mode)")
    ap.add_argument("--panel-port", type=int, default=8766,
                    help="panel web page port (default 8766; Wiam's own day demo uses 8765)")
    args = ap.parse_args()

    from atech import Board
    robot = Board.connect(port=args.robot_port) if args.robot_port else Board.connect()
    wearable = Board.connect(port=args.wearable_port) if args.wearable_port else None
    if wearable is None:
        print("No wearable: the user counts as idle (use 'm' + Enter to fake movement).", flush=True)
    try:
        charlie = WalkingCharlie(robot, args.volume, args.slow, args.fast)
        drive = {"on": not args.no_drive, "volume": args.volume}
        real_walk, real_stop = charlie.walk, charlie.walk_stop

        def walk(fast: bool = False) -> None:            # wheels can be switched off (--no-drive / panel)
            if drive["on"]:
                real_walk(fast)
        charlie.walk = walk

        def runner_get() -> dict:
            return {"speed_slow": charlie.slow, "speed_fast": charlie.fast, "drive": drive["on"],
                    "volume": drive["volume"]}

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
                        changed.append(f"{key}={v}")
            if "drive" in new and bool(new["drive"]) != drive["on"]:
                drive["on"] = bool(new["drive"])
                changed.append("wheels " + ("on" if drive["on"] else "off"))
                if not drive["on"]:
                    real_stop()
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

        story = Story(charlie, x=args.x, y=args.y, repeat_s=args.repeat, max_reasks=args.max_reasks, walk_s=args.walk_s,
                      gap_s=args.gap, follow_window_s=args.follow,
                      motion_energy=d.get("motion_energy_moving", 0.05), dock_near_mm=d.get("dock_near_mm", 40),
                      log=lambda m: print(f"{time.strftime('%H:%M:%S')}  {m}", flush=True))
        if args.panel:
            from story_panel import StoryPanel, serve
            panel = StoryPanel(story, charlie, runner_get, runner_set, day_s=d.get("panel_day_s", 180),
                               start_at=d.get("panel_start_at", "08:00"))
            threading.Thread(target=serve, args=(panel, args.panel_port), daemon=True).start()
        for fn, a in ((story.worker, ()), (robot_events, (robot, story)), (keyboard, (story,))):
            threading.Thread(target=fn, args=a, daemon=True).start()
        if wearable:
            threading.Thread(target=wearable_events, args=(wearable, story), daemon=True).start()
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
            except Exception as e:                        # never let one bad moment end the story
                story.log(f"! story step failed: {e} (going on)")
    except KeyboardInterrupt:
        print("\nbye")
    finally:
        robot.close()
        if wearable:
            wearable.close()


if __name__ == "__main__":
    main()
