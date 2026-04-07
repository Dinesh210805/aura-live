# Perception Pipeline

**File:** `perception/perception_pipeline.py` (699 lines)  
**Controller:** `services/perception_controller.py`

---

## Overview

The perception pipeline resolves "where is UI element X?" using three layers in sequence. Each layer attempts element location and returns immediately on success; the next layer is tried only on failure.

```
Layer 1: UI Tree           10–50 ms     ~70-80% success rate
Layer 2: OmniParser CV     200–400 ms   (GPU); 2–3 s (CPU)
Layer 3: VLM SoM Select    300–600 ms   via ThreadPoolExecutor + timeout
Layer 4: Heuristic         <50 ms       fallback using cached detections
```

---

## Key Data Classes

### `PerceptionConfig`
```python
@dataclass
class PerceptionConfig:
    ui_tree_enabled: bool = True
    cv_vlm_enabled: bool = True
    min_confidence: float = 0.70
    min_box_size: tuple = (10, 10)
    vlm_timeout: float = 10.0

_MIN_DETECTIONS: int = 3   # class constant — if OmniParser returns fewer, skip VLM
```

### `LocateResult`
```python
@dataclass
class LocateResult:
    success: bool
    coordinates: Optional[tuple]       # (x, y) pixel center
    confidence: float
    source: str                        # "ui_tree" | "cv_vlm" | "heuristic"
    layer_attempted: List[str]         # audit trail of layers tried
```

### `PerceptionMetrics`
Tracks per-layer attempt/success counts across a session. Exposed via `to_dict()` for logging and observability dashboards.

---

## Layer Flow

### Layer 1 — UI Tree (`_try_ui_tree`)
1. Calls `find_element(target_description)` from `utils/ui_element_finder.py`
2. Validates bounding box `> min_box_size`
3. Validates confidence `>= min_confidence`
4. Returns center coordinates of bounding box on success

### Layer 2+3 — CV + VLM (`_try_cv_vlm`)
1. **Detect**: `OmniParserDetector.detect()` → list of `Detection` objects with bounding boxes
2. **Minimum detection guard**: if `len(detections) < _MIN_DETECTIONS`, skip VLM entirely (not enough context for reliable selection)
3. **Annotate**: draw numbered SoM labels on screenshot, save annotated image via command logger
4. **VLM select**: run `VLMSelector.select_with_fallback()` inside `ThreadPoolExecutor(max_workers=1)` with `_vlm_future.result(timeout=vlm_timeout_seconds)` (default 30 s — configured via `settings.vlm_timeout_seconds`)
5. **Validate**: VLM returns a label letter (e.g., "A", "B") — map back to bounding box center

> **SoM Invariant**: VLM only selects a label letter. It never returns raw pixel coordinates. Coordinates always come from bounding box centers of the selected Detection object. **This invariant must never be broken.**

### Layer 4 — Heuristic (`_try_heuristic`)
- Reuses `cached_detections` from the most recent CV pass
- Calls `HeuristicSelector.select(target_description, cached_detections)`
- Last resort — lower precision but never fails if detections exist

---

## `detect_only()`
Returns raw `Detection` objects without running the VLM step. Used by `PerceiverAgent` when a full screenshot parse is needed (not element location).

---

## VLM Timeout (Fix G6)
The G6 gap was that VLM timeouts were not surfaced — tasks would hang waiting for a slow VLM response. Fix: `select_with_fallback()` is now called inside a `ThreadPoolExecutor` with an explicit `Future.result(timeout=...)`. On timeout, `TimeoutError` is caught and layer 3 is marked as failed, falling through to layer 4.

---

## Integration Points
- `PerceiverAgent` → `PerceptionController` → `PerceptionPipeline`
- Annotated screenshots written to command logger path → visible in HTML execution logs
- `PerceptionMetrics` fed into `TaskState` for post-task analysis
