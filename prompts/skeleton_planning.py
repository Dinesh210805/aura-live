"""
Skeleton planning prompt — layer 1 of the reactive hybrid planner.

Generates 2-4 abstract phases rather than micro-steps.  The coordinator
resolves each phase to concrete UI actions reactively, one step at a time,
grounded in the live screen observed after every action.
"""

SKELETON_PLANNING_PROMPT = """You are planning a mobile automation task. Break the user request into 2-4 high-level PHASES.

USER REQUEST: "{utterance}"
CURRENT SCREEN: {screen_context}
INSTALLED APPS: {app_inventory}

━━━ WHAT A PHASE IS ━━━
A phase is an abstract intent like "Open Apple Music" or "Navigate to personal playlist".
It is NOT a micro-step like "tap Library tab" — the executor resolves those Live from the screen.

━━━ RULES ━━━
1. 2-4 phases maximum. Don't over-split a simple task.
2. Check CURRENT SCREEN before adding navigation phases:
   - UNKNOWN or no screen data → ALWAYS include "Open <app>" as Phase 1.
     Never skip navigation when screen state is unknown.
   - App already confirmed open on the right screen → skip open phase, start from navigation.
   - Target already visible → use 1-2 phases.
3. "my" (possessive) = item is in the user's personal library or account.
   For music apps → Library tab, NOT Search.
4. First phase: "Open <app>" only if the app is not already visible on CURRENT SCREEN.
5. Last phase: the actual user-requested action (play, send, add to cart, etc.).

━━━ commit_actions ━━━
List any irreversible side effects the user explicitly requested.
These MUST execute before the goal is considered complete.
Leave empty [] for read-only tasks.

━━━ EXAMPLES ━━━
"play my feel good playlist from apple music"
→ phases: ["Open Apple Music", "Navigate to Feel Good playlist in personal library", "Play the playlist"]
→ commit_actions: []

"add the first result to cart"  (screen shows Amazon search results)
→ phases: ["Open the first product", "Add to cart"]
→ commit_actions: ["add to cart"]

"send a whatsapp to mum saying i'm home"
→ phases: ["Open WhatsApp", "Open Mum's chat", "Type and send message"]
→ commit_actions: ["send"]

"what's the weather today"
→ phases: ["Check weather"]
→ commit_actions: []

━━━ OUTPUT (JSON ONLY) ━━━
{{
  "goal_summary": "one-line summary of what the user wants",
  "phases": [
    "phase 1 description",
    "phase 2 description"
  ],
  "commit_actions": ["send"]
}}"""


def get_skeleton_planning_prompt(utterance: str, screen_context: str, app_inventory: str = "") -> str:
    return SKELETON_PLANNING_PROMPT.format(
        utterance=utterance,
        screen_context=screen_context or "Unknown (no screen data available)",
        app_inventory=app_inventory or "Not available",
    )
