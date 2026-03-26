"""
AURA Centralized Prompts Module - v2.1.0

All LLM prompts are versioned and centralized here for:
- Easy maintenance and updates
- A/B testing different prompt versions
- Consistent behavior across agents
- Token optimization tracking

Version History:
- v2.1.0 (2026-03-25): Modular builder (OpenClaw-inspired), safety sections, runtime metadata,
                        VLM CoT preamble, verifier improvements, duplicate icons fix
- v2.0.0 (2026-01-31): Centralized prompts, condensed reasoning, fixed hallucinations
- v1.0.0 (legacy): Inline prompts in individual service files
"""

# Modular Prompt Builder (v1.0 - OpenClaw-inspired)
from .builder import (
    PromptMode,
    build_aura_agent_prompt,
    build_runtime_line,
    build_prompt_report,
)

# Personality (unchanged)
from .personality import (
    AURA_PERSONALITY,
    EMOTIONAL_PATTERNS,
    EMOTIONAL_RESPONSES,
    USER_NAME,
)

# Reasoning (v2.0 - condensed)
from .reasoning import (
    REASONING_PROMPT_V2,
    VISION_REASONING_PROMPT,
    GOAL_VERIFICATION_PROMPT,
    get_reasoning_prompt,
    build_loop_warning,
)

# Planning (v2.0 - with failure handling)
from .planning import (
    GOAL_DECOMPOSITION_PROMPT,
    REPLANNING_PROMPT,
    SIMPLE_COMMANDS,
    get_planning_prompt,
    get_replanning_prompt,
)

# Reactive hybrid planning (v3.0)
from .skeleton_planning import get_skeleton_planning_prompt
from .reactive_step import get_reactive_step_prompt, get_reactive_step_messages
from .dynamic_rules import get_contextual_rules

# Classification (v2.0 - modern actions)
from .classification import (
    INTENT_CLASSIFICATION_PROMPT,
    INTENT_PARSING_PROMPT,
    INTENT_PARSING_PROMPT_WITH_CONTEXT,
    VISUAL_PATTERNS,
    get_classification_prompt,
    get_parsing_prompt,
)

# Vision (v2.0 - improved icons)
from .vision import (
    ELEMENT_LOCATION_PROMPT,
    ACTION_LOCATION_PROMPT,
    ELEMENT_SELECTION_PROMPT,
    SCREEN_ANALYSIS_PROMPT,
    ORDINAL_LOCATION_PROMPT,
    VISUAL_TRUST_RULES,
    get_vision_prompt,
    get_element_prompt,
    get_action_prompt,
    get_ordinal_prompt,
)

# Screen State (v1.0 - new)
from .screen_state import (
    SCREEN_STATE_PROMPT,
    STATE_INDICATORS,
    detect_screen_state_prompt,
    detect_state_from_text,
    get_blocking_state_action,
)

# Screen Reader (v1.0)
from .screen_reader import (
    SCREEN_DESCRIPTION_PROMPT,
    FOCUS_INSTRUCTIONS,
    get_screen_description_prompt,
)

# Current prompt versions for tracking
PROMPT_VERSIONS = {
    "builder": "1.0.0",
    "reasoning": "2.1.0",
    "planning": "2.0.0",
    "classification": "2.0.0",
    "vision": "3.1.0",
    "personality": "1.0.0",
    "screen_state": "1.0.0",
    "screen_reader": "1.0.0",
    "reactive_step": "4.1.0",
    "dynamic_rules": "1.0.0",
}

__all__ = [
    # Builder
    "PromptMode",
    "build_aura_agent_prompt",
    "build_runtime_line",
    "build_prompt_report",
    # Personality
    "AURA_PERSONALITY",
    "EMOTIONAL_PATTERNS",
    "EMOTIONAL_RESPONSES",
    "USER_NAME",
    # Reasoning
    "REASONING_PROMPT_V2",
    "VISION_REASONING_PROMPT",
    "GOAL_VERIFICATION_PROMPT",
    "get_reasoning_prompt",
    "build_loop_warning",
    # Planning
    "GOAL_DECOMPOSITION_PROMPT",
    "REPLANNING_PROMPT",
    "SIMPLE_COMMANDS",
    "get_planning_prompt",
    "get_replanning_prompt",
    # Classification
    "INTENT_CLASSIFICATION_PROMPT",
    "INTENT_PARSING_PROMPT",
    "INTENT_PARSING_PROMPT_WITH_CONTEXT",
    "VISUAL_PATTERNS",
    "get_classification_prompt",
    "get_parsing_prompt",
    # Reactive Step
    "get_reactive_step_prompt",
    "get_reactive_step_messages",
    "get_contextual_rules",
    # Vision
    "ELEMENT_LOCATION_PROMPT",
    "ACTION_LOCATION_PROMPT",
    "ELEMENT_SELECTION_PROMPT",
    "SCREEN_ANALYSIS_PROMPT",
    "ORDINAL_LOCATION_PROMPT",
    "VISUAL_TRUST_RULES",
    "get_vision_prompt",
    "get_element_prompt",
    "get_action_prompt",
    "get_ordinal_prompt",
    # Screen State
    "SCREEN_STATE_PROMPT",
    "STATE_INDICATORS",
    "detect_screen_state_prompt",
    "detect_state_from_text",
    "get_blocking_state_action",
    # Screen Reader
    "SCREEN_DESCRIPTION_PROMPT",
    "FOCUS_INSTRUCTIONS",
    "get_screen_description_prompt",
    # Metadata
    "PROMPT_VERSIONS",
]
