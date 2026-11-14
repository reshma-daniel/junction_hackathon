"""Live microphone test on the real robot board. Owner: Reshma.

Upload firmware/robot_mic first (`atech upload .`), then:
    python test_mic_live.py             # guided test: quiet, "Charlie" x3, claps, a sentence
    python test_mic_live.py --wait      # press Enter before each step
    python test_mic_live.py --watch     # just show the live level and every call (Ctrl+C to stop)

The eyes show it too: white while you speak, fast green blink when a call is detected.
"""
import argparse
import time

from atech import Board

STEPS = [
    # (instruction, seconds, expected calls)
    ("Stay QUIET (learning the room's background noise)", 6, 0),
    ('Say "Charlie" 3 times, about 3 s apart, in a normal voice', 15, 3),
    ("CLAP 3 times, about 2 s apart (should be ignored)", 10, 0),
    ('Say one long SENTENCE, e.g. "I think I will stay on the sofa a bit longer today"', 10, 0),
]


def bar(level: float, loud: bool) -> str:
    n = int(min(1.0, level * 4) * 30)          # x4 so normal speech fills the bar
    return f"[{'#' * n:<30}] {level:5.3f} {'LOUD' if loud else '    '}"


def listen(board: Board, seconds: float | None):
    """Yield ("sound", level, loud) and ("call", ms) events for `seconds` (None = forever)."""
    end = None if seconds is None else time.time() + seconds
    for ev in board.events(keys=["robot_sound", "robot_heard"]):
        v = ev.value if isinstance(ev.value, dict) else {}
        if ev.key == "robot_sound":
            yield ("sound", float(v.get("level", 0)), bool(v.get("loud", False)))
        else:
            yield ("call", int(v.get("ms", 0)), None)
        if end is not None and time.time() >= end:
            return


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wait", action="store_true", help="press Enter before each step")
    ap.add_argument("--watch", action="store_true", help="only show live level + calls")
    ap.add_argument("--port", help="serial port, e.g. COM5 (default: first board found)")
    args = ap.parse_args()

    with (Board.connect(port=args.port) if args.port else Board.connect()) as board:
        if args.watch:
            print("Watching the microphone (Ctrl+C to stop)")
            try:
                for kind, a, b in listen(board, None):
                    if kind == "sound":
                        print("  " + bar(a, b), end="\r", flush=True)
                    else:
                        print(f"\n  CALL detected ({a} ms) -> eyes happy")
            except KeyboardInterrupt:
                print()
            return

        results = []
        for i, (what, secs, expected) in enumerate(STEPS, 1):
            print(f"\n[{i}/{len(STEPS)}] {what}  ({secs} s)")
            if args.wait:
                input("    press Enter to start ")
            else:
                for c in (3, 2, 1):
                    print(f"    starting in {c}...", end="\r", flush=True)
                    time.sleep(1)
            print("    GO!                ")
            calls, levels = 0, []
            for kind, a, b in listen(board, secs):
                if kind == "sound":
                    levels.append(a)
                    print("    " + bar(a, b), end="\r", flush=True)
                else:
                    calls += 1
                    print(f"\n    CALL detected ({a} ms)")
            avg = sum(levels) / len(levels) if levels else 0.0
            ok = calls == expected
            results.append((what, expected, calls, ok))
            print(f"\n    calls: {calls} (expected {expected})  avg level {avg:.3f}  -> {'PASS' if ok else 'CHECK'}")

        print("\nSummary")
        for what, expected, calls, ok in results:
            print(f"  {'PASS ' if ok else 'CHECK'}  {calls}/{expected}  {what}")


if __name__ == "__main__":
    main()
