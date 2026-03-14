# Plan: KG-RAG System for Aura Agent

## TL;DR
Build a Knowledge Graph RAG system in `knowledge/` that ingests AndroidControl + AITZ + AITW datasets into SQLite + FAISS, provides task-path lookup to the coordinator, and injects hints into the reactive step prompt — enabling Aura to skip VLM calls for known task paths. Uses sentence-transformers (free, local CPU) for embeddings and a fresh `knowledge/` package (not Phase 4's `experience_memory`). The KG has NO dependency on any LLM/VLM — it outputs plain text hints injected into the prompt. The VLM (Llama 4 Scout via Groq) consumes the prompt as usual.

## Decisions
- **Embedding model**: `sentence-transformers/all-MiniLM-L6-v2` — free, local, no API key, 384-dim vectors
- **Storage**: SQLite (`knowledge/graph.db`) + FAISS index (`knowledge/intent_index.faiss`)
- **Package**: New `knowledge/` package — does NOT implement Phase 4's `services.experience_memory` test surface
- **Datasets**: All three — AndroidControl (15k), AITZ (~5k), AITW (~715k, filtered)
- **Integration model**: Claude Opus 4.6 via existing VLM pipeline (no model changes needed)
- **Auto-record**: Hook into coordinator completion flow to grow KG from live runs
- **Scope exclusions**: No graph visualization UI, no admin API, no multi-device KG sync

---

## Phase 1: Schema & Storage Layer

### Step 1.1 — Create `knowledge/__init__.py`
- Empty init, exports will be added as modules are created

### Step 1.2 — Create `knowledge/schema.py`
- Dataclasses (NOT Pydantic — match `aura_graph/agent_state.py` convention):
  - `ScreenNode`: node_id (str, sha256 hash), app_package (str), screen_label (str), fingerprint (list[str] — top-N stable element labels from UI tree)
  - `TaskPath`: path_id (str, uuid4), app_package (str), task_intent (str), intent_embedding (bytes — numpy array serialized), steps (list[PathStep]), confidence (float 0–1), source (str — "android_control" | "aitz" | "aitw" | "aura_live"), success_count (int), failure_count (int), created_at (str, ISO), updated_at (str, ISO)
  - `PathStep`: step_index (int), screen_node_id (str), action_type (str), target (str), field_hint (str), expected_next_screen (str)

### Step 1.3 — Create `knowledge/store.py`
- `KGStore` class:
  - `__init__(self, db_path: str = "knowledge/graph.db")` — creates SQLite tables if not exist
  - Tables: `screen_nodes`, `task_paths`, `path_steps`
  - `save_task_path(path: TaskPath)` → insert/update
  - `get_task_path(path_id: str)` → TaskPath
  - `find_paths_by_app(app_package: str)` → list[TaskPath]
  - `update_confidence(path_id: str, success: bool)` — +0.15 success / -0.20 failure, capped [0.0, 0.95]
  - `apply_staleness_decay(days_threshold: int = 30)` — ×0.90 for stale paths
  - `save_screen_node(node: ScreenNode)` → insert or ignore
  - `get_screen_node(node_id: str)` → ScreenNode

### Step 1.4 — Create `knowledge/embeddings.py`
- `IntentIndex` class:
  - `__init__(self, index_path: str = "knowledge/intent_index.faiss", model_name: str = "all-MiniLM-L6-v2")`
  - Lazy-loads `sentence_transformers.SentenceTransformer` on first call
  - `embed(text: str)` → numpy array (384-dim)
  - `add(path_id: str, intent_text: str)` — encodes + adds to FAISS index
  - `search(query: str, k: int = 5)` → list[tuple[str, float]] (path_id, similarity score)
  - `save()` / `load()` — persist/restore FAISS index + id-mapping
  - Internal `_id_map: dict[int, str]` maps FAISS integer IDs ↔ path_id strings
  - Stores id_map as JSON sidecar: `knowledge/intent_id_map.json`

**Verification**: Unit test — create store, save a TaskPath, embed its intent, search for it, verify round-trip.

---

## Phase 2: KG Lookup Service

### Step 2.1 — Create `knowledge/kg_service.py`
- `KGService` class:
  - `__init__(self, store: KGStore = None, index: IntentIndex = None)` — defaults instantiate internally
  - `lookup(intent: str, app_package: str = None, top_k: int = 3)` → list[TaskPath] — FAISS search → filter by confidence ≥ 0.50 → optionally filter by app_package → return sorted by confidence desc
  - `get_hint_text(intent: str, app_package: str = None)` → str — formatted hint block for prompt injection:
    - confidence ≥ 0.85: "KNOWN PATH (high confidence): step1 → step2 → ..." + "You may follow this exact path."
    - 0.50–0.84: "SUGGESTED PATH (medium confidence): step1 → step2 → ..." + "Use as guidance, verify each step."
    - < 0.50 or no match: empty string (no injection)
  - `record_run(intent: str, app_package: str, step_memory: list, success: bool)` — converts StepMemory list → TaskPath + PathSteps, embeds intent, saves to store, updates confidence
  - `_step_memory_to_path_steps(step_memory: list)` → list[PathStep] — converts Aura's StepMemory format to KG PathStep format

### Step 2.2 — Create `knowledge/screen_fingerprint.py`
- `fingerprint_screen(ui_elements: list, screen_label: str = "") → str` — hash of sorted top-10 stable labels (skip numeric, skip "unnamed"). For vision-mode (empty elements): use screen_label as key.
- `make_screen_node(app_package: str, screen_label: str, ui_elements: list) → ScreenNode`

**Verification**: Integration test — manually construct step_memory records, call record_run, then lookup and verify the path is returned.

---

## Phase 3: Dataset Ingestion Scripts

### Step 3.1 — Create `scripts/seed_android_control.py`
- Downloads `google-research-datasets/android_control` via HuggingFace `datasets` library
- Iterates rows: each row has `goal`, `episode_id`, `step_data` (action_type, target, screenshot annotations)
- For each episode: build TaskPath (source="android_control", confidence=0.60) + PathSteps
- Embed task_intent, save to store + FAISS index
- Progress bar via `rich.progress`
- CLI: `python scripts/seed_android_control.py [--db-path knowledge/graph.db] [--limit N]`

### Step 3.2 — Create `scripts/seed_aitz.py`
- Downloads AITZ dataset (subset of AITW with bounding box annotations)
- Same flow as 3.1 but adapted to AITZ schema (includes element bounding boxes — extract as target hints)
- Source="aitz", confidence=0.60
- CLI: `python scripts/seed_aitz.py [--db-path knowledge/graph.db] [--limit N]`

### Step 3.3 — Create `scripts/seed_aitw.py`
- Downloads AITW dataset (~715k episodes)
- **Quality filter**: skip episodes with < 3 steps or > 50 steps (noise)
- **Dedup filter**: skip if identical (app_package + normalized_intent) already exists from AndroidControl/AITZ
- Source="aitw", confidence=0.55 (lower baseline — noisier data)
- Batch processing: commit every 1000 records
- CLI: `python scripts/seed_aitw.py [--db-path knowledge/graph.db] [--limit N] [--batch-size 1000]`

### Step 3.4 — Add new dependencies to `requirements.txt`
- `sentence-transformers>=2.2.0`
- `faiss-cpu>=1.7.4`
- `datasets>=2.14.0` (HuggingFace datasets library, for ingestion scripts only)

**Verification**: Run `seed_android_control.py --limit 100`, then query `KGService.lookup("open settings")` — should return paths with confidence=0.60.

---

## Phase 4: Aura Integration

*Depends on Phase 1-2 being complete.*

### Step 4.1 — Add `{kg_hints}` slot to `prompts/reactive_step.py`
- Add new placeholder in CONTEXT section, after COMMIT ACTIONS NEEDED:
  ```
  KNOWN TASK PATH:        {kg_hints}
  ```
- Add `kg_hints: str = ""` parameter to `get_reactive_step_prompt()`
- Default: "No known path — proceed with screen observation."
- Add **Rule 36** to DECISION RULES:
  ```
  36. KNOWLEDGE GRAPH HINTS — trusted but not mandatory:
      If KNOWN TASK PATH shows a high-confidence path, you MAY follow it step-by-step
      as long as each step matches what you SEE on the current screen.
      If the screen does NOT match the expected step, IGNORE the hint and fall back
      to your standard screen-reading + app-knowledge process.
      Never blindly follow a hint that contradicts the screenshot.
  ```

### Step 4.2 — Wire `KGService.get_hint_text()` into `services/reactive_step_generator.py`
- Import KGService (lazy — only instantiate on first use)
- In `generate_next_step()`, before building the prompt:
  - `kg_hint = self._kg_service.get_hint_text(goal.original_utterance, app_package=fg_package)`
  - Pass `kg_hints=kg_hint` to `get_reactive_step_prompt()`
- Add `fg_package: str = ""` parameter to `generate_next_step()` signature
- Fallback: if KGService fails (import error, DB missing), log warning and pass empty string

### Step 4.3 — Wire `fg_package` from coordinator to reactive_step_generator
- In `agents/coordinator.py` at line ~286 where `self.reactive_gen.generate_next_step(...)` is called:
  - Pass `fg_package=_fg_pkg` (already available at line 214 as `_bundle.ui_tree.source_package`)

### Step 4.4 — Wire auto-record into coordinator completion flow
- In `agents/coordinator.py` at line ~1268 (completion block):
  - After `status = "completed"`:
    ```python
    if status == "completed":
        try:
            self._kg_service.record_run(
                intent=goal.original_utterance,
                app_package=_last_fg_pkg,  # track last known foreground package
                step_memory=step_memory,
                success=True,
            )
        except Exception:
            logger.debug("KG auto-record failed", exc_info=True)
    ```
  - Need to track `_last_fg_pkg` — update it each loop iteration from `_fg_pkg`
  - Lazy-init `self._kg_service` in coordinator `__init__` (import only if knowledge/ exists)

**Verification**:
1. Start Aura, run a known task (e.g. "open settings"), verify KG hint appears in VLM prompt logs
2. Complete a task, verify auto-record wrote to SQLite
3. Run the same task again, verify KG hint now appears with higher confidence

---

## Phase 5: Confidence Scoring & Maintenance

*Parallel with Phase 4.*

### Step 5.1 — Implement confidence decay in `knowledge/store.py`
- `apply_staleness_decay()` — query paths where `updated_at < now - 30 days`, multiply confidence by 0.90
- Can be called manually or on a schedule

### Step 5.2 — Add failure recording to coordinator
- When `status == "aborted"` in completion flow:
  ```python
  if status == "aborted" and _last_fg_pkg:
      try:
          self._kg_service.record_run(
              intent=goal.original_utterance,
              app_package=_last_fg_pkg,
              step_memory=step_memory,
              success=False,
          )
      except Exception:
          logger.debug("KG failure record failed", exc_info=True)
  ```

### Step 5.3 — Create `scripts/kg_maintenance.py`
- CLI tool: `python scripts/kg_maintenance.py decay` — runs staleness decay
- `python scripts/kg_maintenance.py stats` — prints KG statistics (total paths, by source, by confidence tier, by app)
- `python scripts/kg_maintenance.py prune --below 0.10` — removes paths with confidence < threshold

**Verification**: Record a run, manually set its updated_at to 60 days ago, run decay, verify confidence dropped.

---

## Phase 6: Testing

### Step 6.1 — Create `tests/test_kg_store.py`
- Test CRUD operations on KGStore
- Test confidence update math (+0.15, -0.20, caps at 0.0/0.95)
- Test staleness decay

### Step 6.2 — Create `tests/test_kg_service.py`
- Test lookup returns paths sorted by confidence
- Test get_hint_text returns correct format for each confidence tier
- Test record_run creates valid TaskPath from StepMemory
- Test empty/missing KG gracefully returns empty hints

### Step 6.3 — Create `tests/test_embeddings.py`
- Test embed returns 384-dim vector
- Test search finds semantically similar intents ("open settings" matches "go to settings")
- Test save/load round-trip preserves index

---

## Relevant Files

**New files to create:**
- `knowledge/__init__.py` — package init
- `knowledge/schema.py` — ScreenNode, TaskPath, PathStep dataclasses
- `knowledge/store.py` — KGStore (SQLite CRUD)
- `knowledge/embeddings.py` — IntentIndex (FAISS + sentence-transformers)
- `knowledge/kg_service.py` — KGService (lookup, hint generation, auto-record)
- `knowledge/screen_fingerprint.py` — screen hashing utility
- `scripts/seed_android_control.py` — AndroidControl ingestion
- `scripts/seed_aitz.py` — AITZ ingestion
- `scripts/seed_aitw.py` — AITW ingestion (with quality/dedup filters)
- `scripts/kg_maintenance.py` — decay, stats, prune CLI
- `tests/test_kg_store.py`
- `tests/test_kg_service.py`
- `tests/test_embeddings.py`

**Existing files to modify:**
- `prompts/reactive_step.py` — add `{kg_hints}` slot + `kg_hints` param + Rule 36
- `services/reactive_step_generator.py` — wire KGService.get_hint_text() before prompt, add `fg_package` param
- `agents/coordinator.py` — pass `fg_package` to reactive_gen, auto-record on completion/abort, track `_last_fg_pkg`
- `requirements.txt` — add sentence-transformers, faiss-cpu, datasets

**Reference files (read-only, use as patterns):**
- `aura_graph/agent_state.py` — StepMemory dataclass structure (lines 56-75)
- `services/vlm.py` — VLM service pattern for dependency injection
- `models/gestures.py` — Pydantic model patterns (though we use dataclasses)
- `config/settings.py` — settings pattern if KG config is needed later
