# services/gateway — Owner: Wanhui

Connects to the Atech boards and exposes them to the rest of the Python code.

- WiFi: WebSocket client to the Atech gateway using the project ID(s) in shared/config.yaml.
  USB fallback: pyserial, 115200 baud, one JSON per line.
- Inbound: parse board JSON -> publish on the event bus. Outbound: `send_to_robot(msg)`.
- Auto-reconnect with backoff; log connect/disconnect (the brain should know if the robot is offline).
- Mock mode: `--sim` connects to tools/simulator instead of real boards.

Interface (suggested):
```python
class Bus:  # asyncio pub/sub
    async def publish(self, msg: dict): ...
    def subscribe(self, prefix: str) -> asyncio.Queue: ...
```


Implemented story path: `story_inputs.py` dispatches the SDK events from the Board connections already opened by `run_story.py`. It opens no extra serial ports and replaces a separate bridge process for the full system.
