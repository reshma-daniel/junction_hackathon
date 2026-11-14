"""Drive panel for the Kaamos robot (owner: Sara).

    python tools/drive_ui/server.py          # real robot on USB
    python tools/drive_ui/server.py --mock   # no hardware: just prints commands

Open http://localhost:8765 . Sends `robot_drive "l,r"` / `robot_mode <m>` / `robot_ping`
(see docs/MESSAGES.md). Safety: if the page stops sending for 0.6 s the robot is stopped,
and the firmware's own 2 s watchdog stops it if this server dies.
"""
import argparse, json, os, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument("--mock", action="store_true")
ap.add_argument("--port", type=int, default=8765)
args = ap.parse_args()

lock = threading.Lock()
state = {"l": 0, "r": 0, "mode": "manual", "last_cmd": 0.0, "log": [], "board": "mock" if args.mock else "connecting"}
board = None


def call(key, value=""):
    if args.mock:
        return True
    with lock:
        board.call(key, value, timeout=1.0)
    return True


def log(msg):
    state["log"] = (state["log"] + [time.strftime("%H:%M:%S ") + msg])[-8:]
    print(msg, flush=True)


def keepalive():
    """Heartbeat for the firmware watchdog + dead-man stop if the page goes quiet."""
    while True:
        time.sleep(0.3)
        try:
            if (state["l"] or state["r"]) and time.time() - state["last_cmd"] > 0.6 and state["mode"] == "manual":
                state["l"] = state["r"] = 0
                call("robot_drive", "0,0")
                log("page quiet -> stopped")
            else:
                call("robot_ping")
        except Exception as e:
            state["board"] = f"error: {e}"


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path in ("/", "/index.html"):
                b = open(os.path.join(HERE, "index.html"), "rb").read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)
            elif u.path == "/drive":
                l = max(-255, min(255, int(float(q.get("l", 0)))))
                r = max(-255, min(255, int(float(q.get("r", 0)))))
                state.update(l=l, r=r, mode="manual", last_cmd=time.time())
                call("robot_drive", f"{l},{r}")
                self._json({"ok": True, "l": l, "r": r})
            elif u.path == "/mode":
                m = q.get("m", "stop")
                if m not in ("idle", "walk", "follow", "come", "stop"):
                    return self._json({"ok": False, "err": "bad mode"}, 400)
                state.update(l=0, r=0, mode=m, last_cmd=time.time())
                call("robot_mode", m)
                log(f"mode {m}")
                self._json({"ok": True, "mode": m})
            elif u.path == "/status":
                self._json({k: state[k] for k in ("l", "r", "mode", "board", "log")} | {"mock": args.mock})
            else:
                self.send_error(404)
        except Exception as e:
            log(f"error: {e}")
            self._json({"ok": False, "err": str(e)}, 500)


if __name__ == "__main__":
    if not args.mock:
        from atech import Board
        board = Board.connect()
        state["board"] = "connected"
        log("board connected")
    threading.Thread(target=keepalive, daemon=True).start()
    print(f"drive panel: http://localhost:{args.port}  ({'MOCK' if args.mock else 'real robot'})", flush=True)
    try:
        ThreadingHTTPServer(("127.0.0.1", args.port), H).serve_forever()
    finally:
        if board:
            try:
                call("robot_drive", "0,0")
            except Exception:
                pass
