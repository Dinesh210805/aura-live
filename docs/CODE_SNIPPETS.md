# AURA Agent — Code Snippets for Project Report

> Selected from the codebase to showcase key architectural patterns, organized by layer.

---

## Recommended Grouping for the Report

| Section | Snippet |
|---|---|
| System Architecture | #1 (Graph), #2 (State) |
| Perception Subsystem | #5 (3-Layer Pipeline) |
| Planning & Reasoning | #6 (Goal Decomposer) |
| Execution & Resilience | #3 (Retry Ladder), #4 (Completion Heuristics) |
| Model Integration | #7 (VLM Multi-Provider) |
| Control Flow | #8 (Conditional Routing) |

---

## Snippet 1 — LangGraph Parallel Execution Graph

**File:** `aura_graph/graph.py`  
**Shows:** Fan-out/fan-in parallel architecture, node wiring

```python
def create_aura_graph() -> StateGraph:
    """
    PARALLEL ARCHITECTURE:
        STT → Parse Intent → [Fan-Out] → UI Analysis  → [Fan-In] → Plan → Execute → Speak
                                  ↘                   ↗
                                   → Validation     →
    The fan-out allows UI analysis and validation to run concurrently,
    reducing total latency when both operations are needed.
    """
    graph = StateGraph(TaskState)

    # Core pipeline nodes
    graph.add_node("stt",               stt_node)
    graph.add_node("parse_intent",      parse_intent_node)
    graph.add_node("validate_intent",   validate_intent_node)
    graph.add_node("perception",        perception_node)
    graph.add_node("parallel_processing", parallel_ui_and_validation_node)
    graph.add_node("create_plan",       plan_node)
    graph.add_node("execute",           execute_node)
    graph.add_node("speak",             speak_node)
    graph.add_node("error_handler",     error_handler_node)

    # Goal-driven execution nodes
    graph.add_node("decompose_goal",    decompose_goal_node)
    graph.add_node("validate_outcome",  validate_outcome_node)
    graph.add_node("retry_router",      retry_router_node)
    graph.add_node("next_subgoal",      next_subgoal_node)

    # Multi-agent coordinator (Phase 3)
    graph.add_node("coordinator",       coordinator_node)

    # Conditional entry: text input skips STT
    graph.add_conditional_edges("__start__", route_from_start, {
        "stt":           "stt",
        "parse_intent":  "parse_intent",
        "error_handler": "error_handler",
    })
```

---

## Snippet 2 — TaskState with Custom Reducers

**File:** `aura_graph/state.py`  
**Shows:** LangGraph `TypedDict` state, custom fan-in reducers for parallel nodes

```python
def add_errors(existing: Optional[str], new: str) -> str:
    """Merge errors from parallel branches."""
    if not existing:
        return new
    return f"{existing}; {new}"

def update_step(existing: Optional[int], new: int) -> int:
    """Take max step index — safe across concurrent node writes."""
    return max(existing, new) if existing is not None else new

class TaskState(TypedDict):
    # Audio / transcript
    raw_audio:            Optional[bytes]
    transcript:           Optional[str]
    streaming_transcript: Optional[str]
    intent:               Optional[Dict[str, Any]]

    # Planning & execution
    plan:           Optional[List[Dict[str, Any]]]
    current_step:   Annotated[Optional[int], update_step]      # max reducer
    executed_steps: Optional[List[ActionResult]]

    # Fan-in safe fields
    feedback_message: Annotated[Optional[str], update_status]  # last-writer-wins
    error_message:    Annotated[Optional[str], add_errors]     # accumulates errors

    retry_count: Optional[int]
    max_retries: Optional[int]
    session_id:  Optional[str]
```

---

## Snippet 3 — Escalating Retry Ladder

**File:** `aura_graph/agent_state.py`  
**Shows:** Enum-based strategy escalation, short-term step memory

```python
class RetryStrategy(Enum):
    """Each failure escalates to the next strategy."""
    SAME_ACTION        = "same_action"
    ALTERNATE_SELECTOR = "alternate_selector"  # try different UI element
    SCROLL_AND_RETRY   = "scroll_and_retry"    # scroll to expose element
    VISION_FALLBACK    = "vision_fallback"     # VLM coordinate detection
    ABORT              = "abort"

RETRY_LADDER = [
    RetryStrategy.SAME_ACTION,
    RetryStrategy.ALTERNATE_SELECTOR,
    RetryStrategy.SCROLL_AND_RETRY,
    RetryStrategy.VISION_FALLBACK,
    RetryStrategy.ABORT,
]

@dataclass
class StepMemory:
    """Short-term memory passed forward to each perception & planning call."""
    subgoal_description: str
    action_type:         str
    target:              Optional[str]
    result:              str           # "success" | "failed"
    screen_type:         str           # "native" | "webview" | "keyboard_open"
    screen_before:       str           # UI signature pre-action
    screen_after:        str           # UI signature post-action
    screen_description:  Optional[str] = None  # VLM description for WebView screens
    key_state_after:     Optional[str] = None  # e.g. "playing New York Nagaram | Pause"
```

---

## Snippet 4 — Deterministic Goal-Completion Detection

**File:** `agents/coordinator.py`  
**Shows:** UI-tree heuristics that avoid a VLM call when goal is provably complete

```python
def _detect_goal_completion(utterance: str, elements: list) -> tuple[bool, str]:
    """
    Checks post-action element tree for strong completion signals —
    avoids a VLM round-trip when outcome is deterministic.
    """
    goal_type = _classify_goal_type(utterance)

    if goal_type == "media":
        # Pause button visible ⟹ playback is active ⟹ DONE
        for cd in _all_cd:
            if any(sig in cd for sig in ("pause", "⏸", "‖")):
                return True, f"Media playing — Pause detected (cd='{cd}')"

    elif goal_type == "navigation":
        # Active navigation: ETA/Turn/End present AND Start button gone
        nav_indicators = ("end", "eta", "min", "arrival", "head ", "turn ", "reroute")
        has_nav = any(ind in cd for cd in _all_cd for ind in nav_indicators)
        has_start = any("start" in t for t in _all_text)
        if has_nav and not has_start:
            return True, "Navigation active — ETA visible, Start button gone"

    elif goal_type == "messaging":
        for txt in _all_text:
            if any(s in txt for s in ("sent", "delivered", "message sent")):
                return True, f"Message sent (text='{txt}')"

    elif goal_type == "call":
        for txt in _all_text:
            if any(s in txt for s in ("calling", "ringing", "on call", "dialing")):
                return True, f"Call active (text='{txt}')"

    return False, ""
```

---

## Snippet 5 — Three-Layer Perception Pipeline Configuration

**File:** `perception/perception_pipeline.py`  
**Shows:** Layered fallback architecture (UI Tree → CV → VLM), YAML-driven config

```python
"""
Layer 1: UI Tree (Primary)     — 10-50 ms,   70-80% success, pixel-perfect coords
Layer 2: CV Detection (YOLOv8) — 200-400 ms, geometrically finds all elements
Layer 3: VLM Selection (Gemini) — 300-600 ms, picks from CV candidates by ID

KEY INSIGHT: Coordinates always come from deterministic sources.
             VLM only classifies — it NEVER generates coordinates.
"""

@dataclass
class PerceptionConfig:
    # Layer enables
    ui_tree_enabled: bool = True
    cv_vlm_enabled:  bool = True

    # UI Tree
    ui_tree_min_score:        float = 0.5
    ui_tree_prefer_clickable: bool  = True

    # CV Detector (YOLOv8)
    detector_confidence: float = 0.25
    detector_device:     str   = "auto"

    # VLM (Gemini / Claude)
    vlm_max_tokens:  int   = 10
    vlm_temperature: float = 0.0
    vlm_timeout:     float = 10.0

    # Policy gate
    min_confidence: float = 0.70
    max_retries:    int   = 2

    @classmethod
    def from_yaml(cls, path: str = "config/perception_config.yaml") -> "PerceptionConfig":
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls(**data.get("perception", {}))
```

---

## Snippet 6 — Skeleton Goal Decomposer (Two-Layer Planning)

**File:** `services/goal_decomposer.py`  
**Shows:** LLM decomposes abstract goal → phases; Coordinator grounds each phase reactively

```python
def decompose(self, utterance: str, current_screen=None,
              step_history=None) -> Goal:
    """
    Layer 1 (here):  LLM generates 2-4 abstract phases + commit actions.
    Layer 2 (Coordinator + ReactiveStepGenerator):
                     Each phase is grounded to concrete UI steps at runtime.
    """
    screen_context = self._extract_screen_context(current_screen)

    if step_history:
        history_lines = [
            f"{'✅' if m.result == 'success' else '❌'} "
            f"{m.action_type}({m.target or ''})"
            for m in step_history[-3:]
        ]
        screen_context += " | Recent: " + " → ".join(history_lines)

    phases, commit_actions, summary = self._create_skeleton(utterance, screen_context)

    goal = Goal(
        original_utterance=utterance,
        description=summary,
        phases=phases,
        pending_commits=commit_actions,
    )
    return goal

def replan_from_obstacle(self, goal, obstacle, current_screen=None,
                         step_history=None) -> List[Subgoal]:
    """Dynamic replanning: enriches context with VLM screen description
    from step history (critical for WebView screens) before calling LLM."""
    if step_history:
        history_lines = [
            f"{'✅' if m.result == 'success' else '❌'} "
            f"{m.action_type}({m.target}) on {m.screen_type}"
            + (f' [screen: "{m.screen_description[:120]}"]'
               if m.screen_description else "")
            for m in step_history[-5:]
        ]
```

---

## Snippet 7 — Multi-Provider VLM with Auto-Fallback

**File:** `services/vlm.py`  
**Shows:** Provider abstraction (Groq / Gemini / NVIDIA NIM), graceful degradation

```python
class VLMService:
    """Unified interface for VLM providers with automatic fallback."""

    def __init__(self, settings: Settings) -> None:
        self.provider_models = self._build_provider_models()
        self._initialize_clients()

    def _initialize_clients(self) -> None:
        # Groq
        if self.settings.groq_api_key:
            self.groq_client = groq.Groq(api_key=self.settings.groq_api_key)

        # Gemini (Google GenAI)
        if GEMINI_AVAILABLE and self.settings.gemini_api_key:
            self.gemini_client = genai.Client(api_key=self.settings.gemini_api_key)

        # NVIDIA NIM
        if self.settings.nvidia_api_key:
            from services.nvidia_nim import get_nvidia_client
            self.nvidia_client = get_nvidia_client(self.settings.nvidia_api_key)

    def _build_provider_models(self) -> dict:
        """Map each provider to the correct model based on the configured default."""
        return {
            "nvidia": self.settings.default_vlm_model
                      if self.settings.default_vlm_provider == "nvidia"
                      else self.settings.vlm_secondary_model,
            "gemini": self.settings.default_vlm_model
                      if self.settings.default_vlm_provider == "gemini"
                      else self.settings.fallback_vlm_model,
            "groq":   self.settings.default_vlm_model
                      if self.settings.default_vlm_provider == "groq"
                      else self.settings.fallback_vlm_model,
        }
```

---

## Snippet 8 — Intelligent Graph Routing (Conditional Edges)

**File:** `aura_graph/edges.py`  
**Shows:** Input-type routing (audio vs text skips STT), STT failure gating

```python
def route_from_start(state: TaskState) -> Literal["stt", "parse_intent", "error_handler"]:
    """Text/streaming input bypasses STT entirely."""
    input_type = state.get("input_type", "audio")
    if input_type in ("text", "streaming"):
        if state.get("transcript") or state.get("streaming_transcript"):
            return "parse_intent"
    return "stt"

def should_continue_after_stt(state: TaskState) -> Literal["parse_intent", "error_handler"]:
    """Gate: only proceed if transcript is meaningful."""
    transcript = state.get("transcript") or state.get("streaming_transcript") or ""
    if state.get("status") == "stt_failed" or len(transcript.strip()) < 2:
        return "error_handler"
    return "parse_intent"
```
