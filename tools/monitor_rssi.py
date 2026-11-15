"""Print robot's wearable BLE RSSI without running the motor-control bridge."""
import argparse
from collections import deque
from datetime import datetime
import json
import time

import serial


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="/dev/cu.usbmodem101")
    parser.add_argument("--seconds", type=float, help="Stop after this many seconds")
    args = parser.parse_args()
    history = deque()
    start = time.monotonic()
    last_report = start
    print(f"RSSI monitor: {args.port}; move wearable near / far / near.", flush=True)
    print("Positive delta = stronger signal; negative = weaker. Not a distance measurement.", flush=True)
    with serial.Serial(args.port, 115200, timeout=1) as port:
        while args.seconds is None or time.monotonic() - start < args.seconds:
            raw = port.readline()
            now = time.monotonic()
            if now - last_report > 5:
                print("No BLE reports for 5 seconds; check robot firmware and USB.", flush=True)
                last_report = now
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except (ValueError, UnicodeDecodeError):
                continue
            if not isinstance(data, dict):
                continue
            payload = data.get("payload", {})
            if not isinstance(payload, dict) or payload.get("key") != "wearable_ble":
                continue
            sample = payload.get("value", {})
            if not isinstance(sample, dict):
                continue
            last_report = now
            stamp = datetime.now().strftime("%H:%M:%S")
            if not sample.get("detected"):
                history.clear()
                print(f"[{stamp}] wearable NOT DETECTED", flush=True)
                continue
            smoothed = sample.get("rssi_smoothed_dbm")
            rssi = sample.get("rssi_dbm")
            if not isinstance(smoothed, (int, float)) or not isinstance(rssi, (int, float)):
                continue
            history.append((now, smoothed))
            while history and now - history[0][0] > 5:
                history.popleft()
            elapsed = now - history[0][0]
            delta = smoothed - history[0][1]
            trend = "warming up" if elapsed < 3 else "stronger" if delta >= 3 else "weaker" if delta <= -3 else "roughly steady"
            print(f"[{stamp}] raw={rssi:4.0f} dBm  smooth={smoothed:6.1f} dBm  delta={delta:+5.1f} dB/{elapsed:.0f}s  {trend}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("RSSI monitor stopped.")
