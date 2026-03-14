# 🔥 God-Level Debugging Guide

Your unified logging system that combines **EVERYTHING** for insane debugging power!

## What You Get

| Feature | What It Shows |
|---------|---------------|
| **Terminal Logs** | Real-time execution logs in your console |
| **Command Logs** | Detailed files in `logs/` with every LLM call and gesture |
| **LangSmith Traces** | Visual traces in browser with full agent workflow |
| **Unified Logger** | ALL logs combined with cross-references and search |
| **Performance Tracking** | Exact timing of each operation |
| **Error Context** | Full state when errors happen |
| **Failure Screenshots** | Auto-saved PNG + JSON when tasks fail |

## 🎯 Quick Start

### 1. Start Your Server
```powershell
python main.py
```

Watch terminal logs in real-time:
```
[09:15:23] ℹ️ [terminal] [abc123] POST /api/v1/tasks → 200 (1234ms)
[09:15:23] ℹ️ [langsmith] LangSmith trace available
  🔗 LangSmith: https://smith.langchain.com/...
  🔖 Trace: streaming_1234567890
[09:15:24] ℹ️ [perf] Performance Timeline completed (945ms)
```

### 2. View Unified Logs (God Mode)

**In your browser:**
```
http://localhost:8000/api/v1/debug/unified-logs/export/html
```

This opens an **interactive HTML viewer** with:
- ✅ All logs from all sources
- ✅ Color-coded by severity
- ✅ Grouped by trace ID
- ✅ Live search box
- ✅ Direct links to LangSmith
- ✅ Full context for each log

**Search logs:**
```bash
# Find all errors
curl "http://localhost:8000/api/v1/debug/unified-logs?level=ERROR"

# Search for "WhatsApp" in logs
curl "http://localhost:8000/api/v1/debug/unified-logs?query=WhatsApp"

# Get logs from specific source
curl "http://localhost:8000/api/v1/debug/unified-logs?source=langsmith"
```

**Get specific trace:**
```bash
# See everything that happened in one execution
curl "http://localhost:8000/api/v1/debug/unified-logs/trace/streaming_1234567890"
```

### 3. Check LangSmith Traces

1. Go to https://smith.langchain.com
2. Click "aura-agent-visualization" project
3. See visual tree of all agent calls
4. Click any run to see prompts/responses

### 4. View Command Logs

```powershell
# Open latest command log
cd logs
notepad (Get-ChildItem command_log_*.txt | Sort LastWriteTime -Desc | Select -First 1).Name
```

Shows:
- Full execution summary (tokens, time, status)
- Every LLM call with prompt/response
- Every gesture with timing
- What the AI saw on screen
- AI's reasoning for each decision

### 5. Check Failure Screenshots

```powershell
# List failure screenshots
ls data/failure_screenshots/

# View latest failure
start data/failure_screenshots/(ls data/failure_screenshots/*.png | Sort LastWriteTime -Desc | Select -First 1).Name
```

Each failure creates:
- `failure_TIMESTAMP_description.png` - Screenshot at failure
- `failure_TIMESTAMP_description.json` - Full context (goal, error, etc.)

## 🔍 Debugging Workflow

### When Something Fails:

1. **Check Terminal** - See the error immediately
   ```
   ❌ [terminal] ElementNotFoundError: Cannot find "Settings"
   Traceback...
   ```

2. **Get the Trace ID** from terminal or API response
   ```
   🔖 Trace: streaming_1234567890
   ```

3. **View Unified Timeline**
   ```bash
   # See everything that happened before the error
   curl "http://localhost:8000/api/v1/debug/unified-logs/trace/streaming_1234567890"
   ```

4. **Open LangSmith** - Click the LangSmith URL from logs
   - See what prompts were sent
   - See what AI responded
   - Check token usage

5. **Check Command Log** in `logs/` folder
   - See full execution flow
   - Check what AI saw on screen
   - Verify element detection

6. **View Failure Screenshot** (if action failed)
   - See exact screen state
   - Check if element was actually visible

## 📊 God-Level Features

### Timeline View
See everything in chronological order:
```bash
curl "http://localhost:8000/api/v1/debug/unified-logs/timeline?limit=100"
```

### Export Everything
```bash
# HTML viewer (opens in browser)
curl "http://localhost:8000/api/v1/debug/unified-logs/export/html" > debug.html
start debug.html

# JSON (for scripts)
curl "http://localhost:8000/api/v1/debug/unified-logs/export/json"
```

### Real-Time Filtering
```bash
# Only errors from last 5 minutes
curl "http://localhost:8000/api/v1/debug/unified-logs?level=ERROR&since=$(date -d '5 minutes ago' +%s)"

# Performance logs only
curl "http://localhost:8000/api/v1/debug/unified-logs?source=perf"

# Find specific action
curl "http://localhost:8000/api/v1/debug/unified-logs?query=tap+Settings"
```

## 🎨 HTML Viewer Features

The HTML export (`/debug/unified-logs/export/html`) gives you:

- **Search box** - Type to filter logs instantly
- **Color coding**:
  - 🟢 Green = INFO
  - 🔴 Red = ERROR  
  - 🟡 Yellow = WARNING
  - ⚪ Gray = DEBUG
- **Trace grouping** - All logs from same execution grouped together
- **LangSmith links** - Click to open trace in browser
- **Context expansion** - Click to see full error context
- **Stats dashboard** - Total entries, errors, warnings at top

## 💡 Pro Tips

### 1. Terminal is Your Friend
The terminal shows EVERYTHING in real-time. Keep it visible!

### 2. Use Trace IDs
Every execution has a trace ID. Use it to see the full story:
```bash
curl "http://localhost:8000/api/v1/debug/unified-logs/trace/YOUR_TRACE_ID"
```

### 3. LangSmith for AI Debugging
When the AI does something weird, check LangSmith to see:
- What prompt it received
- What it responded
- How long it took
- Which tokens it used

### 4. Command Logs for Deep Dives
When you need to understand EXACTLY what happened:
- Open the command log file
- Search for the action
- See full UI state
- Read AI's reasoning

### 5. Failure Screenshots
Pictures don't lie! When an action fails:
- Check the screenshot
- Verify element was visible
- Check if coordinates were right

## 🚀 All Debug Endpoints

| Endpoint | Description |
|----------|-------------|
| `/debug/state` | Current agent state |
| `/debug/device` | Device connection info |
| `/debug/ui-tree` | Current UI elements |
| `/debug/screenshot` | Latest screenshot |
| `/debug/perception` | Perception pipeline state |
| `/debug/metrics` | Performance metrics |
| `/debug/errors/recent` | Last 100 errors |
| `/debug/config` | System configuration |
| `/debug/unified-logs` | **God-level logs (all sources)** |
| `/debug/unified-logs/timeline` | Timeline view |
| `/debug/unified-logs/trace/{id}` | All logs for trace |
| `/debug/unified-logs/export/html` | Interactive HTML viewer |
| `/debug/unified-logs/export/json` | JSON export |

## 📝 Example Session

```powershell
# 1. Start server
python main.py

# 2. Run a task (from Android or API)
# Watch terminal logs in real-time

# 3. Task failed? Get the trace ID from terminal
# Example: streaming_1770289719497

# 4. View everything that happened
curl "http://localhost:8000/api/v1/debug/unified-logs/trace/streaming_1770289719497"

# 5. Open interactive viewer
start "http://localhost:8000/api/v1/debug/unified-logs/export/html"

# 6. Check LangSmith (URL in logs)
# Click the LangSmith link from unified logs

# 7. Check command log
cd logs
notepad command_log_20260205_163839_498900.txt

# 8. Check failure screenshot (if exists)
start data/failure_screenshots/(ls *.png | Select -Last 1).Name
```

## 🎯 When to Use What

| Situation | Tool |
|-----------|------|
| Quick check | Terminal logs |
| "Why did AI do that?" | LangSmith + Command log |
| "What did AI see?" | Command log UI state |
| "Where did it fail?" | Unified logs by trace |
| "Show me the screen" | Failure screenshot |
| Performance issue | `/debug/metrics` + perf logs |
| Full investigation | HTML viewer (all sources) |

---

**You now have god-level debugging power!** 🔥

Every log source cross-references each other through trace IDs.
Terminal → LangSmith → Command Logs → Unified View = Complete picture.
