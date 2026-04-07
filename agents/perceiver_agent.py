"""
Perceiver Agent - Screen understanding and target location.

Wraps PerceptionController to provide structured screen state
for the Coordinator's perceive→decide→act→verify loop.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from services.ui_signature import compute_ui_signature
from utils.logger import get_logger

if TYPE_CHECKING:
    from perception.perception_pipeline import PerceptionPipeline
    from services.perception_controller import PerceptionController
    from perception.models import PerceptionBundle
    from aura_graph.agent_state import StepMemory, Subgoal
    from services.vlm import VLMService

logger = get_logger(__name__)


@dataclass
class ScreenState:
    """Snapshot of the current screen state after perception."""
    perception_bundle: Any  # PerceptionBundle
    ui_signature: str
    elements: List[Dict[str, Any]] = field(default_factory=list)
    target_match: Optional[Dict[str, Any]] = None
    screen_type: str = "unknown"  # native, webview, keyboard_open, empty
    # VLM-generated semantic description, populated when skip_description=False
    screen_description: Optional[str] = None
    # The exact annotated screenshot the VLM saw (for debug logging — same indices)
    vlm_annotated_b64: Optional[str] = None
    # VLM signalled the current screen doesn't match the expected plan step
    replan_suggested: bool = False
    replan_reason: str = ""
    # Highlighted screenshot: original screenshot with only the selected element boxed (for logs)
    highlighted_b64: Optional[str] = None
    # Brief label of the VLM-selected element (text or contentDescription)
    element_description: Optional[str] = None


class PerceiverAgent:
    """
    Perceive the current screen state and locate targets.

    Provides all visual perception capabilities (screen description, element
    location, before/after comparison) — previously split across ScreenVLM and
    PerceiverAgent.

    Call order: create PerceiverAgent first (perception_controller=None), then
    build PerceptionController passing this instance as screen_vlm, then set
    perceiver_agent.perception_controller = controller.
    """

    def __init__(
        self,
        vlm_service: "VLMService",
        perception_pipeline: "PerceptionPipeline",
        perception_controller: Optional["PerceptionController"] = None,
    ):
        self.vlm_service = vlm_service
        self.perception_pipeline = perception_pipeline
        self.perception_controller = perception_controller  # set post-construction

    async def perceive(
        self,
        subgoal: "Subgoal",
        intent: Dict[str, Any],
        force_screenshot: bool = False,
        step_history: Optional[List["StepMemory"]] = None,
        user_command: str = "",
        plan_context: str = "",
    ) -> ScreenState:
        """
        Capture and analyze the current screen state.

        Args:
            subgoal: Current subgoal (used for action_type and target).
            intent: Parsed user intent for modality selection.
            force_screenshot: Force screenshot capture (skips UI tree, uses OmniParser+VLM).
            step_history: Completed step memory from coordinator. When the last
                          successful step was on a webview screen, force_screenshot
                          is automatically set to True so we skip the UI tree and
                          go straight to OmniParser+VLM for the current step.

        Returns:
            ScreenState with perception data, UI signature, and target info.
        """
        # If the previous screen was WebView, current content is likely also
        # WebView-rendered (product cards, listings, etc.) — skip UI tree.
        if not force_screenshot and step_history:
            last = step_history[-1]
            if last.screen_type == "webview":
                logger.info(
                    "Perceiver: last step was webview — forcing screenshot to skip UI tree"
                )
                force_screenshot = True

        # Determine whether to generate a VLM semantic description.
        # We want it whenever:
        #   a) force_screenshot is True (retry / VLM fallback path), OR
        #   b) last step was on a WebView — the UI tree will be blind to
        #      current content, so we need VLM to understand the screen for
        #      planning and context (product cards, search results, etc.)
        need_description = force_screenshot or (
            step_history is not None and
            len(step_history) > 0 and
            step_history[-1].screen_type in ("webview", "unknown")
        )

        # Build VLM mission context so the screen reader knows what to look for
        _subgoal_hint = ""
        if subgoal.target:
            _subgoal_hint = f"[{subgoal.action_type}] {subgoal.description} (target: {subgoal.target})"
        elif subgoal.description:
            _subgoal_hint = f"[{subgoal.action_type}] {subgoal.description}"
        _recent_steps = ""
        if step_history:
            _recent_steps = " → ".join(
                f"[{s.action_type}] {'✅' if s.result == 'success' else '❌'} {s.subgoal_description[:45]}"
                for s in step_history[-3:]
            )

        # Check if we'll use the combined describe_and_locate fast-path.
        # If so, skip the separate describe_screen call in request_perception
        # to avoid a redundant VLM call (describe_and_locate does both).
        _will_use_combined = (
            subgoal.target
            and need_description
        )

        bundle = await self.perception_controller.request_perception(
            intent=intent,
            action_type=subgoal.action_type,
            force_screenshot=force_screenshot,
            skip_description=True if _will_use_combined else not need_description,
            goal=user_command,
            subgoal_hint=_subgoal_hint,
            recent_steps=_recent_steps,
        )

        elements = []
        if bundle.ui_tree and hasattr(bundle.ui_tree, "elements"):
            elements = bundle.ui_tree.elements or []

        ui_sig = compute_ui_signature(elements)
        screen_type = self._classify_screen(elements, bundle)

        # If this screen is WebView, skip UI tree matching entirely — product
        # cards and custom views won't appear in the accessibility tree.
        # Also request a VLM description NOW if we haven't already, so the
        # planner gets meaningful context about what's on screen.
        has_any_webview = any(
            "webview" in (e.get("className") or "").lower()
            for e in elements[:20]
        )
        if (screen_type == "webview" or has_any_webview) and not bundle.visual_description:
            if (
                subgoal.target
                and not _will_use_combined
            ):
                # Webview screen detected with a target — upgrade to combined fast-path instead
                # of firing a separate describe call (VLM #1) then a separate locate call (VLM #2).
                # describe_and_locate will handle both in a single VLM call.
                _will_use_combined = True
                logger.info(
                    "Perceiver: webview + target — upgrading to describe_and_locate fast-path "
                    f"({'hybrid webview' if has_any_webview and screen_type != 'webview' else 'webview'} screen)"
                )
            elif not _will_use_combined:
                # No target (pure describe pass) — still need the separate describe re-fetch
                try:
                    bundle = await self.perception_controller.request_perception(
                        intent=intent,
                        action_type=subgoal.action_type,
                        force_screenshot=True,
                        skip_description=False,
                        goal=user_command,
                        subgoal_hint=_subgoal_hint,
                        recent_steps=_recent_steps,
                    )
                    elements = []
                    if bundle.ui_tree and hasattr(bundle.ui_tree, "elements"):
                        elements = bundle.ui_tree.elements or []
                    ui_sig = compute_ui_signature(elements)
                    logger.info(
                        f"Perceiver: re-fetched with VLM description "
                        f"({'hybrid webview' if has_any_webview and screen_type != 'webview' else 'webview'} screen)"
                    )
                except Exception as e:
                    logger.warning(f"Perceiver: webview re-fetch failed: {e}")

        # PRIMARY: send annotated screenshot + UI tree + full context to VLM.
        # VLM sees BOTH the visual numbered boxes AND the element list + command/plan.
        # Returns element index + whether screen matches the expected plan step.
        target_match = None
        vlm_annotated_b64 = None
        replan_suggested = False
        replan_reason = ""

        # Fast-path: one combined VLM call for both description + location
        # Only used when we need both and the screen reader supports it
        _combined_result = None
        _highlighted_b64: Optional[str] = None
        _element_description: Optional[str] = None
        if _will_use_combined:
            _elements_for_combine = elements
            if not _elements_for_combine and bundle.screenshot and self.perception_pipeline:
                # Vision-only screen (no accessibility tree) — use OmniParser detections
                # so describe_and_locate can draw numbered SoM boxes and do both tasks
                # in one VLM call instead of separate describe_screen + VLMSelector calls.
                _elements_for_combine = self._get_omniparser_elements(bundle)
                if _elements_for_combine:
                    logger.info(
                        f"Perceiver: vision-only screen — using {len(_elements_for_combine)} "
                        f"OmniParser detections for combined describe_and_locate"
                    )
            if _elements_for_combine:
                from utils.ui_element_finder import format_ui_tree
                _ui_hints = format_ui_tree(_elements_for_combine)
                try:
                    _combined_result = await self.describe_and_locate(
                        bundle,
                        target=subgoal.target,
                        subgoal_hint=_subgoal_hint,
                        goal=user_command,
                        recent_steps=_recent_steps,
                        ui_elements_text=_ui_hints,
                        elements=_elements_for_combine,  # enables SoM annotation inside describe_and_locate
                    )
                except Exception as _e:
                    logger.warning(f"describe_and_locate fast-path failed: {_e}")
                    _combined_result = None

        if _combined_result and _combined_result.get("description"):
            # Combined call succeeded — extract description + coordinates
            bundle = bundle.model_copy(update={"visual_description": _combined_result["description"]})
            # describe_and_locate now resolves x/y internally from the annotated SoM image.
            # Use them directly — no index re-lookup needed and no mismatch with filtered list.
            _x = _combined_result.get("x")
            _y = _combined_result.get("y")
            if _x is not None and _y is not None:
                target_match = {
                    "x": _x,
                    "y": _y,
                    "text": subgoal.target,
                    "format": "pixels",
                    "source": "combined_describe_and_locate",
                    "confidence": _combined_result.get("confidence", 0.92),
                }
                _highlighted_b64 = _combined_result.get("highlighted_b64")
                _element_description = _combined_result.get("element_description")
                logger.info(
                    f"✅ Combined path located '{subgoal.target}' at ({_x}, {_y})"
                )
        elif _will_use_combined and need_description and not bundle.visual_description:
            # Combined fast-path was expected but failed (no elements or error).
            # Fall back to a separate describe_screen call so the planner still
            # gets a screen description.
            try:
                desc = await self.describe_screen(
                    bundle,
                    goal=user_command,
                    subgoal_hint=_subgoal_hint,
                    recent_steps=_recent_steps,
                )
                bundle = bundle.model_copy(update={"visual_description": desc})
                logger.info("Perceiver: fallback describe_screen after combined fast-path miss")
            except Exception as _e:
                logger.warning(f"Perceiver: fallback describe_screen also failed: {_e}")

        # Fall through to annotated UI tree when combined call didn't find target
        if target_match is None and subgoal.target and bundle.screenshot and elements:
            logger.info(
                f"🔍 Sending annotated UI tree + screenshot to VLM for '{subgoal.target}'"
            )
            try:
                vl_result = self.locate_with_annotated_ui_tree(
                    elements=elements,
                    screenshot_b64=bundle.screenshot.screenshot_base64,
                    target=subgoal.target,
                    screen_width=bundle.screen_meta.width,
                    screen_height=bundle.screen_meta.height,
                    user_command=user_command,
                    plan_context=plan_context,
                    subgoal_description=subgoal.description,
                )
                if vl_result:
                    vlm_annotated_b64 = vl_result.get("annotated_b64")
                    replan_suggested = vl_result.get("replan_suggested", False)
                    replan_reason = vl_result.get("replan_reason", "")
                    if replan_suggested:
                        logger.warning(
                            f"⚠️ VLM flagged screen mismatch for '{subgoal.target}': {replan_reason}"
                        )
                    if vl_result.get("x") is not None:
                        target_match = {
                            "x": vl_result["x"],
                            "y": vl_result["y"],
                            "text": subgoal.target,
                            "format": "pixels",
                            "source": vl_result.get("source", "vlm_annotated_ui_tree"),
                            "confidence": vl_result.get("confidence", 0.92),
                        }
                        _highlighted_b64 = vl_result.get("highlighted_b64")
                        _element_description = vl_result.get("element_description")
                        logger.info(
                            f"✅ VLM selected '{subgoal.target}' at "
                            f"({vl_result['x']}, {vl_result['y']})"
                        )
            except Exception as e:
                logger.warning(f"VLM annotated selection failed for '{subgoal.target}': {e}")

        # OmniParser fallback: element is visible on screen but NOT in the UI tree
        # (custom views, canvas-rendered content, elements outside accessibility tree)
        if target_match is None and subgoal.target and bundle.screenshot:
            logger.info(
                f"🔍 Not in UI tree annotations — trying OmniParser for '{subgoal.target}'"
            )
            try:
                vl_result = self.locate_from_bundle(
                    bundle,
                    subgoal.target,
                    screen_context=bundle.visual_description,
                    user_command=user_command,
                    plan_context=plan_context,
                    subgoal_description=subgoal.description,
                )
                if vl_result:
                    target_match = {
                        "x": vl_result["x"],
                        "y": vl_result["y"],
                        "text": subgoal.target,
                        "format": "pixels",
                        "source": vl_result.get("source", "omniparser"),
                        "confidence": vl_result.get("confidence", 0.0),
                    }
                    logger.info(
                        f"✅ OmniParser found '{subgoal.target}' at "
                        f"({vl_result['x']}, {vl_result['y']}) "
                        f"via {vl_result.get('source', 'unknown')}"
                    )
            except Exception as e:
                logger.warning(f"OmniParser fallback failed for '{subgoal.target}': {e}")

        return ScreenState(
            perception_bundle=bundle,
            ui_signature=ui_sig,
            elements=elements,
            target_match=target_match,
            screen_type=screen_type,
            screen_description=bundle.visual_description,
            vlm_annotated_b64=vlm_annotated_b64,
            replan_suggested=replan_suggested,
            replan_reason=replan_reason,
            highlighted_b64=_highlighted_b64,
            element_description=_element_description,
        )

    def _get_omniparser_elements(self, bundle: Any) -> List[Dict]:
        """
        Run OmniParser on the bundle screenshot and convert detections to the
        element-dict format expected by describe_and_locate.  Used when there is
        no accessibility tree (vision-only screens like Google Maps) so that the
        combined describe_and_locate call can draw numbered SoM boxes.
        """
        if not self.perception_pipeline or not bundle.screenshot:
            return []
        try:
            screenshot_b64 = bundle.screenshot.screenshot_base64
            detections = self.perception_pipeline.detect_only(screenshot_b64)
            elements = []
            for d in detections:
                x1, y1, x2, y2 = d.box
                elements.append({
                    "bounds": {"left": x1, "top": y1, "right": x2, "bottom": y2},
                    "clickable": d.class_name != "text_block",
                    "text": d.id or "",
                    "contentDescription": "",
                    "className": d.class_name or "View",
                })
            return elements
        except Exception as e:
            logger.warning(f"_get_omniparser_elements failed: {e}")
            return []

    def _classify_screen(self, elements: List[Dict], bundle: Any) -> str:
        """Classify the current screen type from UI elements."""
        if not elements:
            return "empty"

        class_names = [e.get("className", "") for e in elements[:20]]
        class_str = " ".join(class_names).lower()

        if "webview" in class_str:
            # Only treat as webview if no native interactive form elements exist
            # BELOW the WebView region. Header chrome (search bars, back buttons)
            # sitting above the WebView shouldn't prevent webview classification —
            # e.g. Amazon brand store has native ImageButtons in the top bar but
            # the entire product listing is inside a WebView.
            native_interactive = {"edittext", "textinputedittext", "button", "imagebutton"}
            webview_top = next(
                (
                    (e.get("bounds") or e.get("boundsInScreen") or {}).get("top", 0)
                    for e in elements
                    if "webview" in (e.get("className") or "").lower()
                ),
                0,
            )
            has_native_forms_below = any(
                any(c in (e.get("className") or "").lower() for c in native_interactive)
                and (e.get("bounds") or e.get("boundsInScreen") or {}).get("top", 0) > webview_top
                for e in elements
            )
            if not has_native_forms_below:
                return "webview"

        # Check for keyboard by looking for key-like elements
        text_values = [e.get("text", "") for e in elements if e.get("text")]
        keyboard_keys = sum(1 for t in text_values if len(t) == 1 and t.isalpha())
        if keyboard_keys > 10:
            return "keyboard_open"

        return "native"

    def _find_target(
        self, elements: List[Dict], target: str
    ) -> Optional[Dict[str, Any]]:
        """Find best matching element for target description."""
        if not target or not elements:
            return None

        target_lower = target.lower().strip()

        # Collect ALL exact matches (text OR contentDescription), then pick tightest bounds.
        # Combining both pools ensures a nav tab with only contentDescription beats a
        # phantom full-screen TextView that happens to have the same text.
        exact = [
            el for el in elements
            if (el.get("text") or "").strip().lower() == target_lower
            or (el.get("contentDescription") or "").strip().lower() == target_lower
        ]

        # Substring fallback across both text and contentDescription
        candidates = [
            el for el in elements
            if target_lower in (el.get("text") or "").strip().lower()
            or target_lower in (el.get("contentDescription") or "").strip().lower()
        ]

        if exact:
            # Prefer exact matches in the main content area (y_center >= 350px).
            # Search bars and header breadcrumbs live in the top ~350px and can
            # display the current query text — tapping them navigates away from results.
            content_exact = [el for el in exact if self._y_center(el) >= 350]
            if content_exact:
                return self._extract_coordinates(self._best_element(content_exact))
            # All exact matches are in the navigation/header zone.
            # Prefer content-area substring matches (e.g. product titles) if available.
            content_candidates = [el for el in candidates if self._y_center(el) >= 350]
            if content_candidates:
                return self._extract_coordinates(self._best_element(content_candidates))
            # Only navigation-area elements found — use the exact match as last resort.
            return self._extract_coordinates(self._best_element(exact))

        if candidates:
            return self._extract_coordinates(self._best_element(candidates))

        return None

    def _y_center(self, element: Dict) -> int:
        """Return the vertical center pixel of an element's bounding box."""
        b = element.get("bounds") or element.get("visibleBounds") or element.get("boundsInScreen") or {}
        return (b.get("top", 0) + b.get("bottom", 0)) // 2

    def _best_element(self, elements: List[Dict]) -> Dict:
        """Return the element with the smallest bounding-box area — avoids full-screen ghost labels."""
        def area(el):
            b = el.get("bounds") or el.get("visibleBounds") or el.get("boundsInScreen") or {}
            w = b.get("right", 0) - b.get("left", 0)
            h = b.get("bottom", 0) - b.get("top", 0)
            return w * h if w > 0 and h > 0 else float("inf")
        return min(elements, key=area)

    def _extract_coordinates(self, element: Dict) -> Dict[str, Any]:
        """Extract tap coordinates from element bounds."""
        bounds = (
            element.get("bounds")
            or element.get("visibleBounds")
            or element.get("boundsInScreen")
            or element
        )
        left = bounds.get("left", 0)
        top = bounds.get("top", 0)
        right = bounds.get("right", left)
        bottom = bounds.get("bottom", top)

        return {
            "x": (left + right) // 2,
            "y": (top + bottom) // 2,
            "text": element.get("text", ""),
            "bounds": {"left": left, "top": top, "right": right, "bottom": bottom},
            "format": "pixels",
        }

    # ── Visual perception methods (formerly ScreenVLM) ─────────────────

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

            # Step 1: collect valid-bounds interactive elements only
            candidates = []
            for el in elements:
                b = el.get("bounds") or el.get("visibleBounds") or el.get("boundsInScreen") or {}
                left, top, right, bottom = (
                    b.get("left", 0), b.get("top", 0),
                    b.get("right", 0), b.get("bottom", 0),
                )
                # OmniParser elements use box:[x1,y1,x2,y2] instead of bounds dict
                if right <= left or bottom <= top:
                    raw_box = el.get("box")
                    if raw_box and len(raw_box) == 4:
                        left, top, right, bottom = (int(raw_box[0]), int(raw_box[1]),
                                                    int(raw_box[2]), int(raw_box[3]))
                if right <= left or bottom <= top:
                    continue
                if (right - left) * (bottom - top) > screen_area * 0.6:
                    continue

            meaningful = candidates  # no containment filtering — see locate_with_annotated_ui_tree

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

            # Nudge badges that overlap a previous badge
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

    async def describe_screen(
        self,
        bundle: Any,
        focus: str = "general",
        goal: str = "",
        subgoal_hint: str = "",
        recent_steps: str = "",
    ) -> str:
        """Describe the current screen content using PerceptionBundle."""
        try:
            modality_str = bundle.modality.value if hasattr(bundle.modality, 'value') else str(bundle.modality)
            logger.info(f"📖 Perceiver: Describing screen (focus: {focus}, modality={modality_str})")

            screenshot_b64 = None
            if bundle.screenshot:
                screenshot_b64 = bundle.screenshot.screenshot_base64

            ui_elements_text = ""
            if bundle.ui_tree:
                from utils.ui_element_finder import format_ui_tree
                ui_elements_text = format_ui_tree(bundle.ui_tree.elements)

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

            description = self.vlm_service.analyze_image(screenshot_b64, prompt, agent="PerceiverAgent", temperature=0.2)
            description = description.strip()

            logger.info(f"✅ Screen description: {description[:100]}...")
            return description

        except Exception as e:
            logger.error(f"Perceiver describe_screen failed: {e}", exc_info=True)
            elem_count = len(bundle.ui_tree.elements) if bundle.ui_tree else 0
            return f"I can see the screen has {elem_count} elements, but I couldn't generate a detailed description due to an error."

    async def describe_and_locate(
        self,
        bundle: Any,
        target: str,
        subgoal_hint: str = "",
        goal: str = "",
        recent_steps: str = "",
        ui_elements_text: str = "",
        elements: Optional[List[Dict]] = None,
    ) -> dict:
        """
        Combined call: describe screen AND locate target element in one VLM call.
        Returns dict with keys: description, element_id, x, y, blocker, confidence.
        """
        screenshot_b64 = None
        if bundle.screenshot:
            screenshot_b64 = bundle.screenshot.screenshot_base64
        if not screenshot_b64:
            return {"description": "", "element_id": None, "x": None, "y": None, "blocker": ""}

        annotated_b64 = screenshot_b64
        meaningful: list = []
        element_summary = ui_elements_text
        if elements:
            try:
                import base64 as _b64
                import cv2
                import numpy as np
                screen_width = getattr(getattr(bundle, "screen_meta", None), "width", 0) or 1080
                screen_height = getattr(getattr(bundle, "screen_meta", None), "height", 0) or 1920
                screen_area = screen_width * screen_height

                candidates: list = []
                for el in elements:
                    b = el.get("bounds") or el.get("visibleBounds") or el.get("boundsInScreen") or {}
                    left, top, right, bottom = (
                        b.get("left", 0), b.get("top", 0),
                        b.get("right", 0), b.get("bottom", 0),
                    )
                    if right <= left or bottom <= top:
                        raw_box = el.get("box")
                        if raw_box and len(raw_box) == 4:
                            left, top, right, bottom = (int(raw_box[0]), int(raw_box[1]),
                                                        int(raw_box[2]), int(raw_box[3]))
                    if right <= left or bottom <= top:
                        continue
                    if (right - left) * (bottom - top) > screen_area * 0.6:
                        continue
                    candidates.append((el, left, top, right, bottom))
                meaningful = candidates  # no containment filtering — see locate_with_annotated_ui_tree

                if meaningful:
                    arr = np.frombuffer(_b64.b64decode(screenshot_b64), dtype=np.uint8)
                    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                    if img is not None:
                        h_img, w_img = img.shape[:2]
                        font = cv2.FONT_HERSHEY_DUPLEX
                        font_scale, font_thick = 1.0, 2
                        pad = 6
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
                        from utils.ui_element_finder import format_ui_tree
                        element_summary = format_ui_tree([el for el, *_ in meaningful])
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
            raw = self.vlm_service.analyze_image(annotated_b64, prompt, agent="PerceiverAgent", temperature=0.1)

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
                            # Semantic cross-check: verify the selected element's label
                            # has at least one word in common with the target string.
                            # This catches VLM hallucinations where the wrong element ID
                            # is returned (e.g. carousel arrow [34] labelled "Add to Cart").
                            _el_label = (
                                (el.get("text") or el.get("contentDescription") or "")
                                .strip().lower()
                            )
                            _target_words = set(target.lower().split())
                            _label_words = set(_el_label.split())
                            _has_overlap = bool(_target_words & _label_words)
                            _el_is_unlabelled = not _el_label

                            # For commit-action targets (add to cart, buy, pay, delete,
                            # send, remove, purchase) an unlabelled element is also
                            # suspicious — real buttons always carry accessibility labels.
                            # Force OmniParser to find the visually-rendered button instead.
                            _commit_kws = {"add", "cart", "buy", "pay", "delete", "remove", "purchase", "send", "order"}
                            _is_commit_target = bool(_target_words & _commit_kws)

                            # Math/symbol operators whose accessibility label is the English word
                            # (same alias table as locate_with_annotated_ui_tree).
                            _SYMBOL_ALIASES_DAL: Dict[str, set] = {
                                "+": {"add", "plus", "addition"},
                                "-": {"subtract", "minus", "subtraction", "negative"},
                                "*": {"multiply", "times", "multiplication", "asterisk"},
                                "/": {"divide", "division"},
                                "=": {"equals", "equal"},
                                "%": {"percent", "percentage"},
                                "^": {"power", "exponent"},
                                "√": {"sqrt", "square", "root"},
                                "×": {"multiply", "times"},
                                "÷": {"divide", "division"},
                                "·": {"multiply", "times", "dot"},
                                ".": {"point", "decimal"},
                                "(": {"left", "parenthesis", "open"},
                                ")": {"right", "parenthesis", "close"},
                            }
                            _target_stripped_dal = target.strip()
                            _alias_words = _SYMBOL_ALIASES_DAL.get(_target_stripped_dal, set()) \
                                if len(_target_stripped_dal) <= 2 else set()
                            _has_alias_match = bool(_label_words & _alias_words)

                            _should_reject = (not _has_overlap and not _el_is_unlabelled and not _has_alias_match) or \
                                             (not _has_overlap and _el_is_unlabelled and _is_commit_target and not _has_alias_match)

                            if _should_reject:
                                # Either: element has a label that doesn't match (hallucination),
                                # or: element is unlabelled but this is a commit-action target
                                # (empty View picked instead of the real button).
                                logger.warning(
                                    f"⚠️ describe_and_locate: VLM picked element {idx + 1} "
                                    f"(label='{_el_label[:50] if _el_label else '<empty>'}') for target='{target}' — "
                                    f"{'no label' if _el_is_unlabelled else 'label mismatch'}, "
                                    f"rejecting and falling through to OmniParser"
                                )
                                x, y = None, None
                            else:
                                x, y = cx, cy
                                if not elem_desc:
                                    elem_desc = (el.get("text") or el.get("contentDescription") or "").strip()
                                logger.info(
                                    f"✅ describe_and_locate: '{target}' at ({x}, {y}) "
                                    f"via element {idx + 1} label='{_el_label[:40]}' "
                                    f"(annotated={using_annotated})"
                                )
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
            result = self.vlm_service.analyze_two_images(before_b64, after_b64, prompt, temperature=0.1)
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

    def locate_element(
        self,
        screenshot_b64: str,
        element_description: str,
        screen_width: int,
        screen_height: int,
    ) -> Optional[Dict[str, int]]:
        """Locate an element visually using screenshot. Uses hybrid OmniParser when available."""
        if not screenshot_b64 or len(screenshot_b64) < 1000:
            logger.warning("Screenshot too small for visual location")
            return None

        if self.perception_pipeline:
            try:
                result = self.perception_pipeline.locate_element(
                    intent=element_description,
                    ui_tree=None,
                    screenshot=screenshot_b64,
                    screen_bounds=(screen_width, screen_height),
                )
                if result.success:
                    x, y = result.coordinates
                    logger.info(
                        f"✅ Located '{element_description}' at ({x}, {y}) via {result.source} "
                        f"confidence={result.confidence:.2f}"
                    )
                    return {"x": x, "y": y, "confidence": result.confidence, "source": result.source}
                else:
                    logger.warning(f"Hybrid perception failed: {result.reason}")
            except Exception as e:
                logger.warning(f"Hybrid perception error: {e}, falling back to legacy")

        return self._legacy_vlm_locate(screenshot_b64, element_description, screen_width, screen_height)

    def _legacy_vlm_locate(
        self,
        screenshot_b64: str,
        element_description: str,
        screen_width: int,
        screen_height: int,
    ) -> Optional[Dict[str, int]]:
        """Legacy VLM coordinate prediction fallback (use only when OmniParser unavailable)."""
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
            result = self.vlm_service.analyze_image(screenshot_b64, prompt, agent="PerceiverAgent", temperature=0.1)
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
                logger.warning(f"Element '{element_description}' not found: {parsed.get('reason')}")
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
        on the screenshot, then asks the VLM to pick the right box number.
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

        candidates: List[tuple] = []
        for el in elements:
            b = el.get("bounds") or el.get("visibleBounds") or el.get("boundsInScreen") or {}
            left, top, right, bottom = (
                b.get("left", 0), b.get("top", 0),
                b.get("right", 0), b.get("bottom", 0),
            )
            if right <= left or bottom <= top:
                raw_box = el.get("box")
                if raw_box and len(raw_box) == 4:
                    left, top, right, bottom = (int(raw_box[0]), int(raw_box[1]),
                                                int(raw_box[2]), int(raw_box[3]))
            if right <= left or bottom <= top:
                continue
            if (right - left) * (bottom - top) > screen_area * 0.6:
                continue
            candidates.append((el, left, top, right, bottom))
        # Use all valid candidates — parent-containment filtering removed.
        # That filter silently dropped valid interactive children (e.g. inner icon
        # buttons, calculator keys) whenever their bounds sat inside a parent cell,
        # causing index mismatches between VLM picks and coordinate resolution.
        meaningful: List[tuple] = candidates

        if not meaningful:
            return None

        try:
            arr = np.frombuffer(_b64.b64decode(screenshot_b64), dtype=np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img is None:
                return None

            h_img, w_img = img.shape[:2]
            font = cv2.FONT_HERSHEY_DUPLEX
            font_scale, font_thick = 1.0, 2
            pad = 6

            overlay = img.copy()
            for i, (el, left, top, right, bottom) in enumerate(meaningful):
                color = (60, 200, 80) if el.get("clickable") else (200, 120, 40) if el.get("scrollable") else (130, 110, 200)
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

            for i, (el, left, top, right, bottom) in enumerate(meaningful):
                label = str(i + 1)
                color = (0, 255, 0) if el.get("clickable") else (0, 165, 255) if el.get("scrollable") else (255, 100, 255)
                cv2.rectangle(img, (left, top), (right, bottom), color, 2)
                bx1, by1, bx2, by2 = badge_rects[i]
                (tw, th), _ = cv2.getTextSize(label, font, font_scale, font_thick)
                cv2.rectangle(img, (bx1 - 2, by1 - 2), (bx2 + 2, by2 + 2), (0, 0, 0), -1)
                cv2.rectangle(img, (bx1, by1), (bx2, by2), (0, 0, 0), -1)
                cv2.putText(img, label, (bx1 + pad, by1 + th + pad),
                            font, font_scale, (0, 255, 255), font_thick, cv2.LINE_AA)

            _, buf = cv2.imencode(".png", img)
            annotated_b64 = _b64.b64encode(buf).decode("utf-8")
        except Exception as e:
            logger.warning(f"Failed to draw UI tree annotations: {e}")
            return None

        from utils.ui_element_finder import format_ui_tree
        element_summary = format_ui_tree([el for el, *_ in meaningful])

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
            raw = self.vlm_service.analyze_image(annotated_b64, prompt, agent="PerceiverAgent", temperature=0.1).strip()
            logger.info(f"🎯 VLM annotation response for '{target}': {raw!r}")

            import json as _json
            cleaned = raw.strip().strip("```json").strip("```").strip()
            try:
                parsed = _json.loads(cleaned)
            except Exception:
                parsed = {"element": cleaned, "screen_ok": True, "deviation": None}

            replan_suggested = not parsed.get("screen_ok", True)
            replan_reason = parsed.get("deviation") or ""
            element_val = str(parsed.get("element", "not_found")).strip()

            if "not_found" in element_val.lower():
                logger.info(f"VLM: '{target}' not in UI tree annotations — OmniParser needed")
                return {"annotated_b64": annotated_b64, "replan_suggested": replan_suggested, "replan_reason": replan_reason}

            import re
            numbers = re.findall(r"\d+", element_val)
            if not numbers:
                logger.warning(f"VLM returned unparseable element value: {element_val!r}")
                return {"annotated_b64": annotated_b64, "replan_suggested": replan_suggested, "replan_reason": replan_reason}

            idx = int(numbers[0]) - 1
            if not (0 <= idx < len(meaningful)):
                logger.warning(f"VLM index {idx + 1} out of range (max {len(meaningful)})")
                return {"annotated_b64": annotated_b64, "replan_suggested": replan_suggested, "replan_reason": replan_reason}

            el, left, top, right, bottom = meaningful[idx]
            _el_label2 = (el.get("text") or el.get("contentDescription") or "").strip().lower()
            _target_words2 = set(target.lower().split())
            _label_words2 = set(_el_label2.split())
            _has_overlap2 = bool(_target_words2 & _label_words2)
            _el_is_unlabelled2 = not _el_label2

            _commit_kws2 = {"add", "cart", "buy", "pay", "delete", "remove", "purchase", "send", "order"}
            _is_commit_target2 = bool(_target_words2 & _commit_kws2)

            # Math/symbol operators whose accessibility label is the English word,
            # not the character. Without this, "+" target fails the cross-check
            # because {"+"} ∩ {"add"} = ∅ — triggering a spurious OmniParser fallback
            # that picks the wrong element (e.g. Equals instead of Add).
            _SYMBOL_ALIASES: Dict[str, set] = {
                "+": {"add", "plus", "addition"},
                "-": {"subtract", "minus", "subtraction", "negative"},
                "*": {"multiply", "times", "multiplication", "asterisk"},
                "/": {"divide", "division"},
                "=": {"equals", "equal"},
                "%": {"percent", "percentage"},
                "^": {"power", "exponent"},
                "√": {"sqrt", "square", "root"},
                "×": {"multiply", "times"},
                "÷": {"divide", "division"},
                "·": {"multiply", "times", "dot"},
                ".": {"point", "decimal"},
                "(": {"left", "parenthesis", "open"},
                ")": {"right", "parenthesis", "close"},
            }
            _target_stripped = target.strip()
            _alias_words2 = _SYMBOL_ALIASES.get(_target_stripped, set()) if len(_target_stripped) <= 2 else set()
            _has_alias_match2 = bool(_label_words2 & _alias_words2)

            _should_reject2 = (not _has_overlap2 and not _el_is_unlabelled2 and not _has_alias_match2) or \
                              (not _has_overlap2 and _el_is_unlabelled2 and _is_commit_target2 and not _has_alias_match2)

            if _should_reject2:
                # Element has a label that shares no words with target, OR element is
                # unlabelled but this is a commit-action target — VLM hallucinated.
                # Fall through so OmniParser can locate the real element.
                logger.warning(
                    f"⚠️ locate_with_annotated_ui_tree: VLM picked element {idx + 1} "
                    f"(label='{_el_label2[:50] if _el_label2 else '<empty>'}') for target='{target}' — "
                    f"{'no label' if _el_is_unlabelled2 else 'label mismatch'}, "
                    f"rejecting and falling through to OmniParser"
                )
                return {"annotated_b64": annotated_b64, "replan_suggested": replan_suggested, "replan_reason": replan_reason}

            elem_desc = (
                parsed.get("element_description")
                or (el.get("text") or el.get("contentDescription") or "").strip()
            )

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
        bundle: Any,
        element_description: str,
        screen_context: Optional[str] = None,
        user_command: str = "",
        plan_context: str = "",
        subgoal_description: str = "",
    ) -> Optional[Dict[str, int]]:
        """
        Locate element using PerceptionBundle (hybrid mode support).

        1. First tries UI tree matching (Layer 1 - fast)
        2. Falls back to CV Detection + VLM Selection (Layer 2+3)
        """
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

        return self._legacy_locate_from_bundle(bundle, enriched_intent)

    def _legacy_locate_from_bundle(
        self,
        bundle: Any,
        element_description: str,
    ) -> Optional[Dict[str, int]]:
        """Legacy bundle location (UI tree search + VLM fallback)."""
        target_lower = element_description.lower()

        if bundle.ui_tree:
            best_match = None
            best_score = 0.0

            for elem in bundle.ui_tree.elements:
                text = (elem.get("text") or "").lower()
                content_desc = (elem.get("contentDescription") or "").lower()
                resource_id = (elem.get("resourceId") or "").lower()

                score = 0.0
                if target_lower == text:
                    score = 1.0
                elif target_lower in text or target_lower in content_desc:
                    score = 0.8
                elif text in target_lower or content_desc in target_lower:
                    score = 0.6
                elif target_lower.replace(" ", "_") in resource_id:
                    score = 0.7

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

    def get_metrics(self) -> Dict:
        """Get perception pipeline metrics."""
        if self.perception_pipeline:
            return self.perception_pipeline.get_metrics()
        return {}
