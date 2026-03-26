"""
Token usage tracker for monitoring LLM/VLM API consumption.

Tracks token usage across all API calls for cost analysis and optimization.
Supports per-task budget caps: set a limit before execution, check it in the
coordinator to abort runaway tasks before they exhaust API quotas.
"""

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from utils.logger import get_logger

logger = get_logger(__name__)

# Path where usage records are persisted across restarts (G9).
_PERSISTENCE_FILE = os.path.join("logs", "token_usage.jsonl")

# Default per-task token budget (0 = unlimited).
# Override via set_task_budget() before starting a task.
DEFAULT_TASK_BUDGET = 0


@dataclass
class TokenUsage:
    """Single token usage record."""

    timestamp: datetime
    agent: str  # "commander", "navigator", "responder", "screen_reader"
    model_type: str  # "llm" or "vlm"
    provider: str  # "groq" or "gemini"
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass
class TokenStats:
    """Aggregated token statistics."""

    total_calls: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    by_agent: Dict[str, int] = field(default_factory=dict)
    by_model: Dict[str, int] = field(default_factory=dict)
    by_provider: Dict[str, int] = field(default_factory=dict)


class TokenTracker:
    """
    Global token usage tracker.

    Tracks all LLM/VLM API calls for monitoring and optimization.
    Thread-safe singleton instance.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.usage_history: List[TokenUsage] = []
        # Per-task budget tracking: task_id → max_tokens (0 = unlimited)
        self._task_budgets: Dict[str, int] = {}
        # Per-task accumulated usage: task_id → total_tokens_used
        self._task_usage: Dict[str, int] = {}
        self._initialized = True
        # G9: load any records persisted from previous sessions
        self._load_persisted()
        logger.info(
            f"Token tracker initialized "
            f"({len(self.usage_history)} records loaded from disk)"
        )

    # -------------------------------------------------------------------------
    # Persistence (G9)
    # -------------------------------------------------------------------------

    def _load_persisted(self) -> None:
        """Load token usage records persisted by previous server sessions."""
        try:
            if not os.path.exists(_PERSISTENCE_FILE):
                return
            with open(_PERSISTENCE_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                        self.usage_history.append(
                            TokenUsage(
                                timestamp=datetime.fromisoformat(rec["timestamp"]),
                                agent=rec["agent"],
                                model_type=rec["model_type"],
                                provider=rec["provider"],
                                model=rec["model"],
                                prompt_tokens=rec["prompt_tokens"],
                                completion_tokens=rec["completion_tokens"],
                                total_tokens=rec["total_tokens"],
                            )
                        )
                    except Exception:
                        pass  # Skip malformed lines
        except Exception as exc:
            logger.debug(f"TokenTracker: could not load persisted records — {exc}")

    def _append_to_disk(self, usage: TokenUsage) -> None:
        """Append a single usage record to the JSONL persistence file."""
        try:
            os.makedirs(os.path.dirname(_PERSISTENCE_FILE), exist_ok=True)
            record = {
                "timestamp": usage.timestamp.isoformat(),
                "agent": usage.agent,
                "model_type": usage.model_type,
                "provider": usage.provider,
                "model": usage.model,
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens,
            }
            with open(_PERSISTENCE_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        except Exception as exc:
            logger.debug(f"TokenTracker: disk write failed (non-fatal) — {exc}")

    def track(
        self,
        agent: str,
        model_type: str,
        provider: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        task_id: Optional[str] = None,
    ) -> bool:
        """
        Track a single API call's token usage.

        Args:
            agent: Agent name (e.g., "navigator", "responder")
            model_type: "llm" or "vlm"
            provider: "groq" or "gemini"
            model: Model name
            prompt_tokens: Input tokens
            completion_tokens: Output tokens
            total_tokens: Total tokens
            task_id: Optional task ID for per-task budget tracking.

        Returns:
            True if within budget (or no budget set), False if budget exceeded.
        """
        usage = TokenUsage(
            timestamp=datetime.now(),
            agent=agent,
            model_type=model_type,
            provider=provider,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )

        self.usage_history.append(usage)
        self._append_to_disk(usage)  # G9: persist across restarts

        # Per-task accumulation
        within_budget = True
        if task_id:
            self._task_usage[task_id] = self._task_usage.get(task_id, 0) + total_tokens
            used = self._task_usage[task_id]
            budget = self._task_budgets.get(task_id, DEFAULT_TASK_BUDGET)
            if budget > 0 and used > budget:
                logger.warning(
                    f"TokenTracker: task '{task_id}' exceeded budget "
                    f"({used:,} / {budget:,} tokens) — agent={agent}"
                )
                within_budget = False
            elif budget > 0 and used > budget * 0.8:
                logger.warning(
                    f"TokenTracker: task '{task_id}' at {used/budget:.0%} of budget "
                    f"({used:,} / {budget:,} tokens)"
                )

        logger.debug(
            f"Tracked: {agent} ({model_type}/{provider}) - {total_tokens} tokens"
            + (f" [task={task_id}]" if task_id else "")
        )
        return within_budget

    def get_stats(self, agent: str = None) -> TokenStats:
        """
        Get aggregated token statistics.

        Args:
            agent: Optional agent name to filter by

        Returns:
            TokenStats with aggregated data
        """
        stats = TokenStats()

        # Filter by agent if specified
        history = self.usage_history
        if agent:
            history = [u for u in history if u.agent == agent]

        for usage in history:
            stats.total_calls += 1
            stats.total_prompt_tokens += usage.prompt_tokens
            stats.total_completion_tokens += usage.completion_tokens
            stats.total_tokens += usage.total_tokens

            # Aggregate by agent
            stats.by_agent[usage.agent] = (
                stats.by_agent.get(usage.agent, 0) + usage.total_tokens
            )

            # Aggregate by model
            stats.by_model[usage.model] = (
                stats.by_model.get(usage.model, 0) + usage.total_tokens
            )

            # Aggregate by provider
            stats.by_provider[usage.provider] = (
                stats.by_provider.get(usage.provider, 0) + usage.total_tokens
            )

        return stats

    def print_summary(self, agent: str = None):
        """
        Print formatted token usage summary.

        Args:
            agent: Optional agent name to filter by
        """
        stats = self.get_stats(agent)

        title = f"Token Usage Summary - {agent}" if agent else "Token Usage Summary"
        print("=" * 60)
        print(f"📊 {title}")
        print("=" * 60)
        print(f"Total API Calls: {stats.total_calls}")
        print(f"Total Tokens: {stats.total_tokens:,}")
        print(f"  - Prompt Tokens: {stats.total_prompt_tokens:,}")
        print(f"  - Completion Tokens: {stats.total_completion_tokens:,}")
        print()

        if stats.by_agent:
            print("By Agent:")
            for agent_name, tokens in sorted(
                stats.by_agent.items(), key=lambda x: -x[1]
            ):
                percentage = (
                    (tokens / stats.total_tokens * 100) if stats.total_tokens > 0 else 0
                )
                print(f"  {agent_name:15s}: {tokens:7,} tokens ({percentage:5.1f}%)")
            print()

        if stats.by_provider:
            print("By Provider:")
            for provider, tokens in sorted(
                stats.by_provider.items(), key=lambda x: -x[1]
            ):
                percentage = (
                    (tokens / stats.total_tokens * 100) if stats.total_tokens > 0 else 0
                )
                print(f"  {provider:15s}: {tokens:7,} tokens ({percentage:5.1f}%)")
            print()

        if stats.by_model:
            print("By Model:")
            for model, tokens in sorted(stats.by_model.items(), key=lambda x: -x[1]):
                percentage = (
                    (tokens / stats.total_tokens * 100) if stats.total_tokens > 0 else 0
                )
                model_short = model.split("/")[-1][:30]  # Shorten model name
                print(f"  {model_short:30s}: {tokens:7,} tokens ({percentage:5.1f}%)")

        print("=" * 60)

    # -------------------------------------------------------------------------
    # Per-task budget management
    # -------------------------------------------------------------------------

    def set_task_budget(self, task_id: str, max_tokens: int) -> None:
        """Set the maximum token budget for a specific task.

        Call this at the start of each task execution. Pass max_tokens=0 to
        remove the limit.

        Args:
            task_id:    Unique task identifier (session_id or UUID).
            max_tokens: Token cap (0 = unlimited).
        """
        if max_tokens > 0:
            self._task_budgets[task_id] = max_tokens
            self._task_usage.setdefault(task_id, 0)
            logger.debug(f"TokenTracker: budget set for task '{task_id}' — {max_tokens:,} tokens")
        else:
            self._task_budgets.pop(task_id, None)

    def get_task_usage(self, task_id: str) -> int:
        """Return tokens consumed so far for a given task (0 if unknown)."""
        return self._task_usage.get(task_id, 0)

    def check_task_budget(self, task_id: str) -> Tuple[bool, int, int]:
        """Check whether a task is within its token budget.

        Returns:
            (within_budget, used_tokens, max_tokens)
            within_budget is True when no budget is set OR used <= max.
        """
        used = self._task_usage.get(task_id, 0)
        budget = self._task_budgets.get(task_id, 0)
        if budget == 0:
            return True, used, 0
        return used <= budget, used, budget

    def clear_task(self, task_id: str) -> None:
        """Remove budget and usage records for a completed task (frees memory)."""
        self._task_budgets.pop(task_id, None)
        self._task_usage.pop(task_id, None)

    def reset(self):
        """Clear all tracking history and per-task records."""
        self.usage_history.clear()
        self._task_budgets.clear()
        self._task_usage.clear()
        logger.info("Token tracking history cleared")

    def get_recent(self, count: int = 10) -> List[TokenUsage]:
        """
        Get most recent token usage records.

        Args:
            count: Number of recent records to return

        Returns:
            List of recent TokenUsage records
        """
        return self.usage_history[-count:]


# Global tracker instance
token_tracker = TokenTracker()
