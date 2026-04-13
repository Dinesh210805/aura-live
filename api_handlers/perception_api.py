"""
Perception API Endpoints.

Exposes OmniParser (YOLOv8 UI element detector) as a REST endpoint
so the MCP server (separate process) can call it without importing
the heavy model directly.

OmniParser is pre-warmed at server startup by PerceptionPipeline.warmup().
This endpoint just re-uses that already-loaded model instance.
"""

import base64
from io import BytesIO
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["Perception"])


class OmniParserRequest(BaseModel):
    """OmniParser detection request."""

    screenshot_b64: str = Field(..., description="Base64-encoded PNG screenshot")
    screen_width: int = Field(1080, description="Screen width in pixels")
    screen_height: int = Field(1920, description="Screen height in pixels")
    confidence: float = Field(0.3, description="Detection confidence threshold (0-1)")
    include_annotated_image: bool = Field(
        False, description="If true, return annotated SoM image as base64"
    )


class DetectionResult(BaseModel):
    """Single detected UI element."""

    label: str
    description: str
    bounds: Dict[str, float]
    confidence: float
    center_x: float
    center_y: float
    element_type: str


class OmniParserResponse(BaseModel):
    """OmniParser detection response."""

    elements_detected: int
    detections: List[DetectionResult]
    annotated_image_b64: Optional[str] = None
    error: Optional[str] = None


@router.post("/omniparser-detect", response_model=OmniParserResponse)
async def omniparser_detect(request: OmniParserRequest) -> OmniParserResponse:
    """
    Run OmniParser (YOLOv8) on a screenshot and return labeled UI elements.

    OmniParser assigns Set-of-Marks labels (A1, A2 ... ZZ) to detected elements.
    These labels are used by the VLM to select elements without hallucinating coordinates.

    The model is pre-loaded at server startup — this endpoint has low latency
    on the first call after startup (no cold-load cost).
    """
    try:
        # Decode screenshot
        try:
            img_bytes = base64.b64decode(request.screenshot_b64)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid base64 screenshot data")

        # Get the OmniParser detector via the perception pipeline singleton
        from perception import get_omniparser_detector, get_perception_pipeline

        PerceptionPipeline, _, _, create_pipeline = get_perception_pipeline()
        OmniParserDetector, Detection, create_detector = get_omniparser_detector()

        # Use the pipeline's already-loaded detector if available, else create one
        from services.perception_controller import get_perception_controller
        controller = get_perception_controller()

        detector = None
        pipeline = getattr(controller, "_pipeline", None)
        if pipeline is not None:
            detector = getattr(pipeline, "_detector", None)

        if detector is None:
            # Fallback: create a fresh detector (will load model)
            logger.info("Creating fresh OmniParser detector for API request")
            from config.settings import get_settings
            s = get_settings()
            detector = create_detector(
                model_path=getattr(s, "omniparser_model_path", "weights/omniparser/best.pt"),
                device="cpu",
                confidence=request.confidence,
                iou=0.45,
            )

        # Load image
        try:
            from PIL import Image
            image = Image.open(BytesIO(img_bytes)).convert("RGB")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to decode image: {e}")

        # Run detection
        detections = detector.detect(image, use_cache=False)

        results: List[DetectionResult] = []
        for det in detections:
            bounds = getattr(det, "bounds", {})
            if not isinstance(bounds, dict):
                bounds = {
                    "left": det.x1 if hasattr(det, "x1") else 0,
                    "top": det.y1 if hasattr(det, "y1") else 0,
                    "right": det.x2 if hasattr(det, "x2") else 0,
                    "bottom": det.y2 if hasattr(det, "y2") else 0,
                }
            center_x = bounds.get("centerX", (bounds.get("left", 0) + bounds.get("right", 0)) / 2)
            center_y = bounds.get("centerY", (bounds.get("top", 0) + bounds.get("bottom", 0)) / 2)

            results.append(DetectionResult(
                label=getattr(det, "label", ""),
                description=getattr(det, "description", ""),
                bounds=bounds,
                confidence=float(getattr(det, "confidence", 0.0)),
                center_x=float(center_x),
                center_y=float(center_y),
                element_type=getattr(det, "element_type", "unknown"),
            ))

        # Optionally produce annotated SoM image
        annotated_b64 = None
        if request.include_annotated_image and detections:
            try:
                annotated = detector.draw_set_of_marks(image, detections)
                annotated_b64 = detector.annotated_image_to_base64(annotated)
            except Exception as e:
                logger.warning(f"Failed to generate annotated image: {e}")

        logger.info(f"OmniParser detected {len(results)} elements")
        return OmniParserResponse(
            elements_detected=len(results),
            detections=results,
            annotated_image_b64=annotated_b64,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OmniParser detection failed: {e}")
        return OmniParserResponse(
            elements_detected=0,
            detections=[],
            error=str(e),
        )
