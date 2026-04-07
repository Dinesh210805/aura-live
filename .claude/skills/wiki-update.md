# wiki-update

After every task, automatically update the wiki brain.
Wiki lives at: aura brain vault/Aura brain/wiki/

## 1. Check what changed
git diff HEAD --name-only

## 2. Map changed files to wiki pages

agents/*.py           → wiki/agents/{agent-name}.md
aura_graph/graph.py   → wiki/aura_graph/graph.md
aura_graph/state.py   → wiki/aura_graph/state.md
aura_graph/edges.py   → wiki/aura_graph/edges.md
aura_graph/nodes/     → wiki/aura_graph/nodes.md
perception/           → wiki/perception/pipeline.md
services/llm.py       → wiki/services/llm.md
services/vlm.py       → wiki/services/vlm.md
services/stt.py       → wiki/services/stt.md
services/tts.py       → wiki/services/tts.md
services/prompt_guard.py    → wiki/services/safety.md
services/reflexion_service.py → wiki/services/reflexion.md
services/hitl_service.py    → wiki/services/hitl.md
api/                  → wiki/api/routes.md
api_handlers/         → wiki/api/handlers.md
config/settings.py    → wiki/services/config.md
policies/             → wiki/services/safety.md
utils/                → wiki/services/utils.md

## 3. What to write in each page
Focus on meaning, not just listing functions:
- What does this module DO in plain English?
- How does it connect to the 9-agent pipeline?
- What are the critical invariants for this module?
- What gotchas or non-obvious patterns exist?
- What was recently changed and why?

## 4. Special pages to keep current

wiki/backlog.md — mirror the P1/P2/P3 items from CLAUDE.md
and add implementation notes as work progresses.

wiki/decisions.md — whenever a design decision is made,
record it here: what was chosen, what was rejected, and why.

## 5. Update wiki/index.md
If a new page was created, add it with a one-line summary.

## 6. Append to wiki/log.md
## [YYYY-MM-DD] | task type | files changed | wiki pages updated