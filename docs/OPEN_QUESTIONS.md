# Open questions – verify early on real hardware

1. **Can two boards share one Atech WiFi gateway/project?** Docs show one board ↔ one project ID.
   If not: run two project IDs (one per board), brain connects to both. Or fall back to USB serial for the robot. (Wanhui, M0)
2. **Audio over JSON.** Speaker "audio streaming" and Microphone "recording" exist, but a base64-in-JSON
   stream over WebSocket may be laggy. Fallbacks: pre-render short phrases onto the microSD card on the
   robot and trigger by id (`robot.say_clip {id}`), keep STT for the mic only on short clips. (Wiam, M1)
3. **Following a person / relative position.** Atech gives no board-to-board link; Wanhui tries RSSI/BLE, otherwise ToF. MVP = ToF 8x8 nearest-blob tracking at
   300–1200 mm. Stretch = Camera module. "Leading" the user (walk away, user follows) is easier than
   following and is the first behaviour to get working. (Sara/Reshma)
4. **Mixed WiFi dependency.** Demo venue WiFi may be bad. Bring a phone hotspot/router; pre-cache TTS phrases. (Wiam/Wanhui)
5. ~~LED count~~ resolved: two LED grids = two eyes. (Reshma)
6. **Wake-word quality.** STT-based "Charlie" detection costs latency (~1–2 s). Mitigate with local
   loudness trigger + short clip + fuzzy match. (Wiam)
7. **Power.** Wearable and robot each need USB-C power banks. Motors may brown out the ESP32: use separate supply if resets. (Sara/Reshma)
8. **Privacy.** Mic audio goes to ElevenLabs: only send clips after a loudness trigger, don't store them. Medication/activity data stays local (SQLite). Decide and state this for the pitch. (all)
