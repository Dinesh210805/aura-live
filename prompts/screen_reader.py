"""
Screen Reader Prompts - v1.0.0

Prompts for describing screen content to users.
"""


# =============================================================================
# SCREEN DESCRIPTION PROMPT
# =============================================================================
SCREEN_DESCRIPTION_PROMPT = """You are an Android UI perception agent analyzing a screenshot for an automation system.

{focus_instruction}

{ui_elements}

Analyze this screen and respond in 3-5 sentences covering ONLY these four points:
1. SCREEN IDENTITY: App name and screen/section (e.g. "Amazon search results page" or "WhatsApp chat with John")
2. PRIMARY CONTENT: What is the dominant content visible? (product listing, conversation, article, form, etc.)
3. ACTIONABLE ELEMENTS: Name the most relevant interactive elements you can see right now (buttons, text fields, links, visible items to tap)
4. BLOCKERS: Is there anything obstructing progress — keyboard open, loading spinner, popup/dialog, empty state, error message?

VISUAL TRUST: The screenshot is ground truth — element metadata has bugs and mismatches.
A UI element that spans most of the screen is a ghost container, not a real input or button.
Real inputs are compact rectangles; buttons have text. When labels contradict visual shape, trust the shape.

Be specific and factual. No filler phrases like "The screen shows" or "I can see". Use direct statements.
"""


# =============================================================================
# FOCUS INSTRUCTIONS
# =============================================================================
FOCUS_INSTRUCTIONS = {
    "general": "Identify the screen, its primary content, key actionable elements, and any blockers.",
    "text": "Focus on readable text and labels. List the key text visible on screen.",
    "buttons": "Enumerate all interactive elements: buttons, links, input fields, toggles — include their labels.",
    "navigation": "Describe the screen layout and available navigation paths (tabs, back button, menus).",
    "webview": "This screen contains WebView content. Pay special attention to dynamically rendered elements, product cards, and scroll position that may not be in the accessibility tree.",
}


# =============================================================================
# HELPER FUNCTION
# =============================================================================
def get_screen_description_prompt(
    focus: str = "general",
    ui_elements: str = "",
) -> str:
    """
    Build screen description prompt.
    
    Args:
        focus: What to focus on (general, text, buttons, navigation)
        ui_elements: Optional formatted UI elements list
    """
    focus_instruction = FOCUS_INSTRUCTIONS.get(focus, FOCUS_INSTRUCTIONS["general"])
    
    elements_section = ""
    if ui_elements:
        # Truncate at element boundary (newline) to avoid cutting mid-element
        truncated = ui_elements[:1000]
        if len(ui_elements) > 1000:
            last_nl = truncated.rfind("\n")
            if last_nl > 0:
                truncated = truncated[:last_nl]
        elements_section = f"Available UI Elements:\n{truncated}"
    
    return SCREEN_DESCRIPTION_PROMPT.format(
        focus_instruction=focus_instruction,
        ui_elements=elements_section,
    )
