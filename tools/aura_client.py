"""
Simple AURA client to send tasks and persist results, without changing backend code.

This helps the agent monitor pick up results from files under tools/runs.

Examples (Windows cmd):
  # Send a text task to a local server
  > python tools\aura_client.py --server http://127.0.0.1:8000 --text "Open Gallery"

  # Send another task and name the output file
  > python tools\aura_client.py --text "Call John" --out-name call_john
"""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
from typing import Any, Dict, Optional

import httpx


def save_result(
    payload: Dict[str, Any], runs_dir: Path, out_name: Optional[str] = None
) -> Path:
    runs_dir.mkdir(parents=True, exist_ok=True)
    status = payload.get("status", "unknown")
    task_id = payload.get("task_id", "task")
    fname = f"{out_name or task_id}_{status}.json"
    out_path = runs_dir / fname
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="AURA simple client")
    parser.add_argument(
        "--server",
        type=str,
        default="http://127.0.0.1:8000",
        help="AURA server base URL",
    )
    parser.add_argument("--text", type=str, default=None, help="Text input to execute")
    parser.add_argument(
        "--audio", type=str, default=None, help="Path to an audio file to send"
    )
    parser.add_argument(
        "--runs-dir",
        type=str,
        default=str(Path("tools") / "runs"),
        help="Directory to save responses",
    )
    parser.add_argument(
        "--out-name", type=str, default=None, help="Optional basename for output file"
    )
    args = parser.parse_args()

    if not args.text and not args.audio:
        raise SystemExit("Provide --text or --audio")

    runs_dir = Path(args.runs_dir)

    if args.text:
        payload = {
            "text_input": args.text,
            "input_type": "text",
        }
    else:
        audio_path = Path(args.audio)
        if not audio_path.exists():
            raise SystemExit(f"Audio file not found: {audio_path}")
        audio_bytes = audio_path.read_bytes()
        payload = {
            "audio_data": base64.b64encode(audio_bytes).decode("utf-8"),
            "input_type": "audio",
        }

    url = args.server.rstrip("/") + "/tasks/execute"
    with httpx.Client(timeout=60) as client:
        resp = client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()

    out_path = save_result(data, runs_dir, args.out_name)
    print(f"Saved result → {out_path}")


if __name__ == "__main__":
    main()
