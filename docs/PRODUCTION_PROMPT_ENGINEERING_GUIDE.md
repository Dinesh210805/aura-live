# Production-Grade Agent Prompt Engineering Guide

## For Aura — A Mobile UI Automation Agent

> Compiled from research across OpenAI CUA, Anthropic Computer Use, Google AndroidWorld/M3A,
> ByteDance UI-TARS, THUDM CogAgent, Tencent AppAgent, SeeAct-V, browser-use, Alibaba MobileWorld,
> AgentCPM-GUI, and Anthropic/OpenAI production best practices.

---

## Table of Contents

1. [Core Philosophy](#1-core-philosophy)
2. [Prompt Architecture Patterns from Industry Leaders](#2-prompt-architecture-patterns-from-industry-leaders)
3. [The Ideal Agent Prompt Structure](#3-the-ideal-agent-prompt-structure)
4. [Reasoning & Chain-of-Thought Design](#4-reasoning--chain-of-thought-design)
5. [Action Space Design](#5-action-space-design)
6. [Grounding Techniques](#6-grounding-techniques)
7. [Error Recovery & Self-Correction](#7-error-recovery--self-correction)
8. [Output Format Design](#8-output-format-design)
9. [Token Optimization](#9-token-optimization)
10. [Few-Shot Examples — The Highest-Impact Technique](#10-few-shot-examples--the-highest-impact-technique)
11. [Aura-Specific Diagnosis & Recommendations](#11-aura-specific-diagnosis--recommendations)
12. [Concrete Rewrite Plan for reactive_step.py](#12-concrete-rewrite-plan-for-reactive_steppy)
13. [Prompt Checklist — Pre-Ship Review](#13-prompt-checklist--pre-ship-review)

---

## 1. Core Philosophy

### What the Giants Agree On

Every production system we studied converges on the same core truths:

| Principle | Source |
|---|---|
| **Context engineering > prompt engineering** | Anthropic (2025 blog) — "The art of building dynamic systems that provide the right information and tools at the right time" |
| **Do the simplest thing that works** | Anthropic — "Exhaust each level of complexity before graduating to the next" |
| **Few-shot examples > rule lists** | Anthropic Docs — "The single highest-impact technique for steering behavior" |
| **Role prompting is ineffective for correctness** | Production research — personalities don't improve accuracy; context does |
| **Separation of concerns** | All major systems — planning ≠ grounding ≠ execution ≠ verification |
| **Right altitude** | Anthropic — between "brittle if-else hardcoding" and "vague high-level guidance" |

### The Anti-Pattern Aura Currently Exhibits

Aura's `reactive_step.py` is a **monolithic 18K-char prompt** with 37+ numbered rules, non-sequential ordering (Rule 35 → 37 → 36 → 38 → 40 → 39), triple redundancy on autocomplete handling, and rules placed AFTER the output format section where LLMs weight them less. This is the opposite of what every production system does.

**The fix is not to add more rules. It is to restructure.**

---

## 2. Prompt Architecture Patterns from Industry Leaders

### Pattern A: UI-TARS (ByteDance) — Minimal Instruction + CoT Output

```
System: "You are a GUI agent. You are given a task and your action history, 
with screenshots. You need to perform the next action to complete the task."

Output: Thought: <reasoning about screen state>
        Action: click(start_box='<|box_start|>(x,y)<|box_end|>')
```

**Key insight:** 42.5% OSWorld, 64.2% AndroidWorld (SOTA). The system prompt is **2 sentences**. All intelligence is in the model's training and the structured output format.

**Applicable to Aura:** You're using a general LLM (Groq/Gemini), not a fine-tuned GUI model, so you need more instruction — but the direction is clear: **less instruction, more structure**.

### Pattern B: browser-use — Structured Output with Self-Evaluation

```json
{
  "thinking": "reasoning about current state",
  "evaluation_previous_goal": "Success - the page loaded correctly",
  "memory": "Searched for flights. Found 3 options. Selected cheapest.",
  "next_goal": "Fill in passenger details",
  "action": [{"click_element": {"index": 15}}]
}
```

**Key insight:** The `evaluation_previous_goal` field is a one-sentence success/failure analysis that provides **built-in self-correction** without needing explicit rules about "check previous step." The `memory` field (1-3 sentences) maintains task context across turns without the system prompt needing to explain how.

**Applicable to Aura:** This output structure is directly adoptable. It replaces Rules 20, 37, and parts of Rule 13 with **structured fields** instead of prose rules.

### Pattern C: SeeAct-V — Separation of Planning from Grounding

```
Step 1: Planner (GPT-4o) → "Click the 'Add to Cart' button"
Step 2: Visual Grounder (UGround) → coordinates (x=342, y=1205)
```

**Key insight:** The planner never deals with coordinates. The grounder never deals with intent. Each model does what it's best at.

**Applicable to Aura:** You already have this split (`reactive_step.py` = planner, `vision.py` = grounder). But `reactive_step.py` still contains grounding rules (Rule 21 about ghost containers, Rule 38 about UI tree coordinates). **Move all grounding rules to `vision.py`.**

### Pattern D: Anthropic Computer Use — XML-Structured Sections

```xml
<context>Current screen state and history</context>
<instructions>
  <rule priority="critical">Always verify element visibility before clicking</rule>
  <rule priority="normal">Prefer keyboard shortcuts when available</rule>
</instructions>
<examples>
  <example>
    <input>Screen shows login form with empty fields</input>
    <output>{"action": "click", "target": "username_field"}</output>
  </example>
</examples>
```

**Key insight:** XML tags are "cognitive containers" for Claude — they create clear boundaries between types of information. For non-Anthropic models, **Markdown headers achieve the same effect**.

### Pattern E: AppAgent (Tencent) — RAG Knowledge Base

```
Phase 1 (Exploration): Agent explores the app, learns UI patterns
Phase 2 (Deployment): Agent uses learned knowledge via RAG retrieval
```

**Each action includes:** Retrieved knowledge from similar past screens + current screenshot + task description.

**Key insight:** Instead of cramming all app-specific knowledge into the system prompt (what Aura does with Gmail compose flow, WhatsApp attachment paths, Spotify shuffle location), **store app knowledge externally and retrieve it per-screen.**

---

## 3. The Ideal Agent Prompt Structure

Based on all research, the production-grade structure for a per-screen executor prompt is:

```
┌─────────────────────────────────────────────┐
│  SECTION 1: IDENTITY (1-2 sentences)        │  ← Who you are, what you do
│  SECTION 2: INPUT DESCRIPTION (3-5 lines)   │  ← What you'll receive each turn
│  SECTION 3: THINKING PROTOCOL               │  ← How to reason (structured steps)
│  SECTION 4: CRITICAL RULES (5-7 max)        │  ← Only rules that prevent failures
│  SECTION 5: ACTION SPACE (compact table)    │  ← Available actions + signatures
│  SECTION 6: FEW-SHOT EXAMPLES (2-4)        │  ← Input/output pairs for key scenarios
│  SECTION 7: OUTPUT FORMAT (schema + 1 ex)   │  ← Exact JSON schema
└─────────────────────────────────────────────┘
```

### Why This Order Matters

LLMs process tokens sequentially. Attention is strongest at the **beginning** and **end** of a prompt (primacy and recency effects). The middle gets the least attention.

- **Beginning:** Identity + inputs (establishes frame). Critical rules (highest attention).
- **Middle:** Thinking protocol + action space (structural guidance).
- **End:** Examples + output format (what the model sees last before generating).

**Aura's current mistake:** The most critical rules (40, 39, 38, 36, 37) are placed AFTER the output format section — in the lowest-attention zone. Rules also appear in the middle of a 37-rule list where individual rules get diluted.

---

## 4. Reasoning & Chain-of-Thought Design

### The Four Models of Agent Reasoning

| Model | Structure | Used By | Best For |
|---|---|---|---|
| **Thought + Action** | `Thought: ...\nAction: ...` | UI-TARS | Fine-tuned models, minimal overhead |
| **Structured CoT** | `{thinking, evaluation, memory, next_goal, action}` | browser-use | General LLMs, needs self-correction |
| **ReAct** | `Thought → Action → Observation → Thought → ...` | LangChain agents | Multi-tool agents with feedback loops |
| **Reflexion** | ReAct + episodic memory of failures | Reflexion paper | Long-horizon tasks with learning |

### Recommendation for Aura

Use **Structured CoT** (browser-use pattern) — it fits your architecture:

```json
{
  "thinking": "2-3 sentences: what I see, what the goal needs, why this action",
  "evaluation": "Previous action succeeded/failed because [evidence from screenshot]",
  "memory": "Key facts: typed 'dinesh@gmail.com' in To, autocomplete showing, need to confirm",
  "action_type": "tap",
  "target": "Dinesh kumar C",
  "description": "Tap autocomplete suggestion to confirm recipient"
}
```

**Why this works better than Aura's current approach:**
- `evaluation` replaces Rules 20, 37 (prev_step_ok, verification_passed) — same info, structured
- `memory` provides persistent context without needing the system prompt to explain it
- `thinking` is explicit CoT that the model generates, not rules about how to think

### What NOT to Do with CoT

From Anthropic's research: "CoT is not universally optimal." Don't force complex reasoning chains for simple actions. The `thinking` field should be allowed to be 1 sentence for obvious actions ("Screen shows search results, tapping first result") and 3-5 sentences for ambiguous situations.

---

## 5. Action Space Design

### Compact Action Spaces Win

| System | Action Space Size | Performance |
|---|---|---|
| UI-TARS | 7 actions | 64.2% AndroidWorld |
| AgentCPM-GUI | 6 actions | Comparable, 8B model |
| Aura (current) | 10 actions | — |
| browser-use | 20+ actions | — |

**Industry consensus:** Fewer, well-defined actions > many overlapping actions. Every additional action type increases the decision space and error rate.

### Aura's Current Actions (10)
```
open_app | tap | type | press_enter | dismiss_keyboard | swipe | scroll_down | scroll_up | back | wait
```

### Recommended Consolidation

```
open_app | tap | type | press_key | scroll | swipe | back | wait
```

Changes:
- Merge `press_enter` into `press_key` (with key name parameter) — future-proof for other keys
- Merge `dismiss_keyboard` into `press_key(key="back")` or `tap(target="outside_keyboard")` — it's not a separate intent
- Merge `scroll_down`/`scroll_up` into `scroll(direction="down"|"up")` — halves the decision space for scrolling

This brings you to **8 actions** — in line with SOTA systems.

### Action Signatures Should Be Explicit

Instead of rules explaining what `target` means for each action type (current Rule about TYPE ACTION), define signatures:

```
tap(target: str)              — tap element matching target label/description
type(text: str, field: str)   — type text into field (field = label of target field)
scroll(direction: up|down)    — scroll current view
swipe(direction: left|right)  — swipe gesture (carousels, dismiss)
open_app(package: str)        — launch app by package name
press_key(key: str)           — press system key (enter, back, home)
back()                        — navigate back
wait()                        — do nothing this turn
```

**This replaces** the entire "TYPE ACTION RULE" section and parts of Rules 7, 8, 19.

---

## 6. Grounding Techniques

### How SOTA Systems Ground Actions to Screen Elements

| System | Grounding Input | Approach |
|---|---|---|
| UI-TARS | Screenshot only | End-to-end, predicts (x,y) coordinates |
| CogAgent | Screenshot (dual-resolution) | 224px LR + 1120px HR encoders |
| AndroidWorld/M3A | Screenshot + UI tree | Hybrid — Set-of-Mark overlays |
| SeeAct-V | Screenshot → separate grounder | Two-stage: plan then locate |
| Aura | Screenshot + UI tree | Hybrid, but grounding rules in planner prompt |

### Key Principle: **Separate Planning from Grounding**

Aura's `reactive_step.py` contains extensive grounding rules:
- Rule 21 (ghost containers, avatar elements — 15+ lines)
- Rule 38 (UI tree is coordinate map, not intent map — 10+ lines)
- The entire `UI ELEMENTS (REFERENCE ONLY)` warning block

**These belong in `vision.py`**, not in the reactive planner. The planner should output:
```json
{"action_type": "tap", "target": "autocomplete suggestion row showing Dinesh kumar C"}
```

And the grounder (`vision.py`) should resolve "autocomplete suggestion row showing Dinesh kumar C" → coordinates (x, y), applying all the ghost-container/avatar/coordinate-validation rules internally.

**This single change removes ~1,200 tokens from reactive_step.py per call.**

---

## 7. Error Recovery & Self-Correction

### What Production Systems Do

| System | Recovery Mechanism |
|---|---|
| browser-use | `evaluation_previous_goal` field — structured pass/fail per turn |
| UI-TARS | System-2 reasoning — explicit reflection when stuck, multi-step retry |
| Reflexion | Episodic memory — past failure summaries retrieved on similar situations |
| AppAgent | RAG retrieval of similar past interactions |
| Aura | Rules 13, 20, 33, 37 — scattered across prompt |

### The Clean Pattern

Instead of scattered rules about error recovery, use a **structured evaluation field** and a **loop detection counter**:

```json
{
  "evaluation": {
    "previous_succeeded": true,
    "evidence": "Search results now visible with query 'Dinesh'",
    "retry_count": 0
  }
}
```

When `retry_count >= 3` for the same action type on the same screen, the system (coordinator, not the LLM) should force strategy change. **Don't ask the LLM to count its own retries** — that's unreliable. The coordinator should inject "You have attempted scroll_down 3 times on this screen without success. Try a different approach." into the context.

### Aura's Specific Recovery Gaps

1. **No structured failure memory across turns.** LAST FAILURE in the user template only shows the most recent failure. browser-use's `memory` field persists key facts across the full task.

2. **Loop detection is in the prompt (Rule 33) instead of the orchestrator.** The LLM cannot reliably count its own scroll history. Move this to `coordinator.py`.

3. **No escalation path.** When the agent is stuck after 5+ retries, there's no "call_user()" or "I cannot complete this" action. UI-TARS has `call_user()`. Add it.

---

## 8. Output Format Design

### The Production Standard: Typed JSON with Constrained Fields

**browser-use (proven at scale):**
```json
{
  "thinking": "string, 1-5 sentences",
  "evaluation_previous_goal": "string, 1 sentence success/fail",
  "memory": "string, 1-3 sentences of accumulated facts",
  "next_goal": "string, 1 sentence of immediate intent",
  "action": [{"action_name": {"param": "value"}}]
}
```

**Aura (current — 12+ fields):**
```json
{
  "thinking": "...",
  "action_type": "...",
  "target": "...",
  "field_hint": "...",
  "description": "...",
  "screen_context": "...",
  "phase_complete": false,
  "goal_complete": false,
  "prev_step_ok": true,
  "prev_step_issue": "",
  "should_screen_change": true,
  "verification_passed": true,
  "verification_reason": "..."
}
```

### Problems with Aura's Current Output Format

1. **12 fields = 12 decisions per turn.** Each field the LLM has to fill is a potential error point. browser-use uses 5 fields.

2. **Redundant evaluation fields:** `prev_step_ok` + `prev_step_issue` + `verification_passed` + `verification_reason` = 4 fields for the same concept (did the previous action work?). Collapse to 1.

3. **`screen_context` is generated by the LLM, not consumed.** The LLM writes a summary of the screen it already sees. This wastes output tokens and provides no new signal. The screen state should be in the INPUT (which it already is), not the output.

4. **`description` duplicates `thinking`.** Both are free-text explanations of what the agent is doing.

### Recommended Output Schema

```json
{
  "thinking": "What I see + why this action (2-4 sentences)",
  "evaluation": "Previous action: succeeded|failed — [evidence]",
  "memory": "Key accumulated facts for this task",
  "action_type": "tap",
  "target": "Send button",
  "field_hint": "",
  "phase_complete": false,
  "goal_complete": false,
  "should_screen_change": true
}
```

**9 fields → 7 fields that matter.** Removed: `description` (merged into thinking), `screen_context` (already in input), `prev_step_ok`/`prev_step_issue`/`verification_passed`/`verification_reason` (replaced by `evaluation`). Added: `memory` (persistent task context).

---

## 9. Token Optimization

### The Numbers

Aura's `reactive_step.py` system prompt: **~5,500 tokens** per call.
Called **5-15 times per task**.
Total: **27,500 – 82,500 tokens** just for the reactive step system prompt.

**This is 80% of the total per-task token cost.**

### Optimization Strategies (in order of impact)

#### Strategy 1: Trim the System Prompt from 5,500 to ~2,500 tokens

| Remove | Tokens Saved | How |
|---|---|---|
| Grounding rules (21, 38) | ~600 | Move to `vision.py` |
| Duplicate autocomplete rules (GATE + Rule 40) | ~400 | Consolidate into GATE only |
| App-specific knowledge (Gmail flow, WhatsApp, Spotify) | ~300 | Move to RAG/dynamic injection |
| `screen_context` output field + explanation | ~100 | Remove from output schema |
| Verbose rule prose → concise bullet points | ~800 | Rewrite rules as 1-2 liners |
| Non-critical rules (28, 30, 34, 35) | ~400 | Move to "extended rules" injected only when relevant |
| **Total savings** | **~2,600** | **From 5,500 → ~2,900 tokens** |

#### Strategy 2: Dynamic Rule Injection (AppAgent Pattern)

Instead of every rule in every call, inject rules based on screen context:

```python
def get_dynamic_rules(screen_context: str) -> str:
    rules = []
    if "KEYBOARD: Visible" in screen_context:
        rules.append(KEYBOARD_RULE)
    if "autocomplete" in screen_context.lower() or "suggestion" in screen_context.lower():
        rules.append(AUTOCOMPLETE_RULE)
    if "loading" in screen_context.lower() or "spinner" in screen_context.lower():
        rules.append(LOADING_RULE)
    if any(app in screen_context for app in ["Maps", "Waze", "navigation"]):
        rules.append(NAVIGATION_APP_RULE)
    return "\n".join(rules)
```

This alone could save 1,000-2,000 tokens per call (most rules are irrelevant on any given screen).

#### Strategy 3: Prompt Caching (Already Partially Implemented)

Groq auto-caches static system prompts. But caching only works when the system prompt is **identical across calls**. If you inject dynamic rules into the system prompt, put them in the **user message** instead:

```
System: [static core rules — always identical → cached]
User: [dynamic context + screen-specific rules + UI elements]
```

This maximizes cache hits on the expensive system prompt.

#### Strategy 4: Compress Rule Prose

Current Rule 14 (before typing, check if field is focused): **~150 words, 9 lines.**

Production version:
```
BEFORE TYPING: If cursor visible in target field OR last step was tap on this field → type directly.
If no cursor visible → tap field first. Never re-tap an already-focused field.
```
**~30 words, 2 lines.** Same information, 80% fewer tokens.

---

## 10. Few-Shot Examples — The Highest-Impact Technique

### Why Examples Beat Rules

From Anthropic's official documentation:
> "Examples are the single highest-impact technique for steering LLM behavior. A good example is worth 100 lines of instruction."

From production prompt engineering research:
> "3 diverse few-shot examples eliminate more failure modes than 20 edge-case rules."

### Aura's Current State

- `reactive_step.py`: **1 example** (WhatsApp attachment tap) — in the output format section
- `skeleton_planning.py`: **4 examples** — well-done, diverse
- `classification.py`: **0 examples** — rule-only
- `reasoning.py`: **0 examples** — rule-only

### Recommended Few-Shot Examples for reactive_step.py

Design 3-4 examples covering the most common failure modes:

#### Example 1: Autocomplete Confirmation (The Gmail Failure)
```json
{
  "input": {
    "goal": "Send an email to dinesh",
    "phase": "Compose email",
    "screen": "Gmail compose | To field has 'dinesh' typed | Autocomplete dropdown showing 'Dinesh kumar C dinesh@gmail.com' | Subject field empty | KEYBOARD: Visible"
  },
  "output": {
    "thinking": "Gmail compose screen. I typed 'dinesh' in To field and an autocomplete suggestion is showing 'Dinesh kumar C dinesh@gmail.com' below the field. The recipient is NOT confirmed until I tap the suggestion. I must tap it now before moving to Subject.",
    "evaluation": "Previous type action succeeded — 'dinesh' appears in To field",
    "action_type": "tap",
    "target": "Dinesh kumar C",
    "phase_complete": false,
    "goal_complete": false
  }
}
```

#### Example 2: Target Behind Keyboard
```json
{
  "input": {
    "goal": "Send an email to dinesh about meeting",
    "phase": "Type subject line",
    "screen": "Gmail compose | To: Dinesh kumar C (confirmed) | Subject field visible at Y=1800 | KEYBOARD: Visible (covers Y>1600)"
  },
  "output": {
    "thinking": "Need to tap Subject field but it's at Y=1800 which is behind the keyboard (keyboard covers Y>1600). Must dismiss keyboard first to reveal the Subject field.",
    "evaluation": "Previous tap on autocomplete succeeded — recipient confirmed as chip",
    "action_type": "dismiss_keyboard",
    "phase_complete": false,
    "goal_complete": false
  }
}
```

#### Example 3: Already at Destination — Don't Re-navigate
```json
{
  "input": {
    "goal": "Play my liked songs on Spotify",
    "phase": "Navigate to Library",
    "screen": "Spotify | Library tab selected (highlighted) | Playlists visible including 'Liked Songs'"
  },
  "output": {
    "thinking": "Screen shows Spotify Library is already open — the Library tab is highlighted and playlists are visible. The phase says 'Navigate to Library' but I'm already here. Setting phase_complete.",
    "evaluation": "Previous open_app succeeded — Spotify is open on Library",
    "action_type": "wait",
    "phase_complete": true,
    "goal_complete": false
  }
}
```

#### Example 4: Loading Screen — Wait
```json
{
  "input": {
    "goal": "Search for restaurants nearby",
    "phase": "View search results",
    "screen": "Google Maps | Search bar shows 'restaurants' | Spinner visible in results area | No results loaded yet"
  },
  "output": {
    "thinking": "The search was submitted but results are still loading — spinner is visible. I should wait for results to load before interacting.",
    "evaluation": "Previous type+enter succeeded — search query submitted",
    "action_type": "wait",
    "phase_complete": false,
    "goal_complete": false
  }
}
```

### How to Integrate Examples

Place examples **AFTER** the output schema and **BEFORE** any late rules. This puts them in the recency zone where they have maximum influence on generation:

```
[Output Format Schema]
[Few-Shot Examples]
[End of system prompt]
```

---

## 11. Aura-Specific Diagnosis & Recommendations

### Problem 1: Dual Parallel Systems

**Finding:** Two execution paths exist:
- `reactive_step.py` (newer) — reactive per-screen executor
- `reasoning.py` (older) — also does "given screen, pick one action"

Two planning paths exist:
- `skeleton_planning.py` (newer) — 2-4 phase decomposition
- `planning.py` (older) — 11-step verbose decomposition

**Recommendation:** If `reactive_step.py` and `skeleton_planning.py` are the active path, **deprecate** `reasoning.py` and `planning.py`. Dead code = dead weight. If they're still used in some code paths, consolidate into one path. Running two parallel systems means two systems to maintain, two systems that can drift, and confusion about which rules matter.

### Problem 2: Rule Ordering and Numbering

**Finding:** Rules are numbered 1-40 but non-sequential: 35 → 37 → 36 → 38 → 40 → 39. Rules 36-40 appear AFTER the output format section.

**Recommendation:** 
- Renumber sequentially
- Move ALL rules BEFORE the output format section
- Or better: eliminate numbered rules entirely and use **categorized sections** (see rewrite plan below)

### Problem 3: Redundancy

**Finding:** Autocomplete handling appears in 3 places:
1. MANDATORY GATE section (a)
2. Rule 40 (~200 words)
3. App knowledge in STEP 1 (Gmail compose example)

**Recommendation:** One location. The MANDATORY GATE is the right place. Remove the duplicate in Rule 40 entirely. The STEP 1 example should reference the gate, not repeat the logic.

### Problem 4: Prompt is Too Long for Its Job

**Finding:** `reactive_step.py` is ~18K chars (~5,500 tokens). It's called 5-15x per task. Token cost dominates at 80%.

**Recommendation:** Target **~8K chars (~2,500 tokens)** — a 55% reduction. Achievable via:
- Consolidate grounding rules into `vision.py` (saves ~1,200 chars)
- Remove Rule 40 duplicate (saves ~800 chars)
- Compress verbose rules to 2-line versions (saves ~3,000 chars)
- Move app-specific knowledge to dynamic injection (saves ~1,000 chars)
- Remove `screen_context` output field and explanation (saves ~500 chars)

### Problem 5: classification.py Has 90% Duplication

**Finding:** Two near-identical intent parsing prompts exist in `classification.py`.

**Recommendation:** Single template with a boolean flag for "has conversation context" that conditionally includes the context block.

### Problem 6: vision.py Repeats VISUAL TRUST Block

**Finding:** The same VISUAL TRUST rule is copy-pasted verbatim across all 5 prompt types in `vision.py`.

**Recommendation:** Extract to a shared constant: `VISUAL_TRUST_RULES = "..."` and interpolate.

### Problem 7: personality.py Hardcoded User Name

**Finding:** `USER_NAME = "Dinesh kumar"` is hardcoded.

**Recommendation:** Move to `config/settings.py` or accept as parameter.

### Problem 8: screen_reader.py Truncates at 1000 chars

**Finding:** UI elements are truncated at an arbitrary 1000-character limit, which can cut mid-element.

**Recommendation:** Truncate at element boundaries, not character boundaries.

---

## 12. Concrete Rewrite Plan for reactive_step.py

### Target: ~8K chars, ~2,500 tokens, structured like production systems

```python
REACTIVE_STEP_SYSTEM = """
You are a mobile UI automation agent. You observe the current screen and execute 
ONE action per turn to progress toward the user's goal.

━━━ INPUTS YOU RECEIVE ━━━
- GOAL: The user's overall objective
- PHASE: Current sub-goal from the planner
- SCREEN: Screenshot + UI element tree + keyboard state
- HISTORY: Actions taken so far + last failure (if any)
- PREVIOUS ACTION: What was attempted last turn

━━━ THINKING PROTOCOL ━━━
Before outputting JSON, reason through:
1. EVALUATE: Did the previous action succeed? (evidence from screenshot)
2. GATE CHECK: Autocomplete dropdown visible? Permission dialog? Keyboard blocking target?
   → If any: resolve it NOW. This IS the action.
3. LOCATE: Find the element matching the next required action.
   → Visible? Act on it. Not visible? Scroll to reveal. Wrong screen? Navigate.
4. ACT: Pick the single most efficient action.

━━━ CRITICAL RULES ━━━
- ONE action per turn. Never plan ahead.
- Ground every decision in the CURRENT screenshot, not assumptions.
- If already at the destination the phase describes, set phase_complete: true.
- open_app to launch apps. Never tap app icons.
- After typing in a multi-field form: next action must be tap on the next field.
- Autocomplete/suggestion dropdown visible = BLOCKING. Tap the best-match row NOW.
  Do NOT proceed to other fields until the suggestion is resolved.
- Keyboard visible + target in lower 40% of screen = dismiss_keyboard first.
- Loading/spinner visible = wait. Do not tap loading content.
- 3+ consecutive scrolls without progress = change strategy (search, go back, navigate differently).
- Toggle/binary controls: read visual state FIRST. If already correct, do not tap.

━━━ ACTIONS ━━━
tap(target)              — tap element by label/description
type(text, field_hint)   — type text into the focused/specified field
scroll(direction)        — scroll up or down
swipe(direction)         — swipe left or right (carousels, dismiss)
open_app(target)         — launch app by package name or name
press_key(key)           — press a key (enter, back)
dismiss_keyboard         — hide the on-screen keyboard  
back                     — navigate back
wait                     — do nothing this turn

{%- if app_rules %}

━━━ APP-SPECIFIC KNOWLEDGE ━━━
{{ app_rules }}
{%- endif %}

━━━ OUTPUT FORMAT ━━━
{
  "thinking": "2-4 sentences: what I see, what's needed, why this action",
  "evaluation": "Previous action: succeeded|failed — [screenshot evidence]",
  "memory": "Key facts accumulated so far (fields filled, items found, pages visited)",
  "action_type": "tap",
  "target": "element label or text to type",
  "field_hint": "field label for type actions, empty otherwise",
  "phase_complete": false,
  "goal_complete": false,
  "should_screen_change": true
}

━━━ EXAMPLES ━━━

INPUT: goal="email dinesh about meeting" | phase="compose email" | screen="Gmail compose, To field has 'dinesh' typed, autocomplete showing 'Dinesh kumar C dinesh@gmail.com', KEYBOARD: Visible"
OUTPUT:
{
  "thinking": "To field shows 'dinesh' with autocomplete dropdown. Recipient not confirmed until I tap the suggestion. Must resolve this before moving to Subject.",
  "evaluation": "Previous type succeeded — 'dinesh' visible in To field",
  "memory": "Composing email to dinesh. To field typed, awaiting autocomplete confirmation.",
  "action_type": "tap",
  "target": "Dinesh kumar C",
  "field_hint": "",
  "phase_complete": false,
  "goal_complete": false,
  "should_screen_change": false
}

INPUT: goal="play liked songs on Spotify" | phase="navigate to Library" | screen="Spotify, Library tab highlighted, playlists visible"
OUTPUT:
{
  "thinking": "Library tab is already selected and playlists are visible. Already at destination.",
  "evaluation": "Previous open_app succeeded — Spotify Library is showing",
  "memory": "Spotify Library open. Liked Songs playlist visible in list.",
  "action_type": "wait",
  "target": "",
  "field_hint": "",
  "phase_complete": true,
  "goal_complete": false,
  "should_screen_change": false
}

INPUT: goal="send whatsapp to mum" | phase="type and send message" | screen="WhatsApp chat with Mum, message input at bottom, KEYBOARD: Hidden"
OUTPUT:
{
  "thinking": "Chat with Mum is open. Message input field visible at bottom. Keyboard is hidden so I need to tap the input field to focus it before typing.",
  "evaluation": "Previous navigation to Mum's chat succeeded — chat screen showing",
  "memory": "Opened WhatsApp, found Mum's chat. Ready to type message.",
  "action_type": "tap",
  "target": "Message input",
  "field_hint": "",
  "phase_complete": false,
  "goal_complete": false,
  "should_screen_change": false
}
"""
```

### What Changed

| Aspect | Before | After |
|---|---|---|
| System prompt size | ~18K chars, ~5,500 tokens | ~4.5K chars, ~1,400 tokens |
| Rules | 37+ numbered, non-sequential | ~10 bullet points, categorized |
| Examples | 1 (output format only) | 3 diverse input/output pairs |
| Grounding rules | In planner prompt | Moved to vision.py |
| App knowledge | Hardcoded in STEP 1 | Dynamic injection slot |
| Output fields | 12 | 9 |
| Autocomplete handling | 3 locations | 1 location (Critical Rules) |
| Late rules after output | Rules 36-40 | Nothing after examples |

### Estimated Token Savings per Task

| Scenario | Before | After | Savings |
|---|---|---|---|
| Simple task (5 calls) | 27,500 tokens | 7,000 tokens | **75%** |
| Complex task (15 calls) | 82,500 tokens | 21,000 tokens | **75%** |
| Mixed average (8 calls) | 44,000 tokens | 11,200 tokens | **75%** |

### Migration Strategy

1. **Phase 1:** Create the new prompt alongside the old one. A/B test on 10 representative tasks.
2. **Phase 2:** Move grounding rules to `vision.py`. Test vision accuracy separately.
3. **Phase 3:** Implement dynamic rule injection based on screen context.
4. **Phase 4:** Add `memory` field to output and wire it through the coordinator for cross-turn persistence.
5. **Phase 5:** Deprecate `reasoning.py` and `planning.py` if not in active use.

---

## 13. Prompt Checklist — Pre-Ship Review

Before shipping any agent prompt to production, verify:

### Structure
- [ ] Identity section is ≤ 2 sentences
- [ ] Critical rules are ≤ 10 items
- [ ] Rules are BEFORE the output format, not after
- [ ] No rule appears in more than one location
- [ ] Rules are numbered sequentially (or better: use categories, not numbers)
- [ ] Few-shot examples are present (≥ 2, ideally 3-4)
- [ ] Examples cover the most common failure modes, not happy paths

### Token Efficiency
- [ ] System prompt is ≤ 3,000 tokens for per-turn prompts
- [ ] Static content is in system message (for caching)
- [ ] Dynamic content is in user message
- [ ] No prose that can be replaced with a 2-line bullet point
- [ ] No grounding rules in the planner prompt (those go in the grounder)
- [ ] App-specific knowledge is dynamically injected, not hardcoded

### Output Format
- [ ] ≤ 10 output fields
- [ ] No redundant fields (two fields for the same concept)
- [ ] No output field that just summarizes an input field
- [ ] Every field has a clear consumer (who reads it and what decision it drives)
- [ ] Output example is shown immediately after schema

### Reasoning
- [ ] CoT is structured (field-based), not free-form prose
- [ ] Self-evaluation of previous action is a required field
- [ ] Memory/context accumulation is supported across turns
- [ ] Escalation path exists for irrecoverable situations

### Separation of Concerns
- [ ] Planning prompt ≠ execution prompt ≠ grounding prompt
- [ ] Each prompt has exactly one job
- [ ] No prompt duplicates rules from another prompt
- [ ] Loop detection and retry logic are in the orchestrator, not the prompt

---

## Appendix A: Key Source References

| Source | Key Takeaway | URL/Paper |
|---|---|---|
| Anthropic Context Engineering Blog (2025) | "Context engineering > prompt engineering" — curate minimal high-signal tokens | anthropic.com blog |
| Anthropic Claude Documentation | XML tags as cognitive containers; few-shot > rules | docs.anthropic.com |
| browser-use (GitHub) | Structured output: thinking + evaluation + memory + action | github.com/browser-use |
| UI-TARS (ByteDance) | 2-sentence system prompt + Thought/Action output = SOTA | arxiv |
| SeeAct-V | Separate planning from visual grounding | arxiv |
| AppAgent (Tencent) | RAG-based app knowledge retrieval | arxiv |
| AndroidWorld (Google) | Screenshot + UI tree hybrid, 116-task benchmark | ICLR 2025 |
| CogAgent (THUDM) | Dual-resolution vision encoder for GUI tasks | arxiv |
| AgentCPM-GUI | Compact action space for on-device efficiency | arxiv |
| OpenAI Agents SDK | Dynamic instructions, agents-as-tools, MCP integration | github.com/openai |

## Appendix B: Package Name Registry for open_app

Move this from Rule 39 to a data file:

```python
# config/app_packages.py
APP_PACKAGES = {
    "whatsapp": "com.whatsapp",
    "instagram": "com.instagram.android",
    "spotify": "com.spotify.music",
    "youtube": "com.google.android.youtube",
    "gmail": "com.google.android.gm",
    "chrome": "com.android.chrome",
    "maps": "com.google.android.apps.maps",
    "settings": "com.android.settings",
    "camera": "com.android.camera2",
    "apple_music": "com.apple.android.music",
}
```

This removes ~200 tokens from the system prompt and makes the registry maintainable.

## Appendix C: Dynamic Rule Injection Template

```python
# prompts/dynamic_rules.py

KEYBOARD_RULES = """
KEYBOARD BLOCKING: Keyboard covers lower 40% of screen. 
Element with top-Y > 60% of screen height is behind keyboard → dismiss_keyboard first."""

AUTOCOMPLETE_RULES = """
AUTOCOMPLETE VISIBLE: Input field has suggestion dropdown. 
Tap the best-matching suggestion row NOW. Field is not confirmed until a row is tapped.
Do NOT proceed to other fields."""

LOADING_RULES = """
LOADING STATE: Spinner/progress visible. Do not tap loading content. Action: wait."""

MEDIA_RULES = """
MEDIA PLAYBACK: Tapping Play ≠ goal complete. Verify playback active (Pause button visible, 
progress bar moving) before setting goal_complete: true."""

NAV_APP_RULES = """
NAVIGATION APP: Search bar = DESTINATION (not starting point). 
Type destination first. Starting point defaults to current location."""

def get_contextual_rules(screen_context: str, phase: str = "") -> str:
    """Return only the rules relevant to the current screen state."""
    rules = []
    ctx = screen_context.lower()
    
    if "keyboard: visible" in ctx:
        rules.append(KEYBOARD_RULES)
    if any(w in ctx for w in ["autocomplete", "suggestion", "dropdown"]):
        rules.append(AUTOCOMPLETE_RULES)
    if any(w in ctx for w in ["loading", "spinner", "buffering"]):
        rules.append(LOADING_RULES)
    if any(w in ctx for w in ["play", "pause", "music", "spotify", "youtube"]):
        rules.append(MEDIA_RULES)
    if any(w in ctx for w in ["maps", "waze", "navigation", "directions"]):
        rules.append(NAV_APP_RULES)
    
    return "\n".join(rules)
```
