"""
Reflexion service — generates and stores task failure lessons.

Based on: Reflexion: Language Agents with Verbal Reinforcement Learning
(Shinn et al., 2023). After each failed task, the agent generates a
natural-language lesson that is prepended to the next attempt's context,
making retries smarter without architecture changes.
"""

import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from typing import Optional

from utils.logger import get_logger

logger = get_logger(__name__)

_REFLEXION_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="reflexion_worker")


class ReflexionService:
    """
    Generates and retrieves natural-language lessons from task failures.

    Lessons are stored as JSON files keyed by a normalized goal hash so
    that future attempts at the same or similar goal can learn from past failures.
    """

    def __init__(self, llm_service, storage_path: Optional[Path] = None):
        self.llm_service = llm_service
        self.storage_path = storage_path or Path("data/reflexion_lessons")
        self.storage_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"ReflexionService initialized, storage: {self.storage_path}")

    async def generate_lesson(
        self,
        goal: str,
        step_history: list,
        failure_reason: str
    ) -> str:
        """
        Generate a natural-language lesson after a task failure.

        Args:
            goal: The original user goal that failed
            step_history: List of StepMemory objects or dicts with action/result
            failure_reason: Why the task was aborted

        Returns:
            Lesson string to be injected into the next attempt's context
        """
        step_lines = "\n".join(
            f"  {i+1}. [{getattr(m, 'action_type', m.get('action', '?') if isinstance(m, dict) else '?')}] "
            f"{getattr(m, 'target', m.get('target', '?') if isinstance(m, dict) else '?')} → "
            f"{getattr(m, 'result', m.get('result', '?') if isinstance(m, dict) else '?')}"
            for i, m in enumerate(step_history[-10:])  # Last 10 steps for context
        )

        prompt = (
            f"You are analyzing why an Android automation task failed.\n\n"
            f"Goal: {goal}\n"
            f"Failure reason: {failure_reason}\n"
            f"Steps taken:\n{step_lines}\n\n"
            f"In 2-3 sentences, explain: what went wrong and what should be done "
            f"differently on the next attempt. Be specific and actionable."
        )

        try:
            loop = asyncio.get_event_loop()
            lesson = await loop.run_in_executor(
                _REFLEXION_EXECUTOR,
                partial(self.llm_service.run, prompt)
            )
            lesson = (lesson or "").strip()
            if lesson:
                await self._store_lesson(goal, lesson, failure_reason)
                logger.info(f"Reflexion lesson generated for goal: {goal[:50]!r}")
            return lesson
        except Exception as e:
            logger.error(f"ReflexionService.generate_lesson failed: {e}", exc_info=True)
            return ""

    async def get_lessons_for_goal(self, goal: str, max_lessons: int = 3) -> list:
        """
        Retrieve the most recent stored lessons for a similar goal.

        Args:
            goal: Current goal to find relevant lessons for
            max_lessons: Maximum number of lessons to return

        Returns:
            List of lesson strings, most recent first
        """
        try:
            goal_key = self._goal_key(goal)
            lesson_file = self.storage_path / f"{goal_key}.json"

            if not lesson_file.exists():
                return []

            data = json.loads(lesson_file.read_text(encoding="utf-8"))
            entries = data.get("lessons", [])
            # Most recent first
            entries.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
            return [e["lesson"] for e in entries[:max_lessons] if e.get("lesson")]
        except Exception as e:
            logger.warning(f"Failed to retrieve reflexion lessons: {e}")
            return []

    async def _store_lesson(self, goal: str, lesson: str, failure_reason: str) -> None:
        """Persist lesson to disk as JSON."""
        try:
            goal_key = self._goal_key(goal)
            lesson_file = self.storage_path / f"{goal_key}.json"

            # Load existing or create new
            if lesson_file.exists():
                data = json.loads(lesson_file.read_text(encoding="utf-8"))
            else:
                data = {"goal": goal, "lessons": []}

            data["lessons"].append({
                "lesson": lesson,
                "failure_reason": failure_reason,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

            # Keep last 10 lessons per goal
            data["lessons"] = data["lessons"][-10:]

            lesson_file.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
        except Exception as e:
            logger.warning(f"Failed to store reflexion lesson: {e}")

    @staticmethod
    def _goal_key(goal: str) -> str:
        """
        Bucket lessons by action type inferred from the goal text.

        "send message to john" and "whatsapp john about meeting" both map to
        'send_message', so they share a lesson pool — no vector DB needed.
        Falls back to a 3-word slug when no action bucket matches.
        """
        import re

        # Match on ACTION VERBS only — not app names.
        # open_app must come before send_message so "open WhatsApp" hits "open" first.
        _ACTION_BUCKETS: list[tuple[str, list[str]]] = [
            ("open_app",       ["open", "launch", "start"]),
            ("send_message",   ["send", "message", "text", "sms"]),
            ("make_call",      ["call", "dial", "phone", "ring"]),
            ("play_media",     ["play", "listen", "watch", "stream", "music", "video", "song", "podcast"]),
            ("search",         ["search", "find", "look up", "google", "browse"]),
            ("navigate",       ["navigate", "directions", "route", "maps"]),
            ("take_screenshot",["screenshot", "capture screen"]),
            ("settings",       ["setting", "toggle", "enable", "disable", "turn on", "turn off", "wifi",
                                 "bluetooth", "volume", "brightness"]),
            ("email",          ["email", "mail", "compose"]),
            ("social",         ["post", "tweet", "like", "share", "comment"]),
        ]

        text = goal.lower().strip()
        for bucket, keywords in _ACTION_BUCKETS:
            if any(kw in text for kw in keywords):
                return bucket

        # Fallback: first 3 meaningful words as slug
        words = re.findall(r'[a-z]+', text)[:3]
        return "_".join(words) or "unknown"


# Module-level singleton
_reflexion_service: Optional[ReflexionService] = None


def get_reflexion_service(llm_service=None) -> Optional[ReflexionService]:
    """Get or initialize the global ReflexionService singleton."""
    global _reflexion_service
    if _reflexion_service is None and llm_service is not None:
        _reflexion_service = ReflexionService(llm_service=llm_service)
    return _reflexion_service
