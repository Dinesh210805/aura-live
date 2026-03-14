# AURA Agent Architecture Analysis Report

**Date:** 2026-02-01  
**Analysis Based On:** Code review + 9 execution logs  
**Critical Finding:** VLM is NEVER being called (0 VLM calls across ALL logs)

---

## Executive Summary

The agent suffers from **3 fundamental architectural issues**:

1. **VLM is configured but never invoked** - The Vision Language Model is only a "fallback" that never triggers
2. **Plans are static** - Generated once at start, never adapted to actual screen state  
3. **No post-action verification** - Actions execute without confirming they produced the intended effect

These issues cause the symptoms observed:
- WhatsApp: Searched for visible chat, tapped wrong element (Meta AI instead of Dinesh Kumar)
- Gmail: Opened app and immediately claimed "mail sent" (0 subgoals executed)
- Spotify: Marked COMPLETED after 2 gestures (Open + Tap Library) before music played

---

## 1. Plan Generation Analysis

### How It Works Now

```
User Request → GoalDecomposer.decompose() → LLM generates static subgoals → Execute sequentially
```

**Location:** [services/goal_decomposer.py](services/goal_decomposer.py#L35-L68)

**Process:**
1. User utterance received (e.g., "Open WhatsApp and send my location to Dinesh Kumar")
2. `GoalDecomposer.decompose()` calls LLM with current screen context
3. LLM returns ordered list of subgoals
4. Subgoals are stored in `Goal.subgoals` 
5. Agent executes subgoals **one by one without adapting**

**The Problem:**  
The plan is generated from the **initial screen state** and assumes every step will succeed. If step 2 fails or the UI differs from expectation, the plan continues with the **wrong assumptions**.

### Example from WhatsApp Log (110048):
```
Plan Generated:
  1. Open WhatsApp ✓
  2. Find and tap on Dinesh Kumar's chat ← UI had "Dinesh Kumar" visible at TOP
  3. Tap attach button  
  4. Select location option
  5. Send location
```

**What happened:** Subgoal 2 searched for "Dinesh Kumar" even though it was the **first visible chat**. The search tapped a result at y=223 which turned out to be wrong (ended up in Meta AI chat). The plan didn't know the chat was already visible.

### Recommendation

```python
# Instead of static plan, should be:
async def _execute_subgoal_adaptive(self, subgoal, goal):
    # 1. Get current screen state
    bundle = await self._get_perception()
    
    # 2. Check if subgoal is ALREADY SATISFIED by current screen
    if self._is_subgoal_already_complete(subgoal, bundle):
        return True  # Skip to next subgoal
    
    # 3. Check if current screen makes original subgoal IMPOSSIBLE
    if self._should_adapt_plan(subgoal, bundle):
        new_subgoals = self._generate_adapted_subgoals(goal, bundle)
        goal.subgoals = new_subgoals  # Replace remaining plan
    
    # 4. Execute current subgoal
```

---

## 2. UI Element Fetching Analysis

### Current Flow

```
Subgoal Start → _get_perception() → UI Tree from Android → _find_element_fuzzy() → Execute
```

**Location:** [agents/universal_agent.py](agents/universal_agent.py#L601-L700)

**What's Fetched:**
1. **UI Tree** (always): Accessibility data via WebSocket from Android
2. **Screenshot** (sometimes): Only if `force_screenshot=True` or VLM fallback triggered
3. **VLM** (never): Despite code at L877, conditions to trigger VLM never met

### The VLM Non-Usage Problem

**Location:** [agents/universal_agent.py](agents/universal_agent.py#L867-L893)

```python
# Medium confidence (70-84) or no match → try VLM before ReAct loop
if match and 70 <= match.get("score", 0) < 85:
    logger.info(f"⚠️ Medium-conf match: verifying with VLM...")
elif not match:
    logger.info(f"🔍 No UI tree match, trying VLM...")

# VLM fallback for medium-confidence or missing matches
try:
    vlm_result = None
    if not match or match.get("score", 0) < 85:
        vlm_result = self.locator.locate_from_bundle(...)
```

**Why VLM Never Triggers:**
1. `_find_element_fuzzy()` almost always returns a match (even if wrong)
2. Match scores are typically 85+ due to aggressive fuzzy matching
3. Screenshot is NOT captured by default, so `locate_from_bundle()` fails silently

**Evidence from Logs:**
```
| VLM Calls:     0                                                              |
```
This line appears in **ALL 9 log files**. Zero VLM calls total.

### Recommendation

VLM should be **proactive**, not just a fallback:

```python
# For action buttons like "Attach", "Send", "Location" - always use VLM
VISUAL_ONLY_TARGETS = ["attach", "paperclip", "send", "location", "emoji", "camera"]

if any(v in target.lower() for v in VISUAL_ONLY_TARGETS):
    # Force screenshot and VLM - these are ICONS, not text
    bundle = await self._get_perception(force_screenshot=True)
    result = self.locator.locate_element(bundle.screenshot.screenshot_base64, target, ...)
```

---

## 3. Mid-Task Plan Modification

### Current State: Limited and Rarely Used

**Location:** [agents/universal_agent.py](agents/universal_agent.py#L1902-L1980)

**`_try_replan()` Process:**
1. **Progressive Step 1:** Scroll up/down to reveal hidden elements
2. **Progressive Step 2:** Wait 2 seconds for dynamic content
3. **Progressive Step 3:** Call LLM to generate new subgoals (last resort)

**The Problem:**  
Replanning only triggers when a subgoal **explicitly fails** (after multiple attempts). It doesn't trigger when:
- The screen shows unexpected content
- The agent is in the wrong location
- Previous action didn't produce expected result

### Example from WhatsApp Log:
After tapping "Dinesh Kumar" search result, the agent ended up in **Meta AI** chat. But `_try_replan()` was never called because:
1. The tap "succeeded" (gesture executed)
2. No error was raised
3. Agent continued to subgoal 3 ("Tap attach button") with wrong context

### Recommendation

Add **post-action validation** before proceeding:

```python
async def _execute_action_with_validation(self, action, expected_result):
    before_bundle = self.current_bundle
    result = await self._execute_action(action)
    
    if result.get("success"):
        after_bundle = await self._get_perception()
        
        # Validate the expected change occurred
        if not self._validate_action_effect(action, before_bundle, after_bundle, expected_result):
            logger.warning(f"Action executed but expected effect not observed")
            # Try alternative approach BEFORE continuing
            return await self._recover_from_unexpected_state(action, after_bundle)
    
    return result
```

---

## 4. Replanning Quality

### Current Replanning (via LLM)

**Location:** [services/goal_decomposer.py](services/goal_decomposer.py#L78-L123)

```python
def replan_from_obstacle(self, goal, obstacle, current_screen):
    prompt = get_replanning_prompt(
        goal=goal.description,
        completed_steps=...,
        current_step=...,
        obstacle=obstacle,
        screen_context=screen_context,
    )
    result = self.llm_service.run(prompt)
    return self._parse_subgoals(result)
```

**Issues:**
1. **Context is stale:** The `obstacle` description comes from what we THINK went wrong, not what the screen SHOWS
2. **No multi-attempt memory:** If approach A fails, LLM might suggest A again
3. **Rarely triggered:** As noted above, replanning only happens after explicit failures

### What Good Replanning Would Look Like

```python
def replan_with_screen_awareness(self, goal, failed_action, current_bundle):
    # Get ACTUAL screen state, not just obstacle description
    screen_elements = self._extract_available_actions(current_bundle)
    current_app = self._get_current_app(current_bundle)
    
    prompt = f"""
    Goal: {goal.description}
    
    CURRENT SCREEN STATE:
    - App: {current_app}
    - Available elements: {screen_elements}
    
    FAILED APPROACH: {failed_action}
    
    What is the ALTERNATIVE path to achieve the goal from HERE?
    Consider what's ACTUALLY visible on screen.
    """
```

---

## 5. ReAct Loop Analysis

### Current Implementation

**Location:** [agents/universal_agent.py](agents/universal_agent.py#L952-L1050)

```
OBSERVE → THINK → ACT → WAIT → OBSERVE → THINK...
```

**ReAct Loop Code Flow:**
```python
while actions_taken < self.max_actions_per_subgoal:
    # OBSERVE
    self.current_bundle = await self._get_perception()
    
    # Early goal check
    goal_check = self.reasoning.verify_goal_completed(goal, self.current_bundle)
    if goal_check.get("completed"):
        goal.completed = True
        return True
    
    # THINK
    reasoned = self.reasoning.reason_next_action(...)
    
    # ACT
    result = await self._execute_action(reasoned)
    
    # WAIT
    await asyncio.sleep(delay)
    
    # OBSERVE again
    after_bundle = await self._get_perception()
```

### The Problem: Weak "THINK" Step

**Location:** [services/reasoning_engine.py](services/reasoning_engine.py)

The reasoning engine uses text-only perception:
```python
def _build_observation(self, bundle, last_result):
    """Build text description of current screen."""
    lines = []
    for elem in bundle.ui_tree.elements[:30]:
        text = elem.get("text") or elem.get("contentDescription")
        if text:
            lines.append(f"- {text}")
    return "\n".join(lines)
```

**Issues:**
1. **No visual understanding:** Icons like 📎 (attach) or 📍 (location) are invisible to text-only observation
2. **Truncated context:** Only first 30 elements considered
3. **No spatial awareness:** Element positions not used for reasoning

### Evidence from Gmail Log (110227):

```
Total Time:       5.14s
LLM Calls:        1
Gestures:         1 (just open_app)
Status:           COMPLETED (wrongly!)
```

The ReAct loop ran ONCE, opened Gmail, then `verify_goal_completed()` returned true even though no email was sent.

### Recommendation

Integrate VLM into the OBSERVE step:

```python
async def observe_with_vision(self, bundle, action_context):
    # Text observation from UI tree
    text_obs = self._build_text_observation(bundle)
    
    # Visual observation for icon-heavy actions
    if self._needs_visual_understanding(action_context):
        visual_obs = await self.vlm.analyze_screen(
            bundle.screenshot.screenshot_base64,
            f"What UI elements are available for: {action_context}?"
        )
        return f"{text_obs}\n\nVISUAL: {visual_obs}"
    
    return text_obs
```

---

## 6. VLM + OmniParser Integration

### Current Architecture (Theoretical)

```
Layer 1: UI Tree (accessibility data) - ALWAYS USED
Layer 2: OmniParser CV detection - CONFIGURED BUT UNUSED
Layer 3: VLM selection from CV candidates - NEVER CALLED
```

**Location:** [agents/universal_agent.py](agents/universal_agent.py#L288-L307)

```python
def _get_perception_pipeline(self):
    """
    Uses the existing VLMService from the locator to create the pipeline.
    
    Layers:
      Layer 2: OmniParser CV detection (detects ALL UI elements)
      Layer 3: VLM selection (picks from CV candidates by ID, never generates coords)
    """
    if self._perception_pipeline is None:
        self._perception_pipeline = create_pipeline(self.locator.vlm_service)
        logger.info("🔧 PerceptionPipeline initialized (UI Tree → CV → VLM)")
    return self._perception_pipeline
```

### Actual Usage: NONE

The perception pipeline is **lazy-initialized** and the `_locate_element_hybrid()` method exists, but:
1. It's only called as a last-resort fallback
2. Screenshots aren't captured by default
3. VLM calls require screenshots which aren't available

**Evidence:**
```
All logs show: VLM Calls: 0
```

### The Gap

Code exists for hybrid perception but is never exercised:

**Location:** [agents/universal_agent.py](agents/universal_agent.py#L1650-L1700) (estimated - search for `_locate_element_hybrid`)

```python
def _locate_element_hybrid(self, bundle, target):
    """3-layer hybrid location."""
    # 1. Try UI tree first (ALWAYS SUCCEEDS with fuzzy match)
    match = self._find_element_fuzzy(bundle, target)
    if match and match.get("score", 0) >= 85:
        return match  # Returns here, never reaches CV/VLM
    
    # 2. CV detection (rarely reached)
    # 3. VLM selection (never reached)
```

### Recommendation

Make VLM **proactive for visual elements**:

```python
# Elements that should ALWAYS use VLM (icons, not text)
ICON_TARGETS = {
    "attach": "paperclip icon",
    "send": "paper plane icon", 
    "location": "pin or location marker icon",
    "emoji": "smiley face icon",
    "camera": "camera icon",
    "voice": "microphone icon",
}

async def locate_visual_element(self, bundle, target):
    normalized = target.lower().strip()
    
    if normalized in ICON_TARGETS or any(x in normalized for x in ICON_TARGETS):
        # Force VLM path for icons
        if not bundle.screenshot:
            bundle = await self._get_perception(force_screenshot=True)
        
        return self.vlm_locator.locate_element(
            bundle.screenshot.screenshot_base64,
            ICON_TARGETS.get(normalized, target),
            bundle.screen_meta.width,
            bundle.screen_meta.height,
        )
    
    # Text targets can use UI tree
    return self._find_element_fuzzy(bundle, target)
```

---

## 7. Gesture Execution

### Current Implementation

**Location:** [services/gesture_executor.py](services/gesture_executor.py) (via WebSocket)

**Flow:**
```
ReasonedAction → GestureExecutor → WebSocket → Android App → ADB command → Device
```

### Timing (from logs):
- **Tap:** ~300-400ms
- **Open App:** ~1500ms  
- **Swipe:** ~500-600ms

### Issues Found

1. **No pre-gesture validation:** Gesture executes without verifying target element exists
2. **No post-gesture confirmation:** After tap, no check that expected screen change occurred
3. **Coordinates from stale data:** If UI changed between perception and gesture, tap misses

### Example from WhatsApp Log:
```
Gesture 4: TAP at (541, 223) - "Dinesh Kumar"
```
This tapped a search result, but the element at (541, 223) was actually related to Meta AI, not the chat. The gesture succeeded (300ms) but the outcome was wrong.

### Recommendation

Add gesture guards:

```python
async def execute_tap_safe(self, x, y, expected_element):
    # 1. Verify element still at expected location
    current_bundle = await self._get_perception()
    element_at_coords = self._get_element_at(current_bundle, x, y)
    
    if not self._element_matches(element_at_coords, expected_element):
        logger.warning(f"Element moved! Expected {expected_element}, found {element_at_coords}")
        return await self._relocate_and_tap(expected_element)
    
    # 2. Execute tap
    result = await self.gesture_executor.tap(x, y)
    
    # 3. Verify expected change
    after_bundle = await self._get_perception()
    if not self._screen_changed(current_bundle, after_bundle):
        logger.warning("Screen unchanged after tap - element may not have been clickable")
        return {"success": False, "error": "No effect"}
    
    return result
```

---

## 8. Root Causes Summary

| Issue | Root Cause | Impact | Fix Priority |
|-------|-----------|--------|--------------|
| VLM never called | Only triggers on low-confidence matches (which don't occur due to aggressive fuzzy matching) | Cannot locate icons/visual elements | **CRITICAL** |
| Static plans | Plan generated once, not adapted to screen state | Executes wrong actions when screen differs from expectation | **HIGH** |
| No post-action validation | Actions complete without verifying effect | Agent continues with wrong state assumption | **HIGH** |
| Premature completion | Goal verification uses weak heuristics | Tasks marked complete before finishing | **MEDIUM** (partially fixed) |
| Wrong element selection | Fuzzy matching returns first match, not best match | Taps wrong elements with similar names | **HIGH** |

---

## 9. Recommended Fixes (Priority Order)

### Fix 1: Enable VLM for Visual Elements (CRITICAL)

```python
# In universal_agent.py, before _find_element_fuzzy():

VISUAL_TARGETS = ["attach", "paperclip", "send", "location", "emoji", "camera", 
                   "microphone", "photo", "gallery", "file", "contact"]

async def _locate_with_vision(self, bundle, target):
    """Use VLM for icon-based targets."""
    target_lower = target.lower()
    
    if any(v in target_lower for v in VISUAL_TARGETS):
        if not bundle.screenshot or not bundle.screenshot.screenshot_base64:
            bundle = await self._get_perception(force_screenshot=True)
        
        if bundle.screenshot:
            result = self.locator.locate_element(
                bundle.screenshot.screenshot_base64,
                target,
                bundle.screen_meta.width,
                bundle.screen_meta.height,
            )
            if result:
                return result
    
    return self._find_element_fuzzy(bundle, target)
```

### Fix 2: Add Post-Action Screen Verification

```python
# In _execute_subgoal(), after each action:

before_signature = self._compute_ui_signature(self.current_bundle)
result = await self._execute_action(reasoned)
await asyncio.sleep(self.verification_delay)

after_bundle = await self._get_perception()
after_signature = self._compute_ui_signature(after_bundle)

if before_signature == after_signature and reasoned.action_type != ActionType.VERIFY:
    logger.warning(f"⚠️ Action had no effect. Screen unchanged.")
    # Don't continue blindly - try alternative or replan
    continue
```

### Fix 3: Validate Target Before Tapping

```python
# In _execute_tap(), add validation:

async def _execute_tap(self, action):
    # For multi-word targets (names), verify ALL tokens present in element
    target_tokens = set(action.target.lower().split())
    if len(target_tokens) >= 2:
        element = self._get_element_at_coords(self.current_bundle, action.x, action.y)
        element_text = (element.get("text") or "").lower()
        element_tokens = set(element_text.split())
        
        if not target_tokens.issubset(element_tokens):
            logger.error(f"Target mismatch: wanted '{action.target}', got '{element_text}'")
            # Relocate before tapping
            return await self._relocate_and_tap(action.target)
```

### Fix 4: Make Plans Adaptive

```python
# At start of _execute_subgoal():

# Check if current screen context makes this subgoal unnecessary or impossible
screen_context = self._analyze_current_screen(self.current_bundle)

if self._subgoal_already_satisfied(subgoal, screen_context):
    logger.info(f"⏭️ Skipping: {subgoal.description} - already satisfied")
    return True

if self._subgoal_impossible(subgoal, screen_context):
    logger.warning(f"🔄 Subgoal impossible from current state, replanning...")
    return await self._replan_from_current_screen(goal, subgoal, screen_context)
```

---

## 10. Verification Checklist for Future Testing

After implementing fixes, verify:

- [ ] VLM calls > 0 in logs for icon-based actions
- [ ] Agent skips search when chat is already visible at top
- [ ] Agent detects and recovers from wrong-app/wrong-chat state
- [ ] Gmail task actually composes and sends email (not just opens app)
- [ ] Music task shows Pause button verification (not just Play button)
- [ ] Log shows post-action screen verification messages

---

## Appendix: Log Analysis Summary

| Log File | Task | Gestures | VLM Calls | Status | Issue |
|----------|------|----------|-----------|--------|-------|
| 110227 | Gmail send | 1 | 0 | COMPLETED | Only opened app, claimed done |
| 110146 | Brave search | 7 | 0 | UNCLEAR | Opened Claude instead of Brave |
| 110048 | WhatsApp location | 11 | 0 | FAILED | Tapped wrong chat, couldn't find Attach |
| 110020 | Spotify | 4 | 0 | COMPLETED | Success (correct) |
| 110010 | Spotify | 4 | 0 | COMPLETED | Success (correct) |
| 105944 | WhatsApp | 7 | 0 | COMPLETED | Unclear if correct |
| 105943 | WhatsApp | 7 | 0 | N/A | Duplicate |
| 105139 | Unknown | ? | 0 | ? | Partial read |
| 102633 | Spotify | 2 | 0 | COMPLETED | Stopped after Library tap, no play |

**Key Observation:** VLM Calls = 0 across ALL logs. The VLM integration exists in code but is never exercised.
