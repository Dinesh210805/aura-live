# UI Elements Inspector

Simple tool to fetch and display UI elements from the current Android screen via HTTP API.

## How It Works

The tool communicates with the running backend server which:
1. Requests fresh UI tree from Android via WebSocket
2. Receives `ui_tree_response` from Android with all elements
3. Returns formatted data to the tool via HTTP API

**Architecture:**
```
Tool (HTTP) → Backend API → UITreeService → WebSocket → Android
                                                            ↓
Tool ← HTTP Response ← UITreeService ← ui_tree_response ← Android
```

## Usage

### Prerequisites

1. **Backend server must be running:**
   ```bash
   python main.py
   ```

2. **Android device must be connected:**
   - AURA app running
   - WebSocket connected to backend
   - Accessibility service enabled

### Run the Inspector

```bash
python tools/get_ui_elements.py
```

### Output Format

```
Element #1
  Label:       Home
  Type:        TextView
  Flags:       [CLICKABLE]
  Position:    (124, 2627)
  Size:        248x63
  Resource ID: com.spotify:id/home_tab

Element #2
  Label:       Your Library
  Type:        TextView
  Flags:       [CLICKABLE]
  Position:    (372, 2627)
  Size:        248x63
  Resource ID: com.spotify:id/library_tab
```

## Requirements

- Backend server running on `http://localhost:8000`
- Android device connected via WebSocket (`/ws/conversation`)
- Accessibility service active on Android
- Network reachability between tool and backend

## Use Cases

1. **Debug UI tree parsing** - See what elements Android is exposing
2. **Find element coordinates** - Get exact positions for gesture testing
3. **Verify clickability** - Check which elements are marked as clickable
4. **Inspect resource IDs** - Find IDs for targeted element selection
5. **Test perception pipeline** - Verify UITreeService is receiving data correctly

## Troubleshooting

**Error: "Cannot connect to backend server"**
- Ensure `python main.py` is running
- Check backend is listening on port 8000
- Verify no firewall blocking localhost

**Error: "Device not connected" (HTTP 503)**
- Ensure Android AURA app is running
- Check WebSocket connection status in backend logs
- Wait for `Device connected` message in logs
- Try reconnecting Android app

**Error: "Request timed out"**
- Backend may be processing another request
- Check backend logs for errors
- Restart backend if unresponsive

**Error: "Failed to get UI tree from device"**
- Check if Accessibility Service is enabled on Android
- Verify app is in foreground
- Try navigating to a different screen
- Check Android app logs for errors

## API Endpoint

The tool calls `GET /api/v1/device/ui-elements` which:
- Returns HTTP 503 if device not connected
- Returns HTTP 500 if internal error
- Returns HTTP 200 with JSON payload:
  ```json
  {
    "success": true,
    "elements": [...],
    "total_count": 87,
    "clickable_count": 23,
    "scrollable_count": 1,
    "editable_count": 0,
    "screen_width": 1080,
    "screen_height": 2400,
    "current_app": "com.spotify.music",
    "timestamp": 1737820800000
  }
  ```
