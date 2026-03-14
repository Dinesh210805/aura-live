"""
Token usage tracker for monitoring LLM/VLM API consumption.

Tracks token usage across all API calls for cost analysis and optimization.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List

from utils.logger import get_logger

logger = get_logger(__name__)


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
        self._initialized = True
        logger.info("✅ Token tracker initialized")

    def track(
        self,
        agent: str,
        model_type: str,
        provider: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
    ):
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

        logger.debug(
            f"📊 Tracked: {agent} ({model_type}/{provider}) - {total_tokens} tokens"
        )

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

    def reset(self):
        """Clear all tracking history."""
        self.usage_history.clear()
        logger.info("🧹 Token tracking history cleared")

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
