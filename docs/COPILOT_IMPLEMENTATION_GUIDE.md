# Building General Agent Architecture with GitHub Copilot

**Goal:** Step-by-step guide to implement the General Agent Architecture using Copilot's agent mode effectively.

---

## Understanding Copilot Agent Mode

GitHub Copilot has specialized agents for different tasks:

| Agent | Purpose | When to Use |
|-------|---------|-------------|
| **Plan** | Research & outline multi-step plans | Start of each phase, architectural decisions |
| **GenerateAgent** | Write new code/features from scratch | Creating new files, implementing features |
| **ProofAgent** | Identify bugs and assumptions | After implementation, before testing |
| **FixAgent** | Apply minimal fixes to identified bugs | After ProofAgent finds issues |

---

## Phase-by-Phase Implementation Strategy

### Phase 1: Vision-First Element Locator (Weeks 1-2)

#### Step 1.1: Use Plan Agent

**Prompt to Plan Agent:**
```
I need to replace text-based UI element finding with vision-based reasoning in my mobile automation agent.

Current system:
- Uses UI tree text matching: find_element(elements, "Send")
- Fails when labels change or use icons
- Language-dependent

Target system:
- Use VLM (Vision Language Model) to locate elements visually
- Work with any language/icons
- More reliable

Files involved:
- agents/navigator.py (uses find_element)
- services/vlm.py (existing VLM service)
- utils/ui_element_finder.py (current text matching)

Create implementation plan for:
1. New VLMElementLocator service
2. Prompt templates for element location
3. Integration with Navigator agent
4. Fallback strategy (vision → UI tree)
5. Testing approach
```

**Expected Output from Plan:**
- File structure
- Implementation order
- Dependencies
- Risk areas

#### Step 1.2: Use GenerateAgent for Core Service

**Prompt to GenerateAgent:**
```
Create services/vlm_element_locator.py

Requirements:
- Class: VLMElementLocator
- Method: locate_element(screenshot_b64: str, description: str, screen_size: tuple) -> ElementLocation
- Uses VLM to find UI elements by description (not text matching)
- Returns coordinates, confidence score, reasoning
- Handles cases where element not found

Technical details:
- Use existing VLMService from services/vlm.py
- Screenshot is base64 encoded
- Screen size is (width, height) in pixels
- Return type should be dataclass or Pydantic model

Prompt engineering:
- Include screen context in VLM prompt
- Ask for percentage-based coordinates
- Request confidence score and reasoning
- Handle ambiguous descriptions

Error handling:
- Element not found
- Multiple matches (return highest confidence)
- VLM API failures
```

**What GenerateAgent Will Do:**
1. Create complete file with imports
2. Implement class structure
3. Add proper type hints
4. Include error handling
5. Add docstrings

#### Step 1.3: Use ProofAgent to Validate

**Prompt to ProofAgent:**
```
Review services/vlm_element_locator.py

Verify:
1. Does locate_element handle all edge cases?
2. Is the VLM prompt effective for element location?
3. Are coordinates properly converted from percentages to pixels?
4. Is error handling comprehensive?
5. Will this work with different screen sizes?
6. Are there race conditions or async issues?

Identify assumptions that might break in production.
```

**Expected Output:**
- List of potential bugs
- Assumptions that need validation
- Missing edge case handling

#### Step 1.4: Use FixAgent for Issues

**Prompt to FixAgent:**
```
Fix the issues identified by ProofAgent in services/vlm_element_locator.py:

1. [Issue from ProofAgent]
2. [Issue from ProofAgent]
3. [Issue from ProofAgent]

Apply minimal fixes only. Don't refactor unnecessarily.
```

#### Step 1.5: Integration with Navigator

**Prompt to GenerateAgent:**
```
Update agents/navigator.py to use VLMElementLocator as fallback when UI tree matching fails.

Current flow in _create_tap_plan():
1. Find element in UI tree
2. If not found, return empty plan (failure)

New flow:
1. Find element in UI tree
2. If not found, use VLMElementLocator with screenshot
3. If still not found, return empty plan

Changes needed:
- Import VLMElementLocator
- Modify _create_tap_plan(), _create_type_plan(), _create_messaging_plan()
- Add logging to show when vision fallback is used
- Ensure perception_bundle has screenshot

Keep existing UI tree logic, just add vision as fallback.
```

---

### Phase 2: Reasoning Engine (Weeks 3-4)

#### Step 2.1: Plan the Reasoning System

**Prompt to Plan Agent:**
```
Design a reasoning engine for general-purpose task execution using ReAct pattern.

Context:
- Current system uses predefined action sequences
- Need general reasoning to handle any task
- Must work with existing perception and execution systems

ReAct pattern:
- Observe: Get screen state
- Think: Reason about next action using LLM
- Act: Execute action
- Verify: Check if action succeeded
- Repeat until goal achieved

Requirements:
1. ReasoningEngine class that orchestrates the loop
2. Structured prompts for LLM reasoning
3. Goal state tracking
4. History/context management
5. Abort conditions (max steps, stuck detection)

Integration points:
- services/perception_controller.py (observation)
- services/gesture_executor.py (action)
- services/vlm.py (verification)
- services/llm.py (reasoning)

Create plan for implementation.
```

#### Step 2.2: Generate Core Reasoning Engine

**Prompt to GenerateAgent:**
```
Create services/reasoning_engine.py

Implement ReasoningEngine class with ReAct loop:

```python
@dataclass
class Thought:
    situation_assessment: str
    goal_achieved: bool
    reasoning: str
    next_action: Optional[Dict[str, Any]]
    confidence: float
    estimated_remaining_steps: int
    should_abort: bool
    abort_reason: Optional[str]

class ReasoningEngine:
    async def reason_next_action(
        self,
        goal: str,
        current_screen: PerceptionBundle,
        action_history: List[Dict]
    ) -> Thought:
        """
        Use LLM with Chain-of-Thought prompting to decide next action.
        
        Prompt structure:
        1. Goal description
        2. Current screen state (from perception bundle)
        3. Actions taken so far
        4. Request step-by-step reasoning
        5. Output structured Thought
        """
```

Key implementation details:
- Use services/llm.py LLMService for reasoning
- Build rich context from perception bundle
- Format action history clearly
- Parse LLM output into Thought dataclass
- Handle cases where LLM output is malformed

Prompt template should guide LLM to:
- Assess current situation
- Check if goal is achieved
- Plan next atomic action (tap, type, scroll, etc.)
- Provide confidence score
- Know when to abort
```

#### Step 2.3: Generate Verification Service

**Prompt to GenerateAgent:**
```
Create services/goal_verifier.py

Implement GoalVerifier class:

```python
@dataclass
class VerificationResult:
    goal_achieved: bool
    confidence: float
    reasoning: str
    evidence: List[str]
    next_action_suggestion: Optional[str]

class GoalVerifier:
    async def verify_goal_achievement(
        self,
        goal: str,
        before_screen: PerceptionBundle,
        after_screen: PerceptionBundle,
        action_taken: Dict[str, Any]
    ) -> VerificationResult:
        """
        Use VLM to verify if action achieved goal by comparing screens.
        
        Visual comparison approach:
        - Provide both screenshots to VLM
        - Ask: "Did this action move closer to goal?"
        - Look for evidence of progress
        - Check for error states
        """
```

Implementation:
- Use VLMService for visual comparison
- Build prompt that shows before/after
- Extract structured verification result
- Include confidence scoring
- Suggest recovery if goal not achieved
```

#### Step 2.4: Create Universal Agent

**Prompt to GenerateAgent:**
```
Create agents/universal_agent.py

Implement UniversalAgent that orchestrates ReAct loop:

```python
class UniversalAgent:
    def __init__(self):
        self.reasoning_engine = ReasoningEngine()
        self.perception = get_perception_controller()
        self.executor = get_gesture_executor()
        self.verifier = GoalVerifier()
    
    async def execute_task(self, goal: str, max_steps: int = 50) -> TaskResult:
        """
        Execute arbitrary task using ReAct loop.
        
        Loop:
        1. Observe current screen
        2. Reason about next action
        3. Execute action
        4. Verify progress
        5. Handle failures adaptively
        6. Repeat until goal achieved or should abort
        """
```

Integration with existing graph:
- Should be callable from aura_graph/core_nodes.py
- Fits into execute_node as alternative to Navigator-based planning
- Returns standard TaskState-compatible results

Error handling:
- Max steps exceeded
- Goal impossible to achieve
- Action execution failures
- VLM/LLM API failures
```

#### Step 2.5: Test with Simple Task

**Prompt to @workspace:**
```
I've implemented UniversalAgent with ReAct loop. Help me create a test script.

Test scenario:
- Goal: "Open WhatsApp and tap search"
- Should work without any app-specific code
- Use only visual reasoning and general actions

Create: tests/test_universal_agent.py

Test should:
1. Mock perception (provide fake screenshots)
2. Mock gesture executor (log actions, don't actually execute)
3. Mock LLM/VLM responses with realistic reasoning
4. Verify correct action sequence emerges
5. Check abort conditions work

Show me how to mock properly for this test.
```

---

### Phase 3: Adaptive Recovery (Weeks 5-6)

#### Step 3.1: Plan Recovery System

**Prompt to Plan Agent:**
```
Design adaptive recovery system for when actions fail.

Current system:
- Fixed retry ladder: same → alternate → scroll → vision → abort
- No reasoning about WHY failure occurred

Target system:
- Analyze failure reason
- Generate recovery strategy based on context
- Learn from failure patterns

Components needed:
1. FailureAnalyzer: Diagnoses why action failed
2. RecoveryStrategist: Generates recovery plan
3. Integration with ReAct loop

Failure types to handle:
- Element not found (moved, different label, scrolled off-screen)
- Action succeeded but goal not achieved
- Unexpected screen appeared (dialog, permission, error)
- App crashed or frozen

Create implementation plan.
```

#### Step 3.2: Implement Failure Analyzer

**Prompt to GenerateAgent:**
```
Create services/failure_analyzer.py

```python
@dataclass
class FailureDiagnosis:
    failure_type: str  # element_not_found, wrong_screen, permission_blocked, etc.
    root_cause: str
    confidence: float
    context: Dict[str, Any]
    suggested_recovery: str

class FailureAnalyzer:
    async def analyze_failure(
        self,
        intended_action: Dict[str, Any],
        current_screen: PerceptionBundle,
        error_message: Optional[str],
        attempt_history: List[Dict]
    ) -> FailureDiagnosis:
        """
        Use VLM + LLM to understand why action failed.
        
        Analysis approach:
        1. Visual: Check current screen state
        2. Contextual: Review attempt history for patterns
        3. Logical: Infer root cause
        
        Prompt should ask:
        - Is element visible but different?
        - Did screen change unexpectedly?
        - Is there an error/dialog blocking?
        - Is action impossible in this context?
        """
```

Use VLM for visual analysis, LLM for reasoning.
Include examples of common failure patterns in prompt.
```

#### Step 3.3: Implement Recovery Strategist

**Prompt to GenerateAgent:**
```
Create services/recovery_strategist.py

```python
@dataclass
class RecoveryStrategy:
    strategy_type: str  # retry_adjusted, scroll_and_retry, dismiss_dialog, backtrack
    actions: List[Dict[str, Any]]
    reasoning: str
    confidence: float
    should_abort: bool

class RecoveryStrategist:
    async def generate_recovery(
        self,
        diagnosis: FailureDiagnosis,
        goal: str,
        current_screen: PerceptionBundle,
        attempt_history: List[Dict]
    ) -> RecoveryStrategy:
        """
        Generate recovery strategy based on failure diagnosis.
        
        Strategy selection:
        - If element_not_found + visible elsewhere → adjust coordinates
        - If wrong_screen → navigate back to correct screen
        - If permission_dialog → allow/deny based on goal necessity
        - If repeated_failure → try alternative approach
        - If no viable recovery → abort gracefully
        """
```

Include reasoning for strategy choice.
Consider attempt history to avoid loops.
```

#### Step 3.4: Integrate with Universal Agent

**Prompt to GenerateAgent:**
```
Update agents/universal_agent.py to use adaptive recovery.

Current flow in execute_task():
```python
result = await self.executor.execute(action)
if not result.success:
    # Currently: just continue or abort
```

New flow:
```python
result = await self.executor.execute(action)
if not result.success:
    # Analyze failure
    diagnosis = await self.failure_analyzer.analyze_failure(...)
    
    # Generate recovery
    recovery = await self.recovery_strategist.generate_recovery(...)
    
    if recovery.should_abort:
        return TaskResult(success=False, reason=recovery.reasoning)
    
    # Execute recovery actions
    for recovery_action in recovery.actions:
        await self.executor.execute(recovery_action)
```

Add imports for FailureAnalyzer and RecoveryStrategist.
Update execute_task() method only, keep rest of file intact.
```

---

### Phase 4: Experience Memory (Weeks 7-8)

#### Step 4.1: Design Memory System

**Prompt to Plan Agent:**
```
Design experience memory system for learning from task executions.

Requirements:
1. Store successful task completions (goal, actions, outcome)
2. Store failures (what didn't work, why)
3. Query similar past experiences for new tasks
4. Extract reusable patterns/insights

Storage:
- SQLite database for persistence
- Schema: tasks table, actions table, outcomes table

Retrieval:
- Semantic search for similar goals
- Filter by app context, success/failure
- Rank by relevance

Integration:
- UniversalAgent queries before starting task
- Records outcome after completion

Create implementation plan with:
- Database schema
- ExperienceMemory class design
- Query/retrieval strategy
- Privacy considerations
```

#### Step 4.2: Create Database Schema

**Prompt to GenerateAgent:**
```
Create database/experience_schema.sql

Design schema for experience memory:

Tables:
1. tasks
   - id (primary key)
   - goal (text, user's original request)
   - goal_embedding (blob, for semantic search)
   - app_context (text, main app used)
   - success (boolean)
   - timestamp
   - execution_time_seconds

2. actions
   - id (primary key)
   - task_id (foreign key)
   - step_number (int)
   - action_type (text: tap, type, scroll, etc.)
   - action_data (json)
   - screen_before_hash (text, for deduplication)
   - result_success (boolean)

3. insights
   - id (primary key)
   - pattern (text, discovered pattern)
   - confidence (float)
   - app_context (text)
   - use_count (int, how many times applied)
   - success_rate (float)

Include indexes for fast queries.
```

#### Step 4.3: Implement Experience Memory

**Prompt to GenerateAgent:**
```
Create services/experience_memory.py

```python
class ExperienceMemory:
    def __init__(self, db_path: str = "experience.db"):
        """Initialize with SQLite database."""
    
    async def record_success(
        self,
        goal: str,
        app_context: str,
        actions: List[Dict],
        execution_time: float
    ):
        """Store successful task execution."""
    
    async def record_failure(
        self,
        goal: str,
        app_context: str,
        failed_action: Dict,
        failure_reason: str
    ):
        """Store failed task execution."""
    
    async def find_similar_tasks(
        self,
        goal: str,
        limit: int = 5
    ) -> List[TaskRecord]:
        """Find similar past tasks using semantic search."""
    
    async def extract_insights(
        self,
        similar_tasks: List[TaskRecord]
    ) -> List[Insight]:
        """Use LLM to extract patterns from similar tasks."""
```

Implementation details:
- Use sqlite3 for database
- Generate embeddings using sentence-transformers or API
- Implement semantic similarity search
- Use LLM to synthesize insights from task history
```

#### Step 4.4: Integrate Learning Loop

**Prompt to GenerateAgent:**
```
Update agents/universal_agent.py to use experience memory.

Add to __init__:
```python
self.memory = ExperienceMemory()
```

Update execute_task():

Before ReAct loop starts:
```python
# Learn from past experiences
insights = await self.memory.find_and_extract_insights(goal)
```

After task completion:
```python
# Record outcome
if result.success:
    await self.memory.record_success(
        goal=goal,
        app_context=result.apps_used,
        actions=result.actions,
        execution_time=result.execution_time
    )
else:
    await self.memory.record_failure(...)
```

Pass insights to reasoning_engine.reason_next_action() as context.
```

---

## Effective Prompting Patterns for Copilot

### Pattern 1: Incremental Implementation

**Bad:**
```
Create the entire universal agent system with all components.
```

**Good:**
```
Create services/reasoning_engine.py with just the core ReasoningEngine class and reason_next_action() method. I'll add verification and recovery in separate steps.
```

### Pattern 2: Provide Context

**Bad:**
```
Fix the bug in universal_agent.py
```

**Good:**
```
In agents/universal_agent.py, the execute_task() method doesn't handle VLM API failures. When self.verifier.verify_goal_achievement() raises an exception, the entire task aborts. Add try-catch to retry verification once, then continue with assumption of success if retry also fails.
```

### Pattern 3: Reference Existing Code

**Bad:**
```
Make the new service work with the existing system
```

**Good:**
```
The new VLMElementLocator should integrate with agents/navigator.py the same way services/vlm.py is used for visual_locate(). Check how Navigator currently calls self.vlm_service.analyze_image() and use the same pattern for element location.
```

### Pattern 4: Specify Testing Approach

**Always include:**
```
After implementation, show me:
1. How to unit test this component
2. Example input/output for the main methods
3. Common edge cases to verify
```

---

## Copilot Agent Workflow

### For Each New Feature:

```
┌─────────────────────────────────────────────┐
│ 1. Plan Agent                               │
│    → Get implementation roadmap             │
└──────────────────┬──────────────────────────┘
                   ↓
┌─────────────────────────────────────────────┐
│ 2. GenerateAgent                            │
│    → Create file structure                  │
│    → Implement core logic                   │
└──────────────────┬──────────────────────────┘
                   ↓
┌─────────────────────────────────────────────┐
│ 3. ProofAgent                               │
│    → Identify bugs and assumptions          │
└──────────────────┬──────────────────────────┘
                   ↓
┌─────────────────────────────────────────────┐
│ 4. FixAgent                                 │
│    → Apply minimal fixes                    │
└──────────────────┬──────────────────────────┘
                   ↓
┌─────────────────────────────────────────────┐
│ 5. Test & Iterate                           │
│    → Manual testing                         │
│    → Back to GenerateAgent for refinements  │
└─────────────────────────────────────────────┘
```

---

## Integration with Existing AURA System

### Where New Components Fit:

```
aura_graph/
├── core_nodes.py
│   └── execute_node()
│       ├── OLD: navigator.create_execution_plan()
│       └── NEW: universal_agent.execute_task()  ← Add here

agents/
├── navigator.py  ← Update with vision fallback
├── universal_agent.py  ← NEW
└── (keep existing agents)

services/
├── reasoning_engine.py  ← NEW
├── vlm_element_locator.py  ← NEW
├── goal_verifier.py  ← NEW
├── failure_analyzer.py  ← NEW
├── recovery_strategist.py  ← NEW
└── experience_memory.py  ← NEW
```

### Gradual Migration Strategy:

**Don't delete old system immediately. Use feature flag:**

```python
# In execute_node()
USE_UNIVERSAL_AGENT = os.getenv("AURA_USE_UNIVERSAL_AGENT", "false") == "true"

if USE_UNIVERSAL_AGENT:
    result = await universal_agent.execute_task(goal)
else:
    plan = navigator.create_execution_plan(intent, bundle)
    result = await executor.execute_plan(plan)
```

Test new system in parallel, switch over when confident.

---

## Testing Strategy with Copilot

### Test Creation Workflow:

**Prompt to GenerateAgent:**
```
Create tests/test_reasoning_engine.py

Test ReasoningEngine.reason_next_action() with mocked LLM:

Test cases:
1. Simple goal ("open WhatsApp") - should reason to tap app icon
2. Multi-step goal progress - should track state and continue
3. Goal achieved - should recognize completion
4. Stuck detection - should abort after repeated failures
5. Malformed LLM output - should handle gracefully

For each test:
- Mock LLMService to return controlled responses
- Mock PerceptionBundle with fake screen descriptions
- Assert correct Thought output
- Verify reasoning makes sense

Use pytest with fixtures for common mocks.
```

**Prompt to ProofAgent after test creation:**
```
Review tests/test_reasoning_engine.py

Check:
1. Do tests actually validate the reasoning logic?
2. Are mocks realistic (would LLM really respond this way)?
3. Are edge cases covered?
4. Will tests catch regressions?

Suggest additional test cases if coverage is insufficient.
```

---

## Debugging with Copilot

### When Things Don't Work:

**Prompt to ProofAgent:**
```
I'm getting unexpected behavior in agents/universal_agent.py

Symptom: Agent gets stuck in loop, keeps trying same action

Current execute_task() implementation at lines 45-120.

Debug questions:
1. Is action history being checked for loops?
2. Does reasoning_engine receive previous actions context?
3. Is abort condition properly evaluated?
4. Could this be a VLM caching issue?

Identify root cause and suggest minimal fix.
```

**Prompt to FixAgent after diagnosis:**
```
ProofAgent identified: Action history not passed to reasoning_engine.

Fix: In execute_task() at line 67, pass action_history to reason_next_action().

Apply minimal fix only.
```

---

## Real-World Example: Complete Feature Implementation

### Task: Add "Visual Element Locator" to Navigator

#### Step 1: Planning
```
@Plan I need to add visual element location to agents/navigator.py as fallback when UI tree matching fails. Current _create_tap_plan() uses find_element(). Create implementation plan.
```

#### Step 2: Generate Service
```
@GenerateAgent Create services/vlm_element_locator.py with VLMElementLocator class that has locate_element(screenshot: str, description: str, screen_size: tuple) -> ElementLocation method. Use existing VLMService from services/vlm.py.
```

#### Step 3: Proof
```
@ProofAgent Review services/vlm_element_locator.py for bugs and edge cases.
```

#### Step 4: Fix
```
@FixAgent Apply fixes for issues found in vlm_element_locator.py: [list issues from ProofAgent]
```

#### Step 5: Integration
```
@GenerateAgent Update agents/navigator.py _create_tap_plan() method to use VLMElementLocator when find_element() returns None. Keep existing logic intact, just add vision fallback.
```

#### Step 6: Test
```
@GenerateAgent Create tests/test_vlm_element_locator.py with mocked VLMService to verify element location works correctly.
```

---

## Key Principles for Success

### 1. **Small, Focused Prompts**
Don't ask for entire system at once. Break into digestible pieces.

### 2. **Always Provide Context**
Reference existing files, explain how new code should integrate.

### 3. **Use Proof → Fix Cycle**
Don't assume generated code is perfect. Always proof, then fix.

### 4. **Test Incrementally**
Test each component before integrating with larger system.

### 5. **Preserve Existing Functionality**
When updating files, explicitly say "keep existing X, just add Y".

---

## Timeline with Copilot

| Week | Focus | Copilot Usage |
|------|-------|---------------|
| 1-2 | Vision locator | Plan → Generate → Proof → Fix → Test |
| 3-4 | Reasoning engine | Plan → Generate → Proof → Fix → Test |
| 5-6 | Adaptive recovery | Plan → Generate → Proof → Fix → Test |
| 7-8 | Experience memory | Plan → Generate → Proof → Fix → Test |
| 9-10 | Integration & refinement | Iterative Fix → Test → Fix |

**With Copilot, each component takes ~2-3 days instead of ~1 week.**

---

## Measuring Progress

### Check After Each Component:

```python
# Test prompt for validation
test_goal = "Open WhatsApp and tap the first chat"

# Without universal agent (old way):
old_result = navigator.create_execution_plan(intent, bundle)
# Should fail on unfamiliar screens

# With universal agent (new way):
new_result = await universal_agent.execute_task(test_goal)
# Should succeed through reasoning
```

### Success Criteria:

✅ Vision locator works without hardcoded element names  
✅ Reasoning engine generates valid action plans  
✅ Recovery adapts to different failure types  
✅ Memory retrieves relevant past experiences  
✅ Full system handles tasks without app-specific code  

---

## Final Integration Prompt

**When all components ready:**

```
@Plan Create integration plan for switching AURA from Navigator-based planning to UniversalAgent-based reasoning.

Requirements:
1. Feature flag for gradual rollout
2. Update aura_graph/core_nodes.py execute_node()
3. Preserve backward compatibility
4. Add monitoring to compare old vs new approach
5. Testing strategy before full switch

Create step-by-step migration plan.
```

---

## Summary: Your Copilot Workflow

```
For each feature:
1. @Plan → Get roadmap
2. @GenerateAgent → Create components
3. @ProofAgent → Find bugs
4. @FixAgent → Fix bugs
5. Manual test → Verify works
6. Iterate if needed
7. Move to next feature

Build incrementally, test continuously, integrate carefully.
```

**The key:** Use Copilot agents for their specialized strengths, prompt with context and specificity, and always validate with ProofAgent before moving forward.

---

*With this approach, building the General Agent Architecture becomes a structured, manageable process rather than an overwhelming task.*
