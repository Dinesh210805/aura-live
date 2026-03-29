"""
Goal Planning & Decomposition Prompts - v2.0.0

Prompts for breaking down complex goals into executable steps.

Changes from v1:
- Added failure handling guidance
- Clearer action type mapping
- Better special case handling
"""

from typing import Optional


# =============================================================================
# GOAL DECOMPOSITION PROMPT
# =============================================================================
GOAL_DECOMPOSITION_PROMPT = """Break down this user request into executable steps for a mobile automation agent.

USER REQUEST: "{utterance}"
CURRENT SCREEN: {screen_context}

━━━ CURRENT SCREEN AWARENESS ━━━
ALWAYS check CURRENT SCREEN before adding navigation steps:
- If CURRENT SCREEN is UNKNOWN or says "no screen data" → ALWAYS include open_app as step 1.
  Never skip navigation when screen state is unknown.
- If CURRENT SCREEN shows the target app is already open → skip open_app
- If CURRENT SCREEN shows a product/item the user wants to act on → skip search steps
- If CURRENT SCREEN is already the right page for the first action → start from that action
- Example: user says "add to cart", screen = iPhone 17 Pro product page →
    plan: scroll (if Add to Cart not visible) → tap "Add to Cart"
    NOT: open_app → tap search → type → press_enter → tap product → tap Add to Cart
NEVER repeat navigation that the current screen already satisfies.

━━━ PERSONAL CONTENT vs SEARCH ━━━
CRITICAL: "my" (possessive) means the item is in the user's personal library — do NOT search for it.

Music apps (Apple Music, Spotify, YouTube Music):
- "play MY playlist / MY songs / MY album" → Library tab → Playlists/Songs/Albums → tap item → Play
  NEVER: Search tab → type name → press_enter → tap result → Play
- "play [song/artist name] I haven't saved" OR "find [song]" → Search tab → type → press_enter → tap result
- Rule: if the user says "my", go to Library. If the user says "find" or "search for", go to Search.

Similarly for other apps:
- "my contacts / my photos / my files" → navigate to the personal section, not Search
- "search for [X]" → use the Search function

━━━ CORE PRINCIPLE ━━━
Each subgoal = ONE atomic UI action (one tap, OR one type into the currently focused field).
The agent can only interact with ONE element at a time. Plan accordingly.

━━━ PLANNING RULES ━━━
1. Each step must produce a visible screen change
2. Only reference elements you can see in CURRENT SCREEN or that are standard (e.g. "Compose" in Gmail)
3. If the target app isn't open yet, the first step MUST be open_app (never tap to find an app icon)
4. Keep plans short: 3-7 steps for most tasks
5. Preserve dependency order: NEVER skip prerequisite actions required before verification steps

━━━ NON-SKIPPABLE COMMIT ACTIONS ━━━
Any step that causes side effects is mandatory and must be explicit in subgoals:
- add to cart / buy / checkout / place order / pay
- send / submit / confirm
- delete / remove / unsubscribe

If user asks to add an item to cart, plan MUST include:
1) add-to-cart action, and
2) optional cart-open verification only AFTER add-to-cart.
Do NOT replace "Add to Cart" with "Cart".

━━━ MULTI-FIELD FORMS (Email, Messages, Posts) ━━━
CRITICAL: Each input field is a SEPARATE subgoal. You CANNOT type into multiple fields in one step.

Email example (Gmail):
  1. open_app → "Gmail"
  2. tap → "Compose"
  3. type → "recipient@email.com"  (goes into the To field which is auto-focused)
  4. dismiss_keyboard                (REQUIRED: close keyboard before tapping next field)
  5. tap → "Subject" field
  6. type → "Meeting Follow-up"
  7. dismiss_keyboard                (REQUIRED: close keyboard before tapping next field)
  8. tap → message body area
  9. type → "Hi, just following up on our discussion..."
  10. dismiss_keyboard               (REQUIRED: close keyboard before tapping Send)
  11. tap → "Send"

Social media post example:
  1. open_app → "LinkedIn"
  2. tap → post button (center of bottom nav)
  3. type → "Your actual post content here..."
  4. tap → "Post"

NEVER combine multiple fields with \\n characters. Each field = separate tap + type steps.

━━━ TYPE ACTION RULES ━━━
For type actions, target = THE ACTUAL TEXT TO TYPE, not a field name or placeholder.
✗ WRONG: target="recipient email address"
✗ WRONG: target="denise@gmail.com\\nSubject: Hello\\nBody text"
✓ RIGHT: target="denise@gmail.com"  (one field at a time)

When user asks to create content (post, email, message), generate the actual text:
- "email about meeting" → Generate: "Hi, just wanted to follow up on our meeting. Let me know your availability."
- "post about our assistant" → Generate: "Introducing our AI assistant that automates Android tasks with voice commands..."
NEVER use placeholders like "[Your Name]" or "(insert content)".

━━━ TAP ACTION RULES ━━━
- Use EXACT labels from screen_context when visible
- If target screen isn't visible yet, use generic terms: "Compose", "Send", "post button"
- NEVER invent specific button labels you can't verify
- If target is a commit action (e.g., "Add to Cart", "Send", "Submit"), keep it as a dedicated step.

━━━ AVAILABLE ACTIONS ━━━
- open_app: Launch app by name — ALWAYS use this to open/launch any app, NEVER use tap for launching apps
- tap: Tap a single UI element already visible on screen (NEVER use tap to open an app)
- type: Type text into the currently focused field
- press_enter: Press Enter/Search key (use after typing in search fields to submit)
- dismiss_keyboard: Close the on-screen keyboard (use after type when the next step is a tap)
- swipe: Directional swipe (up/down/left/right)
- back: Navigate back
- wait: Wait for screen transition
- ask_user: Ask the user for clarification

━━━ APP LAUNCH RULE (CRITICAL) ━━━
To open ANY app (Amazon, WhatsApp, Gmail, YouTube, etc.) you MUST use:
  action_type: "open_app", target: "<app name>"
NEVER use tap + target: "Amazon icon" or similar. The system launches apps directly
via package name — no icon-hunting on the home screen needed.

━━━ SEARCH PATTERN ━━━
When searching in any app: tap search field → type query → press_enter to submit.
Do NOT try to tap a search result before submitting the search.

━━━ KEYBOARD PATTERN ━━━
After every type action, the keyboard stays open and covers part of the screen.
ALWAYS add dismiss_keyboard before the next tap (except press_enter/press_search which close it automatically).
Failure to dismiss means the next `tap` target will be hidden behind the keyboard and cause a scroll loop.

━━━ SCROLLING ━━━
Do NOT add scroll steps. The executor auto-scrolls to find elements.
Only add swipe if the user explicitly asks to scroll.

━━━ KNOWN CONTACTS (canonical spellings — always use these exact names in subgoal targets) ━━━
Voice transcription often garbles these names. Use ONLY the correct spellings below:
- "Saathvic" — variants: sathvic, satvic, sathvik, saatvic, SATHVIC, "saath vic"
- "Elakiya"  — variants: elakia, e car, eka, elakya, EKA, "e la kia"
- "Anu"      — variants: anu aa, anna, anu a
Always write the canonical name (e.g. target: "Saathvic") — never the garbled version.

━━━ OUTPUT (JSON ONLY) ━━━
Output ONLY a JSON object. No text before or after.

Before finalizing, run this internal checklist:
- Did I include every user-required side effect step?
- Did I avoid jumping straight to verification screens?
- For commerce goals, is "Add to Cart/Buy" present before "Cart/Checkout"?
- Are all steps atomic and executable from current context?

{{
  "goal_summary": "One-line summary",
  "subgoals": [
    {{
      "description": "What this step does",
      "action_type": "open_app|tap|type|press_enter|dismiss_keyboard|swipe|back|wait|ask_user",
      "target": "element name or text to type",
      "success_hint": "Expected screen change"
    }}
  ]
}}"""


# =============================================================================
# REPLANNING PROMPT (When Stuck)
# =============================================================================
REPLANNING_PROMPT = """Agent is stuck and needs alternative approach.

ORIGINAL GOAL: {goal}
COMPLETED: {completed_steps}
STUCK ON: {current_step}
REMAINING AFTER FIX: {remaining_steps}
OBSTACLE: {obstacle}
CURRENT SCREEN: {screen_context}

━━━ RECOVERY STRATEGIES ━━━
1. Different path: Is there another way to reach the goal?
2. Scroll first: Target might be off-screen
3. Go back: Wrong screen, return and try again
4. Alternative element: Similar button/link that works
5. Simplify: Break stuck step into smaller actions
6. Overwrite field: If an input field contains wrong/garbage text, type the correct text directly — the type action replaces all existing content.
7. Ask user: If stuck because of ambiguity, ask the user for help

━━━ INPUT FIELD TROUBLESHOOTING ━━━
If stuck on typing into a field:
- Check if the field already has incorrect text → use type to overwrite it directly (no clearing needed)
- Tap directly on the EditText/input element (not labels near it)
- If keyboard is open (field is focused/editable), type directly without tapping again
- If a swipe/scroll failed near an input field, the keyboard may have captured the gesture as keystrokes

━━━ AVAILABLE ACTION TYPES ━━━
You MUST only use action types from this exact list. Any other action type will fail.
  tap | type | press_enter | dismiss_keyboard | swipe | scroll | back | open_app | wait | ask_user

━━━ OUTPUT (JSON ONLY) ━━━
{{
  "analysis": "Why we're stuck",
  "recovery_strategy": "Which strategy to use",
  "subgoals": [
    {{
      "description": "What to do",
      "action_type": "ONE OF: tap, type, press_enter, dismiss_keyboard, swipe, scroll, back, open_app, wait, ask_user",
      "target": "For tap/open_app: the element label or app name to interact with. For type: THE EXACT TEXT TO TYPE (e.g. 'iphone 17'), NOT the field name."
    }}
  ]
}}

Generate 1-3 alternative subgoals."""


# =============================================================================
# SIMPLE COMMAND TEMPLATES (No LLM needed)
# =============================================================================
SIMPLE_COMMANDS = {
    "screenshot": {"action_type": "screenshot", "target": None},
    "back": {"action_type": "back", "target": None},
    "home": {"action_type": "home", "target": None},
    "scroll_down": {"action_type": "scroll", "target": "down"},
    "scroll_up": {"action_type": "scroll", "target": "up"},
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================
def get_planning_prompt(
    utterance: str,
    screen_context: str = "Unknown",
) -> str:
    """Build goal decomposition prompt."""
    return GOAL_DECOMPOSITION_PROMPT.format(
        utterance=utterance,
        screen_context=screen_context,
    )


def get_replanning_prompt(
    goal: str,
    completed_steps: str,
    current_step: str,
    obstacle: str,
    screen_context: str = "Unknown",
    remaining_steps: str = "None",
) -> str:
    """Build replanning prompt for stuck agent."""
    return REPLANNING_PROMPT.format(
        goal=goal,
        completed_steps=completed_steps or "None",
        current_step=current_step,
        remaining_steps=remaining_steps or "None",
        obstacle=obstacle,
        screen_context=screen_context,
    )
