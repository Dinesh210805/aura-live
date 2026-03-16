"""
Dynamic contextual rules for the reactive step prompt.

Instead of including all 37+ rules in every call, inject only the rules
relevant to the current screen state. This saves ~1,000-2,000 tokens per call.
"""

KEYBOARD_RULES = """\
KEYBOARD BLOCKING: Keyboard covers lower ~40% of the screen.
Any element whose top-Y > 60% of screen height is behind the keyboard and untappable.
Generate dismiss_keyboard FIRST, then tap the target on the next turn.
Even elements in the UI tree with valid bounds are physically hidden — a tap lands on a keyboard key instead."""

AUTOCOMPLETE_RULES = """\
AUTOCOMPLETE / SUGGESTION DROPDOWN — BLOCKING CONDITION:
If rows appear DIRECTLY BELOW a focused input field (names, emails, contacts, search results):
→ The field is NOT confirmed until a suggestion row is tapped.
→ Tap the BEST-MATCHING suggestion row NOW — not the text field itself.
→ Do NOT proceed to Subject, Body, or any other field first.
→ In email apps: contact card below To/Cc/Bcc = autocomplete. Tap it to confirm the recipient.
→ Even if typed text looks correct, a visible dropdown means the field is unresolved."""

LOADING_RULES = """\
LOADING STATE: Spinner, progress bar, or blank content area visible.
Do NOT tap anything in the loading area. Action: wait, phase_complete: false.
Exception: functional controls clearly outside the loading area (e.g. a mini-player bar) are tappable."""

MEDIA_RULES = """\
MEDIA PLAYBACK COMPLETION:
If the user's goal is to play/start music, a song, or a video:
• Pause button visible (cd='Pause', '⏸', '‖', text containing 'Pause') → playback IS active → goal_complete: true immediately.
• cd='playing <track>' or 'Now Playing' banner or elapsed time > 00:00 → playback IS active → goal_complete: true.
• Only Play button visible (no Pause) → playback NOT started yet → goal_complete: false.
Do NOT tap Play again if Pause is already showing."""

NAV_APP_RULES = """\
NAVIGATION APP: The main search bar is for DESTINATION, not starting point.
Type destination first → pick result → tap Directions.
Starting point defaults to current location. Only change it if the user explicitly named a custom origin."""

NAV_COMPLETION_RULES = """\
NAVIGATION GOAL COMPLETION:
If the user asked to navigate/get directions and the screen NOW shows:
• Turn-by-turn navigation view (step instructions like 'Head north', ETA, distance remaining)
• 'Start' button is GONE and instead you see 'End', 'Mute', or a live route overlay
• A navigation bar at the top/bottom with live ETA, arrival time, or distance
→ Navigation IS active → goal_complete: true immediately. Do NOT tap anything else.
The 'Start' button being tapped and disappearing = navigation started = DONE."""

FORM_RULES = """\
MULTI-FIELD FORMS: Never generate two consecutive "type" actions.
Correct: tap field → type value → tap next field → type value.
After typing, your NEXT step MUST be a tap on the next field.
Include the field name in both target and field_hint for type actions."""

DIALOG_RULES = """\
PERMISSION / SYSTEM DIALOG VISIBLE: Must be handled before anything else — no element behind it is tappable.
If the goal requires the permission → tap Allow/OK/Continue.
If not → tap Deny/Not now/Skip.
For confirmation dialogs (Delete, Purchase, Block): tap the confirming button to complete the action, not Cancel."""

TOGGLE_RULES = """\
TOGGLE / BINARY CONTROL: Read the control's CURRENT VISUAL STATE before tapping.
If the state already matches the goal (e.g. goal="enable dark mode" and toggle is ON) → do NOT tap.
Tapping an already-correct toggle REVERSES the desired state. Use action_type "wait", goal_complete: true."""

SEARCH_RULES = """\
SEARCH RESULTS vs SEARCH FIELD: After typing in a search field, results appear BELOW the field.
When tapping a result, tap the RESULT ROW in the content list — NEVER tap the search field text itself.
The search field shows your query but tapping it just re-focuses the field."""

SCROLL_GUARD_RULES = """\
INFINITE SCROLL GUARD: 3+ consecutive scrolls in the same direction without progress = the target is NOT here.
Change strategy: scroll back to top, use search, or navigate differently. Do NOT generate another scroll."""

PARTICIPANT_PICKER_RULES = """\
PARTICIPANT / CONTACT PICKER SCREEN (Screen A of group creation) — READ THE SCREEN, NOT THE PHASE:
Recognise Screen A by: EditText with hint 'Search name or number…' at the top, scrollable contact list, 'Next' button.
  NOTE: If 'New group' / 'New contact' / 'New community' options are visible instead of a search EditText,
  you are on Screen 0 ('Select contact') — NOT Screen A. Tap 'New group' on Screen 0 first.
On Screen A (participant picker):
• DO NOT type the group name here. The group NAME field does not exist on this screen.
• Action: type each participant's name in the search field → tap their contact row to select → repeat → tap Next.
• A FOCUSED EditText with hint 'Search name or number' = type a CONTACT NAME, nothing else."""

WHATSAPP_NEW_GROUP_RULES = """\
WHATSAPP GROUP CREATION — THREE-SCREEN SEQUENCE (must follow in order):

  Screen 0 — "Select contact" (entry after tapping the 'New chat' FAB):
    Recognise it by: title 'Select contact', options 'New group' / 'New contact' / 'New community' at top, then a flat contact list.
    ► REQUIRED ACTION: Tap 'New group'. Do NOT tap Search, do NOT tap any contact row here.
    You are NOT yet inside the group creation flow until you tap 'New group'.

  Screen A — "Add participants" (after tapping 'New group'):
    Recognise it by: EditText with hint 'Search name or number…' at the top, contact list, 'Next' button (floating or in toolbar).
    ► REQUIRED ACTION: Type each participant's name in the search field → tap their contact row to select (checkmark appears) → clear and repeat for the next person → tap 'Next' when ALL participants are selected.
    Do NOT type the group name here — that field does not exist on this screen.

  Screen B — "Group name" (after tapping 'Next'):
    Recognise it by: a labelled 'Group name' or 'Group subject' text field.
    ► REQUIRED ACTION: Type the group name → tap the checkmark/create button.

CRITICAL RULE: If you see 'New group' as a tappable option on screen → you are on Screen 0. Tap it immediately. Do NOT search for contacts on Screen 0."""


def get_contextual_rules(screen_context: str, phase: str = "") -> str:
    """Return only the rules relevant to the current screen state.

    Keeps the reactive step prompt lean by injecting situational rules
    instead of including everything on every call.
    """
    rules: list[str] = []
    ctx = (screen_context or "").lower()
    phase_lower = (phase or "").lower()

    if "keyboard: visible" in ctx or "keyboard visible" in ctx:
        rules.append(KEYBOARD_RULES)

    if any(w in ctx for w in ("autocomplete", "suggestion", "dropdown", "contact card")):
        rules.append(AUTOCOMPLETE_RULES)

    if any(w in ctx for w in ("loading", "spinner", "buffering", "progress bar")):
        rules.append(LOADING_RULES)

    if any(w in ctx for w in ("play", "pause", "music", "spotify", "youtube", "player", "now playing")):
        rules.append(MEDIA_RULES)

    if any(w in ctx for w in ("maps", "waze", "navigation", "directions", "route")):
        rules.append(NAV_APP_RULES)
        rules.append(NAV_COMPLETION_RULES)

    if any(w in ctx for w in ("form", "field", "input", "edittext", "compose", "email")):
        rules.append(FORM_RULES)

    if any(w in ctx for w in ("dialog", "permission", "allow", "overlay", "modal", "popup")):
        rules.append(DIALOG_RULES)

    if any(w in ctx for w in ("toggle", "switch", "checkbox", "follow", "subscribe")):
        rules.append(TOGGLE_RULES)

    if any(w in ctx for w in ("search", "result")):
        rules.append(SEARCH_RULES)

    # Always include scroll guard after a few steps (cheap and universal)
    if any(w in phase_lower for w in ("scroll", "find", "look for", "search")):
        rules.append(SCROLL_GUARD_RULES)

    # Participant/contact picker screen: fires on common picker screen cues
    picker_ctx_signals = ("search name or number", "add participants", "select contact", "add members")
    picker_phase_signals = ("participant", "select contact", "add john", "add max", "add members")
    if (
        any(w in ctx for w in picker_ctx_signals)
        or any(w in phase_lower for w in picker_phase_signals)
    ):
        rules.append(PARTICIPANT_PICKER_RULES)

    # WhatsApp group creation: fires whenever the task involves creating or navigating to a group.
    # Uses broad signals — phase "Select John and Max as group participants" only contains "group"
    # and "participant", so we match on those rather than requiring "new group" / "create group".
    group_creation_signals = ("new group", "create group", "group named", "group called", "group subject")
    group_participant_signals = ("group participant", "group member", "select participant", "add participant")
    if (
        any(w in phase_lower or w in ctx for w in group_creation_signals)
        or any(w in phase_lower for w in group_participant_signals)
    ):
        rules.append(WHATSAPP_NEW_GROUP_RULES)

    return "\n\n".join(rules)
