"""
AURA Live Demo Dashboard — served at /demo for judges and reviewers.

Shows a live auto-refreshing screenshot from the connected Android device,
current task status, the last 5 commands, and links to Cloud Storage
execution logs — without requiring an Android device to be physically present.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["Demo"])

_DEMO_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>AURA — Live Demo</title>
<style>
  :root {
    --bg: #0f1117; --card: #1a1d27; --accent: #4f8ef7;
    --green: #34d399; --red: #f87171; --text: #e2e8f0; --muted: #64748b;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text); font-family: system-ui, sans-serif; padding: 24px; }
  h1 { font-size: 1.6rem; font-weight: 700; color: var(--accent); }
  .subtitle { color: var(--muted); font-size: 0.85rem; margin-top: 4px; }
  .grid { display: grid; grid-template-columns: 360px 1fr; gap: 20px; margin-top: 24px; }
  .card { background: var(--card); border-radius: 12px; padding: 16px; }
  .card h2 { font-size: 0.9rem; font-weight: 600; color: var(--muted); text-transform: uppercase;
              letter-spacing: .05em; margin-bottom: 12px; }
  #screen-img { width: 100%; border-radius: 8px; border: 1px solid #2d3148;
                 display: block; min-height: 120px; background: #13151f; }
  #screen-ts  { font-size: 0.7rem; color: var(--muted); text-align: right; margin-top: 6px; }
  .badge { display: inline-block; border-radius: 9999px; padding: 2px 10px;
           font-size: 0.75rem; font-weight: 600; }
  .badge-ok  { background: rgba(52,211,153,.15); color: var(--green); }
  .badge-err { background: rgba(248,113,113,.15); color: var(--red); }
  .badge-idle{ background: rgba(100,116,139,.15); color: var(--muted); }
  #status-row { display: flex; align-items: center; gap: 10px; margin-bottom: 16px; }
  #status-dot { width: 10px; height: 10px; border-radius: 50%; background: var(--green);
                 box-shadow: 0 0 0 3px rgba(52,211,153,.25); }
  #cmd-list   { list-style: none; display: flex; flex-direction: column; gap: 8px; }
  #cmd-list li { background: #13151f; border-radius: 8px; padding: 10px 12px;
                  font-size: 0.85rem; border-left: 3px solid var(--accent); }
  #cmd-list .cmd-time { font-size: 0.7rem; color: var(--muted); }
  #log-links  { list-style: none; display: flex; flex-direction: column; gap: 8px; }
  #log-links li a { color: var(--accent); text-decoration: none; font-size: 0.82rem; }
  #log-links li a:hover { text-decoration: underline; }
  .refresh-note { font-size: 0.7rem; color: var(--muted); margin-top: 8px; }
  .arch-section { margin-top: 20px; }
  .arch-section pre { background: #13151f; border-radius: 8px; padding: 14px;
                       font-size: 0.72rem; overflow-x: auto; color: #a5b4fc; }
</style>
</head>
<body>
<h1>⚡ AURA — Autonomous UI Navigator</h1>
<p class="subtitle">Gemini Live Agent Challenge · Google ADK + Gemini 2.5 Flash + Cloud Run</p>

<div class="grid">
  <!-- Left column: live screenshot -->
  <div>
    <div class="card">
      <h2>Live Device Screen</h2>
      <img id="screen-img" src="/api/v1/device/screenshot" alt="Device screenshot"
           onerror="this.style.opacity='.3'"/>
      <p id="screen-ts" class="refresh-note">Auto-refreshes every 2 s</p>
    </div>
  </div>

  <!-- Right column: status + commands + logs -->
  <div style="display:flex;flex-direction:column;gap:16px;">
    <div class="card">
      <h2>System Status</h2>
      <div id="status-row">
        <span id="status-dot"></span>
        <span id="status-text">Checking…</span>
        <span id="status-badge" class="badge badge-idle">…</span>
      </div>
      <div style="font-size:.8rem;color:var(--muted)" id="status-meta"></div>
    </div>

    <div class="card">
      <h2>Recent Commands</h2>
      <ul id="cmd-list"><li style="color:var(--muted);font-size:.8rem;">No commands yet</li></ul>
    </div>

    <div class="card">
      <h2>Execution Logs (Cloud Storage)</h2>
      <ul id="log-links"><li style="color:var(--muted);font-size:.8rem;">No logs uploaded yet</li></ul>
      <p class="refresh-note">Logs appear here after GCS_LOGS_ENABLED=true is set</p>
    </div>

    <div class="card arch-section">
      <h2>Architecture</h2>
      <pre>
Android App ──WebSocket /ws/audio──▶ FastAPI Backend (Cloud Run)
                                          │
                              ┌───────────┼───────────────┐
                              ▼           ▼               ▼
                         Gemini 2.5   LangGraph       Edge-TTS
                          Flash VLM   (9 agents)      (TTS audio)
                          (primary)        │
                              │       Gemini 2.5 Flash (LLM)
                              │       Groq Whisper (STT)
                              │       YOLOv8 + SoM perception
                              ▼
                      OPA policy gate ──▶ Android gestures
                              │
                              ▼
                       Cloud Storage (execution logs)

/ws/live  ──▶  ADK Runner ──▶  Gemini Live (bidi audio+vision)
                    └──▶  execute_aura_task FunctionTool
      </pre>
    </div>
  </div>
</div>

<script>
const screenshotInterval = 2000;
const pollInterval = 5000;
let recentCmds = [];
let recentLogs = [];

function refreshScreenshot() {
  const img = document.getElementById('screen-img');
  img.src = '/api/v1/device/screenshot?t=' + Date.now();
  document.getElementById('screen-ts').textContent =
    'Last refreshed: ' + new Date().toLocaleTimeString();
}

async function pollHealth() {
  try {
    const r = await fetch('/health');
    const d = await r.json();
    const ok = r.ok;
    document.getElementById('status-dot').style.background =
      ok ? 'var(--green)' : 'var(--red)';
    document.getElementById('status-text').textContent =
      ok ? 'Backend online' : 'Backend unreachable';
    const badge = document.getElementById('status-badge');
    badge.textContent = d.status || (ok ? 'ok' : 'error');
    badge.className = 'badge ' + (ok ? 'badge-ok' : 'badge-err');
    document.getElementById('status-meta').textContent =
      d.version ? 'v' + d.version : '';
  } catch (_) {
    document.getElementById('status-dot').style.background = 'var(--red)';
    document.getElementById('status-text').textContent = 'Backend unreachable';
  }
}

function renderCmds() {
  const ul = document.getElementById('cmd-list');
  if (!recentCmds.length) return;
  ul.innerHTML = recentCmds.slice(-5).reverse().map(c =>
    '<li><div class="cmd-time">' + c.time + '</div>' + escapeHtml(c.text) + '</li>'
  ).join('');
}

function renderLogs() {
  const ul = document.getElementById('log-links');
  if (!recentLogs.length) return;
  ul.innerHTML = recentLogs.slice(-5).reverse().map(l =>
    '<li><a href="' + l.url + '" target="_blank" rel="noopener">' +
    escapeHtml(l.label) + '</a></li>'
  ).join('');
}

function escapeHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// Connect to task WebSocket for live command/log updates
function connectTaskWs() {
  const wsUrl = (location.protocol === 'https:' ? 'wss://' : 'ws://') +
                location.host + '/api/v1/tasks/ws';
  const ws = new WebSocket(wsUrl);
  ws.onmessage = (e) => {
    try {
      const d = JSON.parse(e.data);
      if (d.command) {
        recentCmds.push({ time: new Date().toLocaleTimeString(), text: d.command });
        renderCmds();
      }
      if (d.log_url) {
        recentLogs.push({ url: d.log_url, label: 'Log · ' + new Date().toLocaleTimeString() });
        renderLogs();
      }
    } catch (_) {}
  };
  ws.onclose = () => setTimeout(connectTaskWs, 3000);
}

setInterval(refreshScreenshot, screenshotInterval);
setInterval(pollHealth, pollInterval);
pollHealth();
connectTaskWs();
</script>
</body>
</html>"""


@router.get("/demo", response_class=HTMLResponse, include_in_schema=False)
async def demo_dashboard(request: Request):
    """
    Live demo dashboard for judges.

    Shows the connected Android device screen (auto-refreshes every 2 s),
    system status, recent commands, and links to Cloud Storage execution logs.
    No authentication required so judges can access it without credentials.
    """
    logger.info(f"Demo dashboard accessed from {request.client.host if request.client else 'unknown'}")
    return HTMLResponse(content=_DEMO_HTML)
