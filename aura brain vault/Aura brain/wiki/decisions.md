# Architectural Decisions

> Inferred from codebase analysis. Each decision captures *why* it was built this way, not just *what* was built.

---

## D1: VLM Selects from CV Candidates — Never Generates Coordinates

**Decision**: The VLM receives a screenshot annotated with labeled bounding boxes (Set-of-Marks) from the CV detector and outputs only a label letter. It never predicts `(x, y)` coordinates.

**Why**: VLMs hallucinate spatial locations. A model that says "tap at (500, 300)" is unreliable — small errors cause misses on small buttons. By letting YOLOv8 detect geometrically valid regions first, and having the VLM only *choose among them* semantically, we eliminate the spatial hallucination problem entirely.

**Impact**: The VLM's strength (semantic understanding of UI content) is used; its weakness (spatial precision) is avoided. The pipeline degrades gracefully — if CV detection finds nothing, the system falls back to UI tree parsing.

---

## D2: LangGraph for Agent Orchestration

**Decision**: Use LangGraph (StateGraph) rather than a custom loop or plain async code for the perceive→decide→act→verify cycle.

**Why**: LangGraph provides:
- Built-in state typing with reducers
- Conditional edges for retry/routing logic
- InMemoryStore for cross-task memory
- LangSmith tracing integration out-of-the-box
- Checkpointing for conversation continuity (thread_id)

**Impact**: `aura_graph/state.py` defines the single `TaskState` TypedDict that all nodes read/write. Routing is expressed as pure functions in `edges.py`, separating concerns cleanly.

---

## D3: 9 Single-Responsibility Agents

**Decision**: Split the automation pipeline into exactly 9 agents, each with a single job.

**Why**: A monolithic agent becomes impossible to debug. When a task fails, knowing that "the verifier reported success but the coordinator retried anyway" requires clean agent boundaries. Single-responsibility also enables mocking individual agents in tests.

**Impact**: `Coordinator` is the *only* agent that calls other agents. It is the orchestrator. The others are workers. `Validator` and `Actor` have zero LLM calls — this is intentional for speed and determinism.

---

## D4: Fail-Safe Safety Systems

**Decision**: Both Prompt Guard 2 (input safety) and OPA (gesture gating) allow actions when their respective APIs fail.

**Why**: The alternative (fail-closed) would make the system unusable when Groq is having an outage or OPA isn't installed. The risk of a genuinely dangerous command slipping through during an API error is lower than the cost of complete unavailability.

**Impact**: `services/prompt_guard.py` returns `safe=True` on any exception. `services/policy_engine.py` logs a warning "running in permissive mode" when OPA isn't installed and allows all non-blocklisted actions.

---

## D5: Tri-Provider LLM/VLM Architecture

**Decision**: Build provider-agnostic service wrappers with automatic fallback rather than committing to a single AI provider.

**Why**: Groq provides extremely high throughput (560-750 tps) which is critical for responsive voice UI. But Groq has rate limits and occasional downtime. Gemini provides the backup, and NVIDIA NIM offers a third option for specialized models.

**Impact**: Every `LLMService.run()` or `VLMService.analyze()` call transparently retries on a different provider. 429 errors from Gemini trigger exponential backoff with server-specified `retryDelay` parsing.

---

## D6: Android On-Device TTS as Default

**Decision**: Default `DEFAULT_TTS_PROVIDER=android` — the server sends text over WebSocket and the Android app speaks it locally.

**Why**: Server-side Edge-TTS synthesis takes ~1.4s of latency before audio starts playing. On-device TTS (Android's built-in speech engine) starts near-instantly. For a voice assistant, this latency difference is the difference between feeling responsive and feeling broken.

**Impact**: `services/tts.py` detects the provider and either streams WAV bytes (Edge-TTS) or sends `{"type": "tts_response", "text": "...", "voice": "..."}` JSON. The Android `AuraTTSManager` handles the on-device path.

---

## D7: Per-Subgoal Retry Ladder

**Decision**: The 5-stage retry ladder (`SAME_ACTION → ALTERNATE_SELECTOR → SCROLL_AND_RETRY → VISION_FALLBACK → ABORT`) resets for each new subgoal.

**Why**: Before this fix (G5), the task-level `replan_count` meant that early subgoal failures consumed retry budget that later subgoals needed. A complex multi-step task could abort on step 3 because steps 1-2 had already used all retries.

**Impact**: `aura_graph/agent_state.py`'s `Subgoal` class tracks `current_strategy_index` independently. `AgentState.reset_for_new_task()` resets all per-task counters when a new subgoal begins.

---

## D8: cap_executed_steps Reducer (MAX=50)

**Decision**: The `executed_steps` list in `TaskState` is capped at the 50 most recent entries via a custom LangGraph reducer.

**Why**: Without this cap, tasks with many steps (exploring deep UI trees, retrying many times) would accumulate hundreds of step records in state. This state is serialized and passed to the LLM on each turn, quickly blowing past context window limits.

**Impact**: Only the last 50 steps are retained. The reducer `cap_executed_steps` in `aura_graph/state.py` handles this transparently — nodes just append normally, and LangGraph calls the reducer on state merge.

---

## D9: Lazy Graph Init for ADK Integration

**Decision**: The ADK `FunctionTool` (`adk_agent.py`) stores a `None` reference to the compiled graph until `set_compiled_graph(app)` is called from `main.py` lifespan.

**Why**: `adk_agent.py` must be importable at module load time (ADK discovers agents at import). But `compile_aura_graph()` initializes many services (LLM, VLM, TTS, STT, all 9 agents) which require environment variables loaded and network connections available. Circular imports would also occur if `adk_agent.py` imported from `aura_graph.graph` at module level.

**Impact**: `_get_graph()` raises a clear `RuntimeError` if called before `set_compiled_graph()`. This turns a cryptic `AttributeError` into an actionable error message.

---

## D10: ReflexionService Bucketing by App

**Decision**: `ReflexionService._goal_key()` appends the detected app name to the goal type hash, creating separate lesson pools like `"play_media__spotify"` vs `"play_media__youtube"`.

**Why**: Before this fix (R0a), lessons from failed Spotify navigation were being injected into YouTube navigation attempts. The apps have different UI structures, so cross-app lessons were noise at best, harmful at worst.

**Impact**: Lessons in `data/reflexion_lessons/` are now keyed as `{normalized_goal}__{app_name}.json`. App detection uses the `_APP_NAMES` list in `ReflexionService`.
