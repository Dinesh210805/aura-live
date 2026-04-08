---
last_verified: 2026-04-08
source_files: []
status: current
---

# AURA Wiki — Change Log

---

## 2026-04-07 — Initial Wiki Generation

**Session**: Full codebase read and wiki brain build  
**Branch**: main  
**Author**: Claude Code (Sonnet 4.6)

### Pages Created
- `index.md` — Table of contents with all wiki pages
- `overview.md` — System overview, request lifecycle, tri-provider architecture
- `decisions.md` — Architectural decisions and rationale
- `log.md` — This file
- `aura_graph/graph.md` — LangGraph assembly and entry points
- `aura_graph/state.md` — TaskState TypedDict and reducers
- `aura_graph/edges.md` — Conditional routing and retry ladder
- `aura_graph/nodes.md` — Node implementations
- `agents/overview.md` — 9 agents overview and interaction map
- `agents/coordinator.md` — Main coordination loop
- `agents/perceiver.md` — Screen perception
- `agents/actor.md` — Zero-LLM gesture execution
- `agents/commander.md` — Intent parsing
- `agents/planner.md` — Goal decomposition
- `agents/responder.md` — Response generation
- `agents/validator.md` — Rule-based validation
- `agents/verifier.md` — Post-action verification
- `agents/visual_locator.md` — Set-of-Marks VLM selection
- `perception/pipeline.md` — Three-layer perception pipeline
- `services/llm.md` — LLM tri-provider service
- `services/vlm.md` — VLM service and SoM pipeline
- `services/safety.md` — Prompt Guard 2 and OPA engine
- `services/reflexion.md` — Verbal RL lesson system
- `services/hitl.md` — Human-in-the-Loop service
- `services/config.md` — Settings and configuration
- `api/routes.md` — All HTTP and WebSocket routes
- `api/handlers.md` — WebSocket handler details
- `adk.md` — ADK agent, Gemini Live, GCS uploader
- `backlog.md` — P1–P3 improvement backlog

### Key Facts Discovered
- `agents/visual_locator.py` does not exist at that path — VLM selection is in `perception/vlm_selector.py`
- `DEFAULT_VLM_PROVIDER` defaults to `"groq"` in settings (not `"gemini"` as required for hackathon submission)
- `AuraQueryEngine` (`query_engine` in main.py) is a secondary streaming path — falls back to `execute_aura_task_from_streaming()` when disabled
- Thinking-content filter in `adk_streaming_server.py` strips chain-of-thought headers from Gemini 2.5 transcripts
- GCS upload uses `asyncio.get_event_loop().run_in_executor()` pattern (sync SDK wrapped async)

---

## 2026-04-08 — Mid-Task Web Search Tool

**Session**: Expose web_search as RSG-callable mid-task tool  
**Branch**: main  
**Author**: Claude Code (Sonnet 4.6)

### What changed

**New capability**: The RSG can now emit `action_type: "web_search"` during task execution. The coordinator intercepts it, calls `WebSearchService.search(target)`, and injects the result into `running_screen_context` for the next RSG call. No gesture is executed.

**Files modified**:
- `config/gesture_tools.py` — Added `"web_search"` to `GESTURE_REGISTRY` with `needs_target=False`, `needs_coords=False`, `needs_perception=False`. Auto-appears in RSG's AVAILABLE ACTIONS block via `get_rsg_actions_prompt()`.
- `aura_graph/state.py` — Added `web_search_result: Optional[str]` field to `TaskState`.
- `agents/coordinator.py` — Added dispatch interception for `action_type == "web_search"` between the HITL block and ActorAgent. Handles timeout (8 s), service unavailable, and exceptions gracefully.
- `tests/test_web_search_tool.py` — 20 new tests: registry flags, RSG prompt inclusion, no-target set membership, TaskState field existence, coordinator dispatch (happy path, actor not called, result injection, context preservation, timeout, unavailable).

### Why
Previously `web_search` was only usable as a full-task intent (graph-level routing in `edges.py`). Compound tasks like "find a pizza place and open it in Maps" required web context mid-execution — the agent had no way to look up information once the task had started. This change adds that capability.

### Key architectural point
Result flows through `running_screen_context` (same mechanism as HITL answers), not as a new prompt injection path. This keeps the RSG's information surface consistent — web facts appear as "things observed about the current situation" rather than a special external data field.

### Distinction from planning-time `_web_hints`
`_web_hints` is a silent Tavily call during planning (search_for_guide). The new `web_search` action is RSG-driven, mid-task, and user/agent-visible via step_memory.

---

## 2026-04-08 — Gemini Live Latency Patch

**Session**: Investigate and reduce `/ws/live` transcript/response delays (reported ~52s)  
**Branch**: main  
**Author**: Claude Code (Sonnet 4.6)

### What changed

- `adk_streaming_server.py`
	- Retuned server VAD to lower turn-end latency:
		- `prefix_padding_ms`: `350 -> 160`
		- `silence_duration_ms`: `1200 -> 650`
		- enabled high start/end sensitivity when available.
	- Added explicit client end-of-turn bridging:
		- on `{"type":"end_turn"}` now attempts `live_queue.send_audio_stream_end()` first,
		- falls back to `live_queue.send_activity_end()` when supported.
	- Added per-turn latency instrumentation logs for:
		- first inbound audio,
		- first input transcription,
		- first model audio,
		- turn complete,
		- derived end-to-end deltas.
	- Added guard to ignore `end_turn` when no active turn exists.
	- Hardened metrics reset to avoid clobbering a newly started turn during async flush.

- `UI/app/src/main/java/com/aura/aura_ui/voice/GeminiLiveController.kt`
	- Disabled periodic `ui_tree` sends in Gemini Live streaming loop to reduce WS payload and serialization overhead.
	- Removed now-unused `UI_TREE_INTERVAL_MS` and `captureAndSendUiTree()` code.

- `README.md`
	- Updated Gemini Live VAD docs to match runtime settings.

### Why

The prior pipeline relied mostly on server VAD closure and sent redundant context payloads. In practice this can delay turn finalization and transcript visibility. Explicit end-turn bridging plus lighter upstream traffic and tighter VAD settings reduces avoidable buffering/wait.

---

## 2026-04-08 — Karpathy Wiki Alignment (Frontmatter + Operations)

**Session**: Implement Karpathy LLM Wiki pattern for AURA brain  
**Branch**: main  
**Author**: Claude Code (Sonnet 4.6)

### What changed

**New: `CLAUDE.md` — Three wiki operations section**
Added formal definitions for three wiki operations after the Wiki structure section:
- **Query** (before coding): check `last_verified`, run `git log --since=`, update stale pages first
- **Ingest** (after code changes): find pages by `source_files`, update content, bump `last_verified`
- **Lint** (health check): ORPHAN/STALE/UNLISTED/MISSING_FRONTMATTER report
Also added wiki page schema block (YAML frontmatter format).

**New: `scripts/wiki_lint.py`**
Python script implementing the Lint operation. Detects:
- ORPHAN: source file no longer exists on disk
- STALE: source file modified after `last_verified` (git log based, mtime fallback)
- UNLISTED: page not referenced in `wiki/index.md`
- MISSING_FRONTMATTER: page lacks the YAML header block
Flags: `--fix-dates` bumps stale `last_verified` to today. Meta pages (index.md, log.md, etc.) exempt from source_files requirement.

**New: `.claude/skills/wiki-lint.md`**
Claude skill file giving step-by-step instructions for running lint and acting on each issue type.

**All 28 wiki pages — YAML frontmatter added**
Every wiki page now has a frontmatter block:
```yaml
---
last_verified: 2026-04-08
source_files: [path/to/source.py]
status: current
---
```
Pages covered: all meta pages (index, log, overview, decisions, backlog, adk), all 10 agent pages, all 4 aura_graph pages, perception/pipeline, 6 services pages, 2 api pages.

### Why
The wiki existed but had no freshness metadata — no way to know at session start whether a page was trustworthy or stale. The Karpathy pattern adds `last_verified` + `git log` checks so Claude can verify wiki accuracy in seconds instead of re-reading source files from scratch. This saves tokens and prevents acting on stale documentation.
