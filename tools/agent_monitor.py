"""
Agent Monitor (TUI) for AURA

A standalone, zero-backend-change dashboard to view agent logs and
task results in a clean, separate terminal window.

Usage examples (Windows cmd):
  1) Start your server and redirect logs to a file:
     > python main.py > aura.log 2>&1

  2) In another terminal, run the monitor to follow the log and show latest results:
     > python tools\\agent_monitor.py --log-file aura.log --runs-dir tools\\runs

Optional: use tools\\aura_client.py to send tasks and persist responses under tools\\runs.

This script does not modify or import any AURA backend modules; it only
reads files produced externally (log file, run result JSON files).
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from rich import box
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# ---------------
# Tail utilities
# ---------------


def tail_file(
    path: Path,
    out_queue: "queue.Queue[str]",
    stop_event: threading.Event,
    poll_interval: float = 0.2,
) -> None:
    """Tail a log file and push new lines into a queue.

    This does not lock the file; it simply seeks to the end and then
    reads new lines as they are written.
    """
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            # Seek to end
            f.seek(0, os.SEEK_END)
            while not stop_event.is_set():
                line = f.readline()
                if not line:
                    time.sleep(poll_interval)
                    continue
                out_queue.put(line.rstrip("\n"))
    except FileNotFoundError:
        # If file not found, periodically re-try until stop
        while not stop_event.is_set():
            time.sleep(1.0)
            if path.exists():
                return tail_file(path, out_queue, stop_event, poll_interval)


# ------------------
# Result file lookup
# ------------------


def find_latest_result(runs_dir: Path) -> Optional[Tuple[Path, Dict[str, Any]]]:
    """Return the most recent JSON result in runs_dir if any."""
    if not runs_dir.exists():
        return None
    json_files = sorted(
        runs_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    for jf in json_files:
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return jf, data
        except Exception:
            continue
    return None


# -----------------
# Parsing utilities
# -----------------


LOG_LINE_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} [^ ]+) - (?P<logger>[^ ]+) - (?P<level>[A-Z]+) - (?P<file>[^:]+):(?P<line>\d+) - (?P<msg>.*)$"
)


@dataclass
class ParsedLog:
    ts: str
    logger: str
    level: str
    file: str
    line: int
    msg: str


def parse_log_line(line: str) -> Optional[ParsedLog]:
    m = LOG_LINE_RE.match(line)
    if not m:
        return None
    try:
        return ParsedLog(
            ts=m.group("ts"),
            logger=m.group("logger"),
            level=m.group("level"),
            file=m.group("file"),
            line=int(m.group("line")),
            msg=m.group("msg"),
        )
    except Exception:
        return None


# -------------
# Rich building
# -------------


def build_header_panel(title: str) -> Panel:
    return Panel(Text(title, style="bold cyan"), border_style="cyan", padding=(0, 1))


def build_logs_table(logs: List[ParsedLog], max_rows: int = 30) -> Table:
    table = Table(box=box.SIMPLE_HEAVY)
    table.add_column("Time", style="dim", no_wrap=True)
    table.add_column("Level", style="bold")
    table.add_column("Logger", style="magenta")
    table.add_column("Message", style="white")
    for pl in logs[-max_rows:]:
        lvl_style = {
            "TRACE": "grey42",
            "DEBUG": "grey69",
            "INFO": "green",
            "WARNING": "yellow",
            "ERROR": "red",
            "CRITICAL": "bold red",
        }.get(pl.level, "white")
        table.add_row(pl.ts, Text(pl.level, style=lvl_style), pl.logger, pl.msg)
    return table


def summarize_result(result: Dict[str, Any]) -> Panel:
    status = result.get("status", "unknown")
    transcript = result.get("transcript", "")
    intent = result.get("intent") or {}
    spoken = result.get("spoken_response", "")
    error = result.get("error_message")
    exec_time = result.get("execution_time", 0.0)
    dbg = result.get("debug_info") or {}

    bullets: List[str] = []
    bullets.append(f"Status: [bold]{status}[/]")
    if exec_time:
        bullets.append(f"Time: {exec_time:.2f}s")
    if transcript:
        bullets.append(f"Transcript: {transcript}")
    if intent:
        action = intent.get("action") or intent.get("type") or "?"
        recipient = intent.get("recipient") or intent.get("target") or ""
        content = intent.get("content") or intent.get("text") or ""
        bullets.append(
            f"Intent: action={action} recipient={recipient} content={content}"
        )
    if error:
        bullets.append(f"Error: [red]{error}[/]")
    if spoken:
        bullets.append(f"Spoken: {spoken}")

    # Try to show workflow steps if present inside debug_info
    steps = None
    if isinstance(dbg, dict):
        steps = dbg.get("workflow_steps") or dbg.get("execution_path")
    step_lines: List[str] = []
    if isinstance(steps, list):
        for s in steps[-8:]:
            step_lines.append(f"- {s}")

    body = "\n".join(bullets)
    if step_lines:
        body += "\n\nWorkflow Steps (tail):\n" + "\n".join(step_lines)

    return Panel(body, title="Latest Task Result", border_style="green")


def build_layout(
    logs: List[ParsedLog], latest_result: Optional[Dict[str, Any]]
) -> Layout:
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="body"),
    )
    layout["header"].update(
        build_header_panel("AURA Agent Monitor (no backend changes)")
    )

    body = Layout()
    body.split_row(
        Layout(name="logs"),
        Layout(name="summary", ratio=2),
    )
    body["logs"].update(
        Panel(build_logs_table(logs), title="Live Logs (tail)", border_style="blue")
    )
    if latest_result:
        body["summary"].update(summarize_result(latest_result))
    else:
        body["summary"].update(
            Panel(
                "No results yet. Use tools/aura_client.py to send a task.",
                border_style="yellow",
            )
        )

    layout["body"].update(body)
    return layout


def main() -> None:
    parser = argparse.ArgumentParser(description="AURA Agent Monitor (TUI)")
    parser.add_argument(
        "--log-file",
        type=str,
        required=True,
        help="Path to the server log file (redirect stdout to here)",
    )
    parser.add_argument(
        "--runs-dir",
        type=str,
        default=str(Path("tools") / "runs"),
        help="Directory containing saved TaskResponse JSON files",
    )
    parser.add_argument(
        "--refresh", type=float, default=0.25, help="UI refresh rate in seconds"
    )
    args = parser.parse_args()

    log_path = Path(args.log_file)
    runs_dir = Path(args.runs_dir)
    runs_dir.mkdir(parents=True, exist_ok=True)

    # State buffers
    parsed_logs: List[ParsedLog] = []
    lines_queue: "queue.Queue[str]" = queue.Queue(maxsize=1000)
    stop_event = threading.Event()

    # Start tail thread
    t = threading.Thread(
        target=tail_file, args=(log_path, lines_queue, stop_event), daemon=True
    )
    t.start()

    console = Console()
    with Live(
        build_layout(parsed_logs, None),
        refresh_per_second=int(1 / args.refresh) if args.refresh > 0 else 4,
        console=console,
    ) as live:
        latest_result: Optional[Dict[str, Any]] = None
        last_result_path: Optional[Path] = None
        try:
            while True:
                # Drain any new log lines
                drained = 0
                while True:
                    try:
                        line = lines_queue.get_nowait()
                    except queue.Empty:
                        break
                    drained += 1
                    pl = parse_log_line(line)
                    if pl:
                        parsed_logs.append(pl)
                        # Keep memory bounded
                        if len(parsed_logs) > 500:
                            parsed_logs = parsed_logs[-500:]

                # Update latest result if new file appears
                lr = find_latest_result(runs_dir)
                if lr and lr[0] != last_result_path:
                    last_result_path, latest_result = lr

                live.update(build_layout(parsed_logs, latest_result))
                time.sleep(args.refresh)
        except KeyboardInterrupt:
            pass
        finally:
            stop_event.set()
            t.join(timeout=1.0)


if __name__ == "__main__":
    main()
