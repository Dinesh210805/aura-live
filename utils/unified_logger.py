"""
Unified logging system that aggregates all log sources.

Combines terminal logs, LangSmith traces, command logs, and error context
into a single searchable timeline for god-level debugging.
"""

import json
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from collections import defaultdict

from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class LogEntry:
    """Unified log entry from any source."""
    timestamp: float
    source: str  # "terminal", "langsmith", "command_log", "error", "perf"
    level: str  # "INFO", "ERROR", "WARNING", "DEBUG"
    message: str
    trace_id: Optional[str] = None
    request_id: Optional[str] = None
    langsmith_url: Optional[str] = None
    context: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)
    
    def format_terminal(self) -> str:
        """Format for terminal display."""
        ts = datetime.fromtimestamp(self.timestamp).strftime("%H:%M:%S.%f")[:-3]
        emoji = {
            "INFO": "ℹ️",
            "ERROR": "❌",
            "WARNING": "⚠️",
            "DEBUG": "🔍"
        }.get(self.level, "•")
        
        line = f"[{ts}] {emoji} [{self.source}] {self.message}"
        
        if self.langsmith_url:
            line += f"\n  🔗 LangSmith: {self.langsmith_url}"
        
        if self.trace_id:
            line += f"\n  🔖 Trace: {self.trace_id}"
            
        return line


class UnifiedLogger:
    """
    Aggregates logs from all sources into a unified timeline.
    
    Features:
    - Cross-references terminal logs, LangSmith traces, and command logs
    - Searchable by trace_id, request_id, or content
    - Timeline view of all events
    - Export to JSON or HTML
    """
    
    def __init__(self, log_dir: Path = None):
        self.log_dir = log_dir or Path("logs")
        self.log_dir.mkdir(exist_ok=True)
        self.entries: List[LogEntry] = []
        self.trace_map: Dict[str, List[LogEntry]] = defaultdict(list)
        
    def add(
        self,
        message: str,
        level: str = "INFO",
        source: str = "system",
        trace_id: Optional[str] = None,
        request_id: Optional[str] = None,
        langsmith_url: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        """Add a log entry."""
        entry = LogEntry(
            timestamp=time.time(),
            source=source,
            level=level,
            message=message,
            trace_id=trace_id,
            request_id=request_id,
            langsmith_url=langsmith_url,
            context=context
        )
        
        self.entries.append(entry)
        
        if trace_id:
            self.trace_map[trace_id].append(entry)
        
        # Also log to standard logger
        log_func = getattr(logger, level.lower(), logger.info)
        log_func(entry.format_terminal())
        
    def get_by_trace(self, trace_id: str) -> List[LogEntry]:
        """Get all logs for a specific trace."""
        return self.trace_map.get(trace_id, [])
    
    def search(
        self,
        query: str = None,
        level: str = None,
        source: str = None,
        since: float = None,
        limit: int = 100
    ) -> List[LogEntry]:
        """Search logs with filters."""
        results = self.entries
        
        if since:
            results = [e for e in results if e.timestamp >= since]
        
        if level:
            results = [e for e in results if e.level == level]
        
        if source:
            results = [e for e in results if e.source == source]
        
        if query:
            query_lower = query.lower()
            results = [e for e in results if query_lower in e.message.lower()]
        
        # Sort by timestamp, newest first
        results = sorted(results, key=lambda e: e.timestamp, reverse=True)
        
        return results[:limit]
    
    def export_json(self, filepath: Path = None) -> str:
        """Export all logs to JSON."""
        filepath = filepath or self.log_dir / f"unified_log_{int(time.time())}.json"
        
        data = {
            "exported_at": datetime.now().isoformat(),
            "total_entries": len(self.entries),
            "entries": [e.to_dict() for e in self.entries]
        }
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"📊 Exported {len(self.entries)} log entries to {filepath}")
        return str(filepath)
    
    def export_html(self, filepath: Path = None) -> str:
        """Export logs to interactive HTML viewer."""
        filepath = filepath or self.log_dir / f"unified_log_{int(time.time())}.html"
        
        # Group by trace_id
        traces = {}
        orphans = []
        
        for entry in sorted(self.entries, key=lambda e: e.timestamp):
            if entry.trace_id:
                if entry.trace_id not in traces:
                    traces[entry.trace_id] = []
                traces[entry.trace_id].append(entry)
            else:
                orphans.append(entry)
        
        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>AURA Unified Logs</title>
    <style>
        body {{ font-family: 'Courier New', monospace; background: #1e1e1e; color: #d4d4d4; padding: 20px; }}
        .header {{ background: #252526; padding: 20px; border-radius: 5px; margin-bottom: 20px; }}
        .stats {{ display: flex; gap: 20px; margin-top: 10px; }}
        .stat {{ background: #2d2d30; padding: 10px; border-radius: 3px; }}
        .search {{ margin-bottom: 20px; }}
        #searchBox {{ width: 100%; padding: 10px; background: #2d2d30; border: 1px solid #3e3e42; color: #d4d4d4; }}
        .trace {{ background: #252526; margin-bottom: 20px; padding: 15px; border-radius: 5px; border-left: 4px solid #007acc; }}
        .entry {{ padding: 8px; margin: 5px 0; border-left: 3px solid #333; }}
        .entry.INFO {{ border-left-color: #4ec9b0; }}
        .entry.ERROR {{ border-left-color: #f48771; }}
        .entry.WARNING {{ border-left-color: #dcdcaa; }}
        .entry.DEBUG {{ border-left-color: #808080; }}
        .timestamp {{ color: #858585; font-size: 0.9em; }}
        .source {{ color: #569cd6; font-weight: bold; }}
        .message {{ margin-left: 10px; }}
        .context {{ background: #2d2d30; padding: 5px; margin-top: 5px; font-size: 0.85em; color: #9cdcfe; }}
        .langsmith-link {{ color: #4ec9b0; text-decoration: none; }}
        .langsmith-link:hover {{ text-decoration: underline; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🔥 AURA God-Level Logs</h1>
        <div class="stats">
            <div class="stat">📝 Total Entries: {len(self.entries)}</div>
            <div class="stat">🔗 Traces: {len(traces)}</div>
            <div class="stat">❌ Errors: {sum(1 for e in self.entries if e.level == 'ERROR')}</div>
            <div class="stat">⚠️ Warnings: {sum(1 for e in self.entries if e.level == 'WARNING')}</div>
        </div>
    </div>
    
    <div class="search">
        <input type="text" id="searchBox" placeholder="🔍 Search logs..." onkeyup="filterLogs()">
    </div>
    
    <div id="logsContainer">
"""
        
        # Add trace groups
        for trace_id, entries in traces.items():
            html += f'<div class="trace" data-trace="{trace_id}">\n'
            html += f'<h3>🔖 Trace: {trace_id}</h3>\n'
            
            for entry in entries:
                ts = datetime.fromtimestamp(entry.timestamp).strftime("%H:%M:%S.%f")[:-3]
                html += f'<div class="entry {entry.level}">\n'
                html += f'  <span class="timestamp">[{ts}]</span>\n'
                html += f'  <span class="source">[{entry.source}]</span>\n'
                html += f'  <span class="message">{entry.message}</span>\n'
                
                if entry.langsmith_url:
                    html += f'  <div><a href="{entry.langsmith_url}" target="_blank" class="langsmith-link">🔗 View in LangSmith</a></div>\n'
                
                if entry.context:
                    html += f'  <div class="context">{json.dumps(entry.context, indent=2)}</div>\n'
                
                html += '</div>\n'
            
            html += '</div>\n'
        
        # Add orphan logs
        if orphans:
            html += '<div class="trace"><h3>🌐 Other Logs</h3>\n'
            for entry in orphans:
                ts = datetime.fromtimestamp(entry.timestamp).strftime("%H:%M:%S.%f")[:-3]
                html += f'<div class="entry {entry.level}">\n'
                html += f'  <span class="timestamp">[{ts}]</span>\n'
                html += f'  <span class="source">[{entry.source}]</span>\n'
                html += f'  <span class="message">{entry.message}</span>\n'
                html += '</div>\n'
            html += '</div>\n'
        
        html += """
    </div>
    
    <script>
        function filterLogs() {
            const query = document.getElementById('searchBox').value.toLowerCase();
            const entries = document.querySelectorAll('.entry');
            
            entries.forEach(entry => {
                const text = entry.textContent.toLowerCase();
                entry.style.display = text.includes(query) ? 'block' : 'none';
            });
        }
    </script>
</body>
</html>
"""
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html)
        
        logger.info(f"📊 Exported HTML log viewer to {filepath}")
        return str(filepath)
    
    def get_timeline(self, since: float = None, limit: int = 50) -> str:
        """Get a timeline view of recent logs."""
        entries = self.search(since=since, limit=limit)
        
        lines = ["", "=" * 80, "📅 LOG TIMELINE", "=" * 80, ""]
        
        for entry in reversed(entries):  # Show oldest first for timeline
            lines.append(entry.format_terminal())
            lines.append("")
        
        return "\n".join(lines)
    
    def clear(self):
        """Clear all entries."""
        self.entries.clear()
        self.trace_map.clear()


# Global instance
_unified_logger: Optional[UnifiedLogger] = None


def get_unified_logger() -> UnifiedLogger:
    """Get the global unified logger instance."""
    global _unified_logger
    if _unified_logger is None:
        _unified_logger = UnifiedLogger()
    return _unified_logger


def add_langsmith_link(trace_id: str, run_id: str, project: str = "aura-agent-visualization"):
    """
    Add a LangSmith trace link to logs.
    
    Args:
        trace_id: Your internal trace ID
        run_id: LangSmith run ID
        project: LangSmith project name
    """
    logger = get_unified_logger()
    url = f"https://smith.langchain.com/public/{project}/r/{run_id}"
    logger.add(
        message=f"LangSmith trace available",
        source="langsmith",
        trace_id=trace_id,
        langsmith_url=url
    )
