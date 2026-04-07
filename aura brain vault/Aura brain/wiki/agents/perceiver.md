# Agent: Perceiver

**File**: `agents/perceiver_agent.py`

---

## Role

`PerceiverAgent` is the coordinator's "eyes". It wraps `PerceptionController` and returns a `ScreenState` object describing the current Android screen.

---

## ScreenState Dataclass

The rich object returned by `perceive()`:

| Field | Type | Description |
|-------|------|-------------|
| `perception_bundle` | `PerceptionBundle` | Raw perception data: screenshot, UI tree, elements |
| `ui_signature` | `str` | Hash/fingerprint of current screen for change detection |
| `elements` | `List[dict]` | Accessible UI elements from the tree |
| `target_match` | `Optional[dict]` | Best-matching element for the current goal |
| `screen_type` | `str` | Classified screen type (e.g., "home", "list", "media_player") |
| `screen_description` | `str` | Human-readable description of what's on screen |
| `vlm_annotated_b64` | `Optional[str]` | Base64 screenshot with SoM annotations |
| `replan_suggested` | `bool` | Whether the screen suggests the plan needs updating |
| `highlighted_b64` | `Optional[str]` | Screenshot with target element highlighted |
| `element_description` | `str` | Description of the matched element |

---

## Circular Dependency Pattern

`PerceiverAgent` has a mutual dependency with `PerceptionController`:
- `PerceiverAgent` uses `PerceptionController` for device-level capture
- `PerceptionController` uses `PerceiverAgent` as the `screen_vlm` (the VLM that interprets screens)

Resolution in `compile_aura_graph()`:
```python
# Step 1: Create perceiver without controller (screen_vlm=perceiver is its own VLM role)
perceiver = PerceiverAgent(vlm_service, perception_pipeline)

# Step 2: Create controller that uses perceiver as its VLM
controller = PerceptionController(screen_vlm=perceiver)

# Step 3: Wire back
perceiver.perception_controller = controller
```

---

## `perceive(session_id, hint)` Method

1. Calls `perception_controller.capture()` to get screenshot + UI tree from the Android device
2. Runs the three-layer perception pipeline (see [perception/pipeline.md](../perception/pipeline.md))
3. Returns populated `ScreenState`

If perception fails (no device connection, screenshot timeout):
- Returns `ScreenState` with `perception_bundle=None`
- Coordinator node sets `status = "perception_failed"`
- Edge routes to `error_handler`

---

## VLM Timeout Handling (G6 Fix)

The VLM call in the perception pipeline runs in a `ThreadPoolExecutor` with a timeout from `settings.vlm_timeout_seconds` (default 30s). If the VLM times out, the pipeline falls back from Layer 3 (VLM) to Layer 2 (CV detection) results directly.

Previously, a hanging VLM call would block the entire async event loop.
