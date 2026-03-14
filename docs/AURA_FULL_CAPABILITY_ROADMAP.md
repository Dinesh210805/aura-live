# AURA Full Capability Roadmap

**Goal:** Enable AURA to handle complex, multi-step, context-aware mobile automation tasks like:

- *"Book a cab to the railway station, share my live location with Arun on WhatsApp, and set an alarm 30 minutes before departure."*
- *"Open Spotify, play my liked songs, lower the volume to 30%, and turn on Do Not Disturb for 1 hour."*
- *"Open YouTube and play the latest video from MKBHD. If there's an ad longer than 5 seconds, skip it."*
- *"Read my latest WhatsApp message. If it's work-related, reply 'I'll get back in an hour'. Otherwise, just mark it as read."*
- *"Open Instagram, go to my profile, and archive the third post from the top."*

---

## Current State Analysis

### ✅ What's Already Implemented

| Component | Status | Description |
|-----------|--------|-------------|
| **Gesture Injection** | ✅ Complete | Tap, swipe, scroll, long press, text input via WebSocket |
| **UI Tree Capture** | ✅ Complete | Real-time accessibility node traversal from Android |
| **Screenshot Capture** | ✅ Complete | MediaProjection-based screen capture |
| **Intent Parsing** | ✅ Partial | Commander agent with rule-based + LLM classification |
| **Navigator Agent** | ✅ Partial | Creates execution plans from intent + UI tree |
| **Gesture Executor** | ✅ Complete | Executes action plans with acknowledgment loop |
| **Deep Link Support** | ✅ Partial | WhatsApp, SMS, calls, email, maps integration |
| **App Inventory** | ✅ Complete | Device app catalog with package name mapping |
| **Contact Resolution** | ✅ Partial | WebSocket-based contact name → phone lookup |
| **Perception Controller** | ✅ Complete | UI tree / screenshot / hybrid modality selection |
| **Goal-Driven Nodes** | ✅ Scaffolded | decompose_goal, validate_outcome, retry_router, next_subgoal |
| **Agent State** | ✅ Scaffolded | Goal → Subgoal hierarchy, retry ladder, abort conditions |
| **Visual Feedback** | ✅ Complete | Edge glow, tap ripples via WebSocket |
| **System Actions** | ✅ Complete | Torch, WiFi, Bluetooth, DND, volume (NO_UI_ACTIONS) |

### ⚠️ What's Partially Implemented (Needs Enhancement)

| Component | Gap | Required Work |
|-----------|-----|---------------|
| **Multi-Step Intent Parsing** | Parameters.steps array populated but not reliably decomposed | LLM needs better decomposition prompts |
| **Goal Decomposition** | decompose_goal_node exists but lacks LLM-driven decomposition | Add planner LLM call to break complex commands |
| **Conditional Logic** | No "if-then-else" handling in execution | Add conditional evaluation in next_subgoal |
| **Temporal Actions** | No timer/alarm/reminder handling | Add system action for alarms, integrate Calendar |
| **Content Reading** | Screen reading exists but not OCR/content extraction | Add VLM content extraction for message reading |
| **Loop Detection** | Basic UI signature matching | Needs visual similarity for ad detection |

### ❌ What's Missing Entirely

| Component | Description | Priority |
|-----------|-------------|----------|
| **Planner Agent** | LLM-powered task decomposition for complex goals | 🔴 Critical |
| **Content Extraction** | Read and understand screen text/content semantically | 🔴 Critical |
| **Conditional Executor** | Handle if/else branching based on screen state | 🔴 Critical |
| **Timer/Alarm Integration** | Create alarms, reminders, timers via intents | 🟡 High |
| **Location Services** | Get current location, calculate distances | 🟡 High |
| **App-Specific Adapters** | Specialized logic for Uber/Ola, Spotify, YouTube, Instagram, WhatsApp | 🟡 High |
| **OCR Pipeline** | Extract exact text from screen for reading messages | 🟡 High |
| **Ad Detection** | Recognize YouTube/other app ads using VLM | 🟠 Medium |
| **Ordinal Navigation** | "Third post", "second message" counting logic | 🟠 Medium |
| **State Persistence** | Remember previous actions for follow-ups | 🟠 Medium |
| **Error Recovery Intelligence** | LLM-driven recovery from unexpected states | 🟠 Medium |

---

## Architecture Gaps Illustrated

```
Current Flow:
┌─────────────────────────────────────────────────────────────┐
│  Voice Input → STT → Commander → Navigator → Executor → TTS │
│                         │              │                     │
│                    Intent(single)  Plan(steps)              │
└─────────────────────────────────────────────────────────────┘

Required Flow for Complex Tasks:
┌───────────────────────────────────────────────────────────────────────────┐
│  Voice Input → STT → Commander → PLANNER → [Subgoal Loop] → TTS          │
│                         │           │            │                         │
│                    RawIntent    Decomposed    For each subgoal:           │
│                                 Subgoals      ├→ Perception               │
│                                               ├→ Navigator                │
│                                               ├→ Executor                 │
│                                               ├→ Validator                │
│                                               └→ Conditional Router       │
└───────────────────────────────────────────────────────────────────────────┘
```

---

## Detailed Implementation Plan

### Phase 1: Planner Agent (Critical Path)

**Goal:** Break complex commands into ordered, executable subgoals.

#### 1.1 Create Planner Agent (`agents/planner.py`)

```python
# Responsibilities:
# 1. Take raw transcript + intent classification
# 2. Call LLM with task decomposition prompt
# 3. Output: List[Subgoal] with dependencies, conditions, success criteria

class PlannerAgent:
    def decompose(self, transcript: str, intent: IntentObject) -> Goal:
        """
        Decompose complex command into executable subgoals.
        
        Example:
        Input: "Book a cab to railway station, share live location with Arun"
        Output: Goal with subgoals:
          1. open_app: Uber/Ola
          2. search: "railway station"
          3. tap: "Book" button
          4. wait_for: ride confirmation
          5. open_app: WhatsApp
          6. search_contact: "Arun"
          7. tap: "share location"
          8. tap: "share live location"
        """
```

#### 1.2 Decomposition Prompt Template

```
You are a mobile task planner. Break this command into atomic steps:

COMMAND: "{transcript}"
CURRENT APP: {current_package}

RULES:
1. Each step must be ONE action: tap, scroll, type, wait, open_app
2. Include waits for loading screens
3. Add conditions for variable states (e.g., "if app asks for permission")
4. Number steps with dependencies
5. Include success criteria for each step

OUTPUT JSON:
{
  "goal": "description",
  "subgoals": [
    {
      "step": 1,
      "action": "open_app",
      "target": "Uber",
      "success_criteria": "Uber home screen visible",
      "depends_on": []
    },
    ...
  ],
  "estimated_duration_seconds": 45
}
```

#### 1.3 Update Graph Flow

- Route from `parse_intent` → `decompose_goal` for complex intents
- Modify `decompose_goal_node.py` to call Planner agent
- Ensure subgoals are stored in `AgentState.goal.subgoals`

---

### Phase 2: Content Extraction & Reading

**Goal:** Enable AURA to read and understand on-screen content.

#### 2.1 OCR Service (`services/ocr_service.py`)

```python
class OCRService:
    async def extract_text(self, screenshot_b64: str, region: Optional[Rect] = None) -> str:
        """Extract text from screenshot using VLM or dedicated OCR."""
    
    async def find_text_element(self, screenshot_b64: str, search_text: str) -> Optional[Coords]:
        """Find location of specific text on screen."""
```

#### 2.2 Content Reader Agent (`agents/content_reader.py`)

```python
class ContentReaderAgent:
    async def read_messages(self, perception_bundle: PerceptionBundle) -> List[Message]:
        """Extract message content from messaging apps."""
    
    async def classify_content(self, text: str) -> ContentClassification:
        """Classify content as work-related, personal, spam, etc."""
```

#### 2.3 VLM Prompt for Content Extraction

```
Analyze this screen and extract the latest message content.

SCREEN CONTEXT: {app_name} messaging screen

EXTRACT:
1. Sender name
2. Message text (exact)
3. Timestamp
4. Message type (text/image/voice/document)

OUTPUT JSON:
{
  "messages": [
    {"sender": "John", "text": "Can you review the report?", "timestamp": "2m ago", "type": "text"}
  ]
}
```

---

### Phase 3: Conditional Execution

**Goal:** Handle if/else branching based on dynamic screen state.

#### 3.1 Condition Evaluator (`services/condition_evaluator.py`)

```python
class ConditionEvaluator:
    def evaluate(self, condition: str, perception_bundle: PerceptionBundle) -> bool:
        """
        Evaluate condition against current screen state.
        
        Examples:
        - "ad longer than 5 seconds" → Check for skip button, timer text
        - "work-related message" → Use ContentReader + LLM classification
        - "ride confirmation visible" → Look for confirmation UI patterns
        """
```

#### 3.2 Conditional Subgoal Structure

```python
@dataclass
class ConditionalSubgoal(Subgoal):
    condition: str  # Natural language condition
    if_true: List[Subgoal]  # Steps if condition met
    if_false: List[Subgoal]  # Steps if condition not met
```

#### 3.3 Update `next_subgoal_node.py`

```python
def next_subgoal_node(state: TaskState) -> dict:
    subgoal = agent_state.goal.current_subgoal
    
    if isinstance(subgoal, ConditionalSubgoal):
        condition_met = condition_evaluator.evaluate(
            subgoal.condition, 
            perception_bundle
        )
        if condition_met:
            agent_state.insert_subgoals(subgoal.if_true)
        else:
            agent_state.insert_subgoals(subgoal.if_false)
    
    return advance_to_next_subgoal()
```

---

### Phase 4: App-Specific Adapters

**Goal:** Handle unique UI patterns for popular apps.

#### 4.1 Adapter Interface

```python
class AppAdapter:
    package_patterns: List[str]  # e.g., ["com.ubercab", "com.olacabs"]
    
    async def detect_state(self, bundle: PerceptionBundle) -> AppState:
        """Identify current app state (home, search, booking, etc.)"""
    
    async def get_action_for_goal(self, goal: str, state: AppState) -> List[Subgoal]:
        """Return steps to achieve goal from current state"""
```

#### 4.2 Cab Booking Adapter (`adapters/cab_adapter.py`)

```python
class CabBookingAdapter(AppAdapter):
    package_patterns = ["com.ubercab", "in.swiggy.app.instamart", "com.olacabs"]
    
    states = {
        "home": ["where to?", "search destination"],
        "searching": ["finding rides", "loading"],
        "results": ["UberGo", "Premier", "book now"],
        "confirmed": ["driver on the way", "arriving in"]
    }
    
    async def book_cab(self, destination: str) -> List[Subgoal]:
        return [
            Subgoal(action="tap", target="Where to?"),
            Subgoal(action="type", text=destination),
            Subgoal(action="tap", target=destination),  # Search result
            Subgoal(action="tap", target="Book"),
            Subgoal(action="wait", condition="ride_confirmed")
        ]
```

#### 4.3 YouTube Adapter (`adapters/youtube_adapter.py`)

```python
class YouTubeAdapter(AppAdapter):
    package_patterns = ["com.google.android.youtube"]
    
    async def detect_ad(self, bundle: PerceptionBundle) -> AdInfo:
        """Detect if ad is playing and get skip button location"""
        # Look for: "Skip Ad", "Ad · X:XX", yellow progress bar
    
    async def play_video(self, channel: str, video_type: str = "latest") -> List[Subgoal]:
        return [
            Subgoal(action="tap", target="search"),
            Subgoal(action="type", text=channel),
            Subgoal(action="tap", target="channel_result"),
            Subgoal(action="tap", target="Videos tab"),
            Subgoal(action="tap", target="first_video"),  # Latest is usually first
        ]
```

#### 4.4 Instagram Adapter (`adapters/instagram_adapter.py`)

```python
class InstagramAdapter(AppAdapter):
    package_patterns = ["com.instagram.android"]
    
    async def navigate_to_profile(self) -> List[Subgoal]:
        return [Subgoal(action="tap", target="profile_icon")]
    
    async def archive_nth_post(self, n: int) -> List[Subgoal]:
        return [
            Subgoal(action="tap", target="grid_view"),
            Subgoal(action="tap_nth", target="post", index=n),
            Subgoal(action="tap", target="more_options"),  # Three dots
            Subgoal(action="tap", target="Archive"),
        ]
```

---

### Phase 5: Ordinal & Counting Logic

**Goal:** Handle "third post", "second message", "first result".

#### 5.1 Ordinal Parser

```python
ORDINAL_MAP = {
    "first": 0, "1st": 0, "second": 1, "2nd": 1,
    "third": 2, "3rd": 2, "fourth": 3, "4th": 3,
    "fifth": 4, "5th": 4, "last": -1, "latest": 0
}

def parse_ordinal(text: str) -> Optional[int]:
    for word, idx in ORDINAL_MAP.items():
        if word in text.lower():
            return idx
    return None
```

#### 5.2 Nth Element Finder

```python
async def find_nth_element(
    elements: List[UIElement], 
    element_type: str, 
    n: int
) -> Optional[UIElement]:
    """
    Find the nth element of a type in UI tree.
    
    element_type: "post", "message", "result", "item"
    n: 0-indexed (0 = first)
    """
    matching = [e for e in elements if matches_type(e, element_type)]
    if 0 <= n < len(matching):
        return matching[n]
    return None
```

#### 5.3 Visual Grid Detection

For apps like Instagram where posts are in a grid:

```python
async def find_nth_in_grid(
    bundle: PerceptionBundle, 
    n: int,
    grid_pattern: str = "3-column"
) -> Optional[Coords]:
    """Use VLM to identify nth item in visual grid layout."""
```

---

### Phase 6: System Integrations

#### 6.1 Alarm/Timer Service

```python
class AlarmService:
    async def set_alarm(self, time: datetime, label: str) -> bool:
        """Set alarm via Android intent."""
        uri = f"android.intent.action.SET_ALARM"
        # Use AlarmClock intent
    
    async def set_timer(self, duration_seconds: int, label: str) -> bool:
        """Set countdown timer."""
```

**Android Side (Kotlin):**
```kotlin
fun handleSetAlarm(hour: Int, minutes: Int, label: String) {
    val intent = Intent(AlarmClock.ACTION_SET_ALARM).apply {
        putExtra(AlarmClock.EXTRA_HOUR, hour)
        putExtra(AlarmClock.EXTRA_MINUTES, minutes)
        putExtra(AlarmClock.EXTRA_MESSAGE, label)
        putExtra(AlarmClock.EXTRA_SKIP_UI, true)
    }
    startActivity(intent)
}
```

#### 6.2 Location Service

```python
class LocationService:
    async def get_current_location(self) -> Location:
        """Request current GPS location from Android."""
    
    async def calculate_eta(self, destination: str) -> timedelta:
        """Use Maps API to calculate travel time."""
    
    async def share_live_location(self, app: str, contact: str, duration_minutes: int):
        """Share live location in messaging app."""
```

---

### Phase 7: Ad Detection & Skip

**Goal:** Detect and skip ads in video apps.

#### 7.1 Ad Detection VLM Prompt

```
Is there an advertisement playing on this screen?

INDICATORS TO CHECK:
1. "Skip Ad" or "Skip" button visible
2. "Ad" label with countdown timer (e.g., "Ad · 0:05")
3. Yellow/different colored progress bar
4. "Visit advertiser" or "Learn more" buttons

OUTPUT JSON:
{
  "is_ad": true,
  "skip_available": true,
  "skip_button_location": {"x_percent": 95, "y_percent": 90},
  "ad_duration_remaining": 3
}
```

#### 7.2 Ad Handler Logic

```python
async def handle_youtube_ad(bundle: PerceptionBundle, max_wait: int = 5):
    ad_info = await youtube_adapter.detect_ad(bundle)
    
    if not ad_info.is_ad:
        return  # No ad, continue
    
    if ad_info.skip_available:
        await gesture_executor.execute_tap(ad_info.skip_button_location)
        return
    
    if ad_info.duration_remaining <= max_wait:
        await asyncio.sleep(ad_info.duration_remaining + 1)
        # Re-check for skip button
        new_bundle = await perception_controller.request_perception(...)
        return await handle_youtube_ad(new_bundle, max_wait)
    
    # Ad is longer than threshold, skip when available
    await wait_for_skip_button(timeout=ad_info.duration_remaining)
```

---

### Phase 8: Message Classification

**Goal:** Understand message content for conditional actions.

#### 8.1 Classification Prompt

```
Classify this message:

MESSAGE: "{message_text}"
SENDER: "{sender_name}"

CATEGORIES:
- work: Mentions work, project, deadline, meeting, report, urgent
- personal: Casual chat, family, friends, social plans
- promotional: Offers, discounts, marketing
- transactional: OTP, delivery, payment, booking confirmation

OUTPUT:
{
  "category": "work",
  "confidence": 0.85,
  "keywords_found": ["report", "review"],
  "suggested_action": "reply_later"
}
```

#### 8.2 Response Generator

```python
class ResponseGenerator:
    async def generate_reply(self, context: str, instruction: str) -> str:
        """
        Generate appropriate reply based on instruction.
        
        instruction: "reply 'I'll get back in an hour'"
        → Returns: "I'll get back in an hour"
        
        instruction: "acknowledge receipt"
        → Returns: "Got it, thanks!"
        """
```

---

## Implementation Priority Matrix

| Phase | Feature | Effort | Impact | Priority |
|-------|---------|--------|--------|----------|
| 1 | Planner Agent | High | Critical | P0 |
| 2 | Content Extraction | Medium | High | P0 |
| 3 | Conditional Execution | Medium | Critical | P0 |
| 4 | App Adapters (Cab, YouTube) | High | High | P1 |
| 5 | Ordinal Navigation | Low | Medium | P1 |
| 6 | Alarm/Timer Integration | Low | High | P1 |
| 6 | Location Services | Medium | High | P1 |
| 7 | Ad Detection | Medium | Medium | P2 |
| 8 | Message Classification | Low | Medium | P2 |

---

## Example Execution Traces

### Example 1: "Book a cab to railway station, share location with Arun"

```
1. STT: "Book a cab to railway station, share location with Arun"
2. Commander: {action: "multi_step", requires_decomposition: true}
3. Planner: Decomposes into:
   └── Goal: Book cab and share location
       ├── Subgoal 1: open_app("Uber")
       ├── Subgoal 2: tap("Where to?")
       ├── Subgoal 3: type("Railway Station")
       ├── Subgoal 4: tap(first_result)
       ├── Subgoal 5: tap("Confirm Uber Go")
       ├── Subgoal 6: wait_for("driver assigned")
       ├── Subgoal 7: open_app("WhatsApp")
       ├── Subgoal 8: search("Arun")
       ├── Subgoal 9: tap(chat_result)
       ├── Subgoal 10: tap("attach")
       ├── Subgoal 11: tap("Location")
       └── Subgoal 12: tap("Share live location")

4. Execute loop for each subgoal:
   - Perception → Navigator → Executor → Validator → Next
```

### Example 2: "Read WhatsApp message, reply if work-related"

```
1. STT: "Read WhatsApp message, reply if work-related"
2. Commander: {action: "read_and_respond", conditional: true}
3. Planner:
   └── Goal: Read and conditionally reply
       ├── Subgoal 1: open_app("WhatsApp")
       ├── Subgoal 2: tap(first_unread_chat)
       ├── Subgoal 3: read_message(latest)
       ├── Conditional: is_work_related(message)
       │   ├── if_true:
       │   │   ├── Subgoal 4a: tap(message_field)
       │   │   ├── Subgoal 5a: type("I'll get back in an hour")
       │   │   └── Subgoal 6a: tap(send)
       │   └── if_false:
       │       └── Subgoal 4b: no_action (mark as read by opening)

4. Execution:
   - After Subgoal 3: ContentReader extracts message
   - LLM classifies: "Can you review the report?" → work_related
   - Condition evaluates TRUE → Execute if_true branch
```

### Example 3: "Play MKBHD video, skip ads over 5 seconds"

```
1. STT: "Play MKBHD video, skip ads over 5 seconds"
2. Planner:
   └── Goal: Play video with ad handling
       ├── Subgoal 1: open_app("YouTube")
       ├── Subgoal 2: tap("Search")
       ├── Subgoal 3: type("MKBHD")
       ├── Subgoal 4: tap("MKBHD channel")
       ├── Subgoal 5: tap("Videos")
       ├── Subgoal 6: tap(first_video)  // Latest
       ├── Subgoal 7: wait(2s)  // Let video/ad start
       └── Conditional: is_ad_playing()
           ├── if_true + ad_duration > 5:
           │   └── tap("Skip Ad") when available
           └── if_false:
               └── continue (video playing)

3. Ad Handler runs in parallel/loop until video plays
```

---

## File Structure After Implementation

```
aura_agent/
├── agents/
│   ├── commander.py         ✅ Exists
│   ├── navigator.py         ✅ Exists
│   ├── planner.py            ❌ NEW
│   ├── content_reader.py     ❌ NEW
│   └── responder.py         ✅ Exists
├── adapters/                  ❌ NEW DIRECTORY
│   ├── __init__.py
│   ├── base_adapter.py
│   ├── cab_adapter.py
│   ├── youtube_adapter.py
│   ├── instagram_adapter.py
│   ├── whatsapp_adapter.py
│   └── spotify_adapter.py
├── services/
│   ├── ocr_service.py         ❌ NEW
│   ├── condition_evaluator.py ❌ NEW
│   ├── alarm_service.py       ❌ NEW
│   ├── location_service.py    ❌ NEW
│   └── (existing services)
├── aura_graph/
│   └── nodes/
│       ├── decompose_goal_node.py   ✅ Needs enhancement
│       ├── conditional_router.py     ❌ NEW
│       └── (existing nodes)
└── config/
    └── app_adapters.yaml      ❌ NEW (adapter configurations)
```

---

## Testing Strategy

### Integration Test Cases

1. **Cab Booking Flow**
   - Mock Uber/Ola UI screens
   - Verify correct tap sequences
   - Test ride confirmation detection

2. **Conditional Message Reply**
   - Mock WhatsApp with test messages
   - Verify classification accuracy
   - Test reply/no-reply branches

3. **YouTube Ad Handling**
   - Mock screens with/without ads
   - Test skip timing logic
   - Verify video playback detection

4. **Multi-App Workflow**
   - Test app switching
   - Verify state persistence across apps
   - Test location sharing flow

### VLM Evaluation

- Create golden dataset of 100+ annotated screenshots
- Measure element detection accuracy
- Benchmark ad detection precision/recall

---

## Success Metrics

| Metric | Target | Current |
|--------|--------|---------|
| Single-step task success | 95% | ~85% |
| Multi-step task success (2-3 steps) | 85% | ~40% |
| Multi-step task success (4+ steps) | 70% | ~10% |
| Conditional branching accuracy | 90% | 0% (not implemented) |
| Average task completion time | <30s | N/A |
| Error recovery rate | 80% | ~50% |

---

## Next Steps (Recommended Order)

1. **Week 1-2:** Implement Planner Agent with LLM decomposition
2. **Week 2-3:** Add Content Extraction / OCR service
3. **Week 3-4:** Implement Conditional Execution in graph
4. **Week 4-5:** Build first adapters (YouTube, WhatsApp)
5. **Week 5-6:** Add alarm/timer and location services
6. **Week 6-7:** Build remaining adapters (Uber, Instagram, Spotify)
7. **Week 7-8:** Integration testing and refinement

---

*Document created: January 23, 2026*
*Author: AURA Development Team*
