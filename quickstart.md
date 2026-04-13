# AURA — Quick Start Guide

Get AURA controlling your Android device in under 10 minutes.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.11+ | `python --version` to check |
| Android device | USB debugging enabled (Settings → Developer options) |
| AURA Accessibility Service | Installed on device (see step 5) |
| `adb` in PATH | `adb devices` should list your device |
| Groq API key | [console.groq.com](https://console.groq.com) — free tier works |
| Gemini API key | [aistudio.google.com](https://aistudio.google.com) — free tier works |

---

## Step 1 — Clone and Install

```bash
git clone https://github.com/your-org/aura-live.git
cd aura-live

# One-command setup
bash setup.sh

# Or manually:
pip install -r "requirements copy.txt"
cp .env.example .env
```

---

## Step 2 — Configure API Keys

Edit `.env` (created by `setup.sh`):

```env
# Required
GROQ_API_KEY=gsk_...
GEMINI_API_KEY=AIza...
GOOGLE_API_KEY=AIza...   # same key as GEMINI_API_KEY

# Optional: enable Gemini Live bidirectional audio+vision
GEMINI_LIVE_ENABLED=false

# Optional: upload execution logs to Google Cloud Storage
GCS_LOGS_ENABLED=false
```

All other settings have sensible defaults. See `README.md#configuration` for the full reference.

---

## Step 3 — Connect Your Android Device

```bash
# Verify device is recognized
adb devices
# Should show: <serial>  device
```

Enable USB debugging:
1. Settings → About phone → tap **Build number** 7 times
2. Settings → Developer options → enable **USB debugging**
3. Accept the RSA fingerprint prompt when connecting via USB

---

## Step 4 — Install the Companion App

The Android companion app sends audio, screenshots, and UI trees to AURA.

```bash
# Build and install from source (requires Android Studio)
cd UI
./gradlew installDebug

# Or install the pre-built APK (if provided in releases)
adb install aura-companion.apk
```

In the app, set the **Server URL** to:
- Same network: `ws://192.168.x.x:8000` (your machine's local IP)
- Cloud Run: `wss://your-cloud-run-url`

---

## Step 5 — Enable Accessibility Service

In the companion app:
1. Tap **Grant Accessibility Permission**
2. Settings → Accessibility → AURA → enable

This allows AURA to read the UI tree and execute gestures without root.

---

## Step 6 — Start the AURA Backend

```bash
python main.py
```

Expected output:
```
INFO  Compiling LangGraph application...
INFO  LangGraph application compiled
INFO  AURA backend startup completed
INFO  🚀 Starting AURA server on 0.0.0.0:8000
```

Verify it's running:
```bash
curl http://localhost:8000/health
# → {"status": "healthy", ...}
```

Open the demo dashboard: [http://localhost:8000/demo](http://localhost:8000/demo)

---

## Step 7 — Try a Voice Command

Open the companion app on your Android device, tap the microphone, and say:

> *"Open YouTube and search for lo-fi music"*

AURA will:
1. Capture the current screen
2. Locate the YouTube app icon (via UI tree + YOLOv8 + VLM)
3. Tap it
4. Find the search bar
5. Type "lo-fi music"
6. Respond: *"Done — searching for lo-fi music on YouTube."*

---

## Step 8 — Connect Claude Code (MCP)

Add AURA as an MCP server in your Claude Code config (`~/.claude.json`):

```json
{
  "mcpServers": {
    "aura": {
      "command": "python",
      "args": ["/absolute/path/to/aura-live/aura_mcp_server.py"],
      "env": {}
    }
  }
}
```

Restart Claude Code, then in any session:

```
@aura perceive_screen()
```

Claude will see your Android device's screen and can issue commands:

```
@aura execute_android_task("Open Settings and enable dark mode")
```

### Available MCP Tools

| Tool | Description |
|---|---|
| `perceive_screen()` | Capture screenshot + UI elements with Set-of-Marks labels |
| `execute_gesture(type, target, params)` | Tap, swipe, type, scroll on a specific element |
| `validate_action(type, target)` | Check if an action is allowed by OPA safety policies |
| `watch_device_events(timeout)` | Subscribe to device events (gesture, task, screenshot) |
| `execute_android_task(utterance)` | Run any natural-language command through the full AURA pipeline |

---

## Troubleshooting

### `adb devices` shows no devices

- Reconnect the USB cable
- Accept the RSA fingerprint on the device
- Try `adb kill-server && adb start-server`

### Import errors on startup

```bash
# Ensure you're in the repo root
cd aura-live
pip install -r "requirements copy.txt"
```

### MCP tools not showing in Claude Code

- Verify the path in `~/.claude.json` is absolute
- Run `python aura_mcp_server.py` manually — should exit cleanly
- Check Claude Code logs: `~/.claude/logs/`

### VLM not finding elements

- Set `DEFAULT_PERCEPTION_MODALITY=hybrid` in `.env` (default)
- Increase `PERCEPTION_CACHE_TTL=0` to always get fresh screenshots
- Try `DEFAULT_VLM_PROVIDER=gemini` for more powerful visual reasoning

---

## Next Steps

- [README.md](README.md) — full architecture and configuration reference
- [Google Cloud Deployment](README.md#cloud-run-deployment) — deploy to Cloud Run
- [Gemini Live](README.md#gemini-live-bidirectional-streaming) — enable bidi audio+vision
- [REST API](README.md#rest-api) — programmatic control for non-MCP agents
