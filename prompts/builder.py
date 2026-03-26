"""
AURA Modular Prompt Builder - v1.0.0

OpenClaw-inspired section-based prompt assembly for AURA agents.

Key patterns borrowed from OpenClaw's buildAgentSystemPrompt():
  - PromptMode gating: full / minimal / none (saves tokens for sub-agents)
  - Explicit Safety section (no independent goals, fail-safe on conflict)
  - Runtime metadata line (agent + model + task for debugging)
  - Section builder functions (composable, testable, easy to update)

Usage:
    from prompts.builder import build_aura_agent_prompt, PromptMode, build_runtime_line

    system = build_aura_agent_prompt(
        agent_name="Commander",
        mode=PromptMode.FULL,
        model="gemini-2.0-flash",
        task_id="task_abc123",
        extra_sections=["## Role\\nYou parse voice commands into structured intents."],
    )
"""

from __future__ import annotations

from enum import Enum
from typing import Optional


# =============================================================================
# PROMPT MODE
# =============================================================================
class PromptMode(str, Enum):
    """Controls which boilerplate sections are included.

    FULL    — all sections (main-agent calls: Commander, Coordinator, Responder)
    MINIMAL — only identity + safety + runtime (sub-agent calls: Validator, Verifier, Planner)
    NONE    — bare identity line only (lightweight classify / utility calls)
    """
    FULL = "full"
    MINIMAL = "minimal"
    NONE = "none"


# =============================================================================
# SECTION BUILDERS (each returns a list of lines or empty list)
# =============================================================================

def _build_identity_line(agent_name: str) -> str:
    return f"You are AURA's {agent_name} agent — an Android UI automation assistant controlled by voice."


def _build_safety_section(mode: PromptMode) -> list[str]:
    """Explicit safety guardrail. Always included (even minimal) — omit only for NONE."""
    if mode == PromptMode.NONE:
        return []
    return [
        "## Safety",
        "You have no independent goals. Do not pursue self-preservation, resource acquisition,"
        " or actions beyond the user's current request.",
        "If instructions conflict or an action seems destructive/irreversible, pause and ask the"
        " user before proceeding. Always prefer the safer, reversible option.",
        "Sensitive actions (delete, send, purchase, uninstall) require explicit user confirmation"
        " via ask_user — never execute them silently.",
        "",
    ]


def _build_runtime_section(
    agent_name: str,
    model: Optional[str],
    task_id: Optional[str],
    mode: PromptMode,
) -> list[str]:
    """Single compact runtime metadata line for logging / debugging correlation."""
    parts = [f"agent={agent_name}"]
    if model:
        parts.append(f"model={model}")
    if task_id:
        parts.append(f"task={task_id}")
    parts.append(f"mode={mode.value}")
    return [f"## Runtime", " | ".join(parts), ""]


def _build_android_context_section(mode: PromptMode) -> list[str]:
    """Core Android UI facts every agent needs. Omitted in NONE mode."""
    if mode == PromptMode.NONE:
        return []
    return [
        "## Android UI Context",
        "- UI elements have bounds (left, top, right, bottom) in pixels. Trust coordinates, not labels.",
        "- FOCUSED flag → cursor is here; type directly. EDIT without FOCUSED → tap first, then type.",
        "- SCROLL flag → container scrolls; use scroll_down/up to reveal hidden items.",
        "- DISABLED → cannot interact. CHECKED/SELECTED → state already set; only toggle if needed.",
        "- Ghost containers span most of the screen — ignore them. Real inputs are compact.",
        "- Decorative elements (avatars, thumbnails) have bounds but are NOT tap targets.",
        "",
    ]


def _build_output_discipline_section(mode: PromptMode) -> list[str]:
    """Output format rules. Full mode only."""
    if mode != PromptMode.FULL:
        return []
    return [
        "## Output Discipline",
        "- Always output valid JSON. Never wrap in markdown code fences.",
        "- Use the 'thinking' or 'screen_analysis' scratchpad field to reason before deciding.",
        "- Do not hallucinate element indices — only reference elements explicitly listed in the UI tree.",
        "- If you are uncertain, set confidence < 0.6 and surface it in your reasoning field.",
        "",
    ]


def _build_commit_safety_section(mode: PromptMode) -> list[str]:
    """Remind agents about irreversible commit actions. Full mode only."""
    if mode != PromptMode.FULL:
        return []
    return [
        "## Commit Action Safety",
        "Before executing any of these actions, verify user intent is unambiguous:",
        "  send | delete | remove | purchase | pay | uninstall | clear | factory reset",
        "If the user's command is ambiguous for a commit action → use ask_user to confirm.",
        "",
    ]


# =============================================================================
# MAIN BUILDER
# =============================================================================

def build_aura_agent_prompt(
    agent_name: str,
    mode: PromptMode = PromptMode.FULL,
    model: Optional[str] = None,
    task_id: Optional[str] = None,
    extra_sections: Optional[list[str]] = None,
) -> str:
    """Assemble a complete system prompt for an AURA agent.

    Args:
        agent_name:     Display name of the agent (e.g. "Commander", "Verifier")
        mode:           PromptMode.FULL / MINIMAL / NONE — controls which boilerplate
                        sections are included. Use MINIMAL for sub-agent calls to save tokens.
        model:          LLM model ID being used (for runtime metadata line)
        task_id:        Current task / session ID (for debugging correlation)
        extra_sections: Additional domain-specific sections to append after boilerplate.
                        Each entry is a pre-formatted string (can span multiple lines).

    Returns:
        Complete system prompt string ready to pass to the LLM.
    """
    if mode == PromptMode.NONE:
        return _build_identity_line(agent_name)

    lines: list[str] = [
        _build_identity_line(agent_name),
        "",
        *_build_safety_section(mode),
        *_build_android_context_section(mode),
        *_build_output_discipline_section(mode),
        *_build_commit_safety_section(mode),
        *_build_runtime_section(agent_name, model, task_id, mode),
    ]

    # Append caller-provided domain sections
    for section in (extra_sections or []):
        stripped = section.strip()
        if stripped:
            lines.append(stripped)
            lines.append("")

    # Remove trailing blank lines
    while lines and lines[-1] == "":
        lines.pop()

    return "\n".join(lines)


# =============================================================================
# RUNTIME LINE HELPER (standalone — for injection into existing prompts)
# =============================================================================

def build_runtime_line(
    agent_name: str,
    model: Optional[str] = None,
    task_id: Optional[str] = None,
    extra: Optional[dict] = None,
) -> str:
    """Return a single compact runtime metadata line.

    Use this to inject runtime context into existing prompt constants
    without a full builder refactor.

    Example:
        prompt = REASONING_PROMPT_V2.format(...) + "\\n\\n" + build_runtime_line("Coordinator", model="gemini-flash", task_id=task_id)
    """
    parts = [f"agent={agent_name}"]
    if model:
        parts.append(f"model={model}")
    if task_id:
        parts.append(f"task={task_id}")
    for k, v in (extra or {}).items():
        parts.append(f"{k}={v}")
    return f"[Runtime: {' | '.join(parts)}]"


# =============================================================================
# PROMPT REPORT (token budget awareness — OpenClaw-inspired)
# =============================================================================

def build_prompt_report(prompt: str, agent_name: str = "unknown") -> dict:
    """Return a lightweight size report for a prompt string.

    Useful for tracking token budget across agent calls.
    Rough estimate: 1 token ≈ 4 chars for English text.

    Returns:
        dict with keys: agent, chars, approx_tokens, sections
    """
    chars = len(prompt)
    approx_tokens = chars // 4

    # Count section headers (## ...)
    sections = [line.strip() for line in prompt.splitlines() if line.startswith("## ")]

    return {
        "agent": agent_name,
        "chars": chars,
        "approx_tokens": approx_tokens,
        "sections": sections,
        "sections_count": len(sections),
    }
