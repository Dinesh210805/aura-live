---
last_verified: 2026-04-09
source_files: []
status: current
---

# AURA Wiki — Index

> Living knowledge base for the AURA (Autonomous User-Responsive Agent) system.
> Last built: 2026-04-07 from full codebase read.

---

## Pages

### Architecture
- [overview.md](overview.md) — End-to-end description, request lifecycle, system map

### LangGraph Orchestration (`aura_graph/`)
- [aura_graph/graph.md](aura_graph/graph.md) — Graph assembly, entry points, lifespan
- [aura_graph/state.md](aura_graph/state.md) — `TaskState` TypedDict, reducers, Goal/Subgoal models
- [aura_graph/edges.md](aura_graph/edges.md) — Conditional routing logic, 5-stage retry ladder
- [aura_graph/nodes.md](aura_graph/nodes.md) — Node implementations, STT/TTS/perception nodes

### Agents (`agents/`)
- [agents/overview.md](agents/overview.md) — All 9 agents, responsibilities, interaction map
- [agents/coordinator.md](agents/coordinator.md) — Main orchestration loop (most complex agent)
- [agents/perceiver.md](agents/perceiver.md) — Screen perception, ScreenState
- [agents/actor.md](agents/actor.md) — Zero-LLM gesture execution
- [agents/commander.md](agents/commander.md) — Intent parsing, tri-provider fallback
- [agents/planner.md](agents/planner.md) — Goal decomposition, phase skeleton
- [agents/responder.md](agents/responder.md) — Natural language response generation
- [agents/validator.md](agents/validator.md) — Rule-based pre-execution validation
- [agents/verifier.md](agents/verifier.md) — Post-action verification, settle delays

### Perception Pipeline (`perception/`)
- [perception/pipeline.md](perception/pipeline.md) — Three-layer hybrid: UI tree → CV → VLM
- [perception/vlm_selector.md](perception/vlm_selector.md) — VLMSelector: SoM element selection, SelectionResult, fallback logic

### Services (`services/`)
- [services/llm.md](services/llm.md) — Tri-provider LLM (Groq/Gemini/NVIDIA)
- [services/vlm.md](services/vlm.md) — VLM providers, 429 retry, SoM pipeline
- [services/safety.md](services/safety.md) — Prompt Guard 2, OPA policy engine
- [services/reflexion.md](services/reflexion.md) — Verbal RL lessons, goal bucketing
- [services/hitl.md](services/hitl.md) — Human-in-the-Loop, question types
- [services/config.md](services/config.md) — Pydantic Settings, env vars

### API (`api_handlers/`, `api/`)
- [api/routes.md](api/routes.md) — All HTTP and WebSocket endpoints
- [api/handlers.md](api/handlers.md) — WebSocket router, streaming, HITL barge-in

### Google Cloud / ADK
- [adk.md](adk.md) — ADK root agent, Gemini Live bidi, GCS log uploader

### MCP & Open-Source Strategy
- [mcp_architecture.md](mcp_architecture.md) — Full MCP architecture plan, dual-brain design, two-way pipeline, build phases, open-source positioning
- [mcp_build_plan.md](mcp_build_plan.md) — **ACTIVE BUILD PLAN** — task-by-task implementation guide with interface contracts, session resumption protocol, and status tracking. READ THIS before working on MCP.

### Meta
- [backlog.md](backlog.md) — P1–P3 improvement backlog
- [decisions.md](decisions.md) — Architectural decisions and rationale
- [log.md](log.md) — Change history
