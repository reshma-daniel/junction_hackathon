
import asyncio
import argparse
import json
import math
import threading
import time
import requests
import websockets
from datetime import datetime

WEARABLE_DEVICE_ID = "3ae634a4-5d8d-4764-9d6b-8541f15613db"

# Replace this with your actual robot device ID
ROBOT_DEVICE_ID = "e55c4b95-ff15-49ab-9f64-310a4719f84b"

WEARABLE_WS_URL = (
    f"wss://gateway.atech.dev/ws/live/{WEARABLE_DEVICE_ID}"
)

ROBOT_SEND_URL = (
    f"https://gateway.atech.dev/send/{ROBOT_DEVICE_ID}"
)

# Running the script controls robot from wearable data by default.
FORWARD_TO_ROBOT = True
ROBOT_PORT = None
ROBOT_LOCK = threading.Lock()
SOURCE_CONNECTED = threading.Event()
HEARTBEAT_STOP = threading.Event()


def robot_action(action, value=""):
    with ROBOT_LOCK:
        if ROBOT_PORT:
            from atech import Board
            with Board.connect(port=ROBOT_PORT) as board:
                board.call(action, value, timeout=1)
        else:
            response = requests.post(ROBOT_SEND_URL, json={"action": action, "value": value}, timeout=2)
            response.raise_for_status()
            result = response.json()
            if result.get("ok") is not True:
                raise RuntimeError(f"Gateway rejected {action}: {result}")


def robot_heartbeat():
    while not HEARTBEAT_STOP.wait(0.5):
        if SOURCE_CONNECTED.is_set():
            try:
                robot_action("robot_ping")
            except Exception as error:
                log(f"ROBOT heartbeat error: {error}")



def motion_payload(data):
    """Accept only finite, nonnegative energy and an actual boolean state."""
    if not isinstance(data, dict) or data.get("type") != "wearable.motion":
        return None
    motion = data.get("payload")
    if not isinstance(motion, dict):
        return None
    energy, moving = motion.get("energy"), motion.get("moving")
    if (isinstance(energy, bool) or not isinstance(energy, (int, float))
            or not math.isfinite(energy) or energy < 0 or not isinstance(moving, bool)):
        return None
    return energy, moving


def usb_bridge(port):
    import serial
    log(f"Wearable USB: {port}; robot: {ROBOT_PORT}; forwarding={FORWARD_TO_ROBOT}")
    if not FORWARD_TO_ROBOT:
        log("MONITOR ONLY: motors disabled by --monitor-only.")
    while True:
        try:
            with serial.Serial(port, 115200, timeout=1) as wearable:
                SOURCE_CONNECTED.set()
                # Motion is normally emitted only on state changes. Request the
                # current measured state so reconnecting does not wait for a flip.
                wearable.write((json.dumps({"type": "action", "payload": {
                    "action": "motion", "value": ""
                }}) + "\n").encode())
                last_status = 0.0
                while True:
                    now = time.monotonic()
                    if now - last_status >= 2:
                        wearable.write((json.dumps({"type": "action", "payload": {
                            "action": "status", "value": ""
                        }}) + "\n").encode())
                        last_status = now
                    raw = wearable.readline()
                    if not raw:
                        continue
                    try:
                        data = json.loads(raw)
                    except (ValueError, UnicodeDecodeError):
                        continue
                    if not isinstance(data, dict):
                        continue
                    if data.get("type") == "wearable.status":
                        state = data.get("payload", {})
                        log(f"IMU: sensor_ok={state.get('sensor_ok')}, energy={state.get('energy')}, moving={state.get('moving')}")
                    elif data.get("type") == "error":
                        log(f"WEARABLE ERROR: {data.get('payload')}")
                    motion = motion_payload(data)
                    if motion is None:
                        continue
                    energy, moving = motion
                    log(f"MOTION RECEIVED: energy={energy}, moving={moving}")
                    if FORWARD_TO_ROBOT:
                        send_to_robot(energy, moving)
        except serial.SerialException as error:
            SOURCE_CONNECTED.clear()
            log(f"Wearable USB error: {error}; retrying in 3 seconds")
            time.sleep(3)


def log(message):
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}", flush=True)


def send_to_robot(energy, moving):
    if ROBOT_PORT:
        try:
            robot_action("wearable_motion", json.dumps({"energy": energy, "moving": moving}))
            log(f"ROBOT ACK via {ROBOT_PORT}: moving={moving}, energy={energy}")
        except Exception as error:
            log(f"USB SEND ERROR: {error}")
        return
    command = {
        "action": "wearable_motion",
        "value": {
            "energy": energy,
            "moving": moving
        }
    }

    try:
        response = requests.post(
            ROBOT_SEND_URL,
            json=command,
            timeout=5
        )
        response.raise_for_status()

        result = response.json()

        if result.get("ok"):
            log(f"GATEWAY WROTE TO ROBOT (not firmware ACK): {command}")
        else:
            log(f"ROBOT ERROR: {result}")

    except Exception as error:
        log(f"SEND ERROR: {error}")


async def bridge():
    log("Python Bridge started")
    log(f"Wearable ID: {WEARABLE_DEVICE_ID}")
    log(f"Robot forwarding enabled: {FORWARD_TO_ROBOT}")

    while True:
        try:
            log("Connecting to Atech Cloud...")

            async with websockets.connect(
                WEARABLE_WS_URL,
                open_timeout=10,
                ping_interval=20,
                ping_timeout=20
            ) as ws:

                log("CONNECTED to Atech Cloud")
                # Events are not stored. Request current measured state after
                # subscribing instead of waiting for the next state transition.
                await ws.send(json.dumps({"type": "send_to_device", "payload": {
                    "action": "motion", "value": ""
                }}))

                async for message in ws:
                    # Print every incoming frame
                    log(f"RAW FRAME: {message}")

                    try:
                        frame = json.loads(message)
                    except json.JSONDecodeError:
                        log("Invalid WebSocket JSON")
                        continue

                    if not isinstance(frame, dict):
                        continue
                    frame_type = frame.get("type")

                    if frame_type == "device_connected":
                        SOURCE_CONNECTED.set()
                        log("WEARABLE ONLINE")
                        continue

                    if frame_type == "device_disconnected":
                        SOURCE_CONNECTED.clear()
                        log("WEARABLE OFFLINE")
                        continue

                    if frame_type != "device_event":
                        continue

                    payload = frame.get("payload", {})
                    if not isinstance(payload, dict):
                        continue
                    raw_line = payload.get("value")

                    log(f"WEARABLE OUTPUT: {raw_line}")

                    try:
                        data = json.loads(raw_line)
                    except (json.JSONDecodeError, TypeError):
                        log("Firmware output is not JSON")
                        continue

                    motion = motion_payload(data)
                    if motion is None:
                        continue
                    SOURCE_CONNECTED.set()
                    energy, moving = motion

                    log(
                        f"MOTION RECEIVED: "
                        f"energy={energy}, moving={moving}"
                    )

                    if FORWARD_TO_ROBOT:
                        await asyncio.to_thread(
                            send_to_robot,
                            energy,
                            moving
                        )

        except Exception as error:
            SOURCE_CONNECTED.clear()
            log(
                f"CONNECTION ERROR: "
                f"{type(error).__name__}: {error}"
            )

        log("Reconnecting in 3 seconds...")
        await asyncio.sleep(3)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Read wearable USB IMU data; optionally forward to robot USB")
    parser.add_argument("--cloud", action="store_true", help="Use Atech Cloud instead of USB")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--forward", action="store_true", help="Enable robot forwarding (default; compatible with older commands)")
    mode.add_argument("--monitor-only", action="store_true", help="Only display wearable data; disable robot control")
    parser.add_argument("--robot-port", help="Use an explicit robot USB port instead of cloud HTTP")
    parser.add_argument("--wearable-port", help="Read wearable USB JSON instead of cloud WebSocket")
    args = parser.parse_args()
    if args.cloud and args.wearable_port:
        parser.error("Choose --cloud or --wearable-port, not both")
    if not args.cloud:
        args.wearable_port = args.wearable_port or "/dev/cu.usbmodem11301"
        args.robot_port = args.robot_port or "/dev/cu.usbmodem101"
    FORWARD_TO_ROBOT = not args.monitor_only
    ROBOT_PORT = args.robot_port
    if args.wearable_port and args.wearable_port == ROBOT_PORT:
        parser.error("Wearable and robot must use different USB ports")
    if (
        FORWARD_TO_ROBOT
        and ROBOT_DEVICE_ID == "REPLACE_WITH_ROBOT_DEVICE_ID"
    ):
        raise SystemExit(
            "Set ROBOT_DEVICE_ID before enabling forwarding."
        )

    try:
        if FORWARD_TO_ROBOT:
            robot_action("session_start")
            log("New robot session: capture first fresh measured RSSI as return baseline")
            threading.Thread(target=robot_heartbeat, daemon=True).start()
        if args.wearable_port:
            usb_bridge(args.wearable_port)
        else:
            asyncio.run(bridge())
    except KeyboardInterrupt:
        log("Bridge stopped")
    finally:
        SOURCE_CONNECTED.clear()
        HEARTBEAT_STOP.set()
        if FORWARD_TO_ROBOT:
            try:
                robot_action("stop")
                log("Stop acknowledged" if ROBOT_PORT else "Gateway wrote stop to robot (not firmware ACK)")
            except Exception as error:
                log(f"Stop failed; robot watchdog will stop it: {error}")
