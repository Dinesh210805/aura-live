# OmniParser Perception Architecture

## Overview

This module implements Microsoft's OmniParser hybrid CV + VLM architecture for precise UI element location.

### The Problem We Solve

VLMs (Vision-Language Models) suffer from **spatial hallucination** - they cannot reliably predict pixel coordinates. When asked "where is the play button?", a VLM might say "(450, 320)" but the actual button is at "(380, 290)".

### The Solution: Hybrid Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  COORDINATES NEVER COME FROM VLM                            │
│  VLM ONLY SELECTS AMONG GEOMETRICALLY VALID CANDIDATES      │
└─────────────────────────────────────────────────────────────┘
```

## Three-Layer Pipeline

### Layer 1: UI Tree (Primary)
- **Source:** Android AccessibilityService
- **Speed:** 10-50ms
- **Success rate:** 70-80% of cases
- Uses `utils/ui_element_finder.py` for semantic matching

### Layer 2: CV Detection (Fallback)
- **Model:** YOLOv8 (OmniParser pre-trained)
- **Speed:** 200-400ms (GPU), 2-3s (CPU)
- Detects ALL UI elements geometrically
- Assigns IDs: A, B, C, D...

### Layer 3: VLM Selection (Semantic)
- **Models:** Gemini 2.5 Flash, Claude, etc.
- **Speed:** 300-600ms
- **Task:** "Which labeled box matches the intent?"
- **Output:** Selected ID (e.g., "B")
- **NEVER outputs coordinates!**

## Module Structure

```
perception/
├── __init__.py              # Exports and lazy loaders
├── models.py                # PerceptionBundle, payloads
├── app_classifier.py        # App categorization
├── omniparser_detector.py   # YOLOv8 CV detection (NEW)
├── vlm_selector.py          # VLM semantic selection (NEW)
└── perception_pipeline.py   # 3-layer orchestration (NEW)
```

## Usage

### Basic Usage

```python
from perception.perception_pipeline import create_perception_pipeline
from services.vlm import VLMService
from config.settings import get_settings

# Initialize
vlm_service = VLMService(get_settings())
pipeline = create_perception_pipeline(vlm_service)

# Locate element
result = pipeline.locate_element(
    intent="play button",
    ui_tree=ui_tree,           # From Android Accessibility
    screenshot=screenshot_b64,  # From MediaProjection
    screen_bounds=(1080, 2400),
)

if result.success:
    x, y = result.coordinates
    print(f"Found at ({x}, {y}) via {result.source}")
```

### With VisualLocator

```python
from agents.visual_locator import VisualLocator

locator = VisualLocator(vlm_service)
result = locator.locate_from_bundle(bundle, "play button")

if result:
    gesture_engine.tap(result["x"], result["y"])
```

## Configuration

Edit `config/perception_config.yaml`:

```yaml
perception:
  ui_tree_enabled: true
  cv_vlm_enabled: true
  
  policy:
    min_confidence: 0.70
    validate_bounds: true
```

## Key Classes

### OmniParserDetector
```python
from perception.omniparser_detector import OmniParserDetector

detector = OmniParserDetector(device="auto")
detections = detector.detect(screenshot)
# Returns: [Detection(id="A", box=(...), center=(...), ...)]
```

### VLMSelector
```python
from perception.vlm_selector import VLMSelector

selector = VLMSelector(vlm_service)
result = selector.select(annotated_image, detections, "play button")
# Returns: SelectionResult(selected_id="B", coordinates=(...), ...)
```

### PerceptionPipeline
```python
from perception.perception_pipeline import PerceptionPipeline

pipeline = PerceptionPipeline(vlm_service)
result = pipeline.locate_element(intent, ui_tree, screenshot, bounds)
# Returns: LocateResult(success=True, coordinates=(...), source="ui_tree")
```

## Testing

```bash
pytest tests/test_perception_pipeline.py -v
```

## Performance Metrics

```python
pipeline = PerceptionPipeline(vlm_service)

# After some operations...
metrics = pipeline.get_metrics()
print(metrics)
# {
#   "ui_tree": {"attempts": 100, "successes": 75, "success_rate": 0.75},
#   "cv_vlm": {"attempts": 25, "successes": 20, "success_rate": 0.80},
#   "total_failures": 5,
#   "avg_latency_ms": 150.5
# }
```
