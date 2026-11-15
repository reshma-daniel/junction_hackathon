"""Local per-run diagnostic journal. Logging failures never interrupt control."""
from datetime import datetime
import json
import os
from pathlib import Path
import threading
import time


class RunTelemetry:
    def __init__(self, directory):
        stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S-%f")
        self.path = Path(directory) / f"story-{stamp}-{os.getpid()}.jsonl"
        self._lock = threading.Lock()
        self._start = time.monotonic()
        self._file = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._file = self.path.open("w", encoding="utf-8", buffering=1)
        except OSError as e:
            print(f"! Cannot write telemetry: {e}", flush=True)

    def record(self, kind, value):
        row = {"ts": datetime.now().astimezone().isoformat(timespec="milliseconds"),
               "elapsed_s": round(time.monotonic() - self._start, 3),
               "kind": kind, "value": value}
        try:
            line = json.dumps(row, ensure_ascii=False, allow_nan=False)
        except (ValueError, TypeError):
            return
        with self._lock:
            if self._file is not None:
                try:
                    self._file.write(line + "\n")
                except OSError as e:
                    print(f"! Telemetry write failed: {e}", flush=True)
                    self._file.close()
                    self._file = None

    def close(self):
        with self._lock:
            if self._file is not None:
                self._file.close()
                self._file = None
