"""Live eye test on the real robot board. Owner: Reshma.

Upload firmware/robot_eyes first (`atech upload .`), then:
    python test_eyes_live.py              # each mood held 15 s
    python test_eyes_live.py --wait       # press Enter to go to the next mood
    python test_eyes_live.py --hold 30 sad sleepy   # only these moods, 30 s each

Keeps ONE connection open for the whole run and prints what you should see.
"""
import argparse
import time

from atech import Board

MOODS = [
    ("calm",        "soft blue, SLOW blink: 1.5 s on, 1.5 s off"),
    ("listening",   "bright white, steady, no blinking"),
    ("happy",       "green, VERY FAST blink for 2 s, then calm blue (re-sent every 3 s here)"),
    ("pleading",    "warm amber, blink once a second: 0.5 s on, 0.5 s off"),
    ("encouraging", "turquoise, steady with a quick double blink every 2 s"),
    ("sad",         "dim purple, very slow faint glow (6 s per cycle), never fully off"),
    ("sleepy",      "dim orange, ONLY the middle row lit, steady"),
    ("searching",   "pale blue column sweeping: left eye -> right eye -> back, 0.3 s per step"),
]
HAPPY_RESEND_S = 3.0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("moods", nargs="*", help="only test these moods (default: all)")
    ap.add_argument("--hold", type=float, default=15.0, help="seconds per mood (default 15)")
    ap.add_argument("--wait", action="store_true", help="wait for Enter before each next mood")
    ap.add_argument("--port", help="serial port, e.g. COM5 (default: first board found)")
    args = ap.parse_args()

    known = dict(MOODS)
    todo = [(m, known[m]) for m in args.moods] if args.moods else MOODS
    for m in args.moods:
        if m not in known:
            ap.error(f"unknown mood {m!r}; choose from {', '.join(known)}")

    with (Board.connect(port=args.port) if args.port else Board.connect()) as board:
        board.call("robot_eyes", "calm")           # also stops a running robot_eyes_demo
        for i, (mood, expect) in enumerate(todo, 1):
            print(f"\n[{i}/{len(todo)}] {mood.upper()}")
            print(f"    expect: {expect}")
            board.call("robot_eyes", mood)
            end = time.time() + args.hold
            next_happy = time.time() + HAPPY_RESEND_S
            while time.time() < end:
                left = int(end - time.time()) + 1
                print(f"    holding... {left:3d} s ", end="\r", flush=True)
                if mood == "happy" and time.time() >= next_happy:
                    board.call("robot_eyes", "happy")
                    next_happy = time.time() + HAPPY_RESEND_S
                time.sleep(0.25)
            print("    done.            ")
            if args.wait and i < len(todo):
                input("    press Enter for the next mood ")
        board.call("robot_eyes", "calm")
        print("\nAll moods shown; eyes back to calm.")


if __name__ == "__main__":
    main()
