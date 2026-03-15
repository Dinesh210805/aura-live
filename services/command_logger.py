"""
Command Logger Service - Logs all commands, LLM interactions, and gestures to timestamped files.

This service captures:
- Command inputs (user requests)
- LLM inputs and outputs with call counts
- Gesture executions with sent/executed timestamps
- Timestamps for all operations

All logs are saved to the logs/ folder with timestamps for easy reference.
"""

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from utils.logger import get_logger, log_agent_output

logger = get_logger(__name__)

# Import unified logger for cross-referencing
try:
    from utils.unified_logger import get_unified_logger
    UNIFIED_LOGGER_AVAILABLE = True
except ImportError:
    UNIFIED_LOGGER_AVAILABLE = False

# Import LangSmith integration
try:
    from utils.langsmith_integration import log_langsmith_trace, capture_langsmith_context
    LANGSMITH_INTEGRATION_AVAILABLE = True
except ImportError:
    LANGSMITH_INTEGRATION_AVAILABLE = False

try:
    from services.logcat_capture import get_logcat_capture
    LOGCAT_AVAILABLE = True
except ImportError:
    LOGCAT_AVAILABLE = False


class CommandLogger:
    """Logs all command processing, LLM interactions, and gesture executions."""

    def __init__(self, log_dir: str = "logs", execution_id: str = None):
        """
        Initialize the command logger.
        
        Args:
            log_dir: Directory where log files will be stored
            execution_id: Unique execution identifier for this log file
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        
        # Create execution-specific log file with microsecond precision
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        self.execution_id = execution_id or timestamp
        self.log_file = self.log_dir / f"command_log_{timestamp}.html"
        self.txt_log_file = self.log_dir / f"command_log_{timestamp}.txt"
        self._screenshot_dir = self.log_dir / f"screenshots_{timestamp}"
        
        # Counters for tracking calls
        self.llm_call_count = 0
        self.vlm_call_count = 0
        self.gesture_count = 0
        self.total_llm_tokens = 0
        self.total_execution_time = 0.0
        self.start_time = datetime.now()
        
        # Connect to unified logger
        self.unified_logger = None
        if UNIFIED_LOGGER_AVAILABLE:
            try:
                self.unified_logger = get_unified_logger()
            except Exception as e:
                logger.warning(f"Could not initialize unified logger: {e}")
        
        logger.info(f"📝 Command logger initialized: {self.log_file}")
        
        # Write header (placeholder for counts - will be updated at end)
        self._write_header()
        self._write_txt_header()
        
        # Start terminal log capture for this request
        self._terminal_log_file = None
        self._terminal_file_handler = None
        self._start_terminal_log_capture(timestamp)

        if LOGCAT_AVAILABLE:
            try:
                get_logcat_capture().start()
            except Exception:
                pass

    def log_screenshot(self, label: str, base64_data: str, ext: str = "png") -> str:
        """Save a base64-encoded screenshot to the screenshots folder.
        Returns the path (relative to log_dir) suitable for HTML <img src>.
        """
        try:
            import base64 as _b64
            self._screenshot_dir.mkdir(exist_ok=True)
            counter = len(list(self._screenshot_dir.glob("*.png")) + list(self._screenshot_dir.glob("*.jpg"))) + 1
            safe_label = "".join(c if c.isalnum() or c in "-_" else "_" for c in label)[:40]
            filename = f"{counter:03d}_{safe_label}.{ext}"
            path = self._screenshot_dir / filename
            data = _b64.b64decode(base64_data)
            with open(path, "wb") as f:
                f.write(data)
            # Return relative path from log_dir for HTML src attribute
            return path.relative_to(self.log_dir).as_posix()
        except Exception:
            return ""

    def log_annotated_screenshot(self, label: str, base64_data: str, elements: list, target_match: dict = None) -> str:
        """Save a bounding-box annotated screenshot using UI tree element data."""
        try:
            import base64 as _b64
            import numpy as np
            import cv2
            self._screenshot_dir.mkdir(exist_ok=True)
            counter = len(list(self._screenshot_dir.glob("*.png")) + list(self._screenshot_dir.glob("*.jpg"))) + 1
            safe_label = "".join(c if c.isalnum() or c in "-_" else "_" for c in label)[:40]
            path = self._screenshot_dir / f"{counter:03d}_{safe_label}.png"
            arr = np.frombuffer(_b64.b64decode(base64_data), dtype=np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img is None:
                return ""
            screen_area = img.shape[0] * img.shape[1]
            tx = target_match.get("x") if target_match else None
            ty = target_match.get("y") if target_match else None
            font = cv2.FONT_HERSHEY_SIMPLEX
            for i, el in enumerate(elements):
                b = el.get("bounds") or el.get("visibleBounds") or el.get("boundsInScreen") or {}
                left, top, right, bottom = b.get("left", 0), b.get("top", 0), b.get("right", 0), b.get("bottom", 0)
                if right <= left or bottom <= top:
                    continue
                if (right - left) * (bottom - top) > screen_area * 0.6:
                    continue  # skip full-screen ghost containers
                cx, cy = (left + right) // 2, (top + bottom) // 2
                is_target = tx is not None and cx == tx and cy == ty
                if is_target:
                    color, thickness = (0, 170, 255), 3   # amber
                elif el.get("clickable"):
                    color, thickness = (60, 200, 80), 2   # green
                elif el.get("scrollable"):
                    color, thickness = (200, 120, 40), 1  # blue
                else:
                    color, thickness = (100, 110, 130), 1  # gray
                cv2.rectangle(img, (left, top), (right, bottom), color, thickness)
                lbl = str(i + 1)
                short = ((el.get("text") or "").strip() or (el.get("contentDescription") or "").strip())[:18]
                if short:
                    lbl += f" {short}"
                (tw, th), bl = cv2.getTextSize(lbl, font, 0.6, 1)
                lx, ly = left + 2, top + th + 5
                cv2.rectangle(img, (lx - 2, ly - th - 4), (lx + tw + 2, ly + bl + 1), (10, 10, 10), -1)
                cv2.putText(img, lbl, (lx, ly), font, 0.6, color, 1, cv2.LINE_AA)
            with open(path, "wb") as f:
                f.write(cv2.imencode(".png", img)[1].tobytes())
            return path.relative_to(self.log_dir).as_posix()
        except Exception:
            return ""

    def log_annotated_gesture_screenshot(self, gesture_type: str, gesture_data: dict, base64_data: str) -> str:
        """Draw gesture annotation (tap circle, swipe arrow, etc.) onto a screenshot."""
        try:
            import base64 as _b64
            import numpy as np
            import cv2
            self._screenshot_dir.mkdir(exist_ok=True)
            counter = len(list(self._screenshot_dir.glob("*.png")) + list(self._screenshot_dir.glob("*.jpg"))) + 1
            path = self._screenshot_dir / f"{counter:03d}_gesture_{gesture_type}.png"
            arr = np.frombuffer(_b64.b64decode(base64_data), dtype=np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img is None:
                return ""
            h, w = img.shape[:2]
            font = cv2.FONT_HERSHEY_SIMPLEX
            GREEN = (50, 220, 80)
            CYAN  = (220, 220, 50)
            AMBER = (50, 160, 255)
            WHITE = (220, 220, 220)
            gtype = gesture_type.lower()
            if gtype in ("tap", "click", "press", "double_tap", "long_press"):
                x = int(gesture_data.get("x", 0))
                y = int(gesture_data.get("y", 0))
                color = AMBER if gtype == "long_press" else (CYAN if gtype == "double_tap" else GREEN)
                cv2.line(img, (x - 40, y), (x + 40, y), color, 2, cv2.LINE_AA)
                cv2.line(img, (x, y - 40), (x, y + 40), color, 2, cv2.LINE_AA)
                cv2.circle(img, (x, y), 28, color, 2, cv2.LINE_AA)
                cv2.circle(img, (x, y), 7, color, -1, cv2.LINE_AA)
                if gtype == "double_tap":
                    cv2.circle(img, (x, y), 40, color, 1, cv2.LINE_AA)
                label = {"tap": "TAP", "click": "TAP", "press": "TAP",
                         "double_tap": "x2 TAP", "long_press": "HOLD"}.get(gtype, "TAP")
                (tw, th), _ = cv2.getTextSize(label, font, 0.65, 2)
                lx = min(x + 34, w - tw - 4)
                ly = max(y - 10, th + 4)
                cv2.rectangle(img, (lx - 2, ly - th - 2), (lx + tw + 2, ly + 4), (10, 10, 10), -1)
                cv2.putText(img, label, (lx, ly), font, 0.65, color, 2, cv2.LINE_AA)
            elif gtype in ("swipe", "scroll", "scroll_down", "scroll_up", "scroll_left", "scroll_right"):
                x1 = int(gesture_data.get("x1", gesture_data.get("startX", w // 2)))
                y1 = int(gesture_data.get("y1", gesture_data.get("startY", h // 2)))
                x2 = int(gesture_data.get("x2", gesture_data.get("endX", w // 2)))
                y2 = int(gesture_data.get("y2", gesture_data.get("endY", h // 2)))
                cv2.circle(img, (x1, y1), 10, CYAN, -1, cv2.LINE_AA)
                cv2.arrowedLine(img, (x1, y1), (x2, y2), CYAN, 3, cv2.LINE_AA, tipLength=0.12)
                cv2.circle(img, (x2, y2), 8, WHITE, 2, cv2.LINE_AA)
                dist = int(((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5)
                label = f"SWIPE {dist}px"
                mid = ((x1 + x2) // 2, (y1 + y2) // 2)
                (tw, th), _ = cv2.getTextSize(label, font, 0.55, 1)
                lx = min(mid[0] + 6, w - tw - 4)
                ly = max(mid[1] - 6, th + 4)
                cv2.rectangle(img, (lx - 2, ly - th - 2), (lx + tw + 2, ly + 4), (10, 10, 10), -1)
                cv2.putText(img, label, (lx, ly), font, 0.55, CYAN, 1, cv2.LINE_AA)
            elif gtype in ("type", "input", "type_text"):
                fx = int(gesture_data.get("x", 0))
                fy = int(gesture_data.get("y", 0))
                if fx or fy:
                    cv2.circle(img, (fx, fy), 16, GREEN, 2, cv2.LINE_AA)
                    cv2.circle(img, (fx, fy), 5, GREEN, -1, cv2.LINE_AA)
                text_val = str(gesture_data.get("text", gesture_data.get("value", "")))[:30]
                label = f'TYPE: "{text_val}"'
                (tw, th), _ = cv2.getTextSize(label, font, 0.55, 1)
                lx, ly = 16, h - 24
                cv2.rectangle(img, (lx - 4, ly - th - 4), (lx + tw + 4, ly + 6), (10, 10, 10), -1)
                cv2.putText(img, label, (lx, ly), font, 0.55, GREEN, 1, cv2.LINE_AA)
            with open(path, "wb") as f:
                f.write(cv2.imencode(".png", img)[1].tobytes())
            return path.relative_to(self.log_dir).as_posix()
        except Exception:
            return ""

    def _start_terminal_log_capture(self, timestamp: str):
        """Add a FileHandler to every active logger to capture all terminal output.
        
        The _TeeWriter / stdout-tee approach doesn't work because EnhancedHandler
        stores a direct reference to sys.stdout captured at __init__ time, so
        replacing sys.stdout later has no effect.  Adding a FileHandler directly
        to each logger is the only reliable way to capture all log output.
        """
        self.log_dir.mkdir(exist_ok=True)
        terminal_log_path = self.log_dir / f"command_log_{timestamp}.log"
        try:
            formatter = logging.Formatter(
                "%(asctime)s │ %(levelname)-5s │ %(name)-8s │ %(message)s",
                datefmt="%H:%M:%S",
            )
            handler = logging.FileHandler(terminal_log_path, encoding="utf-8")
            handler.setLevel(logging.DEBUG)
            handler.setFormatter(formatter)
            
            # Add to root logger and every registered logger
            root = logging.getLogger()
            root.addHandler(handler)
            for log_name in list(logging.Logger.manager.loggerDict.keys()):
                logging.getLogger(log_name).addHandler(handler)
            
            self._terminal_file_handler = handler
            self._terminal_log_file = terminal_log_path
        except Exception as e:
            logger.warning(f"Could not start terminal log capture: {e}")
    
    def _stop_terminal_log_capture(self):
        """Remove the terminal capture FileHandler from all loggers."""
        handler = getattr(self, "_terminal_file_handler", None)
        if not handler:
            return
        
        root = logging.getLogger()
        root.removeHandler(handler)
        for log_name in list(logging.Logger.manager.loggerDict.keys()):
            logging.getLogger(log_name).removeHandler(handler)
        
        try:
            handler.close()
        except Exception:
            pass
        self._terminal_file_handler = None

    def _write_header(self):
        """Write HTML log file header."""
        css = """
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');
        :root {
            --bg: #080c10;
            --surface: #0d1117;
            --surface2: #131920;
            --border: #1e2733;
            --border2: #2a3441;
            --text: #cdd9e5;
            --muted: #636e7b;
            --muted2: #8b949e;
            --blue: #4493f8;
            --green: #3fb950;
            --orange: #d29922;
            --red: #f85149;
            --purple: #a371f7;
            --cyan: #39c5cf;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { background: var(--bg); color: var(--text); font-family: 'Inter', 'Segoe UI', sans-serif; font-size: 13px; padding: 60px 24px 40px; line-height: 1.5; max-width: 1400px; margin: 0 auto; }
        h1 { font-size: 20px; color: var(--blue); margin-bottom: 4px; font-weight: 600; letter-spacing: -0.3px; }
        .meta { color: var(--muted); font-size: 11px; }
        .page-header { margin-bottom: 16px; }

        /* ── Summary panel ── */
        #summary { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 18px 24px; margin-bottom: 20px; display: flex; gap: 28px; flex-wrap: wrap; align-items: flex-start; }
        .sum-block { display: flex; flex-direction: column; gap: 4px; min-width: 80px; }
        .sum-label { color: var(--muted); font-size: 10px; text-transform: uppercase; letter-spacing: 0.8px; font-weight: 600; }
        .sum-val { font-size: 20px; font-weight: 700; color: var(--text); line-height: 1.2; }
        .sum-val.status-FAILED { color: var(--red); }
        .sum-val.status-completed { color: var(--green); }
        .sum-val.status-failed { color: var(--red); }

        /* ── Entries ── */
        .entry { border-radius: 8px; margin-bottom: 8px; overflow: hidden; border: 1px solid var(--border); transition: box-shadow 0.15s; }
        .entry:hover { box-shadow: 0 0 0 1px var(--border2); }
        .entry-header { display: flex; align-items: center; gap: 10px; padding: 10px 16px; font-weight: 600; font-size: 12px; border-bottom: 1px solid var(--border); cursor: pointer; user-select: none; }
        .entry-header:hover { filter: brightness(1.12); }
        .entry-body { background: var(--surface); padding: 12px 16px; }
        .entry-body.collapsed { display: none; }
        .chevron { margin-left: auto; font-size: 10px; opacity: 0.4; transition: transform 0.15s ease; display: inline-block; flex-shrink: 0; }
        .chevron.rotated { transform: rotate(-90deg); }
        .entry-COMMAND .entry-header { background: #0f1e3a; border-left: 3px solid var(--blue); }
        .entry-LLM .entry-header { background: #150f2a; border-left: 3px solid var(--purple); }
        .entry-VLM .entry-header { background: #1e1a12; border-left: 3px solid var(--orange); }
        .entry-GESTURE .entry-header { background: #0a1f12; border-left: 3px solid var(--green); }
        .entry-GRAPH_EXECUTION .entry-header { background: #111520; border-left: 3px solid var(--muted); }
        .entry-LOGCAT .entry-header { background: #0d1510; border-left: 3px solid #2ea043; }
        .entry-ERROR .entry-header { background: #200a0a; border-left: 3px solid var(--red); }
        .entry-AGENT_DECISION.decision-PLAN_CREATED .entry-header { background: #111530; border-left: 3px solid var(--blue); }
        .entry-AGENT_DECISION.decision-SUBGOAL_START .entry-header { background: #0a1624; border-left: 3px solid var(--cyan); }
        .entry-AGENT_DECISION.decision-SUBGOAL_COMPLETE .entry-header { background: #0a1f12; border-left: 3px solid var(--green); }
        .entry-AGENT_DECISION.decision-ACTION_FAILED .entry-header { background: #200a0a; border-left: 3px solid var(--red); }
        .entry-AGENT_DECISION.decision-PERCEPTION_RESULT .entry-header { background: #0a1820; border-left: 3px solid var(--cyan); }
        .entry-AGENT_DECISION.decision-POST_ACTION_SCREENSHOT .entry-header { background: #111530; border-left: 3px solid var(--purple); }
        .entry-AGENT_DECISION.decision-VERIFICATION_FAILED .entry-header { background: #1e1608; border-left: 3px solid var(--orange); }
        .entry-AGENT_DECISION.decision-BUDGET_EXHAUSTED .entry-header { background: #200a0a; border-left: 3px solid var(--red); }
        .entry-AGENT_DECISION.decision-LOOP_DETECTED .entry-header { background: #200a0a; border-left: 3px solid var(--red); }
        .entry-AGENT_DECISION.decision-REPLAN .entry-header { background: #180a2a; border-left: 3px solid var(--purple); }
        .entry-AGENT_DECISION.decision-INTENT_PARSED .entry-header { background: #0a1624; border-left: 3px solid var(--cyan); }

        .ts { color: var(--muted); font-size: 11px; font-weight: 400; font-family: 'JetBrains Mono', monospace; }
        .badge { font-size: 10px; padding: 2px 7px; border-radius: 4px; font-weight: 700; letter-spacing: 0.6px; text-transform: uppercase; }
        .badge-LLM { background: #2d1f5e; color: #c4a7ff; border: 1px solid #4a2f9a; }
        .badge-VLM { background: #3d2800; color: #f0a500; border: 1px solid #6b4800; }
        .badge-GESTURE { background: #0d2d17; color: #56d364; border: 1px solid #1b5e30; }
        .badge-COMMAND { background: #0d2050; color: #79c0ff; border: 1px solid #1a3a8f; }
        .badge-AGENT { background: #1a2030; color: #79c0ff; border: 1px solid #2a3548; }
        .badge-GRAPH { background: #1a1f28; color: var(--muted2); border: 1px solid #2a3040; }
        .badge-ERROR { background: #4a0a0a; color: #ff8080; border: 1px solid #8a1a1a; }
        .provider-tag { color: var(--muted2); font-size: 11px; font-weight: 400; }

        /* ── Key-value rows ── */
        .kv-row { display: flex; gap: 0; margin: 3px 0; min-height: 22px; }
        .kv-key { color: var(--muted); min-width: 130px; font-size: 11px; padding-top: 1px; text-transform: uppercase; letter-spacing: 0.4px; font-weight: 500; }
        .kv-val { color: var(--text); font-size: 12px; }
        .kv-val.ok { color: var(--green); font-weight: 600; }
        .kv-val.fail { color: var(--red); font-weight: 600; }
        .divider { border: none; border-top: 1px solid var(--border); margin: 10px 0; }

        /* ── LLM response box ── */
        .agent-box { background: #06090d; border: 1px solid var(--border2); border-left: 3px solid #3a2a6a; border-radius: 6px; padding: 10px 14px; margin: 8px 0; white-space: pre-wrap; font-family: 'JetBrains Mono', monospace; font-size: 11.5px; line-height: 1.65; color: #adbac7; }
        .token-row { color: var(--muted2); font-size: 11px; margin-top: 8px; padding: 5px 8px; background: var(--surface2); border-radius: 4px; display: inline-block; }

        /* ── Prompt box ── */
        .prompt-section { margin: 8px 0; }
        .prompt-toggle { background: #0d1a2e; border: 1px solid #1e3a5a; border-radius: 4px; padding: 5px 12px; cursor: pointer; font-size: 11px; color: #4493f8; font-family: 'JetBrains Mono', monospace; width: 100%; text-align: left; letter-spacing: 0.2px; }
        .prompt-toggle:hover { background: #132040; color: #79c0ff; }
        .prompt-box { background: #04070c; border: 1px solid #1e3a5a; border-radius: 0 0 6px 6px; padding: 12px 16px; margin: 0 0 6px 0; white-space: pre-wrap; font-family: 'JetBrains Mono', monospace; font-size: 11px; line-height: 1.65; color: #7cb8fa; word-break: break-word; max-height: none; overflow-x: auto; }

        /* ── JSON blocks ── */
        .json-section { margin: 8px 0; }
        .json-label { font-size: 10px; text-transform: uppercase; letter-spacing: 0.6px; color: var(--muted); font-weight: 600; margin-bottom: 4px; }
        pre.json { background: #06090d; border: 1px solid var(--border); border-radius: 6px; padding: 10px 14px; font-size: 11px; overflow-x: auto; color: #adbac7; margin: 0; font-family: 'JetBrains Mono', monospace; line-height: 1.55; }
        pre.logcat { background: #06090d; border: 1px solid var(--border); border-radius: 6px; padding: 10px 14px; font-size: 10.5px; overflow-x: auto; color: #8b9dab; margin: 0; font-family: 'JetBrains Mono', monospace; line-height: 1.6; white-space: pre-wrap; word-break: break-word; }

        /* ── Screenshots ── */
        .screenshot-row { margin: 10px 0; }
        .screenshot-row img { max-width: 320px; border-radius: 8px; border: 1px solid var(--border2); display: block; }
        .screenshot-label { color: var(--muted); font-size: 10px; text-transform: uppercase; letter-spacing: 0.6px; margin-bottom: 6px; font-weight: 600; }

        /* ── Elements table ── */
        .elements-section { margin: 10px 0; }
        .elements-section-title { font-size: 10px; text-transform: uppercase; letter-spacing: 0.6px; color: var(--muted2); font-weight: 600; margin-bottom: 6px; padding: 5px 10px; background: var(--surface2); border-radius: 4px; display: block; }
        .elements-table { width: 100%; border-collapse: collapse; font-size: 11px; }
        .elements-table thead tr { background: #06090d; }
        .elements-table th { text-align: left; padding: 5px 10px; color: var(--muted); font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; font-weight: 600; border-bottom: 1px solid var(--border2); white-space: nowrap; }
        .elements-table td { padding: 4px 10px; border-bottom: 1px solid var(--border); vertical-align: middle; color: var(--text); font-size: 11px; }
        .elements-table tbody tr:nth-child(even) td { background: rgba(255,255,255,0.018); }
        .elements-table tr:hover td { background: var(--surface2); }
        .elements-table .col-idx { color: var(--muted); font-size: 10px; text-align: right; padding-right: 8px; width: 28px; }
        .elements-table .col-text { color: #79c0ff; font-weight: 500; max-width: 180px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .elements-table .col-desc { color: var(--muted2); font-style: italic; max-width: 160px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .elements-table .col-class { color: var(--muted2); font-family: 'JetBrains Mono', monospace; font-size: 10px; }
        .elements-table .col-res { color: var(--muted); font-family: 'JetBrains Mono', monospace; font-size: 10px; }
        .elements-table .col-bounds { color: var(--muted); font-family: 'JetBrains Mono', monospace; font-size: 10px; white-space: nowrap; }
        .elements-table .col-center { color: #f0a500; font-family: 'JetBrains Mono', monospace; font-size: 10px; white-space: nowrap; font-weight: 600; }
        .row-target td { background: #1f1200 !important; outline: 1px solid #d29922; }
        .row-target .col-center { color: #ffcc00 !important; }
        .row-target-label { display: inline-block; font-size: 9px; padding: 1px 6px; border-radius: 3px; background: #4a2b00; color: #ffcc00; border: 1px solid #8a5200; font-weight: 700; margin-left: 4px; }
        .tag { display: inline-block; font-size: 9px; padding: 1px 6px; border-radius: 3px; margin: 1px; font-weight: 600; letter-spacing: 0.3px; white-space: nowrap; }
        .tag-clickable { background: #0d2d17; color: #56d364; border: 1px solid #1b4a25; }
        .tag-scrollable { background: #0d1f35; color: #58a6ff; border: 1px solid #1a3560; }
        .tag-editable { background: #2a1800; color: #f0a500; border: 1px solid #4a3000; }
        .tag-focused { background: #1a0d30; color: #c4a7ff; border: 1px solid #3a1f60; }
        .tag-disabled { background: #1a1a1a; color: #555; border: 1px solid #333; }

        .match-found { color: var(--green); font-weight: 600; }
        .match-none { color: var(--red); }
        .debug-line { color: var(--muted); font-size: 11px; padding: 1px 12px; }
        .debug-line:hover { background: var(--surface2); }
        .hidden { display: none; }

        /* ── Logcat coloring ── */
        .lc-E { color: #f85149; }
        .lc-W { color: #d29922; }
        .lc-I { color: #58a6ff; }
        .lc-D { color: #8b949e; }

        /* ── Sticky top bar ── */
        #topbar { position: fixed; top: 0; left: 0; right: 0; z-index: 200; background: #060a0d; border-bottom: 1px solid var(--border); padding: 7px 24px; display: flex; align-items: center; gap: 14px; }
        #topbar-title { color: var(--blue); font-weight: 700; font-size: 13px; white-space: nowrap; }
        #topbar-exec { color: var(--muted); font-family: 'JetBrains Mono', monospace; font-size: 10px; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .ctrl-btn { background: var(--surface2); border: 1px solid var(--border2); border-radius: 5px; color: var(--muted2); font-size: 11px; padding: 3px 10px; cursor: pointer; font-family: 'Inter', sans-serif; transition: background 0.15s, color 0.15s; white-space: nowrap; }
        .ctrl-btn:hover { background: var(--border); color: var(--text); }

        /* ── Elapsed time badge ── */
        .elapsed { font-size: 10px; color: var(--muted); font-family: 'JetBrains Mono', monospace; background: rgba(255,255,255,0.04); padding: 1px 6px; border-radius: 3px; white-space: nowrap; margin-left: 4px; }

        /* ── VLM response box (amber tint, distinct from LLM purple) ── */
        .vlm-box { background: #0e0900; border: 1px solid #4a3008; border-left: 3px solid #8a5a00; border-radius: 6px; padding: 10px 14px; margin: 8px 0; white-space: pre-wrap; font-family: 'JetBrains Mono', monospace; font-size: 11.5px; line-height: 1.65; color: #d4b46a; }

        /* ── Screenshot grid (side-by-side layout) ── */
        .screenshot-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 12px; margin: 10px 0; }
        .screenshot-grid .screenshot-row img { max-width: 100%; }

        /* ── Gesture parallel layout (details + annotated screenshot) ── */
        .gesture-layout { display: flex; gap: 16px; align-items: flex-start; }
        .gesture-details { flex: 1; min-width: 0; }
        .gesture-screenshot { flex-shrink: 0; width: 260px; }
        .gesture-screenshot img { max-width: 100%; border-radius: 8px; border: 2px solid var(--green); display: block; }
        .gesture-screenshot .screenshot-label { color: var(--green); font-size: 10px; text-transform: uppercase; letter-spacing: 0.6px; margin-bottom: 6px; font-weight: 600; }

        /* ── VLM parallel layout (response + input image side-by-side) ── */
        .vlm-layout { display: flex; gap: 16px; align-items: flex-start; }
        .vlm-content { flex: 1; min-width: 0; }
        .vlm-screenshot { flex-shrink: 0; width: 260px; }
        .vlm-screenshot img { max-width: 100%; border-radius: 8px; border: 1px solid var(--orange); display: block; }
        .vlm-screenshot .screenshot-label { color: var(--orange); font-size: 10px; text-transform: uppercase; letter-spacing: 0.6px; margin-bottom: 6px; font-weight: 600; }
        """
        js = """
        function toggle(id) {
            var el = document.getElementById(id);
            if (el) el.classList.toggle('hidden');
        }
        function toggleEntry(bodyId) {
            var body = document.getElementById(bodyId);
            if (!body) return;
            body.classList.toggle('collapsed');
            var header = body.previousElementSibling;
            if (header) {
                var chev = header.querySelector('.chevron');
                if (chev) chev.classList.toggle('rotated');
            }
        }
        function collapseAll() {
            document.querySelectorAll('.entry-body').forEach(function(b) {
                b.classList.add('collapsed');
                var h = b.previousElementSibling;
                if (h) { var c = h.querySelector('.chevron'); if (c) c.classList.add('rotated'); }
            });
        }
        function expandAll() {
            document.querySelectorAll('.entry-body').forEach(function(b) {
                b.classList.remove('collapsed');
                var h = b.previousElementSibling;
                if (h) { var c = h.querySelector('.chevron'); if (c) c.classList.remove('rotated'); }
            });
        }
        """
        with open(self.log_file, "w", encoding="utf-8") as f:
            f.write(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AURA Log &mdash; {self.execution_id}</title>
<style>{css}</style>
<script>{js}</script>
</head>
<body>
<div id="topbar">
  <span id="topbar-title">&#x1F916; AURA Log</span>
  <span id="topbar-exec">{self.execution_id}</span>
  <div style="margin-left:auto;display:flex;gap:8px;">
    <button class="ctrl-btn" onclick="expandAll()">&#x25BC; Expand all</button>
    <button class="ctrl-btn" onclick="collapseAll()">&#x25B6; Collapse all</button>
  </div>
</div>
<div class="page-header">
<h1>&#x1F916; AURA Command Log</h1>
<div class="meta">Execution: <strong>{self.execution_id}</strong> &nbsp;|&nbsp; Started: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}</div>
</div>
[SUMMARY_PLACEHOLDER]
<div id="entries">
""")
    
    def log_command(
        self, 
        command: str, 
        input_type: str = "voice", 
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Log a user command/request.
        
        Args:
            command: The command text
            input_type: Type of input (voice, text, etc.)
            session_id: Optional session identifier
            metadata: Additional metadata
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        
        entry = {
            "timestamp": timestamp,
            "type": "COMMAND",
            "input_type": input_type,
            "command": command,
            "session_id": session_id,
            "metadata": metadata or {}
        }
        
        self._write_entry(entry)
        logger.info(f"📋 Logged command: {command[:50]}...")
        
        # Send to unified logger
        if self.unified_logger:
            self.unified_logger.add(
                message=f"Command: {command[:100]}",
                level="INFO",
                source="command_log",
                trace_id=self.execution_id,
                context={"input_type": input_type, "session_id": session_id}
            )
    
    def log_llm_call(
        self,
        prompt: str,
        response: str,
        provider: str,
        model: str,
        agent: Optional[str] = None,
        token_usage: Optional[Dict[str, int]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        is_vlm: bool = False
    ):
        """
        Log an LLM interaction.
        
        Args:
            prompt: Input prompt to LLM
            response: LLM response
            provider: LLM provider (groq, gemini, etc.)
            model: Model name
            agent: Agent making the call
            token_usage: Token usage stats
            metadata: Additional metadata
            is_vlm: Whether this is a Vision-Language Model call
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        
        # Update counters
        if is_vlm:
            self.vlm_call_count += 1
            call_type = "VLM"
        else:
            self.llm_call_count += 1
            call_type = "LLM"
        
        if token_usage:
            self.total_llm_tokens += token_usage.get("total_tokens", 0)
        
        entry = {
            "timestamp": timestamp,
            "type": call_type,
            "call_number": self.vlm_call_count if is_vlm else self.llm_call_count,
            "agent": agent,
            "provider": provider,
            "model": model,
            "prompt": prompt,
            "response": response,
            "token_usage": token_usage or {},
            "metadata": metadata or {}
        }
        
        self._write_entry(entry)
        
        # Print CrewAI-style agent output box to terminal
        agent_name = agent or call_type
        log_agent_output(agent_name, response, provider, model)
        
        logger.info(f"🤖 Logged {call_type} call #{entry['call_number']}: {agent or 'unknown'} via {provider}")
        
        # Capture LangSmith run context
        langsmith_url = None
        if LANGSMITH_INTEGRATION_AVAILABLE:
            try:
                ls_context = capture_langsmith_context()
                if ls_context and ls_context.get("run_id"):
                    from utils.langsmith_integration import get_langsmith_url
                    langsmith_url = get_langsmith_url(ls_context["run_id"])
                    logger.debug(f"🔗 LangSmith: {langsmith_url}")
            except Exception as e:
                logger.debug(f"Could not capture LangSmith context: {e}")
        
        # Send to unified logger
        if self.unified_logger:
            self.unified_logger.add(
                message=f"{call_type} call #{entry['call_number']}: {agent or model}",
                level="INFO",
                source="llm" if not is_vlm else "vlm",
                trace_id=self.execution_id,
                langsmith_url=langsmith_url,
                context={
                    "provider": provider,
                    "model": model,
                    "tokens": token_usage.get("total_tokens") if token_usage else None,
                    "prompt": prompt
                }
            )
    
    def log_gesture(
        self,
        gesture_type: str,
        gesture_data: Dict[str, Any],
        result: Dict[str, Any],
        execution_time: float,
        sent_at: Optional[datetime] = None,
        executed_at: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Log a gesture execution.
        
        Args:
            gesture_type: Type of gesture (tap, swipe, etc.)
            gesture_data: Gesture parameters
            result: Execution result
            execution_time: Time taken to execute
            sent_at: Timestamp when gesture was sent to device
            executed_at: Timestamp when gesture execution completed
            metadata: Additional metadata
        """
        now = datetime.now()
        timestamp = now.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        
        # Update counters
        self.gesture_count += 1
        self.total_execution_time += execution_time
        
        # Calculate timing info
        sent_timestamp = sent_at.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] if sent_at else None
        executed_timestamp = executed_at.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] if executed_at else timestamp
        
        entry = {
            "timestamp": timestamp,
            "type": "GESTURE",
            "gesture_number": self.gesture_count,
            "gesture_type": gesture_type,
            "gesture_data": gesture_data,
            "result": result,
            "execution_time": execution_time,
            "timing": {
                "sent_at": sent_timestamp,
                "executed_at": executed_timestamp,
            },
            "metadata": metadata or {}
        }
        
        self._write_entry(entry)
        logger.info(f"⚡ Logged gesture #{self.gesture_count}: {gesture_type}")

    def log_agent_decision(
        self,
        decision_type: str,
        details: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
        agent_name: Optional[str] = None,
    ):
        """
        Log an agent-level decision (subgoal transition, shortcut, reasoning, skip, etc.).

        Args:
            decision_type: Type of decision (SUBGOAL_START, SUBGOAL_SKIP, SHORTCUT, 
                          REASONING, ELEMENT_MATCH, VLM_FALLBACK, GOAL_COMPLETE, etc.)
            details: Decision details dict
            metadata: Additional metadata
            agent_name: Name of the agent making this decision
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        entry = {
            "timestamp": timestamp,
            "type": "AGENT_DECISION",
            "decision_type": decision_type,
            "details": details,
            "metadata": metadata or {},
            "agent_name": agent_name,
        }
        self._write_entry(entry)

    def log_error(self, error: str, source: str, details: Optional[Dict[str, Any]] = None):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        entry = {
            "timestamp": timestamp,
            "type": "ERROR",
            "source": source,
            "error": error,
            "details": details or {},
        }
        self._write_entry(entry)

    def log_logcat_snapshot(self, label: str, lines: list):
        if not lines:
            return
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        entry = {
            "timestamp": timestamp,
            "type": "LOGCAT",
            "label": label,
            "lines": lines,
        }
        self._write_entry(entry)

    def log_graph_execution(
        self,
        task_id: str,
        input_data: Dict[str, Any],
        output_data: Dict[str, Any],
        execution_time: float,
        status: str,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Log a complete graph execution.
        
        Args:
            task_id: Task identifier
            input_data: Input to the graph
            output_data: Output from the graph
            execution_time: Total execution time
            status: Final status
            metadata: Additional metadata
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        
        entry = {
            "timestamp": timestamp,
            "type": "GRAPH_EXECUTION",
            "task_id": task_id,
            "input": input_data,
            "output": output_data,
            "execution_time": execution_time,
            "status": status,
            "metadata": metadata or {}
        }
        
        self._write_entry(entry)
        logger.info(f"📊 Logged graph execution: {task_id} ({status})")
        
        # Send to unified logger
        if self.unified_logger:
            level = "ERROR" if status == "failed" else "INFO"
            self.unified_logger.add(
                message=f"Graph execution {status}: {task_id}",
                level=level,
                source="graph",
                trace_id=self.execution_id,
                context={
                    "execution_time": execution_time,
                    "status": status
                }
            )
    
    def _write_entry(self, entry: Dict[str, Any]):
        """Write an HTML log entry to the file."""
        import html as _html
        def esc(v): return _html.escape(str(v)) if v is not None else ""
        def jblk(d, label="Details"):
            if not d: return ""
            try:
                s = json.dumps(d, indent=2, ensure_ascii=False)
            except Exception:
                s = str(d)
            return f'<div class="json-section"><div class="json-label">{esc(label)}</div><pre class="json">{esc(s)}</pre></div>'

        try:
            entry_type = entry["type"]
            ts = entry.get("timestamp", "")
            body_id = f"e{id(entry)}{self.llm_call_count}{self.gesture_count}"

            # --- Determine header icon, badge, label ---
            if entry_type in ("LLM", "VLM"):
                n = entry.get("call_number", "?")
                icon = "&#x1F916;" if entry_type == "LLM" else "&#x1F441;"
                _caller = entry.get("agent") or ""
                _caller_tag = f' <span style="opacity:0.7;font-size:0.85em">({esc(_caller)})</span>' if _caller else ""
                badge = f'<span class="badge badge-{entry_type}">{entry_type} #{n}{_caller_tag}</span>'
                label = f'{esc(entry.get("provider",""))} | {esc(entry.get("model",""))}'
                collapsed = False
            elif entry_type == "GESTURE":
                n = entry.get("gesture_number", "?")
                icon = "&#x26A1;"
                badge = f'<span class="badge badge-GESTURE">GESTURE #{n}</span>'
                label = esc(entry.get("gesture_type", "").upper())
                collapsed = False
            elif entry_type == "COMMAND":
                icon = "&#x1F4CB;"
                badge = '<span class="badge badge-COMMAND">COMMAND</span>'
                label = esc((entry.get("command", ""))[:80])
                collapsed = False
            elif entry_type == "AGENT_DECISION":
                dt = entry.get("decision_type", "")
                icon_map = {
                    "PLAN_CREATED": "&#x1F4CB;", "SUBGOAL_START": "&#x25B6;",
                    "SUBGOAL_COMPLETE": "&#x2705;", "ACTION_FAILED": "&#x274C;",
                    "PERCEPTION_RESULT": "&#x1F50D;", "VERIFICATION_FAILED": "&#x26A0;",
                    "BUDGET_EXHAUSTED": "&#x1F6AB;", "LOOP_DETECTED": "&#x1F504;",
                    "REPLAN": "&#x1F500;", "TARGET_NOT_FOUND": "&#x2753;",
                    "INTENT_PARSED": "&#x1F9E0;", "POLICY_BLOCKED": "&#x1F6AB;",
                    "PROMPT_GUARD_BLOCKED": "&#x1F6E1;", "SENSITIVE_ACTION_BLOCKED": "&#x1F6E1;",
                    "ERROR_SCREEN_DETECTED": "&#x1F4A5;", "PERCEPTION_FAILED": "&#x274C;",
                    "POST_ACTION_SCREENSHOT": "&#x1F4F7;",
                }
                icon = icon_map.get(dt, "&#x1F9E0;")
                _AGENT_LABELS = {
                    "Commander": "Commander Agent", "Planner": "Planner Agent",
                    "Perceiver": "Perceiver Agent", "Actor": "Actor Agent",
                    "Coordinator": "Coordinator", "Reactive": "Reactive Agent",
                    "ReactiveStepGen": "Reactive Step Gen", "Navigator": "Navigator Agent",
                    "AnalyzeUI": "Analyze UI", "AutomationOrchestrator": "Automation Orchestrator",
                }
                _raw_agent = entry.get("agent_name") or "AGENT"
                _agent_display = esc(_AGENT_LABELS.get(_raw_agent, _raw_agent))
                badge = f'<span class="badge badge-AGENT">{_agent_display}</span>'
                label = f'<strong>{esc(dt)}</strong>'
                collapsed = False
            elif entry_type == "GRAPH_EXECUTION":
                icon = "&#x1F4CA;"
                badge = '<span class="badge badge-GRAPH">GRAPH</span>'
                status = entry.get("status", "")
                label = f'Status: <span class="status-{esc(status)}">{esc(status.upper())}</span>'
                collapsed = False
            elif entry_type == "ERROR":
                icon = "&#x274C;"
                badge = '<span class="badge badge-ERROR">ERROR</span>'
                label = esc(entry.get("source", ""))
                collapsed = False
            elif entry_type == "LOGCAT":
                icon = "&#x1F4F1;"
                badge = '<span class="badge">LOGCAT</span>'
                label = esc(entry.get("label", ""))
                collapsed = False
            else:
                icon = "&#x2022;"
                badge = f'<span class="badge">{esc(entry_type)}</span>'
                label = ""
                collapsed = False

            decision_class = f' decision-{entry.get("decision_type", "")}' if entry_type == "AGENT_DECISION" else ""
            body_class = ""
            elapsed_span = ""
            try:
                entry_dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S.%f")
                elapsed_sec = (entry_dt - self.start_time).total_seconds()
                elapsed_span = f'<span class="elapsed">+{elapsed_sec:.1f}s</span>'
            except Exception:
                pass
            header_html = (
                f'<div class="entry-header" onclick="toggleEntry(\'{body_id}\')" title="Click to collapse/expand">'
                f'{icon} {badge} <span class="ts">{esc(ts)}</span> '
                f'<span class="provider-tag">{label}</span>'
                f'{elapsed_span}'
                f'<span class="chevron">&#x25BC;</span>'
                f'</div>'
            )

            # --- Build body HTML ---
            body_parts = []

            if entry_type == "COMMAND":
                body_parts.append(f'<div class="kv-row"><span class="kv-key">Input type</span><span class="kv-val">{esc(entry.get("input_type",""))}</span></div>')
                body_parts.append(f'<div class="kv-row"><span class="kv-key">Command</span><span class="kv-val"><strong>{esc(entry.get("command",""))}</strong></span></div>')
                if entry.get("session_id"):
                    body_parts.append(f'<div class="kv-row"><span class="kv-key">Session</span><span class="kv-val">{esc(entry["session_id"])}</span></div>')
                if entry.get("metadata"):
                    body_parts.append(jblk(entry["metadata"], "Metadata"))

            elif entry_type in ("LLM", "VLM"):
                body_parts.append(f'<div class="kv-row"><span class="kv-key">Provider</span><span class="kv-val">{esc(entry.get("provider",""))}</span></div>')
                body_parts.append(f'<div class="kv-row"><span class="kv-key">Model</span><span class="kv-val">{esc(entry.get("model",""))}</span></div>')
                if entry.get("agent"):
                    body_parts.append(f'<div class="kv-row"><span class="kv-key">Agent</span><span class="kv-val">{esc(entry["agent"])}</span></div>')
                prompt_val = entry.get("prompt", "")
                if prompt_val:
                    prompt_id = f"prompt_{body_id}"
                    body_parts.append(
                        f'<div class="prompt-section">'
                        f'<button class="prompt-toggle" onclick="toggle(\'{prompt_id}\')"'
                        f'>&#x1F4AC; Prompt &mdash; {len(prompt_val):,} chars (click to expand)</button>'
                        f'<pre class="prompt-box hidden" id="{prompt_id}">{esc(prompt_val)}</pre>'
                        f'</div>'
                    )
                resp = entry.get("response", "")
                box_class = "vlm-box" if entry_type == "VLM" else "agent-box"
                resp_html = f'<div class="{box_class}">{esc(resp)}</div>'
                token_html = ""
                if entry.get("token_usage"):
                    tu = entry["token_usage"]
                    token_html = f'<div class="token-row">&#x1F522; Prompt: {tu.get("prompt_tokens","?")} | Completion: {tu.get("completion_tokens","?")} | Total: {tu.get("total_tokens","?")}</div>'
                # Screenshot for VLM calls — shown parallel to the response
                meta = entry.get("metadata") or {}
                img_path = meta.get("screenshot_saved_path") or meta.get("image_path")
                if img_path and entry_type == "VLM":
                    ss_col = (
                        f'<div class="vlm-screenshot">'
                        f'<div class="screenshot-label">&#x1F4F7; VLM input (annotated)</div>'
                        f'<img src="{esc(img_path)}" loading="lazy">'
                        f'</div>'
                    )
                    body_parts.append(
                        f'<div class="vlm-layout">'
                        f'<div class="vlm-content">{resp_html}{token_html}</div>'
                        f'{ss_col}'
                        f'</div>'
                    )
                else:
                    body_parts.append(resp_html)
                    if token_html:
                        body_parts.append(token_html)

            elif entry_type == "GESTURE":
                timing = entry.get("timing", {})
                success = entry.get("result", {}).get("success", False)
                result_data = entry.get("result", {})
                meta = entry.get("metadata") or {}
                # Annotate the pre-gesture screenshot with the gesture target
                ann_path = ""
                ss_b64 = meta.get("screenshot_b64")
                if ss_b64:
                    ann_path = self.log_annotated_gesture_screenshot(
                        entry.get("gesture_type", "gesture"),
                        entry.get("gesture_data", {}),
                        ss_b64,
                    )
                detail_parts = []
                detail_parts.append(f'<div class="kv-row"><span class="kv-key">Sent at</span><span class="kv-val">{esc(timing.get("sent_at",""))}</span></div>')
                detail_parts.append(f'<div class="kv-row"><span class="kv-key">Duration</span><span class="kv-val">{entry.get("execution_time",0)*1000:.1f}ms</span></div>')
                detail_parts.append(f'<div class="kv-row"><span class="kv-key">Result</span><span class="kv-val {"ok" if success else "fail"}">{"SUCCESS" if success else "FAILED"}</span></div>')
                if result_data.get("error"):
                    detail_parts.append(f'<div class="kv-row"><span class="kv-key">Error</span><span class="kv-val fail">{esc(result_data["error"])}</span></div>')
                detail_parts.append(jblk(entry.get("gesture_data", {}), "Gesture data"))
                if result_data.get("details"):
                    detail_parts.append(jblk(result_data["details"], "Result details"))
                if ann_path:
                    ss_col = (
                        f'<div class="gesture-screenshot">'
                        f'<div class="screenshot-label">&#x1F3AF; Gesture target</div>'
                        f'<img src="{esc(ann_path)}" loading="lazy">'
                        f'</div>'
                    )
                    body_parts.append(
                        f'<div class="gesture-layout">'
                        f'<div class="gesture-details">{"".join(detail_parts)}</div>'
                        f'{ss_col}'
                        f'</div>'
                    )
                else:
                    body_parts.extend(detail_parts)

            elif entry_type == "AGENT_DECISION":
                dt = entry.get("decision_type", "")
                details = entry.get("details", {})

                if dt == "PERCEPTION_RESULT":
                    # Rich perception display
                    body_parts.append(f'<div class="kv-row"><span class="kv-key">Screen type</span><span class="kv-val">{esc(details.get("screen_type",""))}</span></div>')
                    body_parts.append(f'<div class="kv-row"><span class="kv-key">Element count</span><span class="kv-val">{details.get("element_count",0)}</span></div>')
                    tm = details.get("target_match")
                    if tm:
                        body_parts.append(f'<div class="kv-row"><span class="kv-key">Target match</span><span class="kv-val match-found">&#x2705; ({tm.get("x")}, {tm.get("y")}) via {esc(tm.get("source","ui_tree"))}</span></div>')
                    else:
                        body_parts.append(f'<div class="kv-row"><span class="kv-key">Target match</span><span class="kv-val match-none">&#x274C; Not found</span></div>')
                    if details.get("screen_description"):
                        body_parts.append(f'<div class="kv-row"><span class="kv-key">VLM description</span><span class="kv-val">{esc(str(details["screen_description"]))}</span></div>')
                    # Screenshots grouped in a side-by-side grid
                    _grid = []
                    ss_path = details.get("screenshot_path")
                    if ss_path:
                        _grid.append(f'<div class="screenshot-row"><div class="screenshot-label">&#x1F4F5; Screen capture</div><img src="{esc(ss_path)}" loading="lazy"></div>')
                    ann_path = details.get("annotated_screenshot_path")
                    if ann_path:
                        _grid.append(f'<div class="screenshot-row"><div class="screenshot-label">&#x1F5FA; Annotated (UI tree)</div><img src="{esc(ann_path)}" loading="lazy"></div>')
                    omni_path = details.get("omniparser_screenshot_path")
                    if omni_path:
                        _grid.append(f'<div class="screenshot-row"><div class="screenshot-label">&#x1F52C; OmniParser</div><img src="{esc(omni_path)}" loading="lazy"></div>')
                    hl_path = details.get("highlighted_element_path")
                    if hl_path:
                        elem_desc_label = details.get("element_description") or "selected element"
                        _grid.append(f'<div class="screenshot-row"><div class="screenshot-label">&#x1F3AF; Target: {esc(elem_desc_label[:60])}</div><img src="{esc(hl_path)}" loading="lazy"></div>')
                    if _grid:
                        body_parts.append('<div class="screenshot-grid">' + "".join(_grid) + '</div>')
                    # Elements table
                    elems = details.get("elements_summary", [])
                    tm_x = tm.get("x") if tm else None
                    tm_y = tm.get("y") if tm else None
                    if elems:
                        def _elem_row(i, e, _tx=tm_x, _ty=tm_y):
                            idx = e.get("index", i + 1)
                            text = esc(e.get("text", "") or "")
                            desc = esc(e.get("content_desc", "") or "")
                            cls = esc((e.get("class", "") or "").split(".")[-1])
                            res = esc(e.get("resource_id", "") or "")
                            b = e.get("bounds") or {}
                            if isinstance(b, dict):
                                l, t, r, bo = b.get("left",0), b.get("top",0), b.get("right",0), b.get("bottom",0)
                                cx, cy = (l + r) // 2, (t + bo) // 2
                                bounds = f'[{l},{t} \u2192 {r},{bo}]'
                            else:
                                cx, cy = 0, 0
                                bounds = esc(str(b))
                            is_target = (_tx is not None) and (cx == _tx) and (cy == _ty)
                            row_class = ' class="row-target"' if is_target else ''
                            tags = ""
                            if is_target: tags += '<span class="row-target-label">&#x25C4; TAPPED</span>'
                            if e.get("clickable"): tags += '<span class="tag tag-clickable">tap</span>'
                            if e.get("scrollable"): tags += '<span class="tag tag-scrollable">scroll</span>'
                            if e.get("editable"): tags += '<span class="tag tag-editable">edit</span>'
                            if e.get("focused"): tags += '<span class="tag tag-focused">focus</span>'
                            if not e.get("enabled", True): tags += '<span class="tag tag-disabled">off</span>'
                            return (f'<tr{row_class}><td class="col-idx">{idx}</td>'
                                    f'<td class="col-text">{text}</td>'
                                    f'<td class="col-desc">{desc}</td>'
                                    f'<td class="col-class">{cls}</td>'
                                    f'<td class="col-res">{res}</td>'
                                    f'<td class="col-bounds">{bounds}</td>'
                                    f'<td class="col-center">{cx},{cy}</td>'
                                    f'<td>{tags}</td></tr>')
                        rows = "".join(_elem_row(i, e) for i, e in enumerate(elems))
                        body_parts.append(
                            f'<div class="elements-section">'
                            f'<div class="elements-section-title">UI Elements ({len(elems)})</div>'
                            f'<table class="elements-table"><thead><tr>'
                            f'<th>#</th><th>Text</th><th>Content Desc</th><th>Class</th><th>Resource ID</th><th>Bounds</th><th>Center</th><th>Flags</th>'
                            f'</tr></thead><tbody>{rows}</tbody></table></div>'
                        )
                elif dt == "POST_ACTION_SCREENSHOT":
                    body_parts.append(f'<div class="kv-row"><span class="kv-key">Subgoal</span><span class="kv-val">{esc(details.get("subgoal",""))}</span></div>')
                    body_parts.append(f'<div class="kv-row"><span class="kv-key">Action</span><span class="kv-val">{esc(details.get("action_type",""))}</span></div>')
                    ss_path = details.get("screenshot_path")
                    if ss_path:
                        body_parts.append(f'<div class="screenshot-row"><div class="screenshot-label">Post-action screen</div><img src="{esc(ss_path)}" loading="lazy"></div>')
                else:
                    # Generic decision display
                    for k, v in details.items():
                        if isinstance(v, (dict, list)):
                            body_parts.append(jblk(v, k))
                        else:
                            body_parts.append(f'<div class="kv-row"><span class="kv-key">{esc(k)}</span><span class="kv-val">{esc(v)}</span></div>')

            elif entry_type == "GRAPH_EXECUTION":
                body_parts.append(f'<div class="kv-row"><span class="kv-key">Task ID</span><span class="kv-val">{esc(entry.get("task_id",""))}</span></div>')
                body_parts.append(f'<div class="kv-row"><span class="kv-key">Duration</span><span class="kv-val">{entry.get("execution_time",0):.3f}s</span></div>')
                body_parts.append(jblk(entry.get("input", {}), "Input"))
                body_parts.append(jblk(entry.get("output", {}), "Output"))

            elif entry_type == "ERROR":
                body_parts.append(f'<div class="kv-row"><span class="kv-key">Source</span><span class="kv-val fail">{esc(entry.get("source",""))}</span></div>')
                body_parts.append(f'<div class="kv-row"><span class="kv-key">Error</span><span class="kv-val fail">{esc(entry.get("error",""))}</span></div>')
                if entry.get("details"):
                    body_parts.append(jblk(entry["details"], "Details"))

            elif entry_type == "LOGCAT":
                lines = entry.get("lines", [])
                body_parts.append(f'<div class="kv-row"><span class="kv-key">Context</span><span class="kv-val">{esc(entry.get("label",""))}</span></div>')
                if lines:
                    content = esc("\n".join(lines))
                    body_parts.append(f'<pre class="logcat">{content}</pre>')

            body_html = "\n".join(body_parts)

            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(
                    f'<div class="entry entry-{esc(entry_type)}{decision_class}">\n'
                    f'{header_html}\n'
                    f'<div class="entry-body {body_class}" id="{body_id}">\n'
                    f'{body_html}\n'
                    f'</div>\n'
                    f'</div>\n'
                )
            self._write_txt_entry(entry)

        except Exception as e:
            logger.error(f"Failed to write HTML log entry: {e}")

    def _write_txt_header(self):
        """Write the plain-text log file header (LLM-friendly)."""
        sep = "=" * 80
        try:
            with open(self.txt_log_file, "w", encoding="utf-8") as f:
                f.write(f"{sep}\n")
                f.write(f"AURA EXECUTION LOG  {self.execution_id}\n")
                f.write(f"Started: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"{sep}\n\n")
        except Exception as e:
            logger.warning(f"Could not write txt log header: {e}")

    def _write_txt_entry(self, entry: Dict[str, Any]):
        """Write a clean, LLM-friendly plain-text representation of a log entry."""
        entry_type = entry.get("type", "")
        ts = entry.get("timestamp", "")
        sep = "-" * 80
        try:
            elapsed_str = ""
            try:
                entry_dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S.%f")
                elapsed_sec = (entry_dt - self.start_time).total_seconds()
                elapsed_str = f" +{elapsed_sec:.1f}s"
            except Exception:
                pass

            lines = []
            if entry_type == "COMMAND":
                lines.append(f"[COMMAND]{elapsed_str} | {ts}")
                lines.append(f"  Input: {entry.get('input_type', '')}")
                lines.append(f"  Command: {entry.get('command', '')}")
                if entry.get("session_id"):
                    lines.append(f"  Session: {entry['session_id']}")

            elif entry_type in ("LLM", "VLM"):
                n = entry.get("call_number", "?")
                agent = entry.get("agent") or ""
                lines.append(f"[{entry_type} #{n}]{elapsed_str} | {ts}")
                if agent:
                    lines.append(f"  Agent: {agent}")
                lines.append(f"  Provider: {entry.get('provider', '')} | Model: {entry.get('model', '')}")
                prompt = entry.get("prompt") or ""
                if prompt:
                    lines.append("  --- PROMPT ---")
                    for pline in prompt.splitlines():
                        lines.append(f"  {pline}")
                resp = entry.get("response") or ""
                if resp:
                    lines.append("  --- RESPONSE ---")
                    for rline in resp.splitlines():
                        lines.append(f"  {rline}")
                tu = entry.get("token_usage") or {}
                if tu:
                    lines.append(
                        f"  Tokens: prompt={tu.get('prompt_tokens', '?')} "
                        f"completion={tu.get('completion_tokens', '?')} "
                        f"total={tu.get('total_tokens', '?')}"
                    )

            elif entry_type == "GESTURE":
                n = entry.get("gesture_number", "?")
                gtype = entry.get("gesture_type", "").upper()
                success = (entry.get("result") or {}).get("success", False)
                lines.append(f"[GESTURE #{n}]{elapsed_str} | {ts}")
                lines.append(f"  Type: {gtype}")
                gdata = entry.get("gesture_data") or {}
                if gdata:
                    lines.append(f"  Data: {json.dumps(gdata, ensure_ascii=False)}")
                lines.append(f"  Result: {'SUCCESS' if success else 'FAILED'}")
                lines.append(f"  Duration: {entry.get('execution_time', 0) * 1000:.1f}ms")
                err = (entry.get("result") or {}).get("error")
                if err:
                    lines.append(f"  Error: {err}")

            elif entry_type == "AGENT_DECISION":
                dt = entry.get("decision_type", "")
                agent_name = entry.get("agent_name") or ""
                details = entry.get("details") or {}
                lines.append(f"[AGENT_DECISION: {dt}]{elapsed_str} | {ts}")
                if agent_name:
                    lines.append(f"  Agent: {agent_name}")
                if dt == "PERCEPTION_RESULT":
                    lines.append(f"  Screen type: {details.get('screen_type', '')}")
                    lines.append(f"  Elements: {details.get('element_count', 0)}")
                    tm = details.get("target_match")
                    if tm:
                        lines.append(
                            f"  Target: FOUND at ({tm.get('x')}, {tm.get('y')}) "
                            f"via {tm.get('source', 'ui_tree')}"
                        )
                    else:
                        lines.append("  Target: NOT FOUND")
                    if details.get("screen_description"):
                        lines.append(f"  VLM description: {details['screen_description']}")
                    elems = details.get("elements_summary") or []
                    if elems:
                        lines.append(f"  UI Elements ({len(elems)}):")
                        for i, e in enumerate(elems[:30]):
                            text = (e.get("text") or "").strip()
                            desc = (e.get("content_desc") or "").strip()
                            cls = (e.get("class") or "").split(".")[-1]
                            b = e.get("bounds") or {}
                            if isinstance(b, dict):
                                cx = (b.get("left", 0) + b.get("right", 0)) // 2
                                cy = (b.get("top", 0) + b.get("bottom", 0)) // 2
                            else:
                                cx, cy = 0, 0
                            flags = [
                                fn for fn in ("clickable", "scrollable", "editable")
                                if e.get(fn)
                            ]
                            flags_str = f" [{', '.join(flags)}]" if flags else ""
                            label = text or desc or "(no label)"
                            lines.append(f"    {i + 1}. {label!r} ({cls}) @ ({cx},{cy}){flags_str}")
                        if len(elems) > 30:
                            lines.append(f"    ... and {len(elems) - 30} more elements")
                elif dt == "POST_ACTION_SCREENSHOT":
                    lines.append(f"  Subgoal: {details.get('subgoal', '')}")
                    lines.append(f"  Action: {details.get('action_type', '')}")
                else:
                    for k, v in details.items():
                        if k.endswith(("_path", "_b64", "_screenshot")):
                            continue
                        if isinstance(v, (dict, list)):
                            try:
                                lines.append(f"  {k}: {json.dumps(v, ensure_ascii=False)}")
                            except Exception:
                                lines.append(f"  {k}: {v}")
                        else:
                            lines.append(f"  {k}: {v}")

            elif entry_type == "GRAPH_EXECUTION":
                lines.append(f"[GRAPH_EXECUTION]{elapsed_str} | {ts}")
                lines.append(f"  Task ID: {entry.get('task_id', '')}")
                lines.append(f"  Status: {entry.get('status', '').upper()}")
                lines.append(f"  Duration: {entry.get('execution_time', 0):.3f}s")

            elif entry_type == "ERROR":
                lines.append(f"[ERROR]{elapsed_str} | {ts}")
                lines.append(f"  Source: {entry.get('source', '')}")
                lines.append(f"  Error: {entry.get('error', '')}")
                details = entry.get("details")
                if details:
                    try:
                        lines.append(f"  Details: {json.dumps(details, ensure_ascii=False)}")
                    except Exception:
                        lines.append(f"  Details: {details}")

            elif entry_type == "LOGCAT":
                log_lines = entry.get("lines") or []
                lines.append(f"[LOGCAT]{elapsed_str} | {ts}")
                lines.append(f"  Context: {entry.get('label', '')}")
                lines.append(f"  Lines: {len(log_lines)}")
                for ll in log_lines[:50]:
                    lines.append(f"  {ll}")
                if len(log_lines) > 50:
                    lines.append(f"  ... and {len(log_lines) - 50} more lines")

            else:
                lines.append(f"[{entry_type}]{elapsed_str} | {ts}")

            lines.append(sep)
            with open(self.txt_log_file, "a", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")

        except Exception as e:
            logger.error(f"Failed to write txt log entry: {e}")

    def _finalize_txt(self, status: str, total_time: float):
        """Write summary footer to the plain-text log."""
        sep = "=" * 80
        try:
            with open(self.txt_log_file, "a", encoding="utf-8") as f:
                f.write(f"\n{sep}\n")
                f.write("SUMMARY\n")
                f.write(f"  Status:        {status.upper()}\n")
                f.write(f"  Duration:      {total_time:.2f}s\n")
                f.write(f"  LLM Calls:     {self.llm_call_count}\n")
                f.write(f"  VLM Calls:     {self.vlm_call_count}\n")
                f.write(f"  Tokens:        {self.total_llm_tokens:,}\n")
                f.write(f"  Gestures:      {self.gesture_count}\n")
                f.write(f"  Gesture time:  {self.total_execution_time * 1000:.0f}ms\n")
                f.write(f"{sep}\n")
        except Exception as e:
            logger.error(f"Failed to write txt log summary: {e}")

    def _format_json_block(self, data: Dict[str, Any], indent: int = 2) -> str:
        """Format a JSON object for readable logging."""
        try:
            formatted = json.dumps(data, indent=indent)
            lines = formatted.split('\n')
            return '\n'.join(f"  {line}" for line in lines) + "\n"
        except Exception:
            return f"  {str(data)}\n"
    
    def finalize(self, status: str = "completed"):
        """
        Finalize the log file by writing the summary at the beginning.
        Call this when execution is complete.
        
        Args:
            status: Final execution status
        """
        end_time = datetime.now()
        total_time = (end_time - self.start_time).total_seconds()
        
        logger.debug(f"Finalizing log: {self.log_file} with status={status}")
        
        # Build summary
        status_class = "status-FAILED" if status == "failed" else "status-completed"
        summary_html = f"""
        <div id="summary">
          <div class="sum-block">
            <span class="sum-label">&#x2611; Status</span>
            <span class="sum-val {status_class}">{status.upper()}</span>
          </div>
          <div class="sum-block">
            <span class="sum-label">&#x23F1; Duration</span>
            <span class="sum-val">{total_time:.2f}s</span>
          </div>
          <div class="sum-block">
            <span class="sum-label">&#x1F916; LLM Calls</span>
            <span class="sum-val">{self.llm_call_count}</span>
          </div>
          <div class="sum-block">
            <span class="sum-label">&#x1F441; VLM Calls</span>
            <span class="sum-val">{self.vlm_call_count}</span>
          </div>
          <div class="sum-block">
            <span class="sum-label">&#x1F522; Tokens</span>
            <span class="sum-val">{self.total_llm_tokens:,}</span>
          </div>
          <div class="sum-block">
            <span class="sum-label">&#x26A1; Gestures</span>
            <span class="sum-val">{self.gesture_count}</span>
          </div>
          <div class="sum-block">
            <span class="sum-label">&#x23F0; Gesture Time</span>
            <span class="sum-val">{self.total_execution_time*1000:.0f}ms</span>
          </div>
          <div class="sum-block">
            <span class="sum-label">&#x1F4F1; Logcat</span>
            <span class="sum-val">{"&#x2705; on" if LOGCAT_AVAILABLE else "&#x274C; off"}</span>
          </div>
        </div>
        """
        summary = summary_html
        
        # Dump full logcat BEFORE closing HTML (so it appears inside the document)
        if LOGCAT_AVAILABLE:
            try:
                all_lines = get_logcat_capture().get_all()
                if all_lines:
                    label = "task_complete_full_logcat" if status != "failed" else "task_failed_full_logcat"
                    self.log_logcat_snapshot(label, all_lines)
                get_logcat_capture().stop()
            except Exception:
                pass

        # Read current file content and replace placeholder
        try:
            log_path = str(self.log_file)
            
            with open(log_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            if "[SUMMARY_PLACEHOLDER]" not in content:
                logger.warning(f"Summary placeholder not found in log file: {log_path}")
            else:
                content = content.replace("[SUMMARY_PLACEHOLDER]", summary)
            
            # Close the HTML document
            if "</body>" not in content:
                content += "\n</div>\n</body>\n</html>"
            
            with open(log_path, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
            
            logger.info(f"📊 Log finalized: {self.llm_call_count} LLM, {self.vlm_call_count} VLM, {self.gesture_count} gestures")
            
        except Exception as e:
            logger.error(f"Failed to finalize log {self.log_file}: {e}", exc_info=True)
        finally:
            self._finalize_txt(status, total_time)
            self._stop_terminal_log_capture()
    
    def get_log_file_path(self) -> str:
        """Get the path to the current log file."""
        return str(self.log_file.absolute())
    
    def log_debug(self, message: str, level: str = "INFO", module: str = None):
        """
        Log a general debug/info message as a small HTML line.
        
        Args:
            message: The log message
            level: Log level (DEBUG, INFO, WARNING, ERROR)
            module: Source module name
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        
        # Only log INFO and above to avoid too much noise
        if level == "DEBUG":
            return  # Skip DEBUG to keep logs readable
        
        try:
            import html as _html
            level_indicator = {"INFO": "&#x2139;", "WARNING": "&#x26A0;", "ERROR": "&#x274C;"}.get(level, "&#x2022;")
            module_str = f"[{_html.escape(module)}] " if module else ""
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(f'<div class="debug-line">{level_indicator} {_html.escape(timestamp)} {module_str}{_html.escape(message)}</div>\n')
            if level in ("WARNING", "ERROR") and hasattr(self, "txt_log_file"):
                prefix = "WARN" if level == "WARNING" else "ERROR"
                mod_str = f"[{module}] " if module else ""
                with open(self.txt_log_file, "a", encoding="utf-8") as f:
                    f.write(f"[{prefix}] {timestamp} {mod_str}{message}\n")
        except Exception:
            pass  # Don't fail on logging errors


class CommandLoggerHandler(logging.Handler):
    """
    Logging handler that forwards log messages to the CommandLogger.
    
    This captures all logger.info(), logger.warning() etc. calls
    and writes them to the execution log file.
    """
    
    def emit(self, record):
        """Forward log record to CommandLogger."""
        try:
            cmd_logger = get_command_logger()
            if cmd_logger and hasattr(cmd_logger, 'log_debug'):
                # Get message
                msg = self.format(record) if self.formatter else str(record.msg)
                # Clean up the message (remove ANSI codes)
                msg = re.sub(r'\x1b\[[0-9;]*m', '', msg)
                
                cmd_logger.log_debug(
                    message=msg,
                    level=record.levelname,
                    module=record.name.split('.')[-1] if record.name else None
                )
        except Exception:
            pass  # Don't fail on logging


def attach_command_logger_handler():
    """
    Attach the CommandLoggerHandler to the root logger.
    
    Call this once at application startup to capture all log output.
    """
    handler = CommandLoggerHandler()
    handler.setLevel(logging.INFO)  # Only INFO and above
    
    # Add to root logger
    root_logger = logging.getLogger()
    
    # Check if already attached
    for h in root_logger.handlers:
        if isinstance(h, CommandLoggerHandler):
            return  # Already attached
    
    root_logger.addHandler(handler)
    logger.info("📝 CommandLoggerHandler attached - all logs will be captured")


# Module-level logger shared across async context and thread-pool workers.
# thread-local broke when LangGraph ran sync nodes in a thread-pool executor,
# because each pool thread got its own (empty) storage and created a second log file.
_current_logger: Optional[CommandLogger] = None


def get_command_logger(execution_id: str = None) -> CommandLogger:
    """Get or create a command logger for current execution."""
    global _current_logger
    if _current_logger is None:
        _current_logger = CommandLogger(execution_id=execution_id)
    return _current_logger


def create_new_execution_logger(execution_id: str = None) -> CommandLogger:
    """Create a new logger for a new execution (clears previous)."""
    global _current_logger
    _current_logger = CommandLogger(execution_id=execution_id)
    return _current_logger


def clear_execution_logger():
    """Clear the current execution logger."""
    global _current_logger
    _current_logger = None
