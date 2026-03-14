"""
Screen VLM Agent — unified visual perception for AURA.

Merges screen description, target location, and before/after comparison
into a single agent. Uses hybrid OmniParser architecture for location:
1. UI Tree matching (Layer 1 - fast, primary)
2. CV Detection + VLM Selection (Layer 2+3 - fallback)

VLM NEVER generates coordinates directly. It only selects from
geometrically valid CV-detected candidates, eliminating spatial hallucination.
"""

from typing import Dict, List, Optional

from perception.models import PerceptionBundle
from services.vlm import VLMService
from utils.logger import get_logger

logger = get_logger(__name__)


class ScreenVLM:
    """
    Unified visual perception agent: screen description, target location,
    and before/after comparison.

    Location uses OmniParser architecture:
    1. UI Tree first (fast path for 70-80% of cases)
    2. CV Detection + VLM Selection fallback (for WebView/Canvas)
    
    The VLM never predicts coordinates - only selects from CV candidates.
    """

    def __init__(self, vlm_service: VLMService, perception_pipeline=None):
        self.vlm_service = vlm_service
        self._perception_pipeline = perception_pipeline  # Accept pre-built pipeline
        logger.info("✅ ScreenVLM agent initialized")

    def build_annotated_screenshot(
        self,
        screenshot_b64: str,
        elements: list,
        screen_width: int = 1080,
        screen_height: int = 1920,
    ) -> tuple:
        """Draw numbered SoM boxes onto a screenshot and return (annotated_b64, filtered_elements).

        The returned filtered_elements list contains only the elements that were
        actually annotated on the image, in the same order as their numbered labels.
        Callers MUST use this list (not the original unfiltered elements) when
        building text prompts so that element numbers match the image annotations.

        Falls back to (original_screenshot_b64, []) if cv2 is unavailable or annotation fails.
        """
        if not elements or not screenshot_b64:
            return screenshot_b64, []
        try:
            import base64 as _b64
            import cv2
            import numpy as np

            screen_area = screen_width * screen_height
            meaningful = []
            for el in elements:
                b = el.get("bounds") or el.get("visibleBounds") or el.get("boundsInScreen") or {}
                left, top, right, bottom = (
                    b.get("left", 0), b.get("top", 0),
                    b.get("right", 0), b.get("bottom", 0),
                )
                if right <= left or bottom <= top:
                    continue
                if (right - left) * (bottom - top) > screen_area * 0.6:
                    continue
                meaningful.append((el, left, top, right, bottom))

            if not meaningful:
                return screenshot_b64, []

            arr = np.frombuffer(_b64.b64decode(screenshot_b64), dtype=np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img is None:
                return screenshot_b64, []

            h_img, w_img = img.shape[:2]
            font = cv2.FONT_HERSHEY_DUPLEX
            font_scale, font_thick = 1.0, 2
            pad = 6

            overlay = img.copy()
            for el, left, top, right, bottom in meaningful:
                color = (60, 200, 80) if el.get("clickable") else (200, 120, 40) if el.get("scrollable") else (130, 110, 200)
                cv2.rectangle(overlay, (left, top), (right, bottom), color, -1)
            cv2.addWeighted(overlay, 0.20, img, 0.80, 0, img)

            # Pre-compute badge rects, then nudge overlapping ones
            badge_rects = []
            for _i, (el, left, top, right, bottom) in enumerate(meaningful):
                label = str(_i + 1)
                (tw, th), _ = cv2.getTextSize(label, font, font_scale, font_thick)
                bx1, by1 = left, top
                bx2 = bx1 + tw + pad * 2
                by2 = by1 + th + pad * 2
                badge_rects.append((bx1, by1, bx2, by2))

            for _i in range(len(badge_rects)):
                bx1, by1, bx2, by2 = badge_rects[_i]
                bw, bh = bx2 - bx1, by2 - by1
                for _j in range(_i):
                    ox1, oy1, ox2, oy2 = badge_rects[_j]
                    if bx1 < ox2 and bx2 > ox1 and by1 < oy2 and by2 > oy1:
                        by1 = oy2 + 2
                        by2 = by1 + bh
                bx2 = min(bx1 + bw, w_img - 1)
                by2 = min(by2, h_img - 1)
                badge_rects[_i] = (bx1, by1, bx2, by2)

            for _i, (el, left, top, right, bottom) in enumerate(meaningful):
                label = str(_i + 1)
                color = (0, 255, 0) if el.get("clickable") else (0, 165, 255) if el.get("scrollable") else (255, 100, 255)
                cv2.rectangle(img, (left, top), (right, bottom), color, 2)
                bx1, by1, bx2, by2 = badge_rects[_i]
                (tw, th), _ = cv2.getTextSize(label, font, font_scale, font_thick)
                cv2.rectangle(img, (bx1 - 2, by1 - 2), (bx2 + 2, by2 + 2), (0, 0, 0), -1)
                cv2.rectangle(img, (bx1, by1), (bx2, by2), (0, 0, 0), -1)
                cv2.putText(img, label, (bx1 + pad, by1 + th + pad),
                            font, font_scale, (0, 255, 255), font_thick, cv2.LINE_AA)

            _, buf = cv2.imencode(".png", img)
            return _b64.b64encode(buf).decode("utf-8"), [el for el, *_ in meaningful]
        except Exception as _err:
            logger.warning(f"build_annotated_screenshot failed ({_err}), using plain screenshot")
            return screenshot_b64, []

    # ── Screen description ─────────────────────────────────────────────

    async def describe_screen(
        self,
        bundle: PerceptionBundle,
        focus: str = "general",
        goal: str = "",
        subgoal_hint: str = "",
        recent_steps: str = "",
    ) -> str:
        """Describe the current screen content using PerceptionBundle."""
        try:
            modality_str = bundle.modality.value if hasattr(bundle.modality, 'value') else str(bundle.modality)
            logger.info(f"📖 ScreenVLM: Describing screen (focus: {focus}, modality={modality_str})")

            screenshot_b64 = None
            if bundle.screenshot:
                screenshot_b64 = bundle.screenshot.screenshot_base64

            ui_elements_text = ""
            if bundle.ui_tree:
                elements = bundle.ui_tree.elements
                element_list = []
                for i, elem in enumerate(elements):
                    desc = f"{i+1}. {elem.get('className', 'element')}"
                    label = (elem.get('text') or elem.get('contentDescription') or '').strip()
                    # For input fields with no text/desc, use the placeholder hint
                    # so the VLM can identify which field is which (e.g. Gmail To field)
                    if not label:
                        placeholder = (elem.get('hint') or elem.get('hintText') or '').strip()
                        editable = (elem.get('editable') or elem.get('isEditable')
                                    or bool(elem.get('inputType') and elem.get('inputType') not in (0, '0', 'none'))
                                    or any(kw in (elem.get('className') or '').lower()
                                           for kw in ('edittext','textinput','recipient','searchview','pinview','otpview')))
                        if placeholder and editable:
                            label = f"[placeholder: {placeholder}]"
                    if label:
                        desc += f": '{label[:80]}'"
                    if elem.get('editable') or elem.get('isEditable') or any(
                        kw in (elem.get('className') or '').lower()
                        for kw in ('edittext','textinput','recipient','searchview','pinview','otpview')
                    ):
                        desc += " [editable]"
                    elif elem.get('clickable'):
                        desc += " [tap]"
                    element_list.append(desc)
                ui_elements_text = "\n".join(element_list)

            focus_supplements = {
                "general": "",
                "text": "EXTRA: Reproduce important text labels, article titles, and body text verbatim.",
                "buttons": "EXTRA: List ALL tappable buttons, icons, and links with their exact label text.",
                "navigation": "EXTRA: Trace every navigation path available — tabs, menus, back button, drawers, deep-link banners.",
                "webview": "EXTRA: This screen renders web content. List every product/result name, price, rating, and availability text visible. Note any pagination, 'Load more', or infinite scroll indicators.",
            }
            focus_supplement = focus_supplements.get(focus, f"Focus especially on: {focus}")

            prompt = f"""You are the visual perception module for an Android automation agent. Your description is the agent's ONLY view of the screen — be precise, complete, and enumerate everything visible.

{"=== AGENT MISSION ===" if (goal or subgoal_hint or recent_steps) else ""}
{f"OVERALL GOAL:   {goal}" if goal else ""}
{f"CURRENT STEP:   {subgoal_hint}" if subgoal_hint else ""}
{f"STEPS DONE:     {recent_steps}" if recent_steps else ""}
{("Pay special attention to elements directly relevant to the current step." if subgoal_hint else "")}

{"=== ACCESSIBILITY HINTS (text labels from UI tree) ===" if ui_elements_text else ""}
{ui_elements_text[:8000] if ui_elements_text else ""}

=== YOUR TASK ===
Analyze the screenshot and produce a structured screen report using the sections below.
Fill every section that applies. Omit a section only if it genuinely has nothing to report.
The agent cannot see the screen — every detail you skip is invisible to it.

APP & SCREEN: [app name] | [screen or section name]
  e.g. "WhatsApp | Chat list", "Amazon | Search results for 'iphone 15'", "YouTube | Home feed"

NAVIGATION: [navigation elements visible and their active/inactive state]
  e.g. "Bottom tabs: Chats (ACTIVE), Status, Channels, Calls | Top: Search icon, Camera icon, Menu ⋮"

CONTENT: [ALL visible content — enumerate lists completely, never summarize them as a category]
  Chat/contact/message lists → every visible name and preview:
    "Shivram Jandhu – 'ok da' – 2:14 PM | Mom – 'Call me' – Yesterday | Work Group – '🎉' – Mon"
  Search results / product cards → every item name, price, key attribute:
    "iPhone 15 Pro 256GB ₹1,34,900 | iPhone 14 ₹69,900 | Samsung Galaxy S24 Ultra ₹1,29,999"
  Menu options / settings → every option listed
  Feed / article → headline(s) and key visible text

INPUT FIELDS: [each visible text input, search bar, or form field and its current value or placeholder]
  e.g. "Search bar: empty" | "To: 'mom@email.com', Subject: 'Dinner'" | "None"

ACTIVE STATE: [what tab, toggle, checkbox, radio button, or filter is currently selected/active]
  e.g. "All tab active | Dark mode ON | Sort: Relevance selected" | "None"

KEYBOARD: [Hidden] or [Visible — covering lower portion of screen]

BLOCKER: Check ALL of the following and report any that apply (say [None] only if none apply):
  1. Dialogs, popups, permission prompts, loading spinners, or error messages blocking main content
     e.g. "Dialog: 'Choose your delivery location' with OK / Cancel buttons"
  2. If CURRENT STEP specifies a tap/swipe target — is that element visible in the current viewport?
     If NOT visible: "TARGET NOT VISIBLE: '[target name]' is not in the current viewport — scroll down to reveal it"
  3. If CURRENT STEP is a type/input action — is the target input field actively focused (cursor visible / keyboard open)?
     If NOT focused: "INPUT NOT FOCUSED: '[field name]' exists but is not focused — tap it first before typing"

{focus_supplement}

RULES:
- Use the EXACT text as it appears on screen (copy button labels and item names verbatim).
- NEVER write "list items", "several items", or "various options" — always list the actual names.
- Do not add filler phrases like "The screen shows" or "I can see".
- Keep each section on one line or use | as a separator between items."""

            if not screenshot_b64:
                logger.warning("No screenshot available, using UI elements only")
                if ui_elements_text:
                    return self._describe_from_ui_elements(bundle.ui_tree.elements, focus)
                elem_count = len(bundle.ui_tree.elements) if bundle.ui_tree else 0
                return f"I can see the screen has {elem_count} UI elements, but I couldn't get more details."

            description = self.vlm_service.analyze_image(screenshot_b64, prompt, agent="ScreenVLM")
            description = description.strip()

            logger.info(f"✅ Screen description: {description[:100]}...")
            return description

        except Exception as e:
            logger.error(f"ScreenVLM describe_screen failed: {e}", exc_info=True)
            elem_count = len(bundle.ui_tree.elements) if bundle.ui_tree else 0
            return f"I can see the screen has {elem_count} elements, but I couldn't generate a detailed description due to an error."

    async def describe_and_locate(
        self,
        bundle,
        target: str,
        subgoal_hint: str = "",
        goal: str = "",
        recent_steps: str = "",
        ui_elements_text: str = "",
        elements: Optional[List[Dict]] = None,
    ) -> dict:
        """
        Combined call: describe screen AND locate target element in one VLM call.
        Generates a SoM-annotated screenshot (numbered boxes) so the VLM sees
        the same visual annotations as locate_with_annotated_ui_tree — eliminating
        the previous dual-call pattern (separate describe + separate locate).
        Resolves x/y internally so the caller gets pixel coordinates directly.
        Returns dict with keys: description (str), element_id (str|None),
                                 x (int|None), y (int|None), blocker (str), confidence (float)
        """
        screenshot_b64 = None
        if bundle.screenshot:
            screenshot_b64 = bundle.screenshot.screenshot_base64
        if not screenshot_b64:
            return {"description": "", "element_id": None, "x": None, "y": None, "blocker": ""}

        # Build annotated (SoM) image so the VLM sees numbered boxes on screen.
        # Uses the same filtering + drawing logic as locate_with_annotated_ui_tree.
        annotated_b64 = screenshot_b64  # fallback: plain screenshot
        meaningful: list = []
        element_summary = ui_elements_text  # fallback: caller-provided text
        if elements:
            try:
                import base64 as _b64
                import cv2
                import numpy as np
                screen_width = getattr(getattr(bundle, "screen_meta", None), "width", 0) or 1080
                screen_height = getattr(getattr(bundle, "screen_meta", None), "height", 0) or 1920
                screen_area = screen_width * screen_height

                # Filter ghost containers + invalid / full-screen elements
                for el in elements:
                    b = el.get("bounds") or el.get("visibleBounds") or el.get("boundsInScreen") or {}
                    left, top, right, bottom = (
                        b.get("left", 0), b.get("top", 0),
                        b.get("right", 0), b.get("bottom", 0),
                    )
                    if right <= left or bottom <= top:
                        continue
                    if (right - left) * (bottom - top) > screen_area * 0.6:
                        continue
                    meaningful.append((el, left, top, right, bottom))

                if meaningful:
                    arr = np.frombuffer(_b64.b64decode(screenshot_b64), dtype=np.uint8)
                    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                    if img is not None:
                        h_img, w_img = img.shape[:2]
                        font = cv2.FONT_HERSHEY_DUPLEX
                        font_scale, font_thick = 1.0, 2
                        pad = 6
                        # Pass 1: semi-transparent tint
                        overlay = img.copy()
                        for _i, (el, left, top, right, bottom) in enumerate(meaningful):
                            color = (60, 200, 80) if el.get("clickable") else (200, 120, 40) if el.get("scrollable") else (130, 110, 200)
                            cv2.rectangle(overlay, (left, top), (right, bottom), color, -1)
                        cv2.addWeighted(overlay, 0.20, img, 0.80, 0, img)
                        # Pre-compute badge rects, then nudge overlapping ones
                        badge_rects = []
                        for _i, (el, left, top, right, bottom) in enumerate(meaningful):
                            label = str(_i + 1)
                            (tw, th), _ = cv2.getTextSize(label, font, font_scale, font_thick)
                            bx1, by1 = left, top
                            bx2 = bx1 + tw + pad * 2
                            by2 = by1 + th + pad * 2
                            badge_rects.append((bx1, by1, bx2, by2))
                        for _i in range(len(badge_rects)):
                            bx1, by1, bx2, by2 = badge_rects[_i]
                            bw, bh = bx2 - bx1, by2 - by1
                            for _j in range(_i):
                                ox1, oy1, ox2, oy2 = badge_rects[_j]
                                if bx1 < ox2 and bx2 > ox1 and by1 < oy2 and by2 > oy1:
                                    by1 = oy2 + 2
                                    by2 = by1 + bh
                            bx2 = min(bx1 + bw, w_img - 1)
                            by2 = min(by2, h_img - 1)
                            badge_rects[_i] = (bx1, by1, bx2, by2)
                        # Pass 2: solid outline + number badge
                        for _i, (el, left, top, right, bottom) in enumerate(meaningful):
                            label = str(_i + 1)
                            color = (0, 255, 0) if el.get("clickable") else (0, 165, 255) if el.get("scrollable") else (255, 100, 255)
                            cv2.rectangle(img, (left, top), (right, bottom), color, 2)
                            bx1, by1, bx2, by2 = badge_rects[_i]
                            (tw, th), _ = cv2.getTextSize(label, font, font_scale, font_thick)
                            cv2.rectangle(img, (bx1 - 2, by1 - 2), (bx2 + 2, by2 + 2), (0, 0, 0), -1)
                            cv2.rectangle(img, (bx1, by1), (bx2, by2), (0, 0, 0), -1)
                            cv2.putText(img, label, (bx1 + pad, by1 + th + pad),
                                        font, font_scale, (0, 255, 255), font_thick, cv2.LINE_AA)
                        _, buf = cv2.imencode(".png", img)
                        annotated_b64 = _b64.b64encode(buf).decode("utf-8")
                        # Build element summary from filtered meaningful list
                        summary_lines = []
                        for _i, (el, *_) in enumerate(meaningful):
                            text = (el.get("text") or "").strip()[:40]
                            desc = (el.get("contentDescription") or "").strip()[:40]
                            cls = (el.get("className") or "").split(".")[-1]
                            label_text = text or desc or f"{cls} (image-only)"
                            clickable = " [tap]" if el.get("clickable") else ""
                            summary_lines.append(f"{_i + 1}. {label_text}{clickable}")
                        element_summary = "\n".join(summary_lines[:80])
            except Exception as _ann_err:
                logger.warning(f"describe_and_locate: annotation failed ({_ann_err}), using plain screenshot")
                meaningful = []

        using_annotated = annotated_b64 is not screenshot_b64
        annotation_note = (
            "The screenshot has numbered boxes drawn on UI elements (SoM annotation). "
            "Use the box numbers to identify the target.\n\n"
            "⚠️  VISUAL VERIFICATION REQUIRED: The accessibility tree may contain elements "
            "that are off-screen, behind overlapping windows, or not rendered in the current view. "
            "BEFORE choosing any element number, LOOK at the annotated screenshot and confirm "
            "you can SEE a visible numbered box for that element on screen. "
            "If you cannot see a numbered box for an element in the screenshot, it is NOT on this "
            "screen — do NOT pick it. Set not_found=true instead.\n\n"
            "VISUAL TRUST RULE — Screenshot geometry is ground truth; element labels are untrusted hints. "
            "A numbered box that covers most of the screen height or width is a GHOST CONTAINER — "
            "not a real input or button. Ignore it and look for a smaller compact box inside it. "
            "Real inputs are compact rectangles. Buttons have visible text. Containers are large. "
            "When a label contradicts the visual shape: trust the shape, ignore the label."
            if using_annotated else
            "No visual annotations available — use the accessibility hints below."
        )

        prompt = f"""You are the visual perception module for an Android automation agent.

=== AGENT MISSION ===
OVERALL GOAL:   {goal}
CURRENT STEP:   {subgoal_hint}
STEPS DONE:     {recent_steps}

{annotation_note}

=== NUMBERED UI ELEMENTS (match the numbered boxes on the annotated screenshot) ===
{element_summary[:8000]}

=== YOUR TASK ===
Do BOTH of the following in ONE response:

PART A — Screen report:
APP & SCREEN: ...
NAVIGATION: ...
CONTENT: ...
INPUT FIELDS: ...
ACTIVE STATE: ...
KEYBOARD: ...
BLOCKER: ...

PART B — Target location:
TARGET TO FIND: "{target}"
{"Look at the annotated screenshot and find which numbered box visually matches the target. ONLY pick an element whose numbered box is VISIBLE in the screenshot — if you cannot see a box for that element on screen, it is not present here. Return not_found if the target is not visually present." if using_annotated else "Look at the accessibility hints above to find which element matches the target."}
Respond with JSON on the LAST LINE of your response (after the screen report):
{{"element_id": "12", "element_description": "brief label of the chosen element", "confidence": 0.95, "not_found": false}}
If the target is not visible: {{"element_id": null, "element_description": "", "confidence": 0.0, "not_found": true}}

DISAMBIGUATION RULE — when the target text matches both an input field and a content row:
- An EditText / SearchView / TextInput containing the target text is the TYPED VALUE
  inside a search/input field — it is NOT the element you should pick.
- The element you want is the RESULT ROW / LIST ITEM / CHAT ENTRY below the input.
- Example: target "Shankar" — element 3 EditText 'Shankar' = search bar (WRONG),
  element 12 contact row 'Shankar' = correct (PICK THIS).
- Always prefer the content row over the input field match.

SEARCH SUGGESTION RULE — when autocomplete suggestions appear under a search bar after typing:
- Suggestion rows are separate tappable buttons listed BELOW the EditText.
- If the target EXACTLY matches a suggestion row button, pick THAT ROW — not the EditText.
- NEVER pick a partial-match suggestion (e.g. "iphone 17 pro case") when an exact match
  ("iphone 17 pro") exists as a separate row, even if it is lower in the list.
- Example: element 16 EditText 'iphone 17 pro' (search bar) vs element 18 Button 'iphone 17 pro'
  (suggestion row) → pick element 18. Do NOT pick element 19 'iphone 17 pro case'.
- If NO exact match row exists, set not_found=true so the agent presses Enter instead."""

        try:
            import json, re
            raw = self.vlm_service.analyze_image(annotated_b64, prompt, agent="ScreenVLM")

            json_match = re.search(r'\{[^{}]*"element_id"[^{}]*\}', raw)
            if not json_match:
                return {"description": raw.strip(), "element_id": None,
                        "x": None, "y": None, "blocker": ""}

            description = raw[:json_match.start()].strip()
            location = json.loads(json_match.group())

            blocker = ""
            for line in description.splitlines():
                if line.strip().upper().startswith("BLOCKER:"):
                    blocker = line.split(":", 1)[1].strip()
                    break

            if location.get("not_found"):
                return {"description": description, "element_id": None,
                        "x": None, "y": None, "blocker": blocker}

            element_id = location.get("element_id")
            confidence = float(location.get("confidence", 0.92))
            elem_desc_from_vlm = (location.get("element_description") or "").strip()

            # Resolve element_id → pixel coordinates from the filtered meaningful list.
            # This avoids the index mismatch that occurs when the caller tries to look up
            # the id in the raw (unfiltered) elements list.
            x, y = None, None
            highlighted_b64 = None
            elem_desc = elem_desc_from_vlm
            if element_id is not None and meaningful:
                nums = re.findall(r"\d+", str(element_id))
                if nums:
                    idx = int(nums[0]) - 1
                    if 0 <= idx < len(meaningful):
                        el, left, top, right, bottom = meaningful[idx]
                        cx, cy = (left + right) // 2, (top + bottom) // 2
                        if cx > 0 and cy > 0:
                            x, y = cx, cy
                            if not elem_desc:
                                elem_desc = (el.get("text") or el.get("contentDescription") or "").strip()
                            logger.info(
                                f"✅ describe_and_locate: '{target}' at ({x}, {y}) "
                                f"via element {idx + 1} (annotated={using_annotated})"
                            )
                            # Generate highlighted screenshot for this element
                            try:
                                import base64 as _b64_h
                                import cv2 as _cv2h
                                import numpy as _nph
                                arr2 = _nph.frombuffer(_b64_h.b64decode(screenshot_b64), dtype=_nph.uint8)
                                h_img2 = _cv2h.imdecode(arr2, _cv2h.IMREAD_COLOR)
                                if h_img2 is not None:
                                    _cv2h.rectangle(h_img2, (left - 3, top - 3), (right + 3, bottom + 3), (0, 255, 255), 4)
                                    _cv2h.rectangle(h_img2, (left - 1, top - 1), (right + 1, bottom + 1), (0, 0, 0), 2)
                                    _font2 = _cv2h.FONT_HERSHEY_SIMPLEX
                                    badge = f"#{idx + 1}: {elem_desc[:30]}"
                                    (tw2, th2), _ = _cv2h.getTextSize(badge, _font2, 0.65, 2)
                                    bx2 = min(left + tw2 + 8, h_img2.shape[1] - 1)
                                    _cv2h.rectangle(h_img2, (left, top - th2 - 8), (bx2, top), (0, 255, 255), -1)
                                    _cv2h.putText(h_img2, badge, (left + 4, top - 4), _font2, 0.65, (0, 0, 0), 2, _cv2h.LINE_AA)
                                    _, buf2 = _cv2h.imencode(".png", h_img2)
                                    highlighted_b64 = _b64_h.b64encode(buf2).decode("utf-8")
                            except Exception:
                                pass

            return {
                "description": description,
                "element_id": element_id,
                "element_description": elem_desc,
                "x": x,
                "y": y,
                "blocker": blocker,
                "confidence": confidence,
                "highlighted_b64": highlighted_b64,
            }
        except Exception as e:
            logger.warning(f"describe_and_locate failed ({e}) — caller should use separate calls")
            return {"description": "", "element_id": None, "x": None, "y": None, "blocker": ""}

    async def compare_screens(
        self,
        before_b64: str,
        after_b64: str,
        action_description: str,
        cart_count_before: Optional[int] = None,
    ) -> tuple:
        """Compare before/after screenshots to verify a commit action succeeded."""
        baseline = ""
        if cart_count_before is not None:
            baseline = f"\nCart/basket item count BEFORE the action: {cart_count_before}. Confirm it increased."

        prompt = f"""You are verifying whether a mobile action succeeded.

IMAGE 1 (BEFORE): The screen state before the action.
IMAGE 2 (AFTER): The screen state after the action.

ACTION PERFORMED: {action_description}{baseline}

Answer ONLY with a JSON object:
{{
  "succeeded": true or false,
  "evidence": "one sentence describing what changed that confirms or denies success",
  "confidence": 0.0 to 1.0
}}

Success signals to look for:
- Cart badge count increased
- "Added to cart" / "Item added" overlay appeared
- Confirmation screen / order summary shown
- Message delivery tick appeared
- Item count or total price changed"""

        try:
            result = self.vlm_service.analyze_two_images(before_b64, after_b64, prompt)
            import json, re
            match = re.search(r"\{.*\}", result, re.DOTALL)
            if match:
                parsed = json.loads(match.group())
                succeeded = bool(parsed.get("succeeded", False))
                evidence = parsed.get("evidence", result[:100])
                return succeeded, evidence
        except Exception as e:
            logger.warning(f"compare_screens failed ({e}), falling back to describe_screen")
        return None, ""

    def _describe_from_ui_elements(self, elements: list, focus: str = "general") -> str:
        """Generate a description from UI elements when no screenshot is available."""
        try:
            texts = []
            buttons = []
            app_name = None

            for elem in elements:
                class_name = elem.get("className", "").lower()
                text = elem.get("text", "").strip()
                content_desc = elem.get("contentDescription", "").strip()
                clickable = elem.get("clickable", False)

                if not app_name and ("actionbar" in class_name or "toolbar" in class_name):
                    if text:
                        app_name = text

                if text and len(text) > 1:
                    texts.append(text)
                elif content_desc and len(content_desc) > 1:
                    texts.append(content_desc)

                if clickable and (text or content_desc):
                    buttons.append(text or content_desc)

            parts = []
            if app_name:
                parts.append(f"You're in {app_name}.")

            unique_texts = list(dict.fromkeys(texts))[:10]
            if unique_texts:
                text_summary = ", ".join(unique_texts[:5])
                if len(text_summary) > 150:
                    text_summary = text_summary[:150] + "..."
                parts.append(f"I can see: {text_summary}.")

            unique_buttons = list(dict.fromkeys(buttons))[:5]
            if unique_buttons:
                parts.append(f"Available actions include: {', '.join(unique_buttons[:3])}.")

            return " ".join(parts) if parts else "Screen content could not be determined from UI elements."
        except Exception as e:
            logger.error(f"_describe_from_ui_elements failed: {e}")
            return "Unable to describe screen from UI elements."

    # ── Element location ───────────────────────────────────────────────

    @property
    def perception_pipeline(self):
        """Lazy-init the perception pipeline to avoid heavy imports at startup."""
        if self._perception_pipeline is None:
            try:
                from perception.perception_pipeline import create_perception_pipeline
                self._perception_pipeline = create_perception_pipeline(self.vlm_service)
                logger.info("✅ OmniParser perception pipeline initialized")
            except ImportError as e:
                logger.warning(f"OmniParser not available, using legacy mode: {e}")
                self._perception_pipeline = None
        return self._perception_pipeline

    def locate_element(
        self,
        screenshot_b64: str,
        element_description: str,
        screen_width: int,
        screen_height: int,
    ) -> Optional[Dict[str, int]]:
        """
        Locate an element visually using screenshot.
        
        Called by Perception Controller as part of the perception pipeline.
        Uses hybrid OmniParser architecture when available.
        """
        if not screenshot_b64 or len(screenshot_b64) < 1000:
            logger.warning("Screenshot too small for visual location")
            return None

        # Try hybrid perception pipeline first
        if self.perception_pipeline:
            try:
                result = self.perception_pipeline.locate_element(
                    intent=element_description,
                    ui_tree=None,  # No UI tree for direct visual location
                    screenshot=screenshot_b64,
                    screen_bounds=(screen_width, screen_height),
                )
                
                if result.success:
                    x, y = result.coordinates
                    logger.info(
                        f"✅ Located '{element_description}' at ({x}, {y}) via {result.source} "
                        f"confidence={result.confidence:.2f}"
                    )
                    return {
                        "x": x,
                        "y": y,
                        "confidence": result.confidence,
                        "source": result.source,
                    }
                else:
                    logger.warning(f"Hybrid perception failed: {result.reason}")
                    # Fall through to legacy VLM approach
            except Exception as e:
                logger.warning(f"Hybrid perception error: {e}, falling back to legacy")

        # Legacy fallback: Direct VLM coordinate prediction
        # NOTE: This has spatial hallucination issues - prefer hybrid pipeline
        return self._legacy_vlm_locate(
            screenshot_b64, element_description, screen_width, screen_height
        )

    def _legacy_vlm_locate(
        self,
        screenshot_b64: str,
        element_description: str,
        screen_width: int,
        screen_height: int,
    ) -> Optional[Dict[str, int]]:
        """
        Legacy VLM-based location (has spatial hallucination issues).
        
        Only used as fallback when OmniParser pipeline is unavailable.
        """
        prompt = f"""You are a visual element locator for an Android app.

TASK: Locate "{element_description}" on this screen.

SCREEN SIZE: {screen_width}x{screen_height} pixels

INSTRUCTIONS:
1. Find the element described
2. Identify its center position
3. Express as percentage from top-left (0-100%)

CRITICAL: If the target element is not visible in the current screenshot,
return: {{"found": false, "reason": "not_visible"}}
Do NOT guess coordinates for elements you cannot see.

OUTPUT FORMAT (JSON):
{{"found": true, "x_percent": 50.5, "y_percent": 30.2, "confidence": 0.95}}

If NOT found:
{{"found": false, "reason": "not visible"}}

RESPOND ONLY WITH JSON."""

        try:
            result = self.vlm_service.analyze_image(screenshot_b64, prompt, agent="ScreenVLM")
            logger.debug(f"Legacy VLM locate result: {result}")

            import json
            parsed = json.loads(result.strip().strip("```json").strip("```"))

            if parsed.get("found"):
                x_percent = parsed.get("x_percent", 50)
                y_percent = parsed.get("y_percent", 50)

                x = int((x_percent / 100.0) * screen_width)
                y = int((y_percent / 100.0) * screen_height)

                confidence = parsed.get("confidence", 0.8)
                logger.info(
                    f"✅ Located '{element_description}' at ({x}, {y}) via legacy VLM "
                    f"confidence={confidence}"
                )

                return {"x": x, "y": y, "confidence": confidence, "source": "legacy_vlm"}
            else:
                logger.warning(
                    f"Element '{element_description}' not found: {parsed.get('reason')}"
                )
                return None

        except Exception as e:
            logger.error(f"Legacy visual location failed: {e}")
            return None

    def locate_with_annotated_ui_tree(
        self,
        elements: List[Dict],
        screenshot_b64: str,
        target: str,
        screen_width: int,
        screen_height: int,
        user_command: str = "",
        plan_context: str = "",
        subgoal_description: str = "",
    ) -> Optional[Dict]:
        """
        Primary VLM-assisted target selection.

        Draws numbered bounding boxes for every meaningful UI tree element
        on the screenshot, sends the annotated image + element list + full
        context (command, plan, current step) to the VLM.  VLM returns JSON
        with the element index AND a screen_matches_plan flag so the agent
        can replan if the screen is wrong for this step.
        Always returns annotated_b64 so the caller can save the exact image
        the VLM saw — no index mismatch in debug logs.
        """
        if not elements or not screenshot_b64:
            return None

        try:
            import base64 as _b64
            import re
            import cv2
            import numpy as np
        except ImportError as e:
            logger.warning(f"locate_with_annotated_ui_tree: missing dependency {e}")
            return None

        screen_area = screen_width * screen_height

        # Build list of meaningful elements (filter ghost containers + invalid bounds)
        meaningful: List[tuple] = []
        for el in elements:
            b = el.get("bounds") or el.get("visibleBounds") or el.get("boundsInScreen") or {}
            left, top, right, bottom = (
                b.get("left", 0), b.get("top", 0),
                b.get("right", 0), b.get("bottom", 0),
            )
            if right <= left or bottom <= top:
                continue
            if (right - left) * (bottom - top) > screen_area * 0.6:
                continue
            meaningful.append((el, left, top, right, bottom))

        if not meaningful:
            return None

        # SoM (Set-of-Mark) annotation: semi-transparent tint + solid corner badge
        try:
            arr = np.frombuffer(_b64.b64decode(screenshot_b64), dtype=np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img is None:
                return None

            h_img, w_img = img.shape[:2]
            font = cv2.FONT_HERSHEY_DUPLEX
            font_scale, font_thick = 1.0, 2
            pad = 6

            # Pass 1: semi-transparent tint over each element region
            overlay = img.copy()
            for i, (el, left, top, right, bottom) in enumerate(meaningful):
                if el.get("clickable"):
                    color = (60, 200, 80)
                elif el.get("scrollable"):
                    color = (200, 120, 40)
                else:
                    color = (130, 110, 200)
                cv2.rectangle(overlay, (left, top), (right, bottom), color, -1)
            cv2.addWeighted(overlay, 0.20, img, 0.80, 0, img)

            # Pre-compute badge rects, then nudge overlapping ones
            badge_rects = []
            for i, (el, left, top, right, bottom) in enumerate(meaningful):
                label = str(i + 1)
                (tw, th), _ = cv2.getTextSize(label, font, font_scale, font_thick)
                bx1, by1 = left, top
                bx2 = bx1 + tw + pad * 2
                by2 = by1 + th + pad * 2
                badge_rects.append((bx1, by1, bx2, by2))

            for i in range(len(badge_rects)):
                bx1, by1, bx2, by2 = badge_rects[i]
                bw, bh = bx2 - bx1, by2 - by1
                for j in range(i):
                    ox1, oy1, ox2, oy2 = badge_rects[j]
                    if bx1 < ox2 and bx2 > ox1 and by1 < oy2 and by2 > oy1:
                        by1 = oy2 + 2
                        by2 = by1 + bh
                bx2 = min(bx1 + bw, w_img - 1)
                by2 = min(by2, h_img - 1)
                badge_rects[i] = (bx1, by1, bx2, by2)

            # Pass 2: solid outline + number badge
            for i, (el, left, top, right, bottom) in enumerate(meaningful):
                label = str(i + 1)
                if el.get("clickable"):
                    color = (0, 255, 0)
                elif el.get("scrollable"):
                    color = (0, 165, 255)
                else:
                    color = (255, 100, 255)

                cv2.rectangle(img, (left, top), (right, bottom), color, 2)

                bx1, by1, bx2, by2 = badge_rects[i]
                (tw, th), _ = cv2.getTextSize(label, font, font_scale, font_thick)
                cv2.rectangle(img, (bx1 - 2, by1 - 2), (bx2 + 2, by2 + 2), (0, 0, 0), -1)
                cv2.rectangle(img, (bx1, by1), (bx2, by2), (0, 0, 0), -1)
                cv2.putText(img, label, (bx1 + pad, by1 + th + pad),
                            font, font_scale, (0, 255, 255), font_thick, cv2.LINE_AA)

            # Save as PNG to preserve sharp annotation edges (JPEG blurs them)
            _, buf = cv2.imencode(".png", img)
            annotated_b64 = _b64.b64encode(buf).decode("utf-8")
        except Exception as e:
            logger.warning(f"Failed to draw UI tree annotations: {e}")
            return None

        # Build compact element list for VLM context
        summary_lines = []
        for i, (el, *_) in enumerate(meaningful):
            text = (el.get("text") or "").strip()[:40]
            desc = (el.get("contentDescription") or "").strip()[:40]
            cls = (el.get("className") or "").split(".")[-1]
            label_text = text or desc or cls
            clickable = " [tap]" if el.get("clickable") else ""
            # Mark elements that have no text — VLM must rely on visual content
            if not text and not desc:
                label_text = f"{cls} (image-only, look at visual content)"
            summary_lines.append(f"{i + 1}. {label_text}{clickable}")
        element_summary = "\n".join(summary_lines[:80])

        context_parts = []
        if user_command:
            context_parts.append(f"USER COMMAND: {user_command}")
        if plan_context:
            context_parts.append(f"FULL PLAN:\n{plan_context}")
        if subgoal_description:
            context_parts.append(f"CURRENT STEP: {subgoal_description}")
        context_section = "\n".join(context_parts)

        prompt = f"""You are the perception agent for an Android automation system.

{context_section}

The screenshot has {len(meaningful)} numbered boxes drawn on UI elements.

ELEMENT LIST (number → label):
{element_summary}

TASK: Find which numbered box is the correct element to interact with for the CURRENT STEP.
Also assess: does this screen look correct for the CURRENT STEP, or is the app on the wrong screen?

CRITICAL — VISUAL VERIFICATION REQUIRED:
The accessibility tree may include elements that are off-screen, behind overlapping windows,
or not rendered in the current view. These elements appear in the element list above but
their numbered boxes will NOT be visible in the annotated screenshot.
BEFORE selecting any element number, LOOK at the annotated screenshot and confirm you
can SEE a visible numbered box for that element on screen.
If you cannot see a numbered box for an element in the screenshot, that element is NOT
on the current visible screen — do NOT pick it. Return "not_found" instead.
Do NOT guess or pick by list position alone — visual confirmation is required.

VISUAL TRUST RULE — Screenshot geometry is ground truth; element labels are untrusted hints.
A numbered box that covers most of the screen height or width is a GHOST CONTAINER — not a
real input or button. Ignore it and look for a smaller compact box INSIDE it.
Real inputs are compact rectangles. Buttons have visible text. Containers are large.
When a label contradicts the visual shape: trust the shape, ignore the label.

IMPORTANT: Some elements are marked "image-only" — they have no text in the accessibility tree.
For these, LOOK AT THE VISUAL CONTENT inside the numbered box on the screenshot to determine
what it represents (album art, playlist tile, icon, product image, etc.).

DISAMBIGUATION RULE — when two elements share the same label text:
- An EditText / SearchView / TextInput box containing the target text means the text is
  the TYPED VALUE inside an input field — it is NOT the element you should tap.
- The element you want is the RESULT ROW / LIST ITEM / CHAT ENTRY below or outside the input.
- Example: if target is "Shivram Jandhu" and element 5 is EditText 'Shivram Jandhu' (search bar)
  while element 12 is a chat/contact row 'Shivram Jandhu', you MUST pick element 12.
- This applies to any search bar, address bar, or text input showing the search query.

SEARCH SUGGESTION RULE — when autocomplete suggestions appear under a search bar after typing:
- Suggestion rows are separate tappable buttons listed BELOW the EditText.
- If the target EXACTLY matches a suggestion row button, pick THAT ROW — not the EditText.
- NEVER pick a partial-match suggestion (e.g. "iphone 17 pro case") when an exact match
  ("iphone 17 pro") exists as a separate row, even if it is lower in the list.
- Example: target "iphone 17 pro" — element 16 EditText 'iphone 17 pro' (search bar, WRONG),
  element 18 Button 'iphone 17 pro' (suggestion row, CORRECT) → pick element 18.
- If NO exact match row exists, return "not_found" so the agent can press Enter instead of
  tapping a longer partial match.

Respond ONLY with this JSON (no markdown, no explanation):
{{"element": "<number or not_found>", "element_description": "<brief label of the chosen element>", "screen_ok": true, "deviation": null}}

Rules:
- "element": the box number that best matches the target "{target}" for this step, or "not_found" if absent
- "element_description": the visible text / content description of the chosen element, or "" if not_found
- "screen_ok": IMPORTANT — set to false ONLY if the element is "not_found" AND the screen is completely wrong for the goal (e.g. app crashed to home screen, or Settings opened instead of Gmail). If the target IS found, always set screen_ok to true.
- screen_ok MUST be true whenever element != "not_found". The target being reachable via a different path than planned is NOT a reason to set screen_ok false.
- "deviation": if screen_ok is false, one sentence describing what is wrong and what screen the agent should navigate to instead; otherwise null"""

        try:
            raw = self.vlm_service.analyze_image(annotated_b64, prompt, agent="ScreenVLM").strip()
            logger.info(f"🎯 VLM annotation response for '{target}': {raw!r}")

            import json as _json
            # Strip markdown code fences if present
            cleaned = raw.strip().strip("```json").strip("```").strip()
            try:
                parsed = _json.loads(cleaned)
            except Exception:
                # Fallback: treat raw as a plain number
                parsed = {"element": cleaned, "screen_ok": True, "deviation": None}

            replan_suggested = not parsed.get("screen_ok", True)
            replan_reason = parsed.get("deviation") or ""
            element_val = str(parsed.get("element", "not_found")).strip()

            if "not_found" in element_val.lower():
                logger.info(f"VLM: '{target}' not in UI tree annotations — OmniParser needed")
                return {"annotated_b64": annotated_b64, "replan_suggested": replan_suggested, "replan_reason": replan_reason}

            numbers = re.findall(r"\d+", element_val)
            if not numbers:
                logger.warning(f"VLM returned unparseable element value: {element_val!r}")
                return {"annotated_b64": annotated_b64, "replan_suggested": replan_suggested, "replan_reason": replan_reason}

            idx = int(numbers[0]) - 1
            if not (0 <= idx < len(meaningful)):
                logger.warning(f"VLM index {idx + 1} out of range (max {len(meaningful)})")
                return {"annotated_b64": annotated_b64, "replan_suggested": replan_suggested, "replan_reason": replan_reason}

            el, left, top, right, bottom = meaningful[idx]
            elem_desc = (
                parsed.get("element_description")
                or (el.get("text") or el.get("contentDescription") or "").strip()
            )

            # Generate a plain highlighted screenshot showing only the selected element
            highlighted_b64 = None
            try:
                arr2 = np.frombuffer(_b64.b64decode(screenshot_b64), dtype=np.uint8)
                h_img2 = cv2.imdecode(arr2, cv2.IMREAD_COLOR)
                if h_img2 is not None:
                    cv2.rectangle(h_img2, (left - 3, top - 3), (right + 3, bottom + 3), (0, 255, 255), 4)
                    cv2.rectangle(h_img2, (left - 1, top - 1), (right + 1, bottom + 1), (0, 0, 0), 2)
                    _font = cv2.FONT_HERSHEY_SIMPLEX
                    badge = f"#{idx + 1}: {elem_desc[:30]}"
                    (tw2, th2), _ = cv2.getTextSize(badge, _font, 0.65, 2)
                    bx2 = min(left + tw2 + 8, h_img2.shape[1] - 1)
                    cv2.rectangle(h_img2, (left, top - th2 - 8), (bx2, top), (0, 255, 255), -1)
                    cv2.putText(h_img2, badge, (left + 4, top - 4), _font, 0.65, (0, 0, 0), 2, cv2.LINE_AA)
                    _, buf2 = cv2.imencode(".png", h_img2)
                    highlighted_b64 = _b64.b64encode(buf2).decode("utf-8")
            except Exception:
                pass

            return {
                "x": (left + right) // 2,
                "y": (top + bottom) // 2,
                "text": (el.get("text") or el.get("contentDescription") or target),
                "bounds": {"left": left, "top": top, "right": right, "bottom": bottom},
                "format": "pixels",
                "source": "vlm_annotated_ui_tree",
                "confidence": 0.92,
                "annotated_b64": annotated_b64,
                "replan_suggested": replan_suggested,
                "replan_reason": replan_reason,
                "element_description": elem_desc,
                "highlighted_b64": highlighted_b64,
            }
        except Exception as e:
            logger.warning(f"VLM annotation selection error: {e}")
            return None

    def locate_from_bundle(
        self,
        bundle: "PerceptionBundle",
        element_description: str,
        screen_context: Optional[str] = None,
        user_command: str = "",
        plan_context: str = "",
        subgoal_description: str = "",
    ) -> Optional[Dict[str, int]]:
        """
        Locate element using PerceptionBundle (hybrid mode support).
        
        NOW USES OmniParser hybrid architecture:
        1. First tries UI tree matching (Layer 1 - fast)
        2. Falls back to CV Detection + VLM Selection (Layer 2+3)
        
        VLM NEVER generates coordinates - only selects from CV candidates.
        
        Args:
            bundle: PerceptionBundle from Perception Controller
            element_description: Natural language description of element
            screen_context: Optional VLM screen description for richer selection context
            user_command: Original user utterance for semantic grounding
            plan_context: High-level plan context
            subgoal_description: Current step description
        
        Returns:
            Dict with x, y, confidence, source or None if not found
        """
        from perception.models import PerceptionBundle, PerceptionModality

        context_parts = []
        if screen_context:
            context_parts.append(f"Screen context: {screen_context}")
        if user_command:
            context_parts.append(f"User command: {user_command}")
        if plan_context:
            context_parts.append(f"Plan context: {plan_context}")
        if subgoal_description:
            context_parts.append(f"Current step: {subgoal_description}")
        enriched_intent = element_description
        if context_parts:
            enriched_intent += "\n\n" + "\n".join(context_parts)
        
        # Use hybrid perception pipeline
        if self.perception_pipeline:
            try:
                result = self.perception_pipeline.locate_element(
                    intent=enriched_intent,
                    ui_tree=bundle.ui_tree,
                    screenshot=bundle.screenshot.screenshot_base64 if bundle.screenshot else None,
                    screen_bounds=(bundle.screen_meta.width, bundle.screen_meta.height),
                )
                
                if result.success:
                    logger.info(
                        f"✅ Located '{element_description}' at {result.coordinates} "
                        f"via {result.source} (layers: {result.layer_attempted})"
                    )
                    return {
                        "x": result.coordinates[0],
                        "y": result.coordinates[1],
                        "confidence": result.confidence,
                        "source": result.source,
                        "element_info": result.element_info,
                    }
                else:
                    logger.warning(
                        f"Perception pipeline failed for '{element_description}': "
                        f"{result.reason} (layers: {result.layer_attempted})"
                    )
            except Exception as e:
                logger.warning(f"Perception pipeline error: {e}, trying legacy approach")
        
        # Fallback to legacy approach
        return self._legacy_locate_from_bundle(bundle, enriched_intent)

    def _legacy_locate_from_bundle(
        self,
        bundle: "PerceptionBundle",
        element_description: str,
    ) -> Optional[Dict[str, int]]:
        """Legacy bundle location (UI tree search + VLM fallback)."""
        from perception.models import PerceptionBundle, PerceptionModality
        
        target_lower = element_description.lower()
        
        # 1. Search UI tree first (more reliable when available)
        if bundle.ui_tree:
            best_match = None
            best_score = 0.0
            
            for elem in bundle.ui_tree.elements:
                text = (elem.get("text") or "").lower()
                content_desc = (elem.get("contentDescription") or "").lower()
                resource_id = (elem.get("resourceId") or "").lower()
                
                # Calculate match score
                score = 0.0
                if target_lower == text:
                    score = 1.0
                elif target_lower in text or target_lower in content_desc:
                    score = 0.8
                elif text in target_lower or content_desc in target_lower:
                    score = 0.6
                elif target_lower.replace(" ", "_") in resource_id:
                    score = 0.7
                
                # Check for button keywords
                class_name = (elem.get("className") or "").lower()
                if "button" in target_lower and "button" in class_name:
                    score = max(score, 0.5)
                
                if score > best_score:
                    best_score = score
                    best_match = elem
            
            if best_match and best_score > 0.5:
                bounds = best_match.get("bounds", {})
                if isinstance(bounds, dict) and bounds:
                    left = bounds.get("left", 0)
                    right = bounds.get("right", 0)
                    top = bounds.get("top", 0)
                    bottom = bounds.get("bottom", 0)
                    
                    if right > left and bottom > top:
                        x = (left + right) // 2
                        y = (top + bottom) // 2
                        logger.info(
                            f"✅ Located '{element_description}' via legacy UI tree at ({x}, {y}), "
                            f"confidence={best_score:.2f}"
                        )
                        return {"x": x, "y": y, "confidence": best_score, "source": "legacy_ui_tree"}
        
        # 2. Fall back to visual search if screenshot available
        if bundle.screenshot and bundle.screenshot.screenshot_base64:
            logger.info(f"Legacy UI tree search failed, trying visual search for '{element_description}'")
            return self.locate_element(
                screenshot_b64=bundle.screenshot.screenshot_base64,
                element_description=element_description,
                screen_width=bundle.screen_meta.width,
                screen_height=bundle.screen_meta.height,
            )
        
        logger.warning(f"❌ Could not locate '{element_description}' in bundle")
        return None

    def find_all_clickable_elements(
        self, screenshot_b64: str, screen_width: int, screen_height: int
    ) -> List[Dict]:
        """
        Detect all clickable elements using OmniParser CV.
        
        Returns structured detections with IDs for selection.
        """
        if not screenshot_b64 or len(screenshot_b64) < 1000:
            return []

        # Use OmniParser detector if available
        if self.perception_pipeline:
            try:
                detector = self.perception_pipeline.detector
                detections = detector.detect(screenshot_b64)
                
                elements = []
                for det in detections:
                    elements.append({
                        "id": det.id,
                        "type": det.class_name,
                        "text": "",  # CV detection doesn't provide text
                        "x": det.center[0],
                        "y": det.center[1],
                        "box": list(det.box),
                        "confidence": det.confidence,
                    })
                
                logger.info(f"✅ Found {len(elements)} elements via OmniParser CV")
                return elements
                
            except Exception as e:
                logger.warning(f"OmniParser detection failed: {e}, using legacy VLM")

        # Legacy fallback
        return self._legacy_find_all_elements(screenshot_b64, screen_width, screen_height)

    def _legacy_find_all_elements(
        self, screenshot_b64: str, screen_width: int, screen_height: int
    ) -> List[Dict]:
        """Legacy VLM-based element detection."""
        prompt = f"""Analyze this Android screen and list ALL clickable elements.

SCREEN SIZE: {screen_width}x{screen_height}

OUTPUT (JSON array):
[
  {{"type": "button", "text": "Settings", "x_percent": 85.5, "y_percent": 15.0}},
  {{"type": "icon", "description": "search", "x_percent": 50.0, "y_percent": 10.0}}
]

Include: buttons, icons, text fields, list items, tabs
Position: center of each element as percentage (0-100%)
RESPOND ONLY WITH JSON ARRAY."""

        try:
            result = self.vlm_service.analyze_image(
                screenshot_b64, prompt, max_tokens=2000, agent="ScreenVLM",
            )

            import json
            elements = json.loads(result.strip().strip("```json").strip("```"))

            located_elements = []
            for elem in elements:
                x_percent = elem.get("x_percent", 50)
                y_percent = elem.get("y_percent", 50)

                located_elements.append({
                    "type": elem.get("type", "unknown"),
                    "text": elem.get("text", elem.get("description", "")),
                    "x": int((x_percent / 100.0) * screen_width),
                    "y": int((y_percent / 100.0) * screen_height),
                })

            logger.info(f"✅ Found {len(located_elements)} clickable elements via legacy VLM")
            return located_elements

        except Exception as e:
            logger.error(f"Visual element detection failed: {e}")
            return []

    def verify_element_at_position(
        self, screenshot_b64: str, x: int, y: int, expected_type: str
    ) -> bool:
        """Verify element at position matches expected type."""
        prompt = f"""Look at coordinates ({x}, {y}) on this screen.

Is there a {expected_type} at this position?

RESPOND: yes or no (one word only)"""

        try:
            result = self.vlm_service.analyze_image(
                screenshot_b64, prompt, max_tokens=10, agent="ScreenVLM",
            )
            return result.strip().lower() == "yes"
        except Exception:
            return False

    def get_metrics(self) -> Dict:
        """Get perception pipeline metrics."""
        if self.perception_pipeline:
            return self.perception_pipeline.get_metrics()
        return {}

