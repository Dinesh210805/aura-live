# Building a Truly General Mobile Agent

**Core Philosophy:** With perception (eyes) and action (hands), any task becomes possible if the reasoning layer is sufficiently intelligent and adaptive.

---

## The Fundamental Insight

```
Specific Agent:          General Agent:
┌──────────────┐        ┌──────────────┐
│ IF task=X    │        │              │
│   DO steps[] │        │   Observe    │
│ ELIF task=Y  │   →    │      ↓       │
│   DO steps[] │        │    Think     │
│ ELSE error   │        │      ↓       │
└──────────────┘        │     Act      │
                        │      ↓       │
Hardcoded              │   Verify     │
                        │      ↓       │
                        │   Repeat     │
                        └──────────────┘
                        Reasoning-based
```

**You're right:** If the agent can SEE any screen and PERFORM any action, the only limit is its ability to **reason** about what to do next.

---

## Current Limitations

### What Makes AURA Specific (Not General)

| Component | Current Approach | Limitation |
|-----------|------------------|------------|
| **Intent Classification** | Pre-defined action types | Can't handle "unknown" tasks |
| **Planning** | Template-based sequences | Fails on unfamiliar app UIs |
| **Navigation** | UI tree text matching | Relies on exact element labels |
| **Success Criteria** | Hardcoded per action | Can't verify arbitrary goals |
| **Error Recovery** | Fixed retry ladder | No learning from mistakes |
| **App Knowledge** | Adapters for specific apps | Doesn't generalize to new apps |

### The Core Problem: **Brittle Reasoning**

Current flow:
```python
if intent.action == "send_message":
    plan = [open_whatsapp, find_contact, type_message, tap_send]
elif intent.action == "book_cab":
    plan = [open_uber, enter_destination, select_car, confirm]
else:
    return "I don't know how to do that"
```

This **doesn't scale** to infinite tasks. We need **emergent behavior**, not programmed sequences.

---

## The General Agent Architecture

### Principle 1: Visual Reasoning Over Text Matching

**Current:** Look for UI element with text="Send"
**General:** "What button on this screen would send a message?"

```python
# OLD: Brittle text matching
element = find_element(ui_tree, "Send")  # Fails if label is "Share" or icon-only

# NEW: Visual reasoning
prompt = f"""
Looking at this screen, I need to send the message I just typed.
Which UI element should I tap?

Analyze:
- Buttons in the message composition area
- Icons that indicate sending (arrows, paper planes)
- Position (usually bottom-right in messaging apps)
- Color (often blue or green for action buttons)

Return: Coordinates and confidence score.
"""
target = vlm.locate_element(screenshot, prompt)
```

**Key:** The VLM uses **visual understanding**, not hardcoded rules.

---

### Principle 2: Goal-Oriented Planning (Not Action Sequences)

**Current:** Pre-planned action sequences
**General:** Work backwards from goal state

```python
class GeneralPlanner:
    async def plan_to_goal(self, current_state: PerceptionBundle, goal: str) -> Plan:
        """
        Generate plan by reasoning about the goal, not matching templates.
        
        Uses: ReAct (Reasoning + Acting) pattern
        """
        
        plan = []
        max_iterations = 20
        
        for i in range(max_iterations):
            # Think: What's needed to achieve the goal?
            thought = await self.llm.reason(
                current_state=self.describe_screen(current_state),
                goal=goal,
                actions_taken=plan,
                prompt=GENERAL_REASONING_PROMPT
            )
            
            # If goal achieved, done
            if thought.goal_achieved:
                break
            
            # Decide next action based on reasoning
            next_action = thought.next_action
            
            # Act
            result = await self.execute_action(next_action)
            plan.append(result)
            
            # Observe new state
            current_state = await self.perceive()
        
        return plan
```

**GENERAL_REASONING_PROMPT:**
```
GOAL: {goal}

CURRENT SCREEN STATE:
{screen_description}

ACTIONS TAKEN SO FAR:
{action_history}

REASONING FRAMEWORK:
1. Where am I now? (Current app/screen)
2. Where do I need to be? (Target state for goal)
3. What's the gap? (Missing steps)
4. What's the NEXT single action to close the gap?

AVAILABLE ACTION PRIMITIVES:
- tap(x, y) - Tap at coordinates
- swipe(x1, y1, x2, y2) - Swipe gesture
- type(text) - Enter text
- scroll(direction) - Scroll in direction
- open_app(name) - Launch app
- back() - Go back
- wait(seconds) - Wait

OUTPUT JSON:
{
  "reasoning": "I'm in WhatsApp home. Goal is to send message to John. Need to: 1) Search for John, 2) Open chat, 3) Type message, 4) Send. NEXT: Tap search bar at top.",
  "next_action": {"action": "tap", "target": "search bar", "x": 0.5, "y": 0.1},
  "goal_achieved": false,
  "estimated_remaining_steps": 4,
  "confidence": 0.9
}
```

---

### Principle 3: Self-Verification (Not Hardcoded Success Criteria)

**Current:** Check if specific element appeared/disappeared
**General:** "Did I achieve the goal state?"

```python
class GeneralValidator:
    async def verify_goal(
        self, 
        goal: str, 
        before: PerceptionBundle, 
        after: PerceptionBundle
    ) -> ValidationResult:
        """Verify goal achievement using visual + semantic understanding."""
        
        prompt = f"""
GOAL: {goal}

SCREEN BEFORE ACTION:
{self.describe_screen(before)}

SCREEN AFTER ACTION:
{self.describe_screen(after)}

QUESTION: Was the goal achieved?

REASONING:
1. What changed on screen?
2. Do these changes indicate goal completion?
3. Are there error messages or unexpected states?
4. What evidence confirms/contradicts success?

OUTPUT JSON:
{{
  "goal_achieved": true/false,
  "confidence": 0.0-1.0,
  "reasoning": "explanation",
  "evidence": ["change1", "change2"],
  "next_action_if_failed": "suggestion"
}}
"""
        
        return await self.vlm.analyze(
            images=[before.screenshot, after.screenshot],
            prompt=prompt
        )
```

---

### Principle 4: Adaptive Error Recovery (Not Fixed Retry Ladder)

**Current:** Same action → Alternate selector → Scroll → Vision → Abort
**General:** "Why did this fail? How should I adjust?"

```python
class AdaptiveRecovery:
    async def recover_from_failure(
        self,
        failed_action: Action,
        error_state: PerceptionBundle,
        failure_reason: str,
        attempt_history: List[Action]
    ) -> RecoveryStrategy:
        """
        Reason about failure and generate recovery strategy.
        
        Uses: Reflexion pattern (self-reflection on failures)
        """
        
        prompt = f"""
TASK FAILURE ANALYSIS:

INTENDED ACTION: {failed_action}
ERROR: {failure_reason}
ATTEMPTS SO FAR: {len(attempt_history)}

CURRENT SCREEN STATE:
{self.describe_screen(error_state)}

PREVIOUS ATTEMPTS:
{self.format_attempts(attempt_history)}

ANALYZE:
1. Why did this fail? (Element not found? Wrong screen? Permission denied?)
2. What's different from expected? (UI changed? App updated? Network issue?)
3. Is the goal still achievable from here?
4. What alternative approach should we try?

RECOVERY OPTIONS:
- retry_same: Try exact same action again (if transient failure)
- adjust_target: Try different element/coordinates
- alternative_path: Different sequence to same goal
- backtrack: Go back and try different route
- escalate_permissions: Request user permission
- abort: Goal not achievable

OUTPUT JSON:
{{
  "failure_diagnosis": "Element 'Send' not found because UI language is not English",
  "recovery_strategy": "adjust_target",
  "recovery_action": {{"action": "tap", "target": "blue icon bottom-right"}},
  "reasoning": "The send button is present but has different label/is icon-only",
  "confidence": 0.8,
  "should_abort": false
}}
"""
        
        return await self.llm.analyze(prompt)
```

---

### Principle 5: Zero-Shot App Understanding

**Current:** Need adapter for each app
**General:** Understand any app through visual reasoning

```python
class UniversalAppAdapter:
    """One adapter to rule them all."""
    
    async def understand_app(self, bundle: PerceptionBundle) -> AppUnderstanding:
        """Figure out what app this is and how it works."""
        
        prompt = f"""
Analyze this mobile app screen:

[Screenshot provided]

IDENTIFY:
1. App name/type (from UI elements, branding, layout patterns)
2. Current screen/section (home, settings, detail view, etc.)
3. Primary action areas (top bar, bottom nav, floating buttons)
4. Content type (messages, posts, products, videos, etc.)
5. Navigation patterns (tabs, drawer, back button, gestures)

INFER CAPABILITIES:
- Can I search? Where?
- Can I create/compose? How?
- Can I interact with items? What actions?
- Are there filters/settings? Where?

OUTPUT JSON:
{{
  "app_type": "messaging",
  "app_name": "WhatsApp",
  "current_screen": "chat_list",
  "key_ui_elements": {{
    "search": {{"type": "icon", "location": "top-right", "x": 0.9, "y": 0.1}},
    "new_chat": {{"type": "fab", "location": "bottom-right", "x": 0.9, "y": 0.9}},
    "navigation": {{"type": "tabs", "location": "top"}}
  }},
  "typical_workflows": [
    "search_and_message",
    "open_chat_from_list",
    "view_status"
  ]
}}
"""
        
        return await self.vlm.analyze_screen(bundle.screenshot, prompt)
    
    async def find_functionality(
        self, 
        bundle: PerceptionBundle, 
        desired_action: str
    ) -> ActionPlan:
        """Find how to perform an action in ANY app."""
        
        prompt = f"""
USER WANTS TO: {desired_action}

CURRENT APP SCREEN:
{self.describe_screen(bundle)}

TASK: Figure out how to accomplish this action in THIS specific app.

REASONING:
1. Is this action possible in this app?
2. What UI elements would enable this? (buttons, menus, gestures)
3. Do I need to navigate to a different screen first?
4. What's the typical UX pattern for this action?

EXAMPLES OF REASONING:
- "To share content": Look for share icon (usually three dots connected or arrow)
- "To delete item": Long-press usually shows context menu with delete
- "To search": Top bar usually has search icon (magnifying glass)
- "To go back": Back button top-left or system back gesture

OUTPUT:
{{
  "action_possible": true,
  "confidence": 0.85,
  "method": "tap_icon",
  "target_element": {{"x": 0.9, "y": 0.1, "description": "share icon"}},
  "alternative_methods": ["long_press_item", "menu_three_dots"],
  "reasoning": "Share icon visible in top-right corner, standard Android pattern"
}}
"""
        
        return await self.vlm.analyze(bundle.screenshot, prompt)
```

---

## The ReAct Loop: Think → Act → Observe

```python
class GeneralAgent:
    """
    A general-purpose mobile automation agent.
    
    Handles ANY task through reasoning, not pre-programming.
    """
    
    async def execute_task(self, goal: str) -> TaskResult:
        """
        Execute arbitrary task using ReAct (Reasoning + Acting) loop.
        
        Example goals:
        - "Book cheapest cab to airport"
        - "Find and share the funniest meme in my gallery"
        - "Order pizza with extra cheese and send ETA to mom"
        - "Archive all Instagram posts from last year"
        """
        
        max_steps = 50
        history = []
        
        for step in range(max_steps):
            # 1. OBSERVE: Get current state
            perception = await self.perception_controller.request_perception(
                intent={"action": "observe", "goal": goal},
                reason=f"Step {step}: Observing for goal: {goal}"
            )
            
            # 2. THINK: Reason about what to do next
            thought = await self.reason(
                goal=goal,
                current_state=perception,
                history=history
            )
            
            # Check if goal achieved
            if thought.goal_achieved:
                logger.info(f"✅ Goal achieved in {step} steps!")
                return TaskResult(success=True, steps=history)
            
            # Check if stuck/impossible
            if thought.should_abort:
                logger.warning(f"⚠️ Aborting: {thought.abort_reason}")
                return TaskResult(success=False, reason=thought.abort_reason)
            
            # 3. ACT: Execute next action
            action = thought.next_action
            result = await self.executor.execute_action(action)
            
            # 4. VERIFY: Did action succeed?
            verification = await self.verify_action(
                action=action,
                before=perception,
                after=await self.perception_controller.request_perception(...)
            )
            
            # 5. LEARN: Update history and adapt
            history.append({
                "step": step,
                "thought": thought,
                "action": action,
                "result": result,
                "verification": verification
            })
            
            # If action failed, reason about recovery
            if not verification.success:
                recovery = await self.adaptive_recovery.recover_from_failure(
                    failed_action=action,
                    error_state=verification.after_state,
                    failure_reason=verification.reason,
                    attempt_history=history
                )
                
                if recovery.should_abort:
                    return TaskResult(success=False, reason=recovery.abort_reason)
                
                # Continue with recovery action
                continue
        
        # Max steps reached
        return TaskResult(success=False, reason="Max steps exceeded")
    
    async def reason(
        self,
        goal: str,
        current_state: PerceptionBundle,
        history: List[Dict]
    ) -> Thought:
        """
        Core reasoning function.
        
        This is where general intelligence emerges.
        """
        
        # Build rich context
        context = self._build_context(goal, current_state, history)
        
        # Use Chain-of-Thought prompting
        prompt = f"""
You are a mobile automation agent with vision and action capabilities.

GOAL: {goal}

CURRENT SCREEN:
{self._describe_screen(current_state)}

ACTIONS TAKEN SO FAR:
{self._format_history(history)}

THINK STEP BY STEP:

1. SITUATION ASSESSMENT:
   - Where am I? (app, screen, context)
   - What can I see? (UI elements, content, state)
   - What have I done? (summary of actions)

2. GOAL ANALYSIS:
   - Is goal achieved? (check against current state)
   - If not, what's the gap?
   - What's the next logical step?

3. ACTION PLANNING:
   - What action closes the gap?
   - What could go wrong?
   - Are there prerequisites?

4. CONFIDENCE CHECK:
   - Am I sure this will work?
   - Do I need more information?
   - Should I try alternative approach?

OUTPUT YOUR REASONING AND DECISION:
{{
  "situation": "I'm in WhatsApp chat list, goal is to message John",
  "goal_achieved": false,
  "reasoning": "Need to find John's chat. I see search icon top-right. Will tap it, then type 'John' to find contact.",
  "next_action": {{
    "action": "tap",
    "target": "search icon",
    "coordinates": {{"x": 0.9, "y": 0.1}},
    "description": "Tap search icon to find contact"
  }},
  "confidence": 0.9,
  "estimated_remaining_steps": 4,
  "alternatives": ["scroll to find John in list", "use voice search"],
  "should_abort": false
}}
"""
        
        return await self.llm.generate_structured(prompt, Thought)
```

---

## Handling Edge Cases Generically

### 1. Permissions & Dialogs

```python
async def handle_unexpected_screen(self, perception: PerceptionBundle) -> Action:
    """Handle popups, permissions, errors generically."""
    
    prompt = f"""
An unexpected screen/dialog appeared:

{self.describe_screen(perception)}

IDENTIFY:
- Type: permission request, error, confirmation, ad, loading
- Required action: allow/deny, ok/cancel, dismiss, wait
- Urgency: blocking, can ignore, informational

DECISION:
- If permission needed for goal: allow
- If error blocks goal: report failure
- If informational/ad: dismiss and continue
- If loading: wait

OUTPUT:
{{
  "screen_type": "permission_request",
  "content": "WhatsApp wants to access your contacts",
  "action": "allow",
  "reasoning": "Need contacts to find user for messaging goal"
}}
"""
```

### 2. Unknown Apps

```python
async def explore_unknown_app(self, app_name: str, goal: str) -> AppStrategy:
    """Figure out how an unfamiliar app works."""
    
    # Take screenshots of different screens
    exploration_results = []
    
    # 1. Home screen
    home = await self.perceive()
    exploration_results.append(home)
    
    # 2. Tap around to see what happens
    for tap_location in [(0.5, 0.3), (0.5, 0.7), (0.9, 0.1)]:
        await self.tap(*tap_location)
        await asyncio.sleep(1)
        state = await self.perceive()
        exploration_results.append(state)
        await self.back()
    
    # 3. Analyze patterns
    prompt = f"""
I explored an unfamiliar app "{app_name}" to accomplish: {goal}

SCREENS OBSERVED:
{self.describe_exploration(exploration_results)}

ANALYZE:
1. App structure (navigation, sections, features)
2. How to accomplish goal (which screens, what actions)
3. Likely success rate

STRATEGY:
{{
  "app_type": "food_delivery",
  "goal_feasible": true,
  "recommended_flow": [
    "tap search",
    "type 'pizza'",
    "select first result",
    "add to cart",
    "checkout"
  ],
  "confidence": 0.7
}}
"""
```

### 3. Ambiguous Goals

```python
async def clarify_ambiguous_goal(self, goal: str) -> str:
    """Break down vague goals into specific actions."""
    
    prompt = f"""
USER GOAL: {goal}

This goal is underspecified. Infer reasonable defaults:

EXAMPLES:
- "Order food" → "Order pizza delivery from nearest restaurant"
- "Message friend" → "Send text message to most recent contact"
- "Play music" → "Play random songs from liked tracks"

INFER:
1. Missing details (what, who, how much, when)
2. Most likely user intent
3. Safe defaults

CLARIFIED GOAL: 
{{
  "original": "{goal}",
  "clarified": "specific actionable goal",
  "assumptions": ["assumption1", "assumption2"],
  "ask_user_if_wrong": ["critical choice1", "critical choice2"]
}}
"""
```

---

## The Vision-First Architecture

### Core Principle: **Vision is Ground Truth**

```
Current:
UI Tree → Text Match → Tap
(Fails if text changes)

General:
Screenshot → Visual Understanding → Tap
(Works regardless of language, icons, styling)
```

### Vision-Language Model as Primary Intelligence

```python
class VisionFirstAgent:
    """
    All decisions made through visual reasoning, not programmed rules.
    """
    
    async def execute_with_vision(self, instruction: str):
        """
        Example: "Tap the blue send button"
        
        No hardcoded element matching - pure visual reasoning.
        """
        
        screenshot = await self.capture_screen()
        
        prompt = f"""
INSTRUCTION: {instruction}

VISUAL ANALYSIS REQUIRED:
1. Locate: Find the button described
2. Verify: Confirm it matches description
3. Coordinate: Return tap coordinates

Screenshot provided. Analyze and return:
{{
  "found": true,
  "element_description": "Blue circular button with paper plane icon",
  "x_percent": 92,
  "y_percent": 87,
  "confidence": 0.95,
  "reasoning": "Located bottom-right corner, blue color (#2196F3), contains white send icon"
}}
"""
        
        result = await self.vlm.analyze(screenshot, prompt)
        
        if result.found and result.confidence > 0.8:
            x = int(result.x_percent / 100 * screen_width)
            y = int(result.y_percent / 100 * screen_height)
            await self.tap(x, y)
```

---

## Learning from Experience

### Self-Supervised Learning Pipeline

```python
class ExperienceMemory:
    """
    Store successful and failed executions for learning.
    """
    
    def record_success(
        self,
        goal: str,
        app_context: str,
        action_sequence: List[Action],
        final_state: PerceptionBundle
    ):
        """Store successful task completion."""
        
        self.db.insert({
            "type": "success",
            "goal": goal,
            "app": app_context,
            "sequence": action_sequence,
            "timestamp": time.time()
        })
    
    def record_failure(
        self,
        goal: str,
        app_context: str,
        failed_action: Action,
        error_state: PerceptionBundle,
        reason: str
    ):
        """Store failure for future avoidance."""
        
        self.db.insert({
            "type": "failure",
            "goal": goal,
            "app": app_context,
            "failed_action": failed_action,
            "reason": reason,
            "timestamp": time.time()
        })
    
    async def learn_from_history(self, new_goal: str) -> List[Insight]:
        """Query past experiences for similar tasks."""
        
        similar_tasks = self.db.query(similarity_search(new_goal))
        
        prompt = f"""
NEW TASK: {new_goal}

SIMILAR PAST EXPERIENCES:
{self.format_experiences(similar_tasks)}

EXTRACT INSIGHTS:
1. What worked before?
2. What failed and why?
3. What patterns can be reused?
4. What should be avoided?

INSIGHTS:
[
  {{
    "insight": "In messaging apps, search is always top-right icon",
    "confidence": 0.9,
    "applies_to": ["whatsapp", "telegram", "messenger"]
  }},
  ...
]
"""
        
        return await self.llm.extract_insights(prompt)
```

---

## Handling "Anything" - Complete Architecture

```python
class UniversalMobileAgent:
    """
    The complete general-purpose agent.
    
    Can handle ANY task through:
    1. Visual reasoning (not text matching)
    2. Goal-oriented planning (not templates)
    3. Self-verification (not hardcoded criteria)
    4. Adaptive recovery (not fixed retries)
    5. Learning (not static knowledge)
    """
    
    def __init__(self):
        self.vlm = VisionLanguageModel()  # GPT-4V, Gemini Vision, Claude with vision
        self.llm = LanguageModel()  # For reasoning
        self.perception = PerceptionController()
        self.executor = GestureExecutor()
        self.memory = ExperienceMemory()
    
    async def handle_any_task(self, user_request: str) -> TaskResult:
        """
        THE UNIVERSAL ENTRY POINT
        
        Can handle:
        - "Book cheapest flight to Tokyo next month"
        - "Find all photos of my dog and create album"
        - "Order birthday cake and send surprise message"
        - "Compare prices across 3 shopping apps"
        - LITERALLY ANYTHING
        """
        
        # 1. Understand goal deeply
        goal_analysis = await self.analyze_goal(user_request)
        
        # 2. Check if we've done similar before
        past_insights = await self.memory.learn_from_history(user_request)
        
        # 3. Execute with ReAct loop
        result = await self.react_loop(
            goal=goal_analysis.clarified_goal,
            constraints=goal_analysis.constraints,
            context=goal_analysis.context,
            insights=past_insights
        )
        
        # 4. Learn from outcome
        if result.success:
            await self.memory.record_success(
                goal=user_request,
                app_context=result.apps_used,
                action_sequence=result.actions,
                final_state=result.final_state
            )
        else:
            await self.memory.record_failure(
                goal=user_request,
                app_context=result.apps_used,
                failed_action=result.failed_action,
                error_state=result.error_state,
                reason=result.failure_reason
            )
        
        return result
    
    async def react_loop(
        self,
        goal: str,
        constraints: Dict,
        context: Dict,
        insights: List[Insight]
    ) -> TaskResult:
        """The core ReAct loop for general task execution."""
        
        state = await self.perception.request_perception(...)
        history = []
        
        for step in range(100):  # Generous max steps
            # THINK: What should I do?
            thought = await self.llm.generate(
                prompt=self._build_reasoning_prompt(
                    goal=goal,
                    state=state,
                    history=history,
                    insights=insights
                ),
                schema=ThoughtSchema
            )
            
            # Goal achieved?
            if thought.goal_achieved:
                return TaskResult(success=True, ...)
            
            # Should abort?
            if thought.should_abort:
                return TaskResult(success=False, reason=thought.abort_reason)
            
            # ACT: Execute action
            action = thought.next_action
            
            # Use vision to understand action target
            if action.needs_visual_target:
                target = await self.vlm.locate_element(
                    screenshot=state.screenshot,
                    description=action.target_description
                )
                action.coordinates = target.coordinates
            
            # Execute
            exec_result = await self.executor.execute(action)
            
            # OBSERVE: Get new state
            new_state = await self.perception.request_perception(...)
            
            # VERIFY: Did it work?
            verification = await self.vlm.verify_action_success(
                goal=goal,
                action=action,
                before=state,
                after=new_state
            )
            
            # Update history
            history.append({
                "thought": thought,
                "action": action,
                "result": exec_result,
                "verification": verification
            })
            
            # ADAPT: If failed, recover
            if not verification.success:
                recovery = await self.adaptive_recovery.recover(
                    goal=goal,
                    failed_action=action,
                    current_state=new_state,
                    history=history
                )
                
                if recovery.should_abort:
                    return TaskResult(success=False, ...)
                
                # Apply recovery and continue
                action = recovery.recovery_action
            
            state = new_state
        
        return TaskResult(success=False, reason="max_steps_exceeded")
```

---

## Key Principles Summary

| Principle | Specific Agent | General Agent |
|-----------|---------------|---------------|
| **Knowledge** | Hardcoded app logic | Visual reasoning |
| **Planning** | Template sequences | Goal-oriented search |
| **Verification** | Fixed criteria | Visual comparison |
| **Recovery** | Retry ladder | Adaptive reasoning |
| **Learning** | None | Experience memory |
| **Scope** | Known apps only | Any app |

---

## What Makes It "General"?

### 1. **No App-Specific Code**
- No WhatsApp adapter, no Instagram adapter
- Every app handled through visual reasoning
- Zero assumptions about UI structure

### 2. **No Hardcoded Action Sequences**
- Plans emerge from reasoning, not templates
- Adapts to unexpected screens
- Handles app updates automatically

### 3. **Vision-First Decision Making**
- All decisions from visual analysis
- Works with any language, any styling
- Handles icon-only UIs

### 4. **Self-Correcting**
- Learns from failures
- Adapts recovery strategies
- Improves over time

### 5. **Handles Unknowns Gracefully**
- Explores unfamiliar apps
- Asks for clarification when needed
- Falls back intelligently

---

## Implementation Roadmap

### Phase 1: Vision-First Navigation (Weeks 1-3)

Replace all text-matching with visual reasoning:

```python
# OLD
element = find_element(ui_tree, "Send")

# NEW
element = vlm.locate_element(
    screenshot, 
    "button to send the message"
)
```

**Files to modify:**
- `agents/navigator.py` - Replace `find_element()` calls
- Add `services/vlm_element_locator.py`

### Phase 2: ReAct Loop (Weeks 4-6)

Implement reasoning-acting loop:

```python
# NEW
agent = UniversalMobileAgent()
result = await agent.handle_any_task(
    "Order pizza and send ETA to mom"
)
```

**New files:**
- `agents/universal_agent.py`
- `services/reasoning_engine.py`
- `services/action_verifier.py`

### Phase 3: Experience Memory (Weeks 7-8)

Add learning from past tasks:

```python
# NEW
memory = ExperienceMemory()
insights = await memory.learn_from_history(new_goal)
```

**New files:**
- `services/experience_memory.py`
- `database/task_history.db`

### Phase 4: Remove Hardcoded Logic (Weeks 9-10)

Delete app-specific adapters, replace with general reasoning.

**Files to remove:**
- `adapters/*` (all app adapters)
- Template-based planning code

---

## Success Metrics for "General" Agent

| Metric | Target |
|--------|--------|
| **Zero-shot success rate** | >60% (first try on new task) |
| **Adaptation rate** | >85% (success after exploration) |
| **App coverage** | 100% (works with ANY app) |
| **Language independence** | 100% (works in any language) |
| **Improvement over time** | >20% (from experience learning) |

---

## The Ultimate Test

**Can AURA handle these WITHOUT any pre-programming?**

1. "Find the cheapest pizza delivery option and order for 4 people"
   - Needs: Compare prices across apps, calculate portions, order

2. "Archive all Instagram posts with less than 10 likes"
   - Needs: Navigate profile, count likes, conditional archiving

3. "Forward any work emails about 'Q4 report' to my manager"
   - Needs: Read emails, classify content, forward selectively

4. "Book movie tickets for tomorrow, share plans in group chat, set reminder 1 hour before"
   - Needs: Multi-app workflow, temporal reasoning

5. "Find my dog's photos, create album, share with family WhatsApp group"
   - Needs: Image recognition, app creation, group messaging

**If the agent can handle these through reasoning alone (no specific code for any of these), it's truly general.**

---

## Conclusion: From Specific to General

```
Current AURA:
┌─────────────────────────────┐
│  Can do: 50 pre-programmed  │
│  tasks across 10 apps       │
│                             │
│  Can't do: Anything new     │
└─────────────────────────────┘

General AURA:
┌─────────────────────────────┐
│  Can do: ANYTHING            │
│  Limitation: Only reasoning  │
│  quality of VLM/LLM          │
│                             │
│  Adapts to: New apps, tasks  │
│  Improves: Through learning  │
└─────────────────────────────┘
```

**You're absolutely right:** With eyes and hands, the only limit is reasoning. Make the reasoning general enough, and AURA becomes truly universal.

---

*The path to AGI for mobile: Perception + Action + General Reasoning*
