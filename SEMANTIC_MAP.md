# AURA Semantic Map
> Complete variable · function · class · import reference for every file in the codebase.
> Generated 2026-03-26. Organised bottom-up: config → state → graph → agents → services → perception → prompts → API → ADK/GCS → Android.

---

## Table of Contents
1. [Config Layer](#1-config-layer)
2. [LangGraph Layer](#2-langgraph-layer)
3. [Agents Layer](#3-agents-layer)
4. [Services Layer](#4-services-layer)
5. [Perception Layer](#5-perception-layer)
6. [Prompts Layer](#6-prompts-layer)
7. [Utils Layer](#7-utils-layer)
8. [API Handlers Layer](#8-api-handlers-layer)
9. [API Routes Layer](#9-api-routes-layer)
10. [ADK / GCS Layer](#10-adk--gcs-layer)
11. [Entry Point — main.py](#11-entry-point--mainpy)
12. [Android / Kotlin Layer](#12-android--kotlin-layer)
13. [Cross-Layer Dependency Map](#13-cross-layer-dependency-map)

---

## 1. Config Layer

### `config/settings.py`
**Singleton export:** `get_settings() → Settings`
**Global cache:** `_settings: Optional[Settings] = None`

#### Class `Settings(BaseSettings)`
All fields read from `.env` via Pydantic Settings.

| Field | Type | Default / Env var |
|-------|------|-------------------|
| `groq_api_key` | str | `GROQ_API_KEY` |
| `gemini_api_key` | str | `GEMINI_API_KEY` |
| `openrouter_api_key` | str | `OPENROUTER_API_KEY` |
| `nvidia_api_key` | str | `NVIDIA_API_KEY` |
| `google_api_key` | str | `GOOGLE_API_KEY` |
| `google_cloud_project` | str | `GOOGLE_CLOUD_PROJECT` |
| `google_cloud_region` | str | `GOOGLE_CLOUD_REGION` |
| `gcs_logs_bucket` | str | `GCS_LOGS_BUCKET` |
| `gcs_logs_enabled` | bool | `GCS_LOGS_ENABLED` |
| `adk_app_name` | str | `ADK_APP_NAME` |
| `langchain_tracing_v2` | str | `LANGCHAIN_TRACING_V2` |
| `langchain_endpoint` | str | `LANGCHAIN_ENDPOINT` |
| `langchain_api_key` | str | `LANGCHAIN_API_KEY` |
| `langchain_project` | str | `LANGCHAIN_PROJECT` |
| `langchain_project_id` | str | `LANGCHAIN_PROJECT_ID` |
| `default_llm_provider` | str | `DEFAULT_LLM_PROVIDER` |
| `default_vlm_provider` | str | `DEFAULT_VLM_PROVIDER` |
| `default_stt_provider` | str | `DEFAULT_STT_PROVIDER` |
| `default_tts_provider` | str | `DEFAULT_TTS_PROVIDER` |
| `planning_provider` | str | `PLANNING_PROVIDER` |
| `planning_fallback_provider` | str | `PLANNING_FALLBACK_PROVIDER` |
| `fallback_vlm_provider` | str | `FALLBACK_VLM_PROVIDER` |
| `planning_model` | str | `PLANNING_MODEL` |
| `planning_fallback_model` | str | `PLANNING_FALLBACK_MODEL` |
| `safety_model` | str | `SAFETY_MODEL` |
| `crewai_model` | str | `CREWAI_MODEL` |
| `intent_classification_model` | str | `INTENT_CLASSIFICATION_MODEL` |
| `intent_classification_fallback` | str | `INTENT_CLASSIFICATION_FALLBACK` |
| `intent_classification_fallback_groq` | str | `INTENT_CLASSIFICATION_FALLBACK_GROQ` |
| `default_llm_model` | str | `DEFAULT_LLM_MODEL` |
| `llm_fallback_model` | str | `LLM_FALLBACK_MODEL` |
| `default_vlm_model` | str | `DEFAULT_VLM_MODEL` |
| `vlm_secondary_model` | str | `VLM_SECONDARY_MODEL` |
| `fallback_vlm_model` | str | `FALLBACK_VLM_MODEL` |
| `default_stt_model` | str | `DEFAULT_STT_MODEL` |
| `default_stt_language` | str | `DEFAULT_STT_LANGUAGE` |
| `default_tts_model` | str | `DEFAULT_TTS_MODEL` |
| `vlm_timeout_seconds` | float | `VLM_TIMEOUT_SECONDS` |
| `gemini_live_model` | str | `GEMINI_LIVE_MODEL` |
| `gemini_live_enabled` | bool | `GEMINI_LIVE_ENABLED` |
| `gemini_live_voice` | str | `GEMINI_LIVE_VOICE` |
| `gemini_live_transcription_language` | str | `GEMINI_LIVE_TRANSCRIPTION_LANGUAGE` |
| `use_vertex_ai` | bool | `USE_VERTEX_AI` |
| `graph_recursion_limit` | int | `GRAPH_RECURSION_LIMIT` |
| `graph_timeout_seconds` | float | `GRAPH_TIMEOUT_SECONDS` |
| `ui_tree_max_retries` | int | `UI_TREE_MAX_RETRIES` |
| `ui_tree_retry_delay_seconds` | float | `UI_TREE_RETRY_DELAY_SECONDS` |
| `step_history_window` | int | `STEP_HISTORY_WINDOW` |
| `enable_parallel_execution` | bool | `ENABLE_PARALLEL_EXECUTION` |
| `max_parallel_tasks` | int | `MAX_PARALLEL_TASKS` |
| `enable_provider_fallback` | bool | `ENABLE_PROVIDER_FALLBACK` |
| `use_universal_agent` | bool | `USE_UNIVERSAL_AGENT` |
| `default_perception_modality` | str | `DEFAULT_PERCEPTION_MODALITY` |
| `fast_perception_apps` | List[str] | `FAST_PERCEPTION_APPS` |
| `perception_cache_enabled` | bool | `PERCEPTION_CACHE_ENABLED` |
| `perception_cache_ttl` | int | `PERCEPTION_CACHE_TTL` |
| `perception_cache_max_actions` | int | `PERCEPTION_CACHE_MAX_ACTIONS` |
| `adaptive_delays_enabled` | bool | `ADAPTIVE_DELAYS_ENABLED` |
| `adaptive_delays_min_samples` | int | `ADAPTIVE_DELAYS_MIN_SAMPLES` |
| `agent_monitor_enabled` | bool | `AGENT_MONITOR_ENABLED` |
| `agent_monitor_history_size` | int | `AGENT_MONITOR_HISTORY_SIZE` |
| `agent_monitor_alert_success_rate` | float | `AGENT_MONITOR_ALERT_SUCCESS_RATE` |
| `agent_monitor_alert_loop_rate` | float | `AGENT_MONITOR_ALERT_LOOP_RATE` |
| `vlm_proactive_enabled` | bool | `VLM_PROACTIVE_ENABLED` |
| `vlm_cache_ttl` | int | `VLM_CACHE_TTL` |
| `host` | str | `HOST` |
| `port` | int | `PORT` |
| `reload` | bool | `RELOAD` |
| `cors_origins` | List[str] | `CORS_ORIGINS` |
| `require_api_key` | bool | `REQUIRE_API_KEY` |
| `device_api_key` | str | `DEVICE_API_KEY` |
| `log_level` | str | `LOG_LEVEL` |
| `environment` | str | `ENVIRONMENT` |

**Inner class `Config`:** `env_file=".env"`, `case_sensitive=False`

---

### `config/action_types.py`
**Exports:** `ACTION_REGISTRY`, `VALID_ACTIONS`, `NO_UI_ACTIONS`, `NO_SCREEN_ACTIONS`, `SIMPLE_DEVICE_ACTIONS`, `VISUAL_ACTIONS`, `COORDINATE_REQUIRING_ACTIONS`, `CONVERSATIONAL_ACTIONS`, `DANGEROUS_ACTIONS`, `REQUIRED_FIELDS`

#### Dataclass `ActionMeta` (frozen)
| Field | Type | Meaning |
|-------|------|---------|
| `needs_ui` | bool | Requires UI tree / perception analysis |
| `needs_coords` | bool | Requires pixel coordinates from Navigator |
| `needs_perception` | bool | Requires full perception bundle |
| `is_dangerous` | bool | Requires user confirmation |
| `is_conversational` | bool | Responds only, no device action |
| `required_fields` | tuple | Fields that must be in intent |
| `opens_panel` | bool | Opens Android settings panel |

**Helper functions:**
- `_get_actions_where(**criteria) → List[str]` — filter registry by metadata flags
- `get_action_meta(action) → Optional[ActionMeta]`
- `needs_perception(action) → bool`
- `needs_coordinates(action) → bool`
- `needs_ui_analysis(action) → bool`
- `is_dangerous(action) → bool`
- `is_conversational(action) → bool`
- `is_valid_action(action) → bool`
- `get_required_fields(action) → List[str]`
- `opens_settings_panel(action) → bool`

---

### `config/gesture_tools.py`
**Exports:** `GESTURE_REGISTRY`, `get_no_target_actions()`, `get_rsg_actions_prompt()`, `resolve_gesture()`

#### Dataclass `FixedGesture` (frozen)
| Field | Type | Default |
|-------|------|---------|
| `action` | str | `"swipe"` |
| `start_x_frac` | float | `0.5` |
| `start_y_frac` | float | `0.0` |
| `start_y_abs` | Optional[int] | `None` |
| `end_x_frac` | float | `0.5` |
| `end_y_frac` | float | `0.6` |
| `end_y_abs` | Optional[int] | `None` |
| `duration` | int | `400` |

**Method:** `resolve(sw: int, sh: int) → Dict[str, Any]` — fractional → pixel coords

#### Dataclass `GestureTool`
| Field | Type |
|-------|------|
| `name` | str |
| `description` | str |
| `prompt_description` | str |
| `needs_target` | bool |
| `needs_coords` | bool |
| `needs_perception` | bool |
| `fixed_gesture` | Optional[FixedGesture] |
| `examples` | List[str] |

**Functions:**
- `get_no_target_actions() → Set[str]`
- `get_rsg_actions_prompt() → str` — builds AVAILABLE ACTIONS block for agent prompts
- `resolve_gesture(name, sw, sh) → Optional[Dict[str, Any]]`

---

## 2. LangGraph Layer

### `aura_graph/state.py`
**Module constant:** `MAX_EXECUTED_STEPS = 50`

**LangGraph reducers:**
- `add_errors(existing, new) → str` — join with semicolon
- `update_status(existing, new) → str` — last writer wins
- `set_once(existing, new) → float` — first writer wins
- `cap_executed_steps(existing, new) → List[ActionResult]` — merge + cap at 50
- `update_step(existing, new) → int` — take maximum

#### TypedDict `TaskState`
All fields `Optional`. Key annotated fields:

| Field | Reducer | Purpose |
|-------|---------|---------|
| `raw_audio` | — | Raw PCM bytes |
| `transcript` | — | STT result |
| `streaming_transcript` | — | Live transcript |
| `language` | — | Detected language |
| `intent` | — | Parsed IntentObject dict |
| `plan` | — | Generated plan dict |
| `current_step` | `update_step` | Current graph step |
| `executed_steps` | `cap_executed_steps` | Action history (max 50) |
| `feedback_message` | `update_status` | TTS text |
| `error_message` | `add_errors` | Accumulated errors |
| `retry_count` | — | Current retry count |
| `max_retries` | — | Max retry limit |
| `session_id` | — | Session identifier |
| `status` | `update_status` | Task status string |
| `start_time` | — | Task start timestamp |
| `end_time` | `set_once` | Task end timestamp |
| `task_id` | — | Unique task ID |
| `perception_bundle` | — | PerceptionBundle object |
| `snapshot_id` | — | Perception snapshot ID |
| `agent_state` | — | Goal-driven state dict |
| `goal_status` | — | Goal completion status |
| `goal_summary` | — | Natural language summary |
| `original_request` | — | Original utterance |
| `log_url` | — | GCS public URL |

---

### `aura_graph/graph.py`
**Module-level:** `logger`

**Functions:**

| Function | Signature | Purpose |
|----------|-----------|---------|
| `_create_initial_state` | `(input_type, raw_audio, transcript, streaming_transcript, config) → dict` | Build initial TaskState |
| `create_aura_graph` | `() → StateGraph` | Assemble full 11-node graph |
| `_finalize_and_upload` | `async (cmd_logger, status, task_id, result)` | Finalize log + GCS upload |
| `compile_aura_graph` | `(checkpointer=None) → Any` | Init all services+agents, compile graph |
| `execute_aura_task_from_streaming` | `async (app, streaming_transcript, config, thread_id, track_workflow, session_id) → dict` | WebSocket path |
| `execute_aura_task_from_text` | `async (app, text_input, config, thread_id, track_workflow) → dict` | ADK / REST path |
| `execute_aura_task` | `async (app, raw_audio, config, thread_id) → dict` | Audio file path |
| `get_graph_info` | `() → dict` | Graph topology info |
| `run_aura_task` | `async (app, initial_state, config) → dict` | Hard-timeout graph runner |

**Graph nodes:** `stt → parse_intent → perception → execute → speak → error_handler → decompose_goal → validate_outcome → retry_router → next_subgoal → coordinator`

---

### `aura_graph/edges.py`
**Module-level:** `_CONVERSATIONAL_TRANSCRIPT_RE` (compiled regex), `logger`, `_SETTINGS`

**Routing functions:**

| Function | Input node | Possible outputs |
|----------|-----------|-----------------|
| `route_from_start` | START | `stt`, `parse_intent`, `error_handler` |
| `should_continue_after_stt` | stt | `parse_intent`, `error_handler` |
| `should_continue_after_intent_parsing` | parse_intent | `perception`, `execute`, `speak`, `error_handler`, `coordinator` |
| `should_continue_after_perception` | perception | `create_plan`, `speak`, `error_handler`, `coordinator` |
| `should_continue_after_execution` | execute | `speak`, `error_handler`, `perception`, `validate_outcome` |
| `should_continue_after_speak` | speak | `__end__` |
| `should_continue_after_validation` | validate_outcome | `next_subgoal`, `retry_router`, `speak` |
| `should_continue_after_retry_router` | retry_router | `perception`, `execute`, `speak` |
| `should_continue_after_error_handling` | error_handler | `perception`, `speak`, `__end__` |

---

### `aura_graph/core_nodes.py`
**Global service singletons (all `None` until `initialize_nodes()`):**
`settings`, `stt_service`, `llm_service`, `vlm_service`, `tts_service`, `accessibility_service`, `device_executor_service`, `commander_agent`, `responder_agent`, `screen_vlm_agent`, `validator_agent`

**Helper functions:**
- `add_workflow_step(state, node_name, status, description, output, error, details)`
- `track_agent_usage(state, agent_name)`
- `update_workflow_step(state, node_name, status, description, output, error, execution_time, details)`

**Node functions:**

| Node | Type | Key locals | Returns |
|------|------|-----------|---------|
| `stt_node` | sync | `streaming_transcript`, `existing_transcript`, `raw_audio`, `language_hint`, `transcript` | `dict` with `transcript` |
| `parse_intent_node` | sync | `start_time`, `existing_intent`, `transcript`, `intent_obj`, `intent_dict`, `action` | `dict` with `intent` |
| `execute_node` | async | `intent_dict`, `action_plan`, `execution_mode`, `execution_successful`, `execution_steps` | `dict` with `executed_steps` |
| `speak_node` | sync | `intent_dict`, `status`, `executed_steps_data`, `full_context`, `session`, `feedback_message`, `audio_data`, `audio_base64` | `dict` with `feedback_message`, `spoken_audio` |
| `error_handler_node` | sync | `error_message`, `error_type`, `recovery_message`, `should_retry` | `dict` with `status`, `feedback_message` |
| `validate_intent_node` | sync | `intent_dict`, `intent_obj`, `validation_result` | `dict` with `validation_routing` |

**Initializer:**
`initialize_nodes(app_settings, app_stt_service, app_llm_service, app_vlm_service, app_tts_service, app_accessibility_service, app_device_executor_service, app_commander_agent, app_responder_agent, app_screen_vlm_agent=None, app_validator_agent=None)`

---

## 3. Agents Layer

### `agents/__init__.py`
**`__all__`:** `CommanderAgent`, `ResponderAgent`, `ScreenVLM`, `ValidatorAgent`, `ValidationResult`, `PlannerAgent`, `PerceiverAgent`, `ActorAgent`, `VerifierAgent`, `Coordinator`

> `ScreenVLM` is a backward-compat alias for `PerceiverAgent`.

---

### `agents/commander.py`
**Module-level:** `logger`

#### Class `CommanderAgent`
| Instance var | Type |
|-------------|------|
| `llm_service` | `LLMService` |
| `rule_classifier` | `Optional[...]` |

| Method | Signature | Purpose |
|--------|-----------|---------|
| `__init__` | `(llm_service)` | Load rule classifier |
| `_build_context_block` | `(context) → str` | Build context string (app, last action, UI) |
| `_parse_direct` | `(transcript, context) → IntentObject` | LLM parse with markdown fence strip |
| `_fallback_intent` | `(transcript, error) → IntentObject` | Low-confidence fallback |
| `parse_intent` | `(transcript, context) → IntentObject` | Rule-first, LLM fallback |
| `_normalize_action` | `(action) → str` | Underscore format + alias map |
| `_normalize_intent_fields` | `(intent_data) → dict` | Move data to correct fields |
| `validate_intent` | `(intent) → bool` | Check action exists, confidence ≥ 0.3 |

---

### `agents/coordinator.py`
**Module-level constants:**

| Constant | Value | Purpose |
|----------|-------|---------|
| `MAX_TOTAL_ACTIONS` | 30 | Hard action cap per task |
| `MAX_REPLAN_ATTEMPTS` | 3 | Replan limit |
| `MAX_STEP_MEMORY` | 20 | History window cap |
| `MAX_SCROLL_SEARCH` | 2 | Max scroll attempts per target |
| `COMMIT_ACTIONS` | set | Finalisation action names |
| `NO_TARGET_ACTIONS` | list | Actions not needing element target |
| `_MEDIA_STATE_KW` | tuple | Media playback state keywords |
| `_MEDIA_GOAL_KW` | set | Media goal detection |
| `_NAV_GOAL_KW` | set | Navigation goal detection |
| `_MSG_GOAL_KW` | set | Messaging goal detection |
| `_CALL_GOAL_KW` | set | Call goal detection |

**Module-level functions:**
- `_media_state_summary(elements) → str`
- `_classify_goal_type(utterance) → str`
- `_detect_goal_completion(utterance, elements, pre_elements) → tuple[bool, str]`

#### Class `Coordinator`
| Instance var | Type |
|-------------|------|
| `planner` | `PlannerAgent` |
| `perceiver` | `PerceiverAgent` |
| `actor` | `ActorAgent` |
| `verifier` | `VerifierAgent` |
| `task_progress` | `TaskProgressService` |
| `reactive_gen` | `Optional[ReactiveStepGenerator]` |

| Method | Signature | Purpose |
|--------|-----------|---------|
| `execute` | `async (utterance, intent, session_id, perception_bundle) → dict` | Main goal-driven loop |
| `_extract_cart_count` | `(screen_state) → Optional[int]` | Parse cart badge count |
| `_find_search_submit_coords` | `(elements) → Optional[Tuple[int,int]]` | Find search/submit button |
| `_extract_open_app_phase` | `(phase_desc) → Optional[str]` | Parse app name from phase |
| `_find_input_field_name` | `(screen_context) → Optional[str]` | Extract form field name |
| `_is_input_element` | `(el) → bool` | Check if element is editable |
| `_match_intended_edit_field` | `(field_hint, description, edit_elements, all_elements) → Optional[dict]` | 5-layer field matching |
| `_apply_replan` | `(goal, new_subgoals)` | Replace remaining subgoals |
| `_broadcast_start` | `(session_id, goal)` | WebSocket task start |
| `_broadcast_step` | `(session_id, success)` | WebSocket step update |
| `_ask_rsg_scroll_direction` | `async (target, screenshot_b64, screen_context) → Optional[str]` | VLM scroll direction |
| `_handle_target_not_found` | `async (subgoal, intent, screen_state, goal, executed_steps, total_actions, screen_hash_history, step_memory) → str` | 5-stage retry ladder |
| `_snapshot_pre` | `async (intent) → str` | Capture UI signature before action |

---

### `agents/perceiver_agent.py`
**Module-level:** `logger`

#### Dataclass `ScreenState`
| Field | Type | Default |
|-------|------|---------|
| `perception_bundle` | Any | — |
| `ui_signature` | str | — |
| `elements` | List[Dict] | `[]` |
| `target_match` | Optional[Dict] | `None` |
| `screen_type` | str | `"unknown"` |
| `screen_description` | Optional[str] | `None` |
| `vlm_annotated_b64` | Optional[str] | `None` |
| `replan_suggested` | bool | `False` |
| `replan_reason` | str | `""` |
| `highlighted_b64` | Optional[str] | `None` |
| `element_description` | Optional[str] | `None` |

#### Class `PerceiverAgent`
| Instance var | Type |
|-------------|------|
| `vlm_service` | `VLMService` |
| `perception_pipeline` | `PerceptionPipeline` |
| `perception_controller` | `Optional[PerceptionController]` |

| Method | Signature | Purpose |
|--------|-----------|---------|
| `perceive` | `async (subgoal, intent, force_screenshot, step_history, user_command, plan_context) → ScreenState` | Main entry — describe + locate |
| `_get_omniparser_elements` | `(bundle) → List[Dict]` | Run OmniParser on screenshot |
| `_classify_screen` | `(elements, bundle) → str` | native / webview / keyboard / empty |
| `_find_target` | `(elements, target) → Optional[Dict]` | Best accessibility-tree match |
| `_y_center` | `(element) → int` | Vertical center of bounding box |
| `_best_element` | `(elements) → Dict` | Smallest bounding-box area |
| `_extract_coordinates` | `(element) → Dict` | Tap coords from element bounds |
| `build_annotated_screenshot` | `(screenshot_b64, elements, screen_width, screen_height) → tuple` | Draw numbered SoM boxes |
| `_describe_from_ui_elements` | `(elements, focus) → str` | Fallback description from UI tree |
| `locate_element` | `(subgoal, perception_bundle, user_command, plan_context) → Optional[Dict]` | Public location API |
| `locate_with_annotated_ui_tree` | `(elements, screenshot_b64, target, screen_width, screen_height, user_command, plan_context, subgoal_description) → Optional[Dict]` | SoM + UI tree location |
| `locate_from_bundle` | `(bundle, target, screen_context, user_command, plan_context, subgoal_description) → Optional[Dict]` | Location from full bundle |
| `describe_screen` | `async (bundle, focus, goal, subgoal_hint, recent_steps) → str` | VLM screen description |
| `describe_and_locate` | `async (bundle, target, subgoal_hint, goal, recent_steps, ui_elements_text, elements) → dict` | Combined one-shot VLM call |
| `get_metrics` | `() → Dict` | Perception metrics |

**Semantic cross-check logic (in `describe_and_locate` and `locate_with_annotated_ui_tree`):**
```
_commit_kws = {"add", "cart", "buy", "pay", "delete", "remove", "purchase", "send", "order"}
_is_commit_target = bool(_target_words & _commit_kws)
_should_reject = (not _has_overlap and not _el_is_unlabelled) or
                 (not _has_overlap and _el_is_unlabelled and _is_commit_target)
```

---

### `agents/actor_agent.py`
**Module-level:** `logger`

#### Dataclass `ActionResult`
| Field | Type |
|-------|------|
| `success` | bool |
| `action_type` | str |
| `coordinates` | Optional[Tuple[int,int]] |
| `duration_ms` | float |
| `error` | Optional[str] |
| `details` | Optional[Dict] |

#### Class `ActorAgent`
| Instance var | Type |
|-------------|------|
| `executor` | `GestureExecutor` |

**Method:** `execute(async, action_type, target, coordinates, parameters) → ActionResult`
Zero LLM calls. Resolves fixed gestures, builds action dict, injects swipe defaults.

---

### `agents/planner_agent.py`
**Module-level:** `logger`, `ATOMIC_MAX_WORDS = 12`, `COMMIT_KEYWORDS: set`

#### Class `PlannerAgent`
| Instance var | Type |
|-------------|------|
| `decomposer` | `GoalDecomposer` |

| Method | Purpose |
|--------|---------|
| `create_plan(utterance, intent, perception, step_history) → Goal` | Decompose into Goal with Subgoals |
| `replan(goal, obstacle, perception, step_history) → List[Subgoal]` | Revised subgoals after failure |
| `_ensure_commit_coverage(utterance, goal)` | Validate commit action coverage |

---

### `agents/responder.py`
**Module-level:** `logger`, `PANEL_ACTION_RESPONSES: dict`

#### Class `ResponderAgent`
| Instance var | Type |
|-------------|------|
| `llm_service` | `LLMService` |
| `tts_service` | `TTSService` |

| Method | Purpose |
|--------|---------|
| `generate_feedback(intent, status, execution_results, error_message, transcript, conversation_history, has_introduced, conversation_turn, is_follow_up, full_context, goal_summary, completed_steps) → str` | LLM response generation |
| `_extract_intent(intent, transcript)` | Pull action/recipient/content |
| `_detect_emotion(transcript) → Optional[str]` | Regex emotion detection |
| `_build_prompt(...) → str` | Build compact LLM prompt |
| `_clean_response(response) → str` | Strip markdown for TTS |
| `_fallback(status, error) → str` | Natural fallback text |
| `speak_feedback(message, voice_settings) → Optional[bytes]` | TTS conversion |

---

### `agents/validator.py`
**Module-level:** `logger`

#### Class `ValidationResult`
| Field | Type | Default |
|-------|------|---------|
| `is_valid` | bool | — |
| `confidence` | float | `1.0` |
| `issues` | List[str] | `[]` |
| `suggestions` | List[str] | `[]` |
| `requires_confirmation` | bool | `False` |
| `refined_intent` | Optional[Dict] | `None` |

**Method:** `to_dict() → Dict`

#### Class `ValidatorAgent`
No instance variables. Zero LLM calls.
**Method:** `validate_intent(intent) → ValidationResult` — rule-based Python checks only.

---

### `agents/verifier_agent.py`
**Module-level:**
- `ACTION_SETTLE_DELAYS: dict` — per-action stabilisation delays (tap: 0.8s, open_app: 3.0s, etc.)
- `DEFAULT_STABILIZE_DELAY = 0.8`
- `ERROR_INDICATORS: list`

**Function:** `get_settle_delay(action_type) → float`

#### Class `VerifierAgent`
| Instance var | Type |
|-------------|------|
| `perception_controller` | `PerceptionController` |
| `llm_service` | `Optional[LLMService]` |

| Method | Purpose |
|--------|---------|
| `capture_post_state(async, intent, action_type) → Tuple[Any, str, List]` | Wait + capture post-action state |
| `is_error_screen(elements) → bool` | Check first 10 elements for error strings |
| `semantic_verify(async, action_desc, elements, success_hint) → tuple[bool, str]` | LLM second-pass verification |

---

### `agents/visual_locator.py`
**Module-level:** `logger`

#### Class `ScreenVLM`
*(Backward-compat alias — functionally identical to `PerceiverAgent`)*

| Instance var | Type |
|-------------|------|
| `vlm_service` | `VLMService` |
| `_perception_pipeline` | `Optional[...]` |

All methods mirror `PerceiverAgent` plus:
- `find_all_clickable_elements(bundle, user_command) → List[Dict]`
- `verify_element_at_position(screenshot_b64, x, y, element_description) → bool`

---

## 4. Services Layer

### `services/llm.py`
**Module-level:** `logger`, `GEMINI_AVAILABLE: bool`, `genai`, `genai_types`

#### Class `LLMService`
| Instance var | Type |
|-------------|------|
| `settings` | `Settings` |
| `groq_client` | `Optional[groq.Groq]` |
| `gemini_client` | `Optional[Any]` |
| `nvidia_client` | `Optional[Any]` |

| Method | Purpose |
|--------|---------|
| `__init__(settings)` | Init + `_initialize_clients()` |
| `_initialize_clients()` | Create clients from API keys |
| `run(prompt, provider, model, caller_agent, system_prompt, **kwargs) → str` | Unified LLM call with fallback |
| `_call_provider(provider, model, prompt, **kwargs) → str` | Dispatch to provider |
| `_call_groq(model, prompt, **kwargs) → str` | Groq call |
| `_call_gemini(model, prompt, **kwargs) → str` | Gemini call |
| `_call_nvidia(model, prompt, **kwargs) → str` | NVIDIA NIM call |
| `_normalize_model_for_provider(provider, model) → str` | Ensure model matches provider |

---

### `services/vlm.py`
**Module-level:** `logger`, `GEMINI_AVAILABLE: bool`, `genai`, `genai_types`

#### Class `VLMService`
| Instance var | Type |
|-------------|------|
| `settings` | `Settings` |
| `groq_client` | `Optional[groq.Groq]` |
| `gemini_client` | `Optional[Any]` |
| `nvidia_client` | `Optional[Any]` |
| `provider_models` | `dict` |

| Method | Purpose |
|--------|---------|
| `analyze_image(image_data, prompt, provider, model, system_prompt, **kwargs) → str` | Single-image VLM call |
| `analyze_two_images(before_b64, after_b64, prompt, provider, model, temperature) → str` | Before/after comparison |
| `_call_groq_two_images(...)` | Groq two-image call |
| `_call_gemini_two_images(...)` | Gemini two-image call |
| `_call_provider(provider, model, image_data, prompt, **kwargs) → str` | Dispatch to VLM provider |
| `_call_gemini(model, image_data, prompt, **kwargs) → str` | Gemini VLM |
| `_call_groq(model, image_data, prompt, **kwargs) → str` | Groq VLM |
| `_call_nvidia(model, image_data, prompt, **kwargs) → str` | NVIDIA NIM VLM |
| `_prepare_image_for_gemini(image_data) → PIL.Image` | Image prep for Gemini |
| `_prepare_image_for_groq(image_data) → str` | Image prep (base64) for Groq |

---

### `services/stt.py`
**Module-level:** `logger`, `GEMINI_AVAILABLE: bool`, `genai`, `genai_types`

#### Class `STTService`
| Instance var | Type |
|-------------|------|
| `settings` | `Settings` |
| `groq_client` | `Optional[groq.Groq]` |
| `gemini_model` | `Optional[Any]` |

| Method | Purpose |
|--------|---------|
| `transcribe(audio_data, provider, model, language, **kwargs) → str` | Batch transcription |
| `transcribe_streaming(audio_data, is_final, language, provider, model) → str` (async) | Streaming transcription |
| `_call_provider(provider, model, audio_data, language, **kwargs) → str` | Dispatch |
| `_convert_pcm_to_wav(pcm_data, sample_rate, channels, sample_width) → bytes` | PCM → WAV |
| `_call_groq(model, audio_data, language, **kwargs) → str` | Groq Whisper |

---

### `services/tts.py`
**Module-level:** `logger`

#### Class `TTSService`
**Class variable:** `VOICE_MAP: dict` — PlayAI name → Edge-TTS name mapping

| Instance var | Type |
|-------------|------|
| `settings` | `Settings` |
| `default_voice` | `str` (`"en-US-AriaNeural"`) |

| Method | Purpose |
|--------|---------|
| `speak_async(text, voice) → Optional[bytes]` (async) | Text → WAV bytes |
| `speak(text, voice) → Optional[bytes]` | Sync wrapper |
| `_sanitize_for_speech(text) → str` (static) | Strip markdown |

---

### `services/gesture_executor.py`
**Module-level:** `logger`, `_gesture_executor: Optional[GestureExecutor]`

**Enums:** `GestureType` (TAP/SWIPE/LONG_PRESS/SCROLL/TYPE_TEXT/DOUBLE_TAP), `ExecutionStrategy` (WEBSOCKET/COMMAND_QUEUE/DIRECT)

**Dataclasses:** `GestureResult` (success, gesture_type, execution_time, strategy_used, error, details), `ExecutionPlan` (steps, total_steps, estimated_time, requires_ui_refresh)

#### Class `GestureExecutor`
| Instance var | Type |
|-------------|------|
| `execution_history` | `List[GestureResult]` |
| `current_plan` | `Optional[ExecutionPlan]` |
| `_screen_size` | `Tuple[int,int]` (1080×2400) |

Key methods: `execute_plan(async)`, `_execute_tap`, `_execute_swipe`, `_execute_scroll`, `_execute_long_press`, `_execute_type`, `_execute_app_launch`, `_execute_deep_link`, `_execute_wait`, `_execute_system_action`, `_send_gesture(async)`, `_extract_coordinates`, `_update_screen_size(async)`

**Singleton:** `get_gesture_executor() → GestureExecutor`

---

### `services/perception_controller.py`
**Module-level:** `logger`, `_perception_controller: Optional[PerceptionController]`

#### Class `PerceptionController`
**Class vars:** `ESCALATION_ORDER: List[PerceptionModality]`, `MAX_RETRIES_PER_LEVEL = 2`

| Instance var | Type |
|-------------|------|
| `ui_tree_service` | — |
| `screenshot_service` | — |
| `screen_vlm` | `Optional[ScreenVLM]` |
| `last_bundle` | `Optional[PerceptionBundle]` |
| `_description_cache` | `Dict[str, str]` |
| `escalation_level` | `int` |
| `retries_at_level` | `int` |
| `consecutive_failures` | `int` |

Key methods: `request_perception(async, ...)`, `invalidate_bundle(reason)`, `escalate(failure_reason) → bool`, `reset_escalation()`, `should_abort() → bool`

**Singleton:** `get_perception_controller(screen_vlm) → PerceptionController`

---

### `services/hitl_service.py`
**Module-level:** `logger`, `_hitl_service: Optional[HITLService]`

**Enum `HITLQuestionType`:** CONFIRMATION / SINGLE_CHOICE / MULTIPLE_CHOICE / TEXT_INPUT / NOTIFICATION / ACTION_REQUIRED / CHOICE_WITH_TEXT

**Dataclass `HITLQuestion`:** id, question_type, title, message, options, default_option, timeout_seconds, allow_cancel, action_type, metadata, created_at, tts_text

**Dataclass `HITLResponse`:** question_id, success, cancelled, timed_out, confirmed, selected_option, selected_options, text_input, acknowledged, action_completed, response_time

#### Class `HITLService`
**Class var:** `DEFAULT_TIMEOUT = 60.0`

| Instance var | Type |
|-------------|------|
| `_websockets` | `WeakSet[WebSocket]` |
| `_pending_questions` | `Dict[str, asyncio.Future]` |
| `_question_history` | `List[HITLQuestion]` |
| `_enabled` | `bool` |

Key methods: `ask_confirmation(async)`, `ask_choice(async)`, `ask_multiple_choice(async)`, `ask_text_input(async)`, `ask_contextual(async)`, `notify(async)`, `wait_for_user_action(async)`, `handle_response(data) → bool`, `register_voice_answer(text) → bool`

**Singleton:** `get_hitl_service() → HITLService`

---

### `services/task_progress.py`
**Module-level:** `logger`, `_task_progress_service: Optional[TaskProgressService]`

**Dataclasses:** `TaskProgressItem` (id, description, status, action_type), `TaskProgress` (session_id, goal_description, items, current_index, is_complete, is_aborted)

**Function:** `_run_async_safe(coro)` — run async from any context

#### Class `TaskProgressService`
| Instance var | Type |
|-------------|------|
| `_websockets` | `WeakSet[WebSocket]` |
| `_sessions` | `dict[str, TaskProgress]` |
| `_cancel_events` | `dict[str, threading.Event]` |

Key methods: `start_task(session_id, goal_description, subgoals)`, `complete_current_step(session_id, success)`, `finish_task(session_id)`, `abort_task(session_id, reason)`, `is_cancelled(session_id) → bool`, `emit_agent_status(agent, output)`

**Singleton:** `get_task_progress_service() → TaskProgressService`

---

### `services/prompt_guard.py`
**Module-level:** `logger`, `PROMPT_GUARD_TIMEOUT_S = 8.0`, `_prompt_guard: Optional[PromptGuard]`

#### Class `PromptGuard`
**Class vars:** `MODEL = "meta-llama/llama-prompt-guard-2-86m"`, `SAFE_LABELS`, `UNSAFE_LABELS`

| Method | Purpose |
|--------|---------|
| `available: bool` (property) | Check if Groq client present |
| `is_safe(user_input) → Tuple[bool, float]` | Safety check |
| `check_or_raise(user_input) → str` | Raise if flagged |

**Singletons:** `get_prompt_guard()`, `initialize_prompt_guard(client, model)`

---

### `services/policy_engine.py`
**Module-level:** `logger`, `OPA_AVAILABLE`, `USE_REGOPY`, `_policy_engine: Optional[PolicyEngine]`

**Dataclasses:** `PolicyDecision` (allowed, reason, requires_confirmation, confirmation_message, policy_violated, metadata), `ActionContext` (action_type, target, app_name, package_name, text_content, coordinates, user_id, session_id, timestamp, previous_actions, action_count_last_minute)

#### Class `PolicyEngine`
**Class vars:** `BLOCKED_ACTIONS`, `BLOCKED_FINANCIAL_APPS`, `BLOCKED_AUTH_APPS`, `BANKING_PATTERNS`, `CONFIRMATION_ACTIONS`, `RATE_LIMITS`, `FINANCIAL_DENIAL_MESSAGE`

Key methods: `evaluate(async, context) → PolicyDecision`, `_check_blocked_actions`, `_check_sensitive_apps`, `_check_confirmation_required`, `_check_rate_limits`, `_check_dangerous_content`

**Singleton:** `get_policy_engine() → PolicyEngine`

---

### `services/reactive_step_generator.py`
**Module-level:** `logger`, `PHASE_COMPLETE_KEY = "__phase_complete__"`, `_LLM_EXECUTOR: ThreadPoolExecutor(max_workers=4)`

**Function:** `_is_commit_satisfied(commit, target) → bool`

#### Class `ReactiveStepGenerator`
| Instance var | Type |
|-------------|------|
| `llm_service` | `LLMService` |
| `vlm_service` | `Optional` |

Key methods:
- `generate_next_step(async, goal, screen_context, step_history, screenshot_b64, ui_hints, ui_elements, prev_subgoal, prev_action_succeeded, screen_width, screen_height, agent_memory) → Optional[Subgoal]`
- `_get_compressed_history(async, step_history, window_size) → tuple`
- `_detect_autocomplete_suggestion(prev_subgoal, ui_elements) → Optional[Subgoal]`
- `_detect_goal_achieved_from_screen(screen_context, original_utterance) → bool`
- `_parse_json(text) → Optional[dict]`

---

### `services/reflexion_service.py`
**Module-level:** `logger`, `_ACTION_BUCKETS: list[tuple[str, list[str]]]`, `_REFLEXION_EXECUTOR: ThreadPoolExecutor(max_workers=2)`, `_reflexion_service: Optional[ReflexionService]`

#### Class `ReflexionService`
| Instance var | Type |
|-------------|------|
| `llm_service` | — |
| `storage_path` | `Path` (`data/reflexion_lessons`) |

Methods: `generate_lesson(async, goal, step_history, failure_reason) → str`, `get_lessons_for_goal(async, goal, max_lessons) → list`, `_store_lesson(async, goal, lesson, failure_reason)`, `_goal_key(goal) → str` (static)

**Singleton:** `get_reflexion_service(llm_service) → Optional[ReflexionService]`

---

## 5. Perception Layer

### `perception/perception_pipeline.py`
**Module-level:** `logger`, `LANGSMITH_AVAILABLE`, `traceable`

#### Dataclass `PerceptionConfig`
Key fields: `ui_tree_enabled`, `cv_vlm_enabled`, `ui_tree_min_score=0.5`, `detector_confidence=0.25`, `vlm_timeout=10.0`, `min_confidence=0.70`, `max_retries=2`

**Class method:** `from_yaml(path) → PerceptionConfig`

#### Dataclass `LocateResult`
| Field | Type |
|-------|------|
| `success` | bool |
| `coordinates` | Optional[Tuple[int,int]] |
| `confidence` | float |
| `source` | str (`ui_tree`/`cv_vlm`/`heuristic`) |
| `element_info` | Optional[Dict] |
| `reason` | Optional[str] |
| `latency_ms` | float |
| `layer_attempted` | List[str] |

#### Dataclass `PerceptionMetrics`
Fields: `ui_tree_attempts`, `ui_tree_successes`, `cv_vlm_attempts`, `cv_vlm_successes`, `heuristic_attempts`, `heuristic_successes`, `total_failures`, `total_latency_ms`
Methods: `record_success`, `record_attempt`, `record_failure`, `ui_tree_success_rate`, `cv_vlm_success_rate`

#### Class `PerceptionPipeline`
| Instance var | Type |
|-------------|------|
| `config` | `PerceptionConfig` |
| `vlm_service` | `VLMService` |
| `_detector` | `Optional[OmniParserDetector]` (lazy) |
| `_vlm_selector` | `Optional[VLMSelector]` (lazy) |
| `_heuristic` | `HeuristicSelector` |
| `metrics` | `PerceptionMetrics` |

Key methods: `locate_element(intent, ui_tree, screenshot, screen_bounds) → LocateResult`, `_try_ui_tree`, `_try_cv_vlm`, `detect_only`, `_try_heuristic`, `warmup()`

**Factories:** `create_perception_pipeline(vlm_service)`, `create_default_pipeline(vlm_service)`

---

### `perception/omniparser_detector.py`
**Module-level:** `logger`, lazy globals `_YOLO`, `_cv2`, `_Image`, `_HF_HUB`

#### Dataclass `Detection`
| Field | Type |
|-------|------|
| `id` | str (letter A–Z, AA–ZZ) |
| `class_name` | str |
| `box` | Tuple[int,int,int,int] (x1,y1,x2,y2) |
| `center` | Tuple[int,int] |
| `confidence` | float |
| `area` | int (computed) |

#### Class `OmniParserDetector`
| Instance var | Type |
|-------------|------|
| `model_path` | Optional[str] |
| `huggingface_repo` | str (`"microsoft/OmniParser-v2.0"`) |
| `confidence_threshold` | float |
| `iou_threshold` | float |
| `device` | str |
| `image_size` | int (640) |
| `max_detections` | int (50) |
| `cache_ttl` | float (5.0) |
| `_model` | Optional (lazy) |
| `_letter_ids` | List[str] |
| `_model_cache` | class-level Dict |
| `_detection_cache` | class-level Dict |

Key methods: `detect(image, use_cache) → List[Detection]`, `draw_set_of_marks(image, detections, ...) → np.ndarray`, `annotated_image_to_base64(annotated_image, format, quality) → str`, `warmup()`, `clear_cache()`

**Factory:** `create_detector(model_path, device, confidence, iou) → OmniParserDetector`

---

### `perception/vlm_selector.py`
**Module-level:** `logger`

#### Dataclass `SelectionResult`
Fields: `success`, `selected_id`, `detection`, `coordinates`, `confidence`, `reasoning`, `screen_description`, `source`, `latency_ms`

#### Class `VLMSelector`
| Instance var | Type |
|-------------|------|
| `vlm_service` | `VLMService` |
| `max_tokens` | int |
| `temperature` | float |
| `timeout` | float |
| `retry_count` | int |
| `SELECTION_PROMPT` | str |
| `DETAILED_PROMPT` | str |

Methods: `select(annotated_image, detections, intent, use_detailed_prompt) → SelectionResult`, `_parse_response(response, detections, intent) → SelectionResult`, `select_with_fallback(annotated_image, detections, intent) → SelectionResult`

#### Class `HeuristicSelector`
**Method:** `select(detections, intent) → SelectionResult` — class name matching + position heuristics

**Factory:** `create_vlm_selector(vlm_service) → VLMSelector`

---

## 6. Prompts Layer

### `prompts/__init__.py`
**Module-level:** `PROMPT_VERSIONS: Dict[str, str]`

**Re-exports from submodules:**
- `builder`: `PromptMode`, `build_aura_agent_prompt`, `build_runtime_line`, `build_prompt_report`
- `personality`: `AURA_PERSONALITY`, `EMOTIONAL_PATTERNS`, `EMOTIONAL_RESPONSES`, `USER_NAME`
- `reasoning`: `REASONING_PROMPT_V2`, `VISION_REASONING_PROMPT`, `GOAL_VERIFICATION_PROMPT`, `get_reasoning_prompt`, `build_loop_warning`
- `planning`: `GOAL_DECOMPOSITION_PROMPT`, `REPLANNING_PROMPT`, `SIMPLE_COMMANDS`, `get_planning_prompt`, `get_replanning_prompt`
- `skeleton_planning`: `get_skeleton_planning_prompt`
- `reactive_step`: `get_reactive_step_prompt`, `get_reactive_step_messages`
- `dynamic_rules`: `get_contextual_rules`
- `classification`: `INTENT_CLASSIFICATION_PROMPT`, `INTENT_PARSING_PROMPT`, `INTENT_PARSING_PROMPT_WITH_CONTEXT`, `VISUAL_PATTERNS`, `get_classification_prompt`, `get_parsing_prompt`
- `vision`: `ELEMENT_LOCATION_PROMPT`, `ACTION_LOCATION_PROMPT`, `ELEMENT_SELECTION_PROMPT`, `SCREEN_ANALYSIS_PROMPT`, `ORDINAL_LOCATION_PROMPT`, `VISUAL_TRUST_RULES`, `get_vision_prompt`, `get_element_prompt`, `get_action_prompt`, `get_ordinal_prompt`
- `screen_state`: `SCREEN_STATE_PROMPT`, `STATE_INDICATORS`, `detect_screen_state_prompt`, `detect_state_from_text`, `get_blocking_state_action`
- `screen_reader`: `SCREEN_DESCRIPTION_PROMPT`, `FOCUS_INSTRUCTIONS`, `get_screen_description_prompt`

---

### `prompts/builder.py`

#### Enum `PromptMode(str, Enum)`
| Value | Constant | Meaning |
|-------|----------|---------|
| `"full"` | `FULL` | All sections (main agents) |
| `"minimal"` | `MINIMAL` | Identity + safety + runtime only |
| `"none"` | `NONE` | Bare identity line only |

**Functions:**
- `_build_identity_line(agent_name) → str`
- `_build_safety_section(mode) → list[str]`
- `_build_runtime_section(agent_name, model, task_id, mode) → list[str]`
- `_build_android_context_section(mode) → list[str]`
- `_build_output_discipline_section(mode) → list[str]`
- `_build_commit_safety_section(mode) → list[str]`
- `build_aura_agent_prompt(agent_name, mode, model, task_id, extra_sections) → str`
- `build_runtime_line(agent_name, model, task_id, extra) → str`
- `build_prompt_report(prompt, agent_name) → dict` — char count, token approx, section list

---

### `prompts/personality.py`
**Pure string constants:**
- `USER_NAME = "Dinesh kumar"`
- `AURA_SKILLS: str`
- `AURA_PERSONALITY: str`
- `EMOTIONAL_RESPONSES: Dict[str, str]` — frustrated / grateful / confused / urgent
- `EMOTIONAL_PATTERNS: Dict[str, List[str]]` — regex patterns per emotion
- `AURA_GREETING_PROMPT: str`

---

### `prompts/reactive_step.py`
**Module-level:**
- `REACTIVE_STEP_SYSTEM: str` — v4.0.0 system prompt
- `_USER_TEMPLATE: str` — user message template

**Functions:**
- `_build_system(screen_context, phase) → str` — inject contextual rules + action list
- `get_reactive_step_messages(goal, phase, screen_context, steps_done, pending_commits, last_failure, ui_hints, ui_elements, prev_action, agent_memory, model, task_id) → tuple` — returns `(system_prompt, user_prompt)`
- `get_reactive_step_prompt(...) → str` — single-string backward-compat path

---

### `prompts/reasoning.py`
**Module-level:**
- `REASONING_PROMPT_V2: str`
- `VISION_REASONING_PROMPT: str`
- `GOAL_VERIFICATION_PROMPT: str`
- `LOOP_WARNING_TEMPLATE: str`

**Functions:**
- `get_reasoning_prompt(observation, context, history, max_element_index, loop_warning, model, task_id) → str`
- `build_loop_warning(loop_type, suggestion) → str`

---

### `prompts/vision.py`
**Module-level:**
- `VISUAL_TRUST_RULES: str` — shared ghost-container / coordinate-validation rules
- `ELEMENT_LOCATION_PROMPT: str`
- `ACTION_LOCATION_PROMPT: str`
- `ELEMENT_SELECTION_PROMPT: str` — Set-of-Marks VLM selection prompt
- `SCREEN_ANALYSIS_PROMPT: str`
- `ORDINAL_LOCATION_PROMPT: str`

**Functions:**
- `get_vision_prompt(prompt_type, **kwargs) → str`
- `get_element_prompt(target, width, height, action_context) → str`
- `get_action_prompt(action, width, height) → str`
- `get_ordinal_prompt(ordinal, item_type, index, width, height) → str`

---

## 7. Utils Layer

### `utils/token_tracker.py`
**Module-level:** `_PERSISTENCE_FILE = "logs/token_usage.jsonl"`, `DEFAULT_TASK_BUDGET = 0`, `logger`

#### Dataclass `TokenUsage`
Fields: `timestamp`, `agent`, `model_type`, `provider`, `model`, `prompt_tokens`, `completion_tokens`, `total_tokens`

#### Dataclass `TokenStats`
Fields: `total_calls`, `total_prompt_tokens`, `total_completion_tokens`, `total_tokens`, `by_agent: Dict[str,int]`, `by_model: Dict[str,int]`, `by_provider: Dict[str,int]`

#### Class `TokenTracker` (singleton)
| Instance var | Type |
|-------------|------|
| `usage_history` | `List[TokenUsage]` |
| `_task_budgets` | `Dict[str, int]` |
| `_task_usage` | `Dict[str, int]` |
| `_initialized` | `bool` |

| Method | Purpose |
|--------|---------|
| `track(agent, model_type, provider, model, prompt_tokens, completion_tokens, total_tokens, task_id) → bool` | Track + enforce budget |
| `get_stats(agent) → TokenStats` | Aggregated stats |
| `set_task_budget(task_id, max_tokens)` | Set per-task cap |
| `check_task_budget(task_id) → Tuple[bool, int, int]` | (within_budget, used, max) |
| `clear_task(task_id)` | Remove task records |
| `reset()` | Clear all history |
| `get_recent(count) → List[TokenUsage]` | Last N records |
| `_load_persisted()` | Load from JSONL on disk |
| `_append_to_disk(usage)` | Append to JSONL file |

**Global singleton:** `token_tracker: TokenTracker`

---

### `utils/fuzzy_classifier.py`
**Module-level:** `GROQ_AVAILABLE`, `GEMINI_AVAILABLE`, `logger`, `CLASSIFIER_MODEL_TIMEOUT_S = 8.0`, `AGENT_MAPPING: Dict[RequiredAgents, List[str]]`

#### Enum `RequiredAgents`
RESPONDER_ONLY / COMMANDER_RESPONDER / COMMANDER_NAVIGATOR_RESPONDER / COMMANDER_EXECUTOR_RESPONDER / ALL_AGENTS

#### Class `ClassificationCache`
| Instance var | Type |
|-------------|------|
| `cache` | `Dict[str, Tuple[Dict, datetime]]` |
| `ttl` | `timedelta` |
| `max_size` | `int` |

Methods: `_generate_key(intent, transcript) → str`, `get(intent, transcript) → Optional[Dict]`, `set(intent, transcript, result)`

#### Class `AIIntentClassifier`
| Instance var | Type |
|-------------|------|
| `groq_client` | `Optional[Groq]` |
| `gemini_model` | `Optional[genai.GenerativeModel]` |
| `cache` | `ClassificationCache` |
| `classification_prompt` | `str` |

Key methods: `classify_intent(intent, transcript, context) → Dict`, `_classify_with_ai(...)`, `_fallback_classification(intent, transcript) → Dict`

---

### `utils/error_types.py`

#### Enum `ErrorType(str, Enum)`
| Value | Constant |
|-------|----------|
| `"stt_failed"` | `STT_FAILED` |
| `"intent_failed"` | `INTENT_FAILED` |
| `"blocked"` | `BLOCKED` |
| `"planning_failed"` | `PLANNING_FAILED` |
| `"perception_failed"` | `PERCEPTION_FAILED` |
| `"target_not_found"` | `TARGET_NOT_FOUND` |
| `"screen_mismatch"` | `SCREEN_MISMATCH` |
| `"execution_failed"` | `EXECUTION_FAILED` |
| `"gesture_rejected"` | `GESTURE_REJECTED` |
| `"input_field_missing"` | `INPUT_FIELD_MISSING` |
| `"action_loop"` | `ACTION_LOOP` |
| `"screen_loop"` | `SCREEN_LOOP` |
| `"budget_exhausted"` | `BUDGET_EXHAUSTED` |
| `"token_budget_exceeded"` | `TOKEN_BUDGET_EXCEEDED` |
| `"hitl_timeout"` | `HITL_TIMEOUT` |
| `"stuck"` | `STUCK` |
| `"replan_limit"` | `REPLAN_LIMIT` |
| `"unknown"` | `UNKNOWN` |

#### Dataclass `RecoveryStrategy` (frozen)
| Field | Type | Default |
|-------|------|---------|
| `action` | str | — (retry/replan/abort/ask_user) |
| `max_attempts` | int | `1` |
| `escalate_to` | Optional[str] | `None` |
| `user_message` | str | `"Something went wrong. I'll try again."` |

**Module-level:** `RECOVERY_STRATEGIES: dict[ErrorType, RecoveryStrategy]`

**Functions:**
- `get_recovery(error: ErrorType | str) → RecoveryStrategy`
- `classify_abort_reason(abort_reason: str) → ErrorType`

---

## 8. API Handlers Layer

### `api_handlers/websocket_router.py`
**Module-level:** `logger`, `router: APIRouter`, `conversation_manager: ConversationManager`, `_openrouter_client: Optional[openai.OpenAI]`, `_groq_client: Optional[Groq]`, `CLASSIFIER_REQUEST_TIMEOUT_S = 8.0`, `CLASSIFIER_TOTAL_TIMEOUT_S = 12.0`

**Functions:**
- `background_websocket_reader(websocket, stop_event) → Coroutine` — handles `ui_tree_response`, `screenshot_response`, `gesture_ack`, `hitl_response`, `cancel_task`
- `_ensure_screen_capture_ready(websocket) → Coroutine[bool]` — MediaProjection permission gate
- `_get_openrouter_client() → Optional[openai.OpenAI]`
- `_get_groq_client() → Optional[Groq]`

---

### `api_handlers/device_router.py`
**Module-level:** `router: APIRouter` (prefix=`/device`), `logger`, `APP_INVENTORY_FILE: Path`

**Pydantic models:** `AppInfo`, `DeviceRegistration`, `DeviceUIData`, `GestureRequest`

**Endpoints (all under `/device`):**

| Method | Path | Handler | Purpose |
|--------|------|---------|---------|
| POST | `/register` | `register_device` | Register Android device |
| POST | `/ui-data` | `upload_ui_data` | Upload UI hierarchy + screenshot |
| POST | `/execute-gesture` | `execute_gesture` | Execute gesture |
| GET | `/status` | `get_device_status` | Connection status |
| GET | `/ui-snapshot` | `get_ui_snapshot` | Current UI snapshot |
| POST | `/request-ui` | `request_ui_capture` | Request fresh capture |
| GET | `/commands/pending` | `get_pending_commands` | Polling for commands |
| POST | `/commands/{id}/result` | `report_command_result` | Report result |
| POST | `/commands/queue` | `queue_command` | Queue a command |
| GET | `/apps/{device_name}` | `get_device_apps` | App inventory |
| POST | `/disconnect` | `disconnect_device` | Disconnect |
| POST | `/gesture-ack` | `receive_gesture_ack` | Gesture acknowledgment |
| POST | `/screen-capture-permission` | `receive_screen_capture_permission` | Permission result |

**Helpers:** `_load_app_inventory() → Dict`, `_store_app_inventory(device_name, apps)`

---

### `api_handlers/real_accessibility_api.py`
**Module-level:** `router: APIRouter`, `logger`

**Pydantic models:** `DeviceConnectionRequest`, `UIDataRequest`, `GestureExecutionRequest`, `UIAnalysisResponse`

**Endpoints:**

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/connect` | Register device + accessibility service |
| POST | `/ui-data` | Receive UI data from AccessibilityService |
| GET | `/current-ui` | Get UI analysis |
| POST | `/execute-gesture` | Execute gesture |
| GET | `/screenshot` | Get current screenshot |
| POST | `/find-element` | Find element by text/class/contentDesc |
| GET | `/device-info` | Device info |

---

## 9. API Routes Layer

### `api/tasks.py`
**Module-level:** `logger`, `router: APIRouter`

**Endpoints:**

| Method | Path | Handler | Purpose |
|--------|------|---------|---------|
| POST | `/tasks/execute` | `execute_task` | Execute voice command |
| POST | `/tasks/execute-file` | `execute_task_from_file` | Execute from audio file upload |
| WS | `/tasks/ws` | `tasks_websocket` | Real-time task streaming |

WebSocket messages handled: `ping → pong`, `execute → task_start / task_progress / task_complete / error`

---

### `api/health.py`
**Module-level:** `logger`, `settings`, `router: APIRouter`

**Pydantic model:** `HITLTestRequest` (question_type, title, message, options, timeout)

**Endpoints:**

| Method | Path | Handler | Rate limit |
|--------|------|---------|-----------|
| POST | `/test/hitl` | `test_hitl` | — |
| GET | `/health` | `health_check` | 60/min |

---

### `api/device.py`
**Module-level:** `logger`, `router: APIRouter`

**Endpoints:**

| Method | Path | Rate limit | Purpose |
|--------|------|-----------|---------|
| GET | `/device/status` | 60/min | Device status + hints |
| GET | `/device/screenshot` | 30/min | Latest JPEG screenshot |
| GET | `/device/ui-elements` | 30/min | UI element array |
| POST | `/device/request-screen-capture` | 10/min | Request permission dialog |
| POST | `/device/register` | 10/min | Register with API key |

---

### `api/demo.py`
**Module-level:** `logger`, `router: APIRouter` (tags=["Demo"]), `_DEMO_HTML: str`

**Endpoint:** GET `/demo` → `demo_dashboard()` — serve judging dashboard (no auth, live screenshot refresh every 2s, GCS log links)

---

### `api/debug.py`
**Module-level:** `logger`, `router: APIRouter` (prefix=`/debug`)

**Endpoints:** `/state`, `/device`, `/ui-tree`, `/screenshot`, `/perception`, `/detections`, `/metrics`, `/errors/recent`, `/clear-cache`, `/config`, `/unified-logs`, `/unified-logs/timeline`, `/unified-logs/trace/{trace_id}`, `/unified-logs/export/html`, `/unified-logs/export/json`

---

### `api/config_api.py`
**Module-level:** `logger`, `settings`, `router: APIRouter`, `_tts_service: Optional[TTSService]`, `TTS_VOICES: List[TTSVoice]` (8 voices)

**Pydantic models:** `TTSVoice`, `TTSVoicesResponse`, `TTSVoiceUpdateRequest`, `TTSPreviewResponse`

**Endpoints:** GET `/tts/voices`, POST `/tts/voice`, GET `/tts/preview/{voice_id}`, GET `/config`

---

### `api/graph.py`
**Module-level:** `logger`, `router: APIRouter`

**Endpoint:** GET `/graph/info` → `get_graph_information()` (30/min, lru_cache)

---

### `api/workflow.py`
**Module-level:** `logger`, `router: APIRouter`, `workflow_sessions: Dict[str, Dict[str, Any]]`

**Function:** `store_workflow_state(session_id, state)` — write to in-memory dict

**Endpoints:** GET `/sessions`, GET `/{session_id}`, GET `/viewer/ui|flow|visual`, DELETE `/{session_id}`, DELETE `/sessions/all`

---

### `api/sensitive_policy.py`
**Module-level:** `logger`, `router: APIRouter`

**Pydantic models:** `SensitiveCheckRequest`, `AddKeywordRequest`

**Endpoints:** POST `/sensitive-policy/check`, GET `/sensitive-policy/stats`, POST `/sensitive-policy/keywords/add` (auth), POST `/sensitive-policy/toggle` (auth), GET `/sensitive-policy/keywords`

---

## 10. ADK / GCS Layer

### `adk_agent.py`
**Module-level:**
- `logger: Logger`
- `_compiled_graph: Optional[Any] = None`
- `aura_tool: Optional[FunctionTool]`
- `root_agent: Optional[Agent]` — named "AURA", wraps `execute_aura_task` FunctionTool

**Functions:**

| Function | Signature | Purpose |
|----------|-----------|---------|
| `set_compiled_graph` | `(app: Any)` | Store compiled graph at startup |
| `_get_graph` | `() → Any` | Return graph or raise RuntimeError |
| `execute_aura_task` | `(command: str, session_id: str = "adk-session") → dict` | ADK FunctionTool entry point |

`execute_aura_task` returns: `{success: bool, response: str, steps_taken: int, execution_log_url: Optional[str]}`

---

### `adk_streaming_server.py`
**Module-level:**
- `logger`
- `_THINKING_HEADER_RE: re.Pattern`
- `_ADK_AVAILABLE: bool`
- `_Runner`, `_InMemorySessionService`, `_LiveRequestQueue`, `_RunConfig`, `_StreamingMode` — guarded ADK class refs
- `_Part`, `_Blob`, `_Content`, `_Modality` — guarded Genai type refs
- `_VAD_TYPES_AVAILABLE: bool`
- `_session_service: Optional[object]` — lazy singleton
- `_runner: Optional[object]` — lazy singleton

**Functions:**

| Function | Purpose |
|----------|---------|
| `_is_thinking_content(text) → bool` | Filter model reasoning vs speech |
| `_get_runner() → object` | Lazy-init ADK Runner singleton |
| `handle_live_websocket(websocket, session_id, voice, transcription_language)` async | Gemini Live bidi handler |

**Nested in `handle_live_websocket`:**
- `receive_from_device()` — handles `ping`, `audio_chunk`, `screenshot`, `ui_tree`
- `send_to_device()` — streams audio, transcripts, task progress back

---

### `gcs_log_uploader.py`
**Module-level:** `logger`, `_gcs: Optional[module]`, `_GCS_AVAILABLE: bool`

**Functions:**

| Function | Signature | Purpose |
|----------|-----------|---------|
| `_resolve_api_key` | `() → Optional[str]` | Best available Google credential |
| `upload_log_to_gcs` | `(log_path, session_id) → Optional[str]` | Sync GCS upload |
| `upload_log_to_gcs_async` | `async (log_path, session_id) → Optional[str]` | Async wrapper via `run_in_executor` |

GCS blob name format: `logs/{safe_id}.html`

---

## 11. Entry Point — `main.py`

**Module-level:**
- `logger`
- `settings`
- `uvicorn_access: Logger`
- `graph_app: Any` — global compiled graph (set in lifespan)
- `_is_production: bool`
- `allowed_origins: List[str]`
- `_allow_credentials: bool`
- `_test_router_available: bool`

**FastAPI app middleware stack:** TrustedHostMiddleware → CORSMiddleware → RequestId → RateLimit

**Routers mounted** (all prefixed with `API_PREFIX`): config_api, demo, device, graph, health, tasks, websocket, workflow, debug, sensitive_policy, device_router (api_handlers), task_router, websocket_router, real_accessibility_api, test_router (conditional)

**WebSocket:** `/ws/live` mounted conditionally when `GEMINI_LIVE_ENABLED=true`

**Functions:**

| Function | Type | Purpose |
|----------|------|---------|
| `lifespan(app)` | async ctx mgr | Compile graph, set compiled graph in ADK agent, warm up services |
| `root(request)` | GET `/` | Serve AURA UI HTML |
| `health_check_legacy(request)` | GET `/health` | Legacy health check |
| `test_suite(request)` | GET `/test` | Test dashboard |
| `gemini_live_test(request)` | GET `/live-test` | Gemini Live browser test |
| `live_websocket_endpoint(websocket, session_id, voice, transcription_language)` | WS `/ws/live` | Gemini Live handler |
| `run_server()` | sync | uvicorn.run() with production config |

---

## 12. Android / Kotlin Layer

### Build Configuration (`app/build.gradle.kts`)
| Setting | Value |
|---------|-------|
| `namespace` | `com.aura.aura_ui` |
| `applicationId` | `com.aura.aura_ui.feature` |
| `compileSdk` | 36 |
| `minSdk` | 24 |
| `targetSdk` | 36 |
| `versionCode` | 1 |
| `versionName` | `"1.0.0"` |
| `javaVersion` | 11 |

**Key dependencies:** Hilt DI, Retrofit2 + OkHttp3, Jetpack Compose + Material3, Navigation Compose, Coroutines, LiteRT-LM (Function Gemma), Porcupine (wake word), DataStore, Lottie

---

### `AuraApplication.kt`
**Class `AuraApplication : Application`** `@HiltAndroidApp`
`onCreate()` → `AuraOverlayManager.initialize(context)`

---

### `VoiceConversationActivity.kt`
**Class `VoiceConversationActivity : AppCompatActivity`**

| Property | Type | Value |
|----------|------|-------|
| `micButton`, `endButton`, `transcriptText`, `statusText` | UI widgets | — |
| `webSocket` | `WebSocket?` | — |
| `isRecording` | `@Volatile Boolean` | — |
| `audioRecord` | `AudioRecord?` | — |
| `sessionId` | `String?` | — |
| `SAMPLE_RATE` | const Int | 16000 |
| `WS_ENDPOINT` | hardcoded | `ws://10.0.2.2:8000/ws/conversation` |

**Incoming WebSocket message types handled:** `transcript`, `response`, `request_ui_tree`, `request_screenshot`, `execute_gesture`, `launch_app`, `launch_deep_link`, `task_progress`

**Key methods:** `connectWebSocket()`, `handleExecuteGesture(gesture, commandId)`, `sendGestureAck(commandId, success, error)`, `handleLaunchApp(packageName, candidates, commandId)`, `startActualRecording()`, `playAudioFromBase64(audioBase64)`, `parseWavHeader(data) → WavInfo`

**Inner data classes:** `WavInfo(sampleRate, channels, encoding, dataOffset, dataLength)`, `ConversationMessage(text, isUser)`

---

### `network/BackendApiClient.kt`
**Class `BackendApiClient(serverUrl: String)`**
**Timeouts:** connect/read/write = 10s

| Method | HTTP | Path | Returns |
|--------|------|------|---------|
| `fetchPendingCommands(deviceName)` | GET | `/device/commands/pending` | `Result<List<Command>>` |
| `reportCommandResult(commandId, result)` | POST | `/device/commands/{id}/result` | `Result<Unit>` |
| `testConnection()` | GET | `/device/status` | `Result<Boolean>` |

---

### `data/network/AuraApiService.kt`
**Retrofit interface `AuraApiService`**

| Method | HTTP | Path |
|--------|------|------|
| `executeTask(request)` | POST | `/tasks/execute` |
| `executeTaskFromFile(file, config, threadId)` | Multipart POST | `/tasks/execute-file` |
| `getHealthStatus()` | GET | `/health` |
| `getConfiguration()` | GET | `/config` |
| `getGraphInfo()` | GET | `/graph/info` |

---

### `data/network/ApiModels.kt`
**Data transfer objects:**

| Class | Key fields |
|-------|-----------|
| `TaskRequestDto` | audioData, inputType, config, threadId |
| `TaskResponseDto` | taskId, status, transcript, intent, spokenResponse, executionTime, errorMessage, debugInfo |
| `IntentDto` | action, recipient, content, confidence |
| `HealthResponseDto` | status, version, timestamp, services |
| `ConfigurationDto` | llmProvider, llmModel, sttProvider, vlmProvider, vlmModel, serverHost, serverPort |
| `TTSVoiceDto` | id, name, description, gender, accent, previewText |
| `TTSVoicesResponseDto` | voices, currentVoice |
| `TTSVoiceUpdateRequestDto` | voiceId |
| `TTSPreviewResponseDto` | voiceId, audioBase64, audioFormat |

---

### `data/Command.kt`
| Class | Key fields |
|-------|-----------|
| `CommandResponse` | status, deviceName, commandCount, commands, timestamp |
| `Command` | commandId, commandType, payload, createdAt |
| `CommandResult` | success, error, timestamp |
| `AppInfo` | packageName, appName, isSystemApp, versionName, deepLinks, intentFilters, deepLinkUri |
| `IntentFilterInfo` | action, categories, dataScheme, dataHost |

---

### `di/AppModule.kt`
**`@Module @InstallIn(SingletonComponent::class) object AppModule`**

**Server discovery:**
- `getAuraBaseUrl() → String` — calls `discoverAuraServer()`
- `discoverAuraServer() → String` — try cached URL → scan candidates
- `generateCandidateIPs() → List<String>` — includes `10.193.156.197`, `192.168.1.42`, `192.168.43.1`, ranges `192.168.1.1–10`, `192.168.0.x`, `10.0.2.2` (emulator)
- `isServerAvailable(url) → Boolean` — test `/health` with 2s timeout

**DI providers:** `provideAuraDatabase`, `provideSettingsRepository`, `provideAudioRepository`, `provideLogger`, `providePermissionManager`, `provideGson`, `provideOkHttpClient` (with logging interceptor), `provideRetrofit` (dynamic baseUrl), `provideAuraApiService`, `provideAssistantRepository`, `provideServerConfigManager`, `provideFunctionGemmaManager`

---

### `services/AssistantForegroundService.kt`
**Class `AssistantForegroundService : LifecycleService`** `@AndroidEntryPoint`

| Constant | Value |
|----------|-------|
| `ACTION_START_OVERLAY` | `"com.aura.aura_ui.START_OVERLAY"` |
| `ACTION_STOP_OVERLAY` | `"com.aura.aura_ui.STOP_OVERLAY"` |
| `ACTION_TOGGLE_LISTENING` | `"com.aura.aura_ui.TOGGLE_LISTENING"` |
| `notificationId` | 1001 |
| `channelId` | `"AuraAssistantChannel"` |
| Notification color | `0xFF6B4EFF` (AURA purple) |

**Hardcoded URLs:** reads from SharedPreferences `"aura_prefs"` key `"server_url"`

---

### `overlay/AuraOverlayManager.kt`
**`object AuraOverlayManager`** (Kotlin object singleton)

| Property | Type |
|----------|------|
| `appContext` | `Context?` |
| `_isVisible` | `MutableStateFlow<Boolean>` |
| `isVisible` | `StateFlow<Boolean>` |
| `_hasPermission` | `MutableStateFlow<Boolean>` |
| `hasPermission` | `StateFlow<Boolean>` |

Methods: `initialize(context)`, `checkPermission() → Boolean`, `requestPermission(context)`, `show() → Boolean`, `hide()`, `toggle() → Boolean`

**TODOs:** `isWakeWordAvailable()` returns false, `enableWakeWord(enabled)` is a placeholder

---

### `presentation/state/AssistantUiState.kt`
**Data class `AssistantUiState`**
All defaults shown:

| Field | Default |
|-------|---------|
| `hasAllPermissions` | `false` |
| `missingPermissions` | `emptyList()` |
| `isServiceRunning` | `false` |
| `voiceSessionState` | `VoiceSessionState.Idle` |
| `isLoading` | `false` |
| `errorMessage` | `null` |
| `currentTranscript` | `""` |
| `isListening` | `false` |
| `currentStep` | `""` |
| `responseText` | `""` |
| `isOverlayVisible` | `false` |
| `overlayPosition` | `Pair(0f, 0f)` |

---

### `domain/model/VoiceSessionState.kt`
**Sealed class `VoiceSessionState`**

| State | Fields |
|-------|--------|
| `Idle` | — |
| `Listening` | amplitude: Float, duration: Long |
| `Processing` | transcript: String |
| `Responding` | response: String, isPlayingAudio: Boolean |
| `Error` | error: String, canRetry: Boolean |
| `Initializing` | — |
| `Connecting` | — |

**Extension functions:** `isActive()`, `canBeInterrupted()`, `getDisplayText() → String`

---

### `data/audio/AudioCaptureManager.kt`
**`@Singleton @Inject class AudioCaptureManager`**

| Constant | Value |
|----------|-------|
| `SAMPLE_RATE` | 44100 |
| `CHANNEL_CONFIG` | CHANNEL_IN_MONO |
| `AUDIO_FORMAT` | ENCODING_PCM_16BIT |

Methods: `startCapture() → Flow<ByteArray>`, `getAmplitudeFlow() → Flow<Float>`, `stopCapture()`, `calculateAmplitude(buffer, samplesRead) → Float` (RMS → 0-1)

---

### `data/manager/ServerConfigManager.kt`
**`@Singleton @Inject class ServerConfigManager`**

| Constant | Value |
|----------|-------|
| `DEFAULT_PORT` | 8000 |
| `HEALTH_ENDPOINT` | `"/health"` |
| `CONNECTION_TIMEOUT` | 5s |
| `READ_TIMEOUT` | 10s |

Methods: `validateServerUrl(url) → ValidationResult`, `formatServerUrl(input) → String`, `testServerConnection(url) → ConnectionTestResult` (suspend), `extractIpAddress(input) → String`

---

### `accessibility/BackendCommunicator.kt`
**Class `BackendCommunicator`**

| Property | Type |
|----------|------|
| `backendUrl` | `AtomicReference<String>` |

Methods: `updateBackendUrl(url)`, `registerDevice(screenWidth, screenHeight, densityDpi, onComplete)`, `sendUIDataWithRequirement(screenshotData, requirement, onComplete)`, `sendUITreeOnly()`, `cleanup()`

HTTP timeouts: connect 10s / read 15s / write 15s

---

### `executor/CommandExecutor.kt`
**Class `CommandExecutor(context: Context)`**

**`executeCommand(command) → CommandResult`** routes by `commandType`:

| Type | Handler |
|------|---------|
| `launch_app` | `executeLaunchApp` |
| `launch_deep_link` | `executeLaunchDeepLink` |
| `gesture` | `executeGesture` → `parseGestureCommand` |
| `capture_screenshot` | `executeCaptureScreenshot` |
| `send_message` | **TODO — not implemented** |

**Gesture actions supported:** tap/click, swipe, scroll_up/down, back, home, dismiss_keyboard, press_enter/search, type/text_input/input, control_torch, wifi_on/off, bluetooth_on/off, volume_up/down, mute/unmute, brightness_up/down, capture_screenshot

---

### `functiongemma/FunctionGemmaManager.kt`
**Class `FunctionGemmaManager(context: Context)`**

| Constant | Value |
|----------|-------|
| `MODEL_FILENAME` | `"mobile_actions_q8_ekv1024.litertlm"` |
| `MODEL_SIZE_BYTES` | 302,000,000 (~302 MB) |
| `GALLERY_PKG` | `"com.google.aiedge.gallery"` |
| `GALLERY_MODEL_VERSION` | `"38942192c9b723af836d489074823ff33d4a3e7a"` |

**Enum `ModelState`:** NOT_DOWNLOADED / DOWNLOADING / DOWNLOADED / INITIALIZING / READY / ERROR

| Property | Type |
|----------|------|
| `_state` | `MutableStateFlow<ModelState>` |
| `_downloadProgress` | `MutableStateFlow<Float>` |
| `_pipelineEnabled` | `MutableStateFlow<Boolean>` |
| `engine` | `FunctionGemmaEngine` |
| `router` | `LocalCommandRouter?` |

Methods: `downloadModel(hfToken) → Boolean` (suspend, with resume support + redirect following), `initializeEngine() → Boolean` (suspend), `deleteModel()`, `cleanup()`

---

## 13. Cross-Layer Dependency Map

```
main.py
  ├── config/settings.py          (Settings singleton)
  ├── aura_graph/graph.py         (compile_aura_graph, execute_*)
  │     ├── aura_graph/state.py   (TaskState)
  │     ├── aura_graph/edges.py   (routing functions)
  │     ├── aura_graph/core_nodes.py (node implementations)
  │     └── agents/*              (all 9 agents)
  │           ├── services/llm.py
  │           ├── services/vlm.py
  │           ├── services/gesture_executor.py
  │           ├── services/perception_controller.py
  │           ├── services/hitl_service.py
  │           ├── services/task_progress.py
  │           ├── services/reactive_step_generator.py
  │           ├── services/reflexion_service.py
  │           ├── perception/perception_pipeline.py
  │           │     ├── perception/omniparser_detector.py  (YOLOv8)
  │           │     └── perception/vlm_selector.py
  │           └── prompts/*
  ├── api_handlers/websocket_router.py  (ws://…/ws/audio, ws://…/ws/device)
  ├── api_handlers/device_router.py
  ├── api_handlers/real_accessibility_api.py
  ├── api/tasks.py                (POST /tasks/execute)
  ├── api/health.py               (GET /health)
  ├── api/device.py               (GET /device/*)
  ├── api/demo.py                 (GET /demo)
  ├── api/debug.py                (GET /debug/*)
  ├── api/config_api.py           (GET/POST /tts/*, GET /config)
  ├── api/graph.py                (GET /graph/info)
  ├── api/workflow.py             (GET/DELETE /workflow/*)
  ├── api/sensitive_policy.py     (POST /sensitive-policy/*)
  ├── adk_agent.py                (ADK root_agent, FunctionTool)
  ├── adk_streaming_server.py     (ws://…/ws/live)
  └── gcs_log_uploader.py         (GCS upload after each task)

Android (UI/)
  ├── AuraApplication             → AuraOverlayManager.initialize()
  ├── AssistantForegroundService  → starts overlay, reads SharedPrefs server_url
  ├── VoiceConversationActivity   → WebSocket ws://10.0.2.2:8000/ws/conversation
  ├── di/AppModule                → Hilt DI graph, server discovery, Retrofit
  ├── data/network/AuraApiService → REST /tasks/execute, /health, /config
  ├── accessibility/BackendCommunicator → POST /device/ui-data, /device/register
  ├── executor/CommandExecutor    → gesture dispatch, AccessibilityService
  └── functiongemma/FunctionGemmaManager → on-device LiteRT model (~302 MB)
```

### Hardcoded URLs / Values (bugs to fix)
| File | Hardcoded value | Should be |
|------|----------------|-----------|
| `VoiceConversationActivity.kt` | `ws://10.0.2.2:8000/ws/conversation` | `BuildConfig.WS_URL` |
| `di/AppModule.kt` (candidates) | `192.168.1.41`, `10.193.156.197` | `BuildConfig.SERVER_IP` |
| `AssistantForegroundService.kt` | reads SharedPrefs manually | `ServerConfigManager` |
| `AssistantRepositoryImpl.kt` | `192.168.1.41:8000` fallback | `BuildConfig.SERVER_URL` |

### Known TODOs
- `AuraOverlayManager.isWakeWordAvailable()` → returns `false` (Porcupine not wired)
- `AuraOverlayManager.enableWakeWord(enabled)` → placeholder
- `CommandExecutor.executeSendMessage()` → `TODO — not implemented`
- Android `buildConfigField` for release WebSocket URL (CLAUDE.md Task 7)
