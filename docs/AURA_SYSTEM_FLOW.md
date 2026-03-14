# How AURA Works — A Plain-English System Flow Guide

> Written for: anyone who wants to understand what happens inside AURA from the moment you speak a command to the moment the phone acts on it.
>
> This document avoids code jargon. Everything is described as a process: who receives what, what they think about, and what they hand off next.

---

## The Big Picture

AURA is a voice-controlled AI assistant for Android phones. You speak to it, it figures out what you want, looks at what's currently on the phone screen, makes a plan, and then physically taps / types / scrolls on the phone on your behalf — just like a person sitting next to you would.

The entire system is a **chain of specialist agents**, each responsible for one part of the job. No single agent does everything. They pass a growing "shared notebook" between them, and each agent adds its contribution to that notebook before handing it off.

---

## The Complete Journey of One Command

Here is the full path, from start to finish:

```
You speak (voice)             You type (text / streaming)
     ↓                                    ↓
[1] STT — voice turned into text     (skips STT entirely)
     ↓                                    ↓
     └──────────────┬─────────────────────┘
                    ↓
[2] Commander — the text is turned into a structured understanding of your intent
                    ↓
[3] Perception — a screenshot and the list of buttons/text on the phone is captured
                    ↓
[4] Planner — a high-level phase plan is created ("open app → navigate → do the thing")
                    ↓
[5] Execution Loop (repeats until done):
     ├─ Perceiver  — looks at the current screen, finds where to tap
     ├─ Actor      — physically performs the tap/type/scroll
     └─ Verifier   — checks that the screen actually changed as expected
                    ↓
[6] Responder — says back to you what happened, in natural conversational language
```

---

## Stage 1 — Listening: Turning Your Voice Into Text

**Who handles this:** The Speech-to-Text engine

**What it receives:**
- Raw audio bytes from the microphone, OR
- A pre-existing text string (if you typed instead of spoke)

**What it does:**
Takes the audio and transcribes it to plain text. If a language hint is configured (e.g., Tamil, English), it uses that. Otherwise it auto-detects.

**What it produces:**
- A plain text transcript: e.g., `"Send a WhatsApp message to mum saying I'll be home by 8"`

**What goes into the shared notebook:**
The transcript is stored and passed to every step that follows.

---

## Stage 2 — Understanding: What Did You Actually Want?

**Who handles this:** The Commander agent

**What it receives:**
- The text transcript
- Optional conversation context: which app is currently open, what the last action was, what's visible on screen, and a summary of the current screen

**What it tries first (the fast path):**
Before calling any AI, it runs your text through a fast rule-based dictionary. If your command matches a known pattern with high confidence (≥85%), it returns immediately. Example: "open WhatsApp" is recognized instantly without an AI call.

**What it does when the rule fails (the LLM path):**
It calls a fast language model with this prompt structure:

> *"Here is what the user said: [transcript].*
> *Here is the current context: [current app, last action, screen text].*
> *Extract a JSON object with: the action type, the recipient (person/app), the content (message/query), optional parameters, and a confidence score."*

**The prompt includes examples like:**
- "Open YouTube" → `{ action: open_app, recipient: YouTube }`
- "Message Priya saying I'm outside" → `{ action: send_message, recipient: Priya, content: I'm outside }`
- "What's the weather?" → `{ action: conversation, content: What's the weather? }`
- "Turn on WiFi" → `{ action: wifi_on }`

**What it produces:**
A structured intent object: `{ action, recipient, content, parameters, confidence }`

**What goes into the shared notebook:**
The intent object — this is what every later agent uses to understand *what you wanted*.

---

## Stage 3 — Looking at the Phone: Capturing the Screen

**Who handles this:** The Perception node

**What it receives:**
- The current intent (to know what kind of screen to expect)

**What it does:**
Connects to the Android phone via ADB and captures two things simultaneously:
1. A **screenshot** — a pixel image of what's on screen right now
2. A **UI accessibility tree** — a structured list of every button, text field, and label on screen, with their exact positions, text content, whether they're clickable, scrollable, or editable

If the UI tree comes back empty (which happens on some screens), it retries up to 3 times.

**What it produces:**
A "perception bundle" containing:
- The screenshot (stored as base64 image data)
- A list of all visible UI elements, each with: text, position/coordinates, clickability, type (button/text/input), resource ID

**What goes into the shared notebook:**
The perception bundle — the Planner and all execution agents use this to understand what's on screen.

---

## Stage 4 — Making a Plan: Breaking the Goal Into Phases

**Who handles this:** The Planner (GoalDecomposer)

**What it receives:**
- Your original spoken request
- The current screen state (what app is open, what's visible)
- Step history from previous actions in this session (if any)

**What it sends to the AI model:**
A prompt that says:

> *"You are planning a mobile automation task. Break this request into 2-4 high-level phases.*
>
> *User request: [your words]*
> *Current screen: [brief description of what's open and visible]*
>
> *Rules:*
> - *A phase is an abstract goal like "Open Apple Music" — not micro-steps like "tap the Library tab"*
> - *If the app is already open on screen, skip the "open app" phase*
> - *"my [playlist/library/etc]" means personal library, NOT search*
> - *The last phase should always be the concrete user-requested action*
> - *List any irreversible actions (send, purchase, post) in commit_actions*"*

**Example — "Send a WhatsApp to mum saying I'm home":**
The AI returns:
```
phases: ["Open WhatsApp", "Open Mum's chat", "Type and send message"]
commit_actions: ["send"]
```

**Example — "Play my Feel Good playlist from Apple Music":**
The AI returns:
```
phases: ["Open Apple Music", "Navigate to Feel Good playlist in personal library", "Play the playlist"]
commit_actions: []
```

**What it produces:**
A Goal object with:
- A plain-English goal summary
- A list of 2-4 phases (abstract, high-level)
- A list of "commit actions" — irreversible things that must happen before the goal is marked complete

**Important:** These phases are deliberately vague. The system does NOT pre-plan individual taps here. The concrete taps are figured out live, one at a time, by looking at the real screen in the next stage.

**What goes into the shared notebook:**
The goal summary, phases list, and commit actions list.

---

## Stage 5 — The Execution Loop: Doing the Work

This is the core of the system. For each phase of the plan, the system runs through a cycle: **look → decide → act → verify**. This repeats until the whole goal is done or something goes wrong.

### The Step Memory — the Thread That Connects Everything

Before explaining each sub-agent, understand the **Step Memory list**. This is a running log of every action taken so far, including:
- What was being attempted (description of the subgoal)
- What action was done (tap, type, scroll, open app)
- What was tapped or typed
- Whether it succeeded or failed
- What type of screen it was on
- A text description of what the screen looked like (from the AI vision model, if used)
- Two "fingerprints" of the screen — before and after the action — so the system can detect if anything changed

Every agent in the loop has access to this entire history. The Reactive Step Generator always includes the most recent **6 steps** in its prompt. The Replanner uses the most recent 5 steps when recovering from failures.

---

### Step 5a — Deciding the Next Concrete Action (Reactive Step Generator)

**Who handles this:** The Reactive Step Generator

**What it receives:**
- The current phase description (e.g., "Navigate to Feel Good playlist in personal library")
- The overall goal (e.g., "Play my Feel Good playlist from Apple Music")
- A text description of what's currently on screen
- Every step completed so far (the Step Memory)
- Any pending "commit actions" still needed
- The last failure reason (if the previous step failed)

**What it sends to the AI model:**
A prompt that says:

> *"You are helping execute one step at a time on a real Android phone.*
>
> *Overall goal: [your words]*
> *Current phase: [phase description]*
> *What you see on screen right now: [text description of current screen]*
> *Steps done so far: [list of completed/failed steps]*
> *Pending required actions: [send/purchase/etc if any]*
> *Last failure: [what went wrong if applicable]*
>
> *What is the single next action to take? Output ONE action only.  
> Also tell me: is this phase complete? Is the whole goal complete?"*

**What it produces:**
One specific action: `{ action_type: tap, target: "Library tab", description: "Tap the Library tab to switch to personal library" }`

Plus two flags: whether the current phase is now done (`phase_complete`), and whether the entire goal is done (`goal_complete`).

**When `goal_complete` is returned true:** The system immediately advances through all remaining phases and exits the loop — it doesn't wait for a final verify pass.

**How pending commit actions are cleared:** The Reactive Step Generator itself monitors the `pending_commits` list. As each step is generated, it checks whether the step's target matches a commit action on the list — and if so, removes it. When the list is empty AND the phases are done, the goal is complete.

**Degraded screen context — VLM fallback:** The Reactive Step Generator normally works from a plain-text description of the screen. But if that description is very short (under 120 characters), or flagged as stale with a `[prev screen]` prefix, the Coordinator first fetches a fresh screenshot and sends it directly to the vision model instead of the text LLM. This handles situations where the screen just changed and a proper text description hasn't been generated yet.

---

### Step 5b — Finding Where to Tap (Perceiver Agent)

**Who handles this:** The Perceiver agent

**What it receives:**
- The specific subgoal just generated (e.g., "tap Library tab")
- The intent object (the overall command)
- The step history (to know the context)
- The full plan (to know where this step fits)

**What it does:**

**First, it captures the screen** (screenshot + UI accessibility tree).

**Then it uses VLM to find the target — always, not just as a fallback.**

This is the key part that replaced the old text-matching approach: the system draws **numbered bounding boxes** (using OpenCV) over every meaningful UI element directly on the screenshot — green for tappable, blue for scrollable, purple for informational. It then sends this annotated image to the VLM along with:
- A numbered list of all the elements (text, type, whether tappable)
- The user's original command
- The full plan context
- The description of the current step (e.g., "tap Library tab")

The VLM prompt says:

> *"The screenshot has [N] numbered boxes drawn on UI elements.*
> *Element list: 1. Library [tap]   2. Search [tap]   3. For You [tap] ...*
> *User command: [your words]. Full plan: [phases]. Current step: [subgoal description].*
>
> *Find which numbered box is the correct element to interact with for the CURRENT STEP.*
> *Also assess: does this screen look correct for the current step, or is the app on the wrong screen?*
>
> *Important disambiguation rule: if two elements share the same label text, an EditText/input field containing the target text means it's a typed search value — pick the result row below it, not the input box.*
>
> *Respond with JSON only: { "element": "3", "screen_ok": true, "deviation": null }*"*

The VLM picks the element **by number** (not by predicting pixel coordinates). The actual tap coordinates are then read from that element's real bounding box in the UI tree. This eliminates a class of AI errors known as spatial hallucination — the VLM never has to guess where something is in pixels, it just picks which numbered box is right.

**If the VLM says "not_found":** The element doesn't exist in the accessibility tree — it's on a custom-rendered screen (a website, canvas view, or app that doesn't expose UI elements). The system then falls through to **OmniParser**: a computer vision pipeline that detects interactive regions in the raw screenshot image and selects the right one, again without asking the VLM to invent coordinates.

**Special case — WebView screens:**
If the previous step happened on a WebView (a screen rendered as a webpage inside an app), the system automatically skips the UI tree for the current step too, since the accessibility tree will only show a blank browser frame. It goes straight to the VLM annotated path. If no description of the current screen exists yet, it re-fetches with VLM screen description enabled so the Reactive Step Generator has meaningful context for the next decision.

**Additionally — screen mismatch detection:**
The VLM's `screen_ok` flag serves as a built-in sanity check. If the VLM says the target element is nowhere to be found AND the current screen looks completely wrong for this step (e.g., the app crashed to the home screen, or Settings opened instead of Gmail), it sets `screen_ok: false` and provides a one-sentence description of what's wrong. This triggers an immediate replan in the Coordinator before wasting further actions.

**What it produces:**
- Exact pixel coordinates of where to tap/interact (from the real UI tree bounds of the VLM-selected numbered element)
- An annotated screenshot showing exactly which numbered box the VLM picked (saved to the log for debugging)
- A description of the entire screen (when the VLM ran a description pass)
- The type of screen (native app, WebView, Android system screen)
- A fingerprint/hash of the current screen state
- A replan flag + reason if the screen was detected as wrong

**What goes into the shared notebook:**
The coordinates, screen description, screen fingerprint, annotated screenshot path, and any replan signal — all passed to the Actor and Verifier.

---

### Step 5c — Actually Doing It (Actor Agent)

**Who handles this:** The Actor agent

**What it receives:**
- The action type (tap, type, scroll, swipe, open_app, press_back, press_enter, etc.)
- The target name (for logging)
- The exact pixel coordinates
- Any parameters (e.g., the text to type, the scroll direction, the app name)

**This agent calls NO AI at all.** It is a pure mechanical executor.

**What it does:**
Translates the action into the appropriate ADB command and sends it to the phone:
- `tap` → sends a touch event at the given coordinates
- `type` → uses ADB input text command
- `scroll` → sends a swipe gesture
- `press_back` → sends the Android back key
- `open_app` → launches the app by its package name
- `swipe` → sends a multi-point touch gesture

**Special case — `open_app` skips the Verifier entirely:**
When the Actor successfully launches an app, the system skips the Verifier and instead waits 3 seconds for the app to finish rendering. It then refreshes the screen context directly. Skipping the Verifier here avoids a false-negative: the app is confirmed launched by the Actor itself (via package name check), so there's nothing left for the Verifier to check.

**What it produces:**
An action result: `{ success: true/false, duration_ms: 340, error: null }`

**What goes into the shared notebook:**
Whether the action physically succeeded (ADB command completed), and how long it took.

---

### Step 5d — Checking the Result (Verifier Agent)

**Who handles this:** The Verifier agent

**What it receives:**
- The subgoal that was just attempted
- The action type that was executed
- The screen fingerprint from BEFORE the action

**What it does:**

**Waits a moment** (300 milliseconds) to let the screen settle, then captures the screen again.

**Compares the new screen fingerprint to the pre-action fingerprint.** If they're different, the screen changed — which usually means the action worked.

**For slow network navigations** (going to a website, loading a feed), it polls the screen for up to 4 seconds waiting for it to finish loading.

**For toggles and media controls** (like/unlike button, play/pause), it skips the change-detection check entirely — because these actions succeed even when the screen looks nearly identical.

**Scans the new screen for error indicators** by looking for text phrases like:
- "try again"
- "network error"
- "app has stopped"
- "unfortunately"
- "connection failed"

If any of these are found, the result is marked as failed even if the screen did change.

**What it produces:**
`{ success: true/false, error: null/"screen did not change" }`

**What goes into the shared notebook:**
Success/failure result, and the new screen fingerprint (so the next step's Perceiver knows the starting state).

---

### The Step Memory Entry Created After Each Step

After every successful or failed action, a record is added to the Step Memory:

```
- What was being attempted: "Tap the Library tab"
- Action type: tap
- Target: Library tab
- Result: success / failed
- Screen type: native app / WebView / system screen
- Screen fingerprint before action: [hash]
- Screen fingerprint after action: [hash]
- Screen description (if VLM was used): "Apple Music home screen showing For You, Radio, Library, and Search tabs"
```

This record is included in every subsequent prompt sent to every AI agent.

---

## Stage 6 — When Things Go Wrong: Recovery Strategies

The system has two separate failure modes, each with its own recovery:

---

### When the target element isn't found on screen

If the Perceiver can't locate the target element (e.g., the button isn't visible), the system escalates through this ladder before giving up:

**Step 1 — Scroll and re-look**
Scroll the screen down (the element might be off-screen below the visible area), then re-run the full perception pass.

**Step 2 — Force VLM re-look**
Re-run perception with a forced screenshot, ensuring the VLM sees the freshest screen content rather than a cached snapshot. This catches cases where the first perception was run on a slightly stale frame.

**Step 3 — Replan**
If the target still can't be found after scrolling and a VLM re-look, call the Planner with a detailed description of what's visible:

> *"Cannot find '[target]' on screen after scrolling.*
> *Visible elements: [list of what is on screen]*
> *Screen: [VLM description of the current screen]*
> *Generate new subgoals to recover and continue toward the original goal."*

The Planner generates a new set of subgoals that route around the problem, and the execution loop continues.

---

### When an action physically fails (ADB error)

If the Actor itself reports a failure executing the action (e.g., ADB command rejected), it retries the same action up to 3 times before skipping to the next subgoal.

---

### When the screen stops changing (loop detection)

If the system notices the same screen fingerprint appearing 3 times in a row — meaning nothing AURA does is having any effect — it triggers a **stuck-screen recovery**. It calls the Planner with a rich description of what's visible and what's been tried, asking for 1-2 recovery steps to break out of the loop. This can happen up to 2 times before the task is aborted.

---

### Replan limit and budget

If replanning is triggered more than 3 times total, or the total number of actions exceeds 30, the task is aborted. This prevents infinite loops on impossible tasks.

---

## Stage 7 — Responding: Talking Back to You

**Who handles this:** The Responder agent

**What it receives:**
- The original intent (what you asked for)
- Whether the task succeeded or failed
- A human-readable goal summary
- The list of steps that were completed
- Any error message
- The full conversation history (for context-aware replies)
- Your original transcript (for emotional tone detection)

**What it sends to the AI model:**
A prompt built around AURA's personality guidelines, which state:
- Responses go through speech synthesis — keep them short and natural (1-2 sentences max)
- Start with a varied natural opener: "Got it", "Alright", "Sure", "Done!" etc. (never repeat the same one twice in a row)
- Occasional natural speech disfluencies feel more human: "um", "so", "right"
- Match the user's energy — if their message was urgent, be quick and focused
- For completed actions: brief confirmation with warmth
- For failures: empathetic, offer an alternative

For conversational questions (no phone action needed), the Responder can optionally perform a live web search to answer factual queries.

For settings panel actions (WiFi, Bluetooth, etc.) that Android 10+ doesn't allow apps to control directly, it gives a pre-written message like: *"I've opened the WiFi panel for you. Just tap to turn it on."*

**What it produces:**
A natural language text response, which is then converted to speech.

---

## What Each Agent Knows — Summary Table

| Agent | What It Receives | What It Produces |
|---|---|---|
| **STT** | Raw audio bytes | Plain text transcript |
| **Commander** | Transcript + current app/screen context | Structured intent: action, recipient, content, confidence |
| **Perception (initial)** | Intent | Screenshot + full UI element list |
| **Planner** | Your words + current screen + step history | 2–4 abstract phases + list of required irreversible actions |
| **Reactive Step Generator** | Current phase + overall goal + screen description + full step history + pending commits + last failure | ONE concrete next action (tap/type/scroll/etc) + target name |
| **Perceiver** | The concrete subgoal + intent + step history + plan context | Exact coordinates + annotated screenshot + screen description + screen fingerprint + replan signal |
| **VLM (Annotated UI tree)** | Annotated screenshot (numbered boxes drawn on all elements) + element list + user command + plan context + current step | Which element NUMBER to tap + whether screen is correct for this step |
| **OmniParser (fallback)** | Raw screenshot (when element is not in accessibility tree at all) | Coordinates for visually-detected element |
| **Actor** | Action type + coordinates + parameters | Success/failure + duration |
| **Verifier** | Subgoal + action type + pre-action screen fingerprint + original utterance + step history | Success/failure + updated screen fingerprint (skipped for open_app) |
| **Replanner** | Original goal + completed steps + stuck step + obstacle + screen + remaining steps | New subgoals to route around the problem |
| **Responder** | Intent + status + completed steps + error + conversation history | Natural spoken response |

---

## The Memory System — How Context Accumulates

The system maintains a **Step Memory list** that grows throughout a task. Every completed action appends a record to this list. Here is how each agent uses it:

**The Planner uses it** when creating the initial plan — it checks what has already been done in this session so it doesn't repeat steps from earlier commands.

**The Reactive Step Generator uses it** as the most critical input — it only advances to the next action by knowing exactly what happened in every prior step, what screens were seen, and what succeeded or failed.

**The Perceiver uses it** to decide whether to force vision mode. If the previous step was on a WebView/browser-rendered screen, it automatically uses screenshot analysis instead of the UI tree for the current step.

**The Planner (on replan) uses it** with the full detail, including VLM screen descriptions for each step — so when it's trying to recover from a failure, it knows not just what happened but what was visually on screen at each point.

---

## A Complete Example: "Send hi to John on WhatsApp"

Walk through every stage:

**Stage 1 — You speak:**
Your voice audio is transcribed. Result: `"Send hi to John on WhatsApp"`

**Stage 2 — Commander parses intent:**
The rule system finds this matches the "send message" pattern.
Result: `{ action: send_message, recipient: John, content: hi, confidence: 0.95 }`

**Stage 3 — Screen captured:**
The phone is currently on the Home Screen. Screenshot shows app icons.
UI tree provides a list of all icon labels.

**Stage 4 — Planner creates phases:**
Prompt to AI: *"Break this into phases: 'Send hi to John on WhatsApp'. Current screen: Home screen with app icons."*
Result: `phases: ["Open WhatsApp", "Open John's chat", "Type and send message"], commit_actions: ["send"]`

**Stage 5 — Execution loop begins:**

**Phase 1: "Open WhatsApp"**
- Reactive Step says: `{ action: open_app, target: WhatsApp }`
- Perceiver: action is "open_app" — no UI element to locate, skip perception
- Actor: launches WhatsApp via ADB package name
- Verifier: waits 300ms, sees screen changed to WhatsApp chat list, fingerprint differs → **success**
- Step Memory entry added: ✅ open_app(WhatsApp) on home screen

**Phase 2: "Open John's chat"**
- Reactive Step sees screen description now shows "WhatsApp chat list with contacts"
  - Says: `{ action: tap, target: "John", description: "Tap John's chat from the list" }`
- Perceiver: draws numbered boxes on all chat row elements on the screenshot, sends to VLM with context "Current step: Tap John's chat from the list". VLM responds: `{ "element": "4", "screen_ok": true }`. Coordinates read from element 4's UI tree bounds → (540, 420)
- Actor: taps at (540, 420)
- Verifier: screen changes to a chat conversation view → **success**
- Step Memory entry added: ✅ tap(John) on WhatsApp chat list

**Phase 3: "Type and send message"**
- Reactive Step sees screen description shows "WhatsApp chat open with John, message input bar at bottom"
  - Says: `{ action: tap, target: "message input box" }`
- Perceiver: annotated screenshot sent to VLM, VLM picks the editable input field element → coordinates (540, 960)
- Actor: taps at (540, 960)
- Verifier: keyboard appears, input field shows cursor → **success**

- Reactive Step (next sub-step): `{ action: type, target: "hi" }`
- Perceiver: action is "type" — no UI element to locate, skip perception
- Actor: types "hi" via ADB
- Verifier: text "hi" appears in input field → **success**

- Reactive Step (next sub-step): `{ action: tap, target: "Send button" }`
  - Also sees "send" is in pending commit_actions — will mark phase_complete=true when this executes
- Perceiver: annotated screenshot → VLM picks the Send arrow element → coordinates (1020, 960)
- Actor: taps at (1020, 960)
- Verifier: input field clears, message bubble "hi" appears in chat → **success**
- Step Memory entry added: ✅ tap(Send button) — commit action "send" fulfilled

**Reactive Step Generator checks:** goal_complete=true (all phases done, all commit actions fulfilled)

**Stage 6 — Loop ends**

**Stage 7 — Responder:**
Prompt to AI: *"Task send_message to John completed. Steps done: opened WhatsApp, tapped John's chat, typed 'hi', tapped Send. Generate a short, natural spoken response in AURA's personality."*
Result spoken aloud: *"Done! Your message to John has been sent."*

---

## Two Ways the Planner Works

Up to now the document has described **Phase-Reactive mode** (the normal way). There is also an older **Static mode** that may still be used for simple commands.

**Static mode:** The Planner pre-generates individual micro-steps upfront (tap this → type this → tap that). These steps are fixed at planning time and don't adapt to what's on screen.

**Phase-Reactive mode (the current default):** The Planner only generates abstract phases. The concrete taps are determined one at a time by looking at the live screen after each action. This is far more reliable because the plan never goes stale — it always works from what's actually on screen right now.

---

## Special Cases and Edge Behaviors

**"Open WiFi" / "Turn on Bluetooth":**
Android 10+ prevents apps from directly toggling system settings. AURA navigates to the relevant settings panel and tells you to tap it manually. The Responder has pre-written messages for all of these cases.

**WebView screens (e.g., app opening a website internally):**
The accessibility tree describes a single browser frame instead of individual buttons. The system automatically detects this and uses the screenshot + AI vision for all interactions on that screen (and the next one, since the page change might also be a WebView).

**The same action repeating in a loop:**
If the Coordinator detects the same screen fingerprint 3 consecutive times, it triggers a stuck-screen recovery: the Planner is called with a description of what's on screen and what's been tried, and it injects 1-2 new recovery steps to break out of the loop.

**Commands with multiple fields:**
If you say "Post a tweet saying 'Just launched my new project'", the system creates separate subgoals for: finding the tweet compose button, tapping the text field, typing the content, and tapping Post — because each field on a form screen requires its own interaction.

---

## The Log File

Every phase of this process — every AI call, every screen seen, every action taken, every success or failure — is written to an HTML log file in real time. The log shows:

- The full text of every prompt sent to AI models (with character count — click to expand)
- The complete response from each AI
- Screenshots of the screen before and after each action
- An annotated screenshot showing which element was selected
- The structured list of all UI elements the system saw
- Retry decisions and replan results
- Timing information for every operation

This log file is the primary debugging tool for understanding exactly what the system did and why.

---

*End of document*
