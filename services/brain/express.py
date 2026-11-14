"""Charlie's emotions: the robot's eyes and one of Wiam's phrases, together. Owner: Reshma.

Runs on the laptop with the robot on USB (firmware/robot_main flashed). Opens the robot's USB
port ONCE and shares it with Wiam's speaker code, so eyes and sound go over the same cable.

    python services/brain/express.py                 # listen: "Charlie" and wake-up react by themselves
    python services/brain/express.py pleading        # one emotion now: eyes + phrase together
    python services/brain/express.py --list          # the emotions
    options: --volume 0.4   --port COM8

Emotion table (eye mood comes from Wiam's reactions.yaml, which uses the moods in shared/protocol.py):
    called       "Charlie!"                 happy eyes  + happy bark, "You called? I'm here!"
    reward       pill taken / walk done     happy eyes  + excited spin, praise
    wake         robot wakes up             robot's own sleepy -> calm eyes + yawn, "Good morning!"
    pleading     pill reminder              amber eyes  + bark, "Time for your medicine..."
    encouraging  walk prompt                turquoise   + happy bark, "Follow me, let's walk a little!"
    sad          pill missed / gave up      dim purple  + gentle back-off line
calm, searching and listening stay silent (the robot does those on its own).

While a phrase plays, the robot holds the mood (robot_express <mood> ... robot_express done),
so happy eyes last exactly as long as Charlie speaks.
"""
from __future__ import annotations

import argparse
import sys
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services" / "voice"))
sys.path.insert(0, str(REPO))

from links import AtechUsbLink  # noqa: E402  (Wiam)
from voice import Voice  # noqa: E402  (Wiam)

# emotion -> (Wiam's reaction, arguments)
EMOTIONS: dict[str, tuple[str, dict]] = {
    "called":      ("called", {}),
    "reward":      ("reward", {"task": "walk"}),
    "wake":        ("wake_up", {}),
    "pleading":    ("pill", {"attempt": 1}),
    "encouraging": ("encourage", {"attempt": 1}),
    "sad":         ("pill", {"attempt": 99}),     # past max_reasks -> Wiam's give_up (sad eyes)
}
ROBOT_DRIVES_EYES = {"wake"}   # the robot shows its own wake-up animation; we only add the sound
IGNORE_AFTER_S = 1.5           # after Charlie spoke, ignore the mic a bit longer (no self-trigger)


class Charlie:
    def __init__(self, board, volume: float = 0.4):
        self.board = board
        self.lock = threading.Lock()          # eyes commands and audio chunks take turns on the cable
        self.voice = Voice(AtechUsbLink(board=board, lock=self.lock, volume=volume), emit=lambda m: None)
        self._busy = threading.Event()
        self._quiet_since = 0.0

    def _robot(self, action: str, value: str) -> None:
        with self.lock:
            self.board.call(action, value)

    def can_react(self) -> bool:
        return not self._busy.is_set() and time.monotonic() - self._quiet_since >= IGNORE_AFTER_S

    def express(self, emotion: str, **overrides) -> None:
        """Eyes and phrase together. Blocks until the phrase has finished."""
        reaction, args = EMOTIONS[emotion]
        args = {**args, **overrides}
        plan = self.voice.reactions.plan(reaction, **args)
        mood = None if emotion in ROBOT_DRIVES_EYES else (plan.get("eyes") or {}).get("color")
        self._busy.set()
        try:
            if mood:
                self._robot("robot_express", mood)          # eyes change now ...
            print(f"  {emotion}: eyes {mood or '(robot)'} + {reaction}"
                  + (f" level {plan['level']}" if plan.get("level") else ""), flush=True)
            self.voice.reactions.play(reaction, **args)     # ... and the phrase starts with them
        finally:
            if mood:
                self._robot("robot_express", "done")        # back to the calm/search cycle
            self._quiet_since = time.monotonic()
            self._busy.clear()

    def express_async(self, emotion: str) -> None:
        threading.Thread(target=self.express, args=(emotion,), daemon=True).start()

    def listen(self) -> None:
        """React to the robot: "Charlie" -> called, wake-up -> wake. Runs until Ctrl+C."""
        print('Listening to the robot. Say "Charlie" (Ctrl+C to stop).', flush=True)
        for ev in self.board.events(keys=["robot_heard", "robot_behavior"]):
            v = ev.value if isinstance(ev.value, dict) else {}
            if ev.key == "robot_heard":
                if self.can_react():
                    print('Heard "Charlie"', flush=True)
                    self.express_async("called")
            elif v.get("state") == "wake" and self.can_react():
                print("Robot woke up", flush=True)
                self.express_async("wake")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("emotion", nargs="?", choices=sorted(EMOTIONS), help="play one emotion and exit")
    ap.add_argument("--list", action="store_true", help="show the emotions")
    ap.add_argument("--volume", type=float, default=0.4, help="robot speaker volume 0..1 (1.0 distorts)")
    ap.add_argument("--port", help="robot USB port, e.g. COM8 (default: first board found)")
    args = ap.parse_args()
    if args.list:
        for name, (reaction, kw) in EMOTIONS.items():
            print(f"  {name:12s} -> Wiam's reaction {reaction} {kw or ''}")
        return

    from atech import Board
    with (Board.connect(port=args.port) if args.port else Board.connect()) as board:
        charlie = Charlie(board, volume=args.volume)
        if args.emotion:
            charlie.express(args.emotion)
            return
        try:
            charlie.listen()
        except KeyboardInterrupt:
            print("\nbye")


if __name__ == "__main__":
    main()
