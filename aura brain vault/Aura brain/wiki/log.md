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
