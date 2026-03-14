"""Unfiltered ADB logcat capture scoped to the AURA Android application."""

import subprocess
import threading
from collections import deque
from datetime import datetime
from typing import List, Optional

# AURA package names (release and debug variants)
AURA_PACKAGES = [
    "com.aura.aura_ui.feature",
    "com.aura.aura_ui.feature.debug",
]


class LogcatCapture:

    def __init__(self):
        self._lines: deque = deque(maxlen=2000)
        self._thread: Optional[threading.Thread] = None
        self._proc: Optional[subprocess.Popen] = None
        self._running = False
        self._start_time: Optional[datetime] = None
        self._pid: Optional[str] = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._start_time = datetime.now()
        self._lines.clear()
        self._pid = self._resolve_pid()
        self._thread = threading.Thread(target=self._read_logcat, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._proc:
            self._proc.terminate()

    def get_recent(self, max_lines: int = 50) -> List[str]:
        """Return the most recent captured logcat lines."""
        return [line for _, line in list(self._lines)[-max_lines:]]

    def get_all(self) -> List[str]:
        """Return ALL captured logcat lines since start."""
        return [line for _, line in list(self._lines)]

    def _resolve_pid(self) -> Optional[str]:
        """Find the PID of the running AURA app on the connected device."""
        for pkg in AURA_PACKAGES:
            try:
                result = subprocess.run(
                    ["adb", "shell", "pidof", pkg],
                    capture_output=True, text=True, timeout=5,
                )
                pid = result.stdout.strip()
                if pid and pid.isdigit():
                    return pid
            except Exception:
                continue
        return None

    def _read_logcat(self):
        # Clear logcat buffer before starting fresh capture
        try:
            subprocess.run(
                ["adb", "logcat", "-c"],
                capture_output=True, timeout=5,
            )
        except Exception:
            pass

        # Build command: filter by PID if found, otherwise capture all
        # No tag filtering — capture everything for debugging
        if self._pid:
            cmd = ["adb", "logcat", "-v", "threadtime", f"--pid={self._pid}"]
        else:
            # Fallback: capture all but at verbose level
            cmd = ["adb", "logcat", "-v", "threadtime"]

        try:
            self._proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, encoding="utf-8", errors="replace",
            )
            for line in self._proc.stdout:
                if not self._running:
                    break
                self._lines.append((datetime.now(), line.rstrip()))
        except Exception:
            pass


_instance: Optional[LogcatCapture] = None


def get_logcat_capture() -> LogcatCapture:
    global _instance
    if _instance is None:
        _instance = LogcatCapture()
    return _instance
