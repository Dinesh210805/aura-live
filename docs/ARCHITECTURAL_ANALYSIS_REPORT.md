# AURA Architectural Analysis Report
## Execution Control Loop — Structural Critique & Redesign Proposal

**Scope:** Perception → Reasoning → Execution → Validation pipeline  
**Based on:** Full source audit of coordinator, perceiver, verifier, actor, gesture executor, perception pipeline, success criteria, and goal decomposer.

---

## A. Current Architecture Map

### Control Loop (as-built)

```
User Utterance
      │
      ▼
  [plan_node]  ← LLM (GoalDecomposer)
      │           Creates Goal + Subgoal list
      ▼
[select_subgoal] ──── idx ≥ len(subgoals) ──→ [complete]
      │          └─── budget exhausted ─────→ [abort]
      │
      ▼
  [perceive]   ← PerceiverAgent 3-layer pipeline
      │           Captures UI tree + optional screenshot
      │           Returns: ScreenState { target_match, scroll_position_hash }
      ▼
  [decide]     ← Deterministic routing (no LLM)
      │           Has target || no-target action → act
      │           No target + tap/long_press ──→ replan
      │
      ▼
    [act]      ← ActorAgent → GestureExecutor → ADB
      │           Returns: ActionResult { success, duration_ms }
      ▼
  [verify]     ← VerifierAgent
      │           Captures fresh UI tree post-action
      │           Compares pre_hash (from perceive) vs post_hash
      │           Checks SuccessCriteria
      │
      ├── subgoal_completed=True ──→ [select_subgoal] (advance idx)
      ├── screen_changed + retry ───→ [perceive] (retry same subgoal)
      ├── loop/stuck/replan ────────→ [replan]
      └── budget exhausted ─────────→ [abort]
```

### Perception Within the Loop

```
PerceiverAgent.perceive()
      │
      ├── [Layer 1] UI Tree fuzzy match       10-50ms
      │     └── confidence ≥ 0.9 → FAST PATH (return immediately)
      │
      ├── Escalation check (_should_escalate_to_omniparser)
      │     Rules: WebView | sparse content | low confidence | visual keywords | visual app
      │
      └── [Layer 2+3] OmniParser → VLM        200ms-3s
            OmniParser: YOLOv8 detects all elements → Set-of-Marks letter labels
            VLM: receives screenshot with labels, returns single letter ID
            Coordinates: assigned from OmniParser bounding box (VLM cannot invent coords)
```

### Verification Within the Loop

```
VerifierAgent.verify(subgoal, pre_screen, action_result, ...)
      │
      ├── request_perception(force_screenshot=True)
      │     → Fresh UI tree capture (post-action)
      │
      ├── post_hash = _compute_screen_hash(elements)
      │     [hash of first 30 elements: text + bounds.top]
      │
      ├── pre_hash = pre_screen.scroll_position_hash  (from perceive step)
      │
      ├── screen_changed = (post_hash != pre_hash)
      │
      ├── _check_success_criteria(subgoal, elements, screen_changed, bundle)
      │     text_appeared → substring search in UI tree text nodes
      │     target_screen_reached → package name substring match
      │     ui_changed → screen_changed
      │     target_element_gone → target text no longer in tree
      │
      └── loop detection: 3+ identical hashes in screen_hash_history
```

### Data Flow Summary

| Stage | Input | LLM Used | Output |
|-------|-------|----------|--------|
| `plan` | utterance + intent | ✓ GoalDecomposer | Goal + Subgoals |
| `perceive` | Subgoal | ✓ VLM (conditional) | ScreenState + coordinates |
| `decide` | ScreenState | ✗ | Routing decision |
| `act` | action_type + coords | ✗ | ActionResult |
| `verify` | pre_screen + subgoal | ✗ | VerificationResult |
| `replan` | Goal + obstacle | ✓ GoalDecomposer | New Subgoals |

---

## B. Structural Weaknesses

### W1 — Verification Uses a Stale Pre-Snapshot

**Problem:** The `pre_screen` passed to `verify` is the `ScreenState` from `_perceive_node`. Perception captures state, then routing runs (`decide`), then execution runs (`act`). By the time the verifier computes `pre_hash`, the device may have moved to a loading state between perceive and act.

For `open_app` subgoals, `pre_screen = None` entirely. The fix `pre_hash = ""` means `screen_changed` is always `True` after app launch — even if the app failed to open (ADB returned success but app never appeared).

**Location:** `coordinator.py:_verify_node` → `verifier_agent.py:verify(pre_screen=state["screen_state"])`

**Risk:** False positive completions for `open_app` actions.

---

### W2 — screen_changed Is Not Goal Progress

**Problem:** `screen_changed = post_hash != pre_hash` detects any UI change. The following events all produce `screen_changed=True` that are not goal progress:
- Keyboard appears after tapping a field (intent: tap a button, not type)
- Notification drawer briefly appears
- Permission dialog closes
- Toast appears and is captured mid-fade
- Ad refreshes on content screen

For all `tap` subgoals, `SuccessCriteria.ui_changed=True` is the only check. Any of the above causes subgoal completion.

**Location:** `config/success_criteria.py` — `tap`, `double_tap`, `long_press` all map to `UI_CHANGE_CRITERIA = SuccessCriteria(ui_changed=True)`

**Risk:** Premature subgoal advancement on spurious UI events.

---

### W3 — The Screen Hash Is UI-Tree-Based, Not Visual

**Problem:** `_compute_screen_hash` hashes `el.get("text") + bounds.top` for the first 30 elements. This hash is blind to:
- WebView content (rendered to canvas, not in UI tree)
- Toast overlays (often zero UI tree nodes)
- Activity transitions mid-animation
- Custom-drawn components (game UIs, charting widgets)
- Scrolled list content (positions change but text may repeat)

**Location:** `perceiver_agent.py:_compute_screen_hash`

**Risk:** On WebView-heavy apps (Amazon product pages, YouTube, Instagram), hash changes correlate poorly with semantic screen changes.

---

### W4 — No Post-Gesture Stabilization Wait

**Problem:** After `GestureExecutor._execute_single_action` returns, `_verify_node` immediately calls `request_perception`. ADB returns success when the command is *sent*, not when the UI has settled. Android UI transitions typically take:
- Button press flash: ~50ms
- Screen navigation: 150–300ms
- Page load: 500ms–5s
- Keyboard open: ~200ms

The `post_delay=0.5s` in `execute_plan` applies when executing a multi-step plan via the old flow. The coordinator's single-action flow has no stabilization delay.

**Location:** `coordinator.py:_act_node` → immediately edges to `_verify_node`

**Risk:** The verifier captures screen mid-transition. Hash comparison is noisy. Loops and replanning fire unnecessarily.

---

### W5 — Error Screen Blindness

**Problem:** The verifier does not classify the post-action screen type. If navigating to a product page produces a "Page Not Found", "Login Required", or "Network Error" screen, `screen_changed=True` (UI changed) and `subgoal_completed=True` (criteria satisfied). The system advances to the next subgoal.

**Location:** `verifier_agent.py:_check_success_criteria` — no error state detection

**Risk:** Silent task failures. The agent advances through error screens without recovery.

---

### W6 — No Goal-Level Terminal Verification

**Problem:** Success is only assessed per-subgoal. When the final subgoal completes, `_complete_node` fires and the task is declared done — with no check of whether the overall goal was achieved.

For "add iPhone 17 Pro to Amazon cart": 6 individual subgoals could each succeed while the correct product was never added (wrong product tapped, cart was empty during checkout, item was out of stock).

**Location:** `coordinator.py:_complete_node` — fires immediately when `idx >= len(subgoals)`

**Risk:** False positive task completions reported to the user.

---

### W7 — Planner Is Perception-Blind at Plan Time

**Problem:** `_plan_node` calls `planner.create_plan(utterance, intent, perception=None)`. The initial plan is generated without any knowledge of the current screen. This forces downstream agents to handle context that the planner should use:
- User says "go back to search results" — planner doesn't know if we're already there
- User says "tap the confirm button" — planner creates `open_app → type → tap` sequence without checking current screen

**Location:** `coordinator.py:_plan_node` — always passes `perception=None`

**Risk:** Plans that include unnecessary setup steps that fail when screen is already in target state.

---

### W8 — Replan Does Not Reset Stale State

**Problem:** When replanning fires, `screen_state`, `screen_hash_history`, and `executed_steps` are not cleared. The new subgoals will be executed against potentially stale state. Specifically:
- `screen_hash_history` retains pre-replan hashes. Loop detection (`consecutive_same >= 3`) may fire prematurely because the new subgoals see the same screens as the old ones
- `screen_state` is not refreshed before the new subgoal's `perceive` runs — if `_route_after_select` goes directly to `perceive`, the first perception call may return a cached snapshot

**Location:** `coordinator.py:_replan_node` — no state cleanup before returning

**Risk:** False loop detection after valid replanning cycles.

---

### W9 — VLM Letter Selection Has No Confidence Signal

**Problem:** The VLM returns a single letter ID (e.g., `"K"`, `"AK"`) selecting a region from OmniParser's Set-of-Marks overlay. If the VLM hallucinates (returns a valid-format letter that matches the wrong region), the system uses whatever coordinates OmniParser assigned to that letter ID.

The pipeline assigns `confidence=0.7` as a default for all pipeline (OmniParser+VLM) matches. There is no signal for VLM selection certainty. A confused VLM returns a letter with the same weight as a confident VLM.

**Location:** `perceiver_agent.py:perceive` — `confidence=result.confidence or 0.7`

**Risk:** Silent misdirection on visual-match failures — tapping wrong elements with medium confidence.

---

### W10 — Retry Strategy Ladder Is Defined but Never Used

**Problem:** `aura_graph/agent_state.py` defines a full `RetryStrategy` enum and `RETRY_LADDER`:
```
SAME_ACTION → ALTERNATE_SELECTOR → SCROLL_AND_RETRY → VISION_FALLBACK → ABORT
```
`Subgoal.escalate_strategy()` exists. However, the coordinator never calls `escalate_strategy()`. When a subgoal fails, the coordinator routes to `replan` (new LLM call) immediately. The intermediate retry strategies (alternate selector, scroll and retry) are dead code.

**Location:** `aura_graph/agent_state.py` — `RetryStrategy`, `RETRY_LADDER` defined. `coordinator.py` — never references these.

**Risk:** The system over-uses LLM replanning for recoverable failures (element scroll-off-screen, different element text) that could be resolved deterministically.

---

## C. Proposed Control Loop Redesign

The target model mirrors human behavioral control:

```
Observe₀ → Plan → [Pre-Act Snapshot] → Act → Stabilize → Observe₁ → 
Compare(Observe₀, Observe₁) → Semantic Judge → Decide → Advance/Retry/Escalate/Abort
```

### Redesigned Per-Subgoal Loop

```
[select_subgoal]
      │
      ▼
  [perceive]           ← 3-layer pipeline (unchanged)
      │                  Returns: ScreenState + target coordinates
      ▼
  [snapshot_pre]  NEW  ← Explicit pre-action snapshot
      │                  Captures: screenshot + UI tree hash
      │                  Separate from perceive (perceive may be old)
      ▼
  [decide]             ← Route to act or replan (unchanged logic)
      │
      ▼
    [act]              ← Execute gesture (unchanged)
      │
      ▼
  [stabilize]     NEW  ← Post-gesture stabilization wait
      │                  Strategy: poll UI tree hash every 150ms up to 1.5s
      │                  Exit condition: hash stable for 2 consecutive polls
      │                  Fallback: always wait at least 300ms
      ▼
  [verify]             ← UPGRADED (see Section E)
      │                  Now receives: pre_snapshot (not pre_screen from perceive)
      │                  Runs: hash diff + error screen check + semantic check
      │
      ├── completed ─────────────────────→ [select_subgoal] (advance)
      ├── retry (subgoal.attempts < 2) ──→ [snapshot_pre] (not perceive)
      ├── escalate ────────────────────→ [perceive] (re-perceive + retry)
      ├── replan ──────────────────────→ [replan]
      └── abort ───────────────────────→ [abort]

[complete_node] + [goal_verify]  NEW
      │                  After all subgoals: capture final screen
      │                  Run goal-level VLM check against original utterance
      └── success / partial / failed → responder
```

### Key Structural Changes

#### Change 1: Decouple Pre-Action Snapshot from Perceive

Add a `snapshot_pre` node between `perceive` and `act`. It captures a final UI tree snapshot *immediately* before the gesture fires. This eliminates the timing gap between perception (which may have run 500ms ago and triggered OmniParser) and execution.

Store as `pre_action_snapshot: ScreenState` in `CoordinatorState` — separate from `screen_state` (which is the perceiver output used for element location).

#### Change 2: Post-Gesture Stabilization

Add a `stabilize` phase after `act`. Implementation:
```python
async def _stabilize_node(self, state):
    MIN_WAIT_MS = 300
    POLL_INTERVAL_MS = 150
    MAX_WAIT_MS = 1500
    STABLE_POLLS = 2
    
    await asyncio.sleep(MIN_WAIT_MS / 1000)
    
    previous_hash = None
    stable_count = 0
    elapsed = MIN_WAIT_MS
    
    while elapsed < MAX_WAIT_MS:
        bundle = await self.perception_controller.request_perception(
            intent=state["intent"], action_type="verify", force_screenshot=False
        )
        elements = bundle.ui_tree.elements if bundle.ui_tree else []
        current_hash = _compute_screen_hash(elements)
        
        if current_hash == previous_hash:
            stable_count += 1
            if stable_count >= STABLE_POLLS:
                break
        else:
            stable_count = 0
        
        previous_hash = current_hash
        await asyncio.sleep(POLL_INTERVAL_MS / 1000)
        elapsed += POLL_INTERVAL_MS
    
    return {"post_action_ui_hash": current_hash}
```

Cost: 300ms minimum, up to 1.5s worst case. Expected average: ~450ms for tap actions, ~800ms for navigation.

#### Change 3: Activate Retry Ladder Before Replan

Before calling LLM replan, exhaust the existing `RetryStrategy` ladder:

```
Attempt 1: SAME_ACTION (retry coordinates)
Attempt 2: ALTERNATE_SELECTOR (re-perceive, different layer)
Attempt 3: SCROLL_AND_RETRY (scroll down 300px, re-perceive)
Attempt 4: VISION_FALLBACK (force VLM + OmniParser, even if UI tree was confident)
Attempt 5: → replan (LLM call)
```

This reduces LLM replan calls from "every failure" to "after 4 deterministic attempts".

#### Change 4: Screen-Level Initial Perception

In `_plan_node`, capture a fast UI tree snapshot *before* calling the LLM planner, and inject it into the prompt as `current_screen_context`. This allows the planner to skip steps that are already done (e.g., app is already open, search field already has text).

---

## D. Required Invariants

The following must hold at all times for correct operation:

**INV-1: Coordinates Are Always Device-Pixel Native**  
All coordinates flowing from PerceiverAgent to ActorAgent must be in device pixels. The `format="pixels"` field must be present on every tap/swipe action dict. Never pass normalized [0,1] floats without explicit `format="normalized"`.

**INV-2: VLM Never Generates Spatial Data**  
VLM responses are always single-character letter IDs. Coordinates are always sourced from OmniParser bounding boxes or UI tree bounds. VLM is exclusively a classifier over a fixed candidate set.

**INV-3: Pre-Action Snapshot Is Captured Immediately Before Gesture**  
The snapshot used for post-action comparison (`pre_action_snapshot`) must be captured in the same control loop cycle as the gesture, after routing decisions and immediately before `act`. It must never be the perceive output (which could be stale by 500ms+).

**INV-4: Verification Hash Must Include Gesture-Relevant Zone**  
Screen hashes for verification must weight content-zone elements higher than nav-bar/status elements. A notification LED change or clock update should not produce `screen_changed=True`.

**INV-5: Budget Counts Must Include Stabilization Polls**  
`total_actions` counter should count perception calls during stabilization. Otherwise, the system can exhaust `MAX_TOTAL_ACTIONS=20` without visible agent progress.

**INV-6: Replan Must Flush Stale Screen State**  
`_replan_node` must reset `screen_state=None` and `screen_hash_history=[]` after generating new subgoals. The new plan starts with fresh perception.

**INV-7: Goal Description Must Flow to Responder in All Exit Paths**  
`goal.description` must be present in the state dict (`goal_summary` key) at both `complete` and `abort` node exits. Responder must never use implicit session context to infer which app or goal was active.

---

## E. Success-Detection Framework

### Tier 1 — Structural Verification (fast, always runs)

Signal: `screen_changed = post_hash != pre_hash`

Enrichment: Zone-weighted hash. Weight content zone elements 3x over nav/status elements. This reduces false positives from clock updates, signal strength changes, battery indicator flips.

```python
def _compute_zone_weighted_hash(elements, screen_height):
    zone_weights = {"STATUS": 0.1, "HEADER": 0.5, "CONTENT": 3.0, "NAV_BAR": 0.2}
    sig_parts = []
    for el in elements[:50]:
        label = el.get("text", "") or el.get("contentDescription", "") or ""
        bounds = el.get("bounds", {})
        top = bounds.get("top", 0)
        zone = _get_zone(top, screen_height)
        weight = zone_weights.get(zone, 1.0)
        if label and weight >= 0.5:
            sig_parts.append(f"{label}:{bounds.get('top', 0)}:{zone[0]}")
    return hashlib.md5("|".join(sig_parts).encode()).hexdigest()[:12]
```

### Tier 2 — Semantic Criteria Verification (medium, on-demand)

Existing `_check_success_criteria` flow. Enhancements needed:

**text_appeared**: Current substring search is too broad. "Added" would match "Added to cart" AND "Already added" (conflicting). Match should be whole-word or use a keyword allowlist.

**target_screen_reached**: Currently only checks package name. Should also check `activity_name` when available in UI tree root node.

**New criterion: error_screen_absent**: Check that first element is not in a known error class:
```python
ERROR_INDICATORS = [
    "page not found", "couldn't load", "network error", "try again",
    "sign in", "log in", "verify your identity", "something went wrong"
]
```

### Tier 3 — Visual Diff Verification (slow, optional)

When screenshot is available both pre and post, run a pixel-level diff:
- Compare screenshot thumbnails (64×64 downscale)
- SSIM score < 0.95 → screen_visually_changed = True

This catches WebView changes, canvas renders, and animations invisible to the UI tree.

### Tier 4 — Goal-Level Verification (LLM, final step only)

After all subgoals complete, run a single VLM query:
```
"The user asked: {goal.description}
Current screen: {screenshot}
Question: Has the user's request been completed? Answer YES or NO and reason."
```

Count this against the LLM budget. Only runs once per task. Provides the telemetry signal needed to know if AURA actually succeeded.

### Success Signal Matrix

| Action Type | Tier 1 Required | Tier 2 Required | Tier 3 Recommended |
|-------------|-----------------|-----------------|---------------------|
| `tap` (navigation) | ✓ | target_element_gone | When WebView |
| `tap` (toggle) | ✓ | text_appeared | — |
| `type` | ✓ | text_appeared | — |
| `scroll` | ✓ | — | — |
| `open_app` | ✓ | target_screen_reached | — |
| `swipe` | ✓ | — | — |
| `back` | ✓ | — | — |

---

## F. Failure-Mode Taxonomy

### Class 1 — Perception Failures

| ID | Mode | Current Handling | Gap |
|----|------|-----------------|-----|
| P1 | Target not in UI tree | Escalate to OmniParser | No scroll-to-find first |
| P2 | Target in UI tree but wrong match | Tap wrong element | No post-tap target-gone check |
| P3 | VLM selects wrong letter ID | Tap wrong region | No confidence signal from VLM |
| P4 | Element off-screen (below fold) | No match → replan | Should scroll first (W10) |
| P5 | Screen mid-transition at perceive time | Stale UI tree | No stabilize before perceive |
| P6 | Keyboard occludes target | `screen_type=keyboard_open` detected | Does not dismiss keyboard |

### Class 2 — Execution Failures

| ID | Mode | Current Handling | Gap |
|----|------|-----------------|-----|
| E1 | ADB command not delivered | `success=False` from executor | Not distinguished from "tap wrong spot" |
| E2 | Tap delivered but no register (touch target too small) | `screen_changed=False` → retry | No coordinate precision check |
| E3 | Type action: keyboard not open | Characters fail silently | No pre-type keyboard check |
| E4 | Swipe outside screen bounds | ADB silently clips | No bounds validation pre-swipe |
| E5 | App launch: multiple matches for app name | First match chosen | No disambiguation logic |

### Class 3 — Verification Failures

| ID | Mode | Current Handling | Gap |
|----|------|-----------------|-----|
| V1 | Screen changed to error page | `completed=True` (any change) | No error screen classifier |
| V2 | Screen changed by unrelated event | `completed=True` (false positive) | Not filtered by zone/relevance |
| V3 | Toast appeared/gone before verify | Hash shows no change | Screenshot diff would catch this |
| V4 | Animation captured mid-frame | Noisy hash | Stabilize node would fix |
| V5 | Goal complete but subgoal order wrong | Subgoal N+1 fires on stale state | No cross-subgoal state check |

### Class 4 — Planning Failures

| ID | Mode | Current Handling | Gap |
|----|------|-----------------|-----|
| PL1 | Plan generated for wrong app | Subgoals for Amazon when YouTube open | Planner never receives current screen |
| PL2 | Replan adds redundant steps | Budget exhaustion | Replan should diff against current state |
| PL3 | Pipe-separated action_type in LLM output | Sanitized post-fix | Prompt fixed; sanitization as defense |
| PL4 | Subgoal count too high | Hits MAX_TOTAL_ACTIONS | Dynamic budget based on task complexity |

### Class 5 — State Management Failures

| ID | Mode | Current Handling | Gap |
|----|------|-----------------|-----|
| SM1 | Stale screen_state used post-replan | Old perceive output used | Must flush on replan |
| SM2 | Hash history grows unbounded across replans | Loop detection false fires | Should window to last N subgoals |
| SM3 | goal_summary absent in state | Responder says wrong goal | Fixed (coordinator_node.py) |
| SM4 | Subgoal advance on open_app false positive | Always advances (pre_hash="") | Needs target_screen_reached criterion |

---

## G. Phased Implementation Roadmap

### Phase 1 — Stabilization (Zero new dependencies)

**Goal:** Eliminate false positives and fix verification reliability. No new infrastructure required.

**1.1 Post-Gesture Stabilization Wait**  
Add `asyncio.sleep(0.3)` in `_verify_node` before calling `request_perception`. No polling — fixed 300ms delay. Removes ~60% of mid-transition noise.  
Files: `agents/coordinator.py:_verify_node`  
Effort: 2 lines

**1.2 Zone-Weighted Screen Hash**  
Replace `_compute_screen_hash` with `_compute_zone_weighted_hash`. Weight content zone 3×, status zone 0.1×.  
Files: `agents/perceiver_agent.py`, `agents/verifier_agent.py`  
Effort: 15 lines

**1.3 Error Screen Classifier**  
Add `_is_error_screen(elements) -> bool` in verifier. Check first 10 UI tree elements against `ERROR_INDICATORS` list. If error screen detected, `subgoal_completed=False`, `suggested_action="back"`.  
Files: `agents/verifier_agent.py`  
Effort: 20 lines

**1.4 Retry Ladder Activation**  
In `_route_after_verify`, before routing to `replan`, check `subgoal.attempts < 2` → route to `perceive` (re-perceive + retry). Only replan after 2 perception retries.  
Files: `agents/coordinator.py:_route_after_verify`  
Effort: 8 lines

**1.5 Replan State Flush**  
In `_replan_node`, add `screen_state=None, screen_hash_history=[]` to return dict.  
Files: `agents/coordinator.py:_replan_node`  
Effort: 2 lines

**Expected outcome:** Reduced false completions, better loop detection, fewer unnecessary LLM replan calls.

---

### Phase 2 — Structural Improvements (Moderate refactor)

**Goal:** Decouple pre-action snapshot from perceive, add initial screen context to planner.

**2.1 Pre-Action Snapshot Node**  
Add `snapshot_pre` node to the graph between `decide` and `act`. Captures a fresh UI tree hash. Stores as `CoordinatorState.pre_action_hash: str`. Verifier uses this hash as `pre_hash` instead of the perceive-time hash.  
Files: `agents/coordinator.py`, `agents/verifier_agent.py`  
Effort: 30 lines + graph rewire

**2.2 Perception-Aware Planning**  
In `_plan_node`, run a fast UI tree capture (no screenshot, no OmniParser) before calling `GoalDecomposer.decompose`. Pass current app name and visible element count as context string.  
Files: `agents/coordinator.py:_plan_node`, `services/goal_decomposer.py`, `prompts/planning.py`  
Effort: 25 lines

**2.3 open_app Verification via target_screen_reached**  
Update `config/success_criteria.py`: `open_app` criterion should be  
`SuccessCriteria(ui_changed=True, target_screen_reached="")` (set at plan time using app name).  
In `goal_decomposer.py:_plan_with_llm`, when `action_type == "open_app"` and `target` is the app name, set `success_criteria.target_screen_reached = target.lower()`.  
Files: `services/goal_decomposer.py`, `agents/verifier_agent.py:_check_success_criteria`  
Effort: 20 lines

**2.4 Scroll-Before-Replan for Off-Screen Targets**  
When `_route_after_decide` returns `"replan"` due to no target match, first attempt scroll recovery:  
- If `subgoal.attempts == 0`: insert a scroll-down subgoal before current subgoal, increment `subgoal.attempts`  
- Only replan if `attempts >= 1`  
Files: `agents/coordinator.py:_route_after_decide`  
Effort: 25 lines

---

### Phase 3 — Screenshot-Based Verification

**Goal:** Add visual diff as a verification signal for WebView-heavy and canvas-rendered screens.

**3.1 Screenshot Delta Signal**  
In `VerifierAgent.verify`, when `bundle.screenshot` is available:
- Retrieve `pre_screenshot` from state (captured in snapshot_pre node)
- Compute SSIM or pixel-diff score at 64×64 resolution
- `visual_changed: bool = diff_score > 0.05`

Combine with UI hash: `screen_changed = ui_hash_changed OR visual_changed`  
Files: `agents/verifier_agent.py`, `agents/coordinator.py` (add `pre_screenshot` to state)  
Dependencies: `scikit-image` (SSIM) or `Pillow` (pixel diff — already in requirements)  
Effort: 40 lines

**3.2 Screenshot Capture in snapshot_pre**  
`snapshot_pre` node captures both UI tree hash AND screenshot (stored as bytes in state). The screenshot is passed to verifier alongside the hash.  
Only activates when `screen_type == "webview"` or `is_visual_app` — avoids overhead for native screens.  
Files: `agents/coordinator.py:_snapshot_pre_node`  
Effort: 20 lines

---

### Phase 4 — Semantic Goal Verification

**Goal:** Add goal-level terminal validation and richer success signals.

**4.1 Goal-Level Verification Node**  
Add `goal_verify` node after `complete`. Takes a screenshot of the final state. Sends to VLM:
```
Goal: {goal.description}
[screenshot]
Was this goal achieved? Reply JSON: {"achieved": true/false, "reason": "..."}
```
Count 1 LLM call. If `achieved=False`, route to `replan` with obstacle = `reason`.  
Files: `agents/coordinator.py`, graph rewire  
Effort: 45 lines

**4.2 Toast/Transient Event Detection**  
During stabilization phase, poll for transient UI events (toasts, snackbars) by looking for `FrameLayout` nodes with short text appearing briefly. Cache these as `transient_events: List[str]` in state. Make them available to verifier as additional success signals.  
Files: `agents/coordinator.py:_stabilize_node`  
Effort: 30 lines

**4.3 VLM Confidence Signal**  
Modify VLM selection prompt to request confidence alongside letter:
```json
{"letter": "K", "confidence": "high|medium|low", "reason": "..."}
```
In `perceiver_agent.py`, map VLM confidence to pipeline match confidence override: low=0.5, medium=0.7, high=0.9.  
Files: `perception/vlm_selector.py`, `agents/perceiver_agent.py`  
Effort: 25 lines

---

### Phase Summary

| Phase | Changes | LLM Budget Impact | Latency Impact | Risk |
|-------|---------|------------------|----------------|------|
| 1 | Stabilization fixes | -20% LLM calls (fewer replans) | +300ms/action | Low |
| 2 | Structural improvements | -10% (scroll before replan) | +50ms/cycle | Medium |
| 3 | Screenshot verification | Neutral | +100ms (WebView only) | Low |
| 4 | Semantic goal check | +1 LLM call/task | +500ms terminal | Medium |

**Recommended implementation order:** Phase 1 → Phase 2 items 2.1+2.3 → Phase 3.1 → Phase 4.1

---

## Appendix: Quick Reference — File-Level Impact

| File | Phase | Nature of Change |
|------|-------|-----------------|
| `agents/coordinator.py` | 1,2,3,4 | New nodes (snapshot_pre, stabilize, goal_verify); routing changes; state flush |
| `agents/verifier_agent.py` | 1,2,3 | Error classifier; zone-weighted hash; screenshot diff; pre_action_hash source |
| `agents/perceiver_agent.py` | 1 | Zone-weighted `_compute_screen_hash` |
| `services/goal_decomposer.py` | 2 | Pass screen context to planner; set target_screen_reached on open_app |
| `config/success_criteria.py` | 2 | open_app: add target_screen_reached pattern |
| `prompts/planning.py` | 2 | Planning prompt + screen context slot |
| `perception/vlm_selector.py` | 4 | Return confidence with letter selection |
| `aura_graph/agent_state.py` | 1 | Use RetryStrategy in coordinator routing |

*No new external dependencies required for Phase 1 or 2. Phase 3 uses Pillow (already installed). Phase 4 is VLM-only.*
