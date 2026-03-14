"""
OmniParser Detector - YOLOv8-based UI element detection.

Uses Microsoft's OmniParser pre-trained models for detecting UI elements
in mobile app screenshots. This is Layer 2 of the perception pipeline.

The detector provides geometrically precise bounding boxes. It does NOT
perform semantic understanding - that's the VLM's job in Layer 3.
"""

import base64
import hashlib
import os
import string
import time
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import numpy as np

from utils.logger import get_logger

logger = get_logger(__name__)

# Lazy imports for heavy dependencies
_YOLO = None
_cv2 = None
_Image = None
_HF_HUB = None


def _lazy_import_yolo():
    """Lazy import ultralytics to avoid startup cost."""
    global _YOLO
    if _YOLO is None:
        try:
            from ultralytics import YOLO
            _YOLO = YOLO
            logger.debug("YOLOv8 (ultralytics) loaded successfully")
        except ImportError as e:
            raise ImportError(
                "ultralytics package required for OmniParser detection. "
                "Install with: pip install ultralytics"
            ) from e
    return _YOLO


def _lazy_import_cv2():
    """Lazy import cv2 for image processing."""
    global _cv2
    if _cv2 is None:
        try:
            import cv2
            _cv2 = cv2
        except ImportError as e:
            raise ImportError(
                "opencv-python required for OmniParser. "
                "Install with: pip install opencv-python"
            ) from e
    return _cv2


def _lazy_import_pil():
    """Lazy import PIL for image conversion."""
    global _Image
    if _Image is None:
        from PIL import Image
        _Image = Image
    return _Image


def _lazy_import_hf_hub():
    """Lazy import huggingface_hub for model download."""
    global _HF_HUB
    if _HF_HUB is None:
        try:
            from huggingface_hub import snapshot_download
            _HF_HUB = snapshot_download
        except ImportError as e:
            raise ImportError(
                "huggingface-hub required for model download. "
                "Install with: pip install huggingface-hub"
            ) from e
    return _HF_HUB


@dataclass
class Detection:
    """Single UI element detection from OmniParser."""
    
    id: str                          # Letter ID: "A", "B", "C", ...
    class_name: str                  # Detection class: "icon", "button", etc.
    box: Tuple[int, int, int, int]   # Bounding box: (x1, y1, x2, y2)
    center: Tuple[int, int]          # Center point: (cx, cy)
    confidence: float                # Detection confidence: 0.0-1.0
    area: int = field(init=False)    # Box area in pixels
    
    def __post_init__(self):
        x1, y1, x2, y2 = self.box
        self.area = (x2 - x1) * (y2 - y1)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "class_name": self.class_name,
            "box": list(self.box),
            "center": list(self.center),
            "confidence": round(self.confidence, 4),
            "area": self.area
        }


class OmniParserDetector:
    """
    YOLOv8-based UI element detector using OmniParser models.
    
    This detector identifies all interactable UI elements in a screenshot
    and assigns each a unique letter ID (A, B, C, ...). The VLM then
    selects from these candidates based on user intent.
    
    Key design principle: This layer provides GEOMETRY only.
    Semantic understanding comes from the VLM in Layer 3.
    """
    
    # Class-level model cache to avoid reloading
    _model_cache: Dict[str, object] = {}
    _detection_cache: Dict[str, Tuple[List[Detection], float]] = {}
    
    def __init__(
        self,
        model_path: Optional[str] = None,
        huggingface_repo: str = "microsoft/OmniParser-v2.0",
        confidence_threshold: float = 0.2,
        iou_threshold: float = 0.5,
        device: str = "auto",
        image_size: int = 640,
        max_detections: int = 50,
        cache_ttl: float = 5.0,
    ):
        """
        Initialize the OmniParser detector.
        
        Args:
            model_path: Path to YOLOv8 weights. If None, downloads from HuggingFace.
            huggingface_repo: HuggingFace repo for model download.
            confidence_threshold: Minimum detection confidence (0.0-1.0).
            iou_threshold: IoU threshold for NMS (0.0-1.0). Higher = allow more overlap.
            device: Inference device ("auto", "cuda", "cpu", "mps").
            image_size: Input image size for YOLOv8.
            max_detections: Maximum detections to return.
            cache_ttl: Cache time-to-live in seconds.
        """
        self.model_path = model_path
        self.huggingface_repo = huggingface_repo
        self.confidence_threshold = confidence_threshold
        self.iou_threshold = iou_threshold
        self.device = device
        self.image_size = image_size
        self.max_detections = max_detections
        self.cache_ttl = cache_ttl
        
        self._model = None
        self._letter_ids = list(string.ascii_uppercase) + [
            f"{a}{b}" for a in string.ascii_uppercase for b in string.ascii_uppercase
        ]  # A-Z, then AA-ZZ (702 total IDs)
        
        logger.info(
            f"OmniParserDetector initialized "
            f"(device={device}, conf={confidence_threshold}, iou={iou_threshold}, cache_ttl={cache_ttl}s)"
        )
    
    @property
    def model(self):
        """Lazy-load the YOLOv8 model on first use."""
        if self._model is None:
            self._model = self._load_model()
        return self._model
    
    def _get_model_path(self) -> Path:
        """Get or download the model path."""
        if self.model_path:
            path = Path(self.model_path)
            if path.exists():
                return path
        
        # Default path in project
        default_path = Path("models/omniparser/icon_detect/best.pt")
        if default_path.exists():
            return default_path
        
        # Need to download from HuggingFace
        logger.info(f"Downloading OmniParser model from {self.huggingface_repo}...")
        snapshot_download = _lazy_import_hf_hub()
        
        try:
            # Download the entire repo
            local_dir = Path("models/omniparser")
            snapshot_download(
                repo_id=self.huggingface_repo,
                local_dir=str(local_dir),
                allow_patterns=["icon_detect/*"],
            )
            
            model_path = local_dir / "icon_detect" / "best.pt"
            if model_path.exists():
                logger.info(f"✅ Model downloaded to {model_path}")
                return model_path
            
            # Try alternate path structure
            model_path = local_dir / "icon_detect" / "model.pt"
            if model_path.exists():
                return model_path
                
            raise FileNotFoundError(
                f"Model not found in downloaded repo. "
                f"Check {local_dir} for available files."
            )
            
        except Exception as e:
            logger.error(f"Failed to download model: {e}")
            raise
    
    def _load_model(self):
        """Load the YOLOv8 model."""
        model_path = self._get_model_path()
        cache_key = str(model_path)
        
        # Check cache
        if cache_key in self._model_cache:
            logger.debug("Using cached YOLOv8 model")
            return self._model_cache[cache_key]
        
        YOLO = _lazy_import_yolo()
        
        logger.info(f"Loading YOLOv8 model from {model_path}...")
        start = time.time()
        
        model = YOLO(str(model_path))
        
        # Set device
        device = self._select_device()
        model.to(device)
        
        load_time = (time.time() - start) * 1000
        logger.info(f"✅ Model loaded in {load_time:.0f}ms on {device}")
        
        # Cache for reuse
        self._model_cache[cache_key] = model
        return model
    
    def _select_device(self) -> str:
        """Select the best available device."""
        if self.device != "auto":
            return self.device
        
        try:
            import torch
            if torch.cuda.is_available():
                return "cuda"
            if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                return "mps"
        except ImportError:
            pass
        
        return "cpu"
    
    def _image_hash(self, image: np.ndarray) -> str:
        """Compute a hash for cache lookup."""
        # Use a fast hash of downsampled image
        small = image[::10, ::10].tobytes()
        return hashlib.md5(small).hexdigest()
    
    def _prepare_image(
        self, 
        image: Union[np.ndarray, bytes, str, "Image.Image"]
    ) -> np.ndarray:
        """Convert various image formats to numpy array (BGR for cv2)."""
        cv2 = _lazy_import_cv2()
        Image = _lazy_import_pil()
        
        if isinstance(image, np.ndarray):
            # Already numpy, ensure BGR
            if len(image.shape) == 3 and image.shape[2] == 4:
                # RGBA -> BGR
                return cv2.cvtColor(image, cv2.COLOR_RGBA2BGR)
            elif len(image.shape) == 3 and image.shape[2] == 3:
                # Assume already BGR or convert RGB->BGR
                return image
            return image
        
        if isinstance(image, bytes):
            # Decode bytes
            nparr = np.frombuffer(image, np.uint8)
            return cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if isinstance(image, str):
            # Could be file path or base64
            if os.path.exists(image):
                return cv2.imread(image)
            else:
                # Assume base64
                try:
                    # Handle data URL format
                    if image.startswith("data:image"):
                        image = image.split(",")[1]
                    img_bytes = base64.b64decode(image)
                    nparr = np.frombuffer(img_bytes, np.uint8)
                    return cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                except Exception as e:
                    raise ValueError(f"Invalid image string: {e}")
        
        if hasattr(image, "convert"):  # PIL Image
            # Convert PIL to numpy BGR
            rgb = np.array(image.convert("RGB"))
            return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        
        raise TypeError(f"Unsupported image type: {type(image)}")
    
    def detect(
        self,
        image: Union[np.ndarray, bytes, str],
        use_cache: bool = True,
    ) -> List[Detection]:
        """
        Detect UI elements in screenshot.
        
        Args:
            image: Screenshot as numpy array, bytes, base64 string, or file path.
            use_cache: Whether to use detection cache.
            
        Returns:
            List of Detection objects with unique IDs.
        """
        start_time = time.time()
        
        # Prepare image
        img = self._prepare_image(image)
        
        # Check cache
        if use_cache:
            img_hash = self._image_hash(img)
            if img_hash in self._detection_cache:
                cached_detections, cache_time = self._detection_cache[img_hash]
                if time.time() - cache_time < self.cache_ttl:
                    logger.debug(f"Cache hit for detection ({len(cached_detections)} elements)")
                    return cached_detections
        
        # Run YOLOv8 inference
        results = self.model(
            img,
            conf=self.confidence_threshold,
            iou=self.iou_threshold,
            imgsz=self.image_size,
            verbose=False,
        )
        
        # Process results
        detections = []
        
        if results and len(results) > 0:
            result = results[0]
            boxes = result.boxes
            
            if boxes is not None and len(boxes) > 0:
                # Sort by confidence descending
                indices = boxes.conf.argsort(descending=True)
                
                for i, idx in enumerate(indices):
                    if i >= self.max_detections:
                        break
                    
                    idx = int(idx)
                    
                    # Get bounding box
                    xyxy = boxes.xyxy[idx].cpu().numpy()
                    x1, y1, x2, y2 = [int(v) for v in xyxy]
                    
                    # Get confidence
                    conf = float(boxes.conf[idx].cpu().numpy())
                    
                    # Get class name
                    class_id = int(boxes.cls[idx].cpu().numpy())
                    class_name = self.model.names.get(class_id, "element")
                    
                    # Calculate center
                    cx = (x1 + x2) // 2
                    cy = (y1 + y2) // 2
                    
                    # Assign letter ID
                    letter_id = self._letter_ids[i] if i < len(self._letter_ids) else f"X{i}"
                    
                    detection = Detection(
                        id=letter_id,
                        class_name=class_name,
                        box=(x1, y1, x2, y2),
                        center=(cx, cy),
                        confidence=conf,
                    )
                    detections.append(detection)
        
        # Update cache
        if use_cache:
            self._detection_cache[img_hash] = (detections, time.time())
        
        elapsed_ms = (time.time() - start_time) * 1000
        logger.info(f"✅ Detected {len(detections)} UI elements in {elapsed_ms:.0f}ms")
        
        return detections
    
    def draw_set_of_marks(
        self,
        image: Union[np.ndarray, bytes, str],
        detections: Optional[List[Detection]] = None,
        box_color: Tuple[int, int, int] = (0, 0, 255),  # Red in BGR
        text_color: Tuple[int, int, int] = (255, 255, 255),  # White
        thickness: int = 3,
        font_scale: float = 1.2,
    ) -> np.ndarray:
        """
        Draw bounding boxes with letter IDs on screenshot.
        
        This "Set-of-Marks" visualization is sent to the VLM for selection.
        Labels are large and placed to avoid overlapping siblings.
        
        Args:
            image: Original screenshot.
            detections: Detection list. If None, runs detection first.
            box_color: Bounding box color (BGR).
            text_color: Label text color (BGR).
            thickness: Box line thickness.
            font_scale: Label font scale.
            
        Returns:
            Annotated image as numpy array (BGR).
        """
        cv2 = _lazy_import_cv2()
        
        img = self._prepare_image(image).copy()
        h_img, w_img = img.shape[:2]
        
        if detections is None:
            detections = self.detect(img)
        
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_thick = max(2, int(thickness))
        pad = 6

        # Pre-compute badge sizes so we can do overlap avoidance
        badge_rects: List[Tuple[int, int, int, int]] = []  # (bx1, by1, bx2, by2)

        for det in detections:
            x1, y1, x2, y2 = det.box
            label = det.id
            (tw, th), _ = cv2.getTextSize(label, font, font_scale, font_thick)
            bw, bh = tw + pad * 2, th + pad * 2

            # Preferred: inside top-left corner of the box
            bx1, by1 = x1 + 2, y1 + 2
            bx2, by2 = bx1 + bw, by1 + bh

            # If badge would overflow the box height, fall back to just outside top
            if by2 > y2 - 4:
                bx1, by1 = x1, max(y1 - bh, 0)
                bx2, by2 = min(bx1 + bw, w_img - 1), by1 + bh

            # Nudge down to avoid overlapping a previously placed badge
            for prev_bx1, prev_by1, prev_bx2, prev_by2 in badge_rects:
                # Simple axis-aligned overlap check
                if bx1 < prev_bx2 and bx2 > prev_bx1 and by1 < prev_by2 and by2 > prev_by1:
                    # Move badge below the conflicting one
                    by1 = prev_by2 + 2
                    by2 = by1 + bh
                    # If that moves it off-screen, place right of conflict instead
                    if by2 > h_img - 1:
                        bx1 = prev_bx2 + 2
                        by1 = prev_by1
                        bx2 = min(bx1 + bw, w_img - 1)
                        by2 = by1 + bh

            badge_rects.append((bx1, by1, bx2, by2))

        for det, (bx1, by1, bx2, by2) in zip(detections, badge_rects):
            x1, y1, x2, y2 = det.box
            label = det.id
            (tw, th), _ = cv2.getTextSize(label, font, font_scale, font_thick)

            # Thick bounding box
            cv2.rectangle(img, (x1, y1), (x2, y2), box_color, thickness)

            # Black outline around badge for contrast on any background
            cv2.rectangle(img, (bx1 - 2, by1 - 2), (bx2 + 2, by2 + 2), (0, 0, 0), -1)
            # Filled colored badge
            cv2.rectangle(img, (bx1, by1), (bx2, by2), box_color, -1)
            # White label text
            cv2.putText(
                img,
                label,
                (bx1 + pad, by1 + th + pad - 2),
                font,
                font_scale,
                text_color,
                font_thick,
                cv2.LINE_AA,
            )
        
        return img
    
    def annotated_image_to_base64(
        self,
        annotated_image: np.ndarray,
        format: str = "jpeg",
        quality: int = 85,
    ) -> str:
        """Convert annotated image to base64 for VLM API."""
        cv2 = _lazy_import_cv2()
        
        if format.lower() == "jpeg":
            encode_params = [cv2.IMWRITE_JPEG_QUALITY, quality]
            ext = ".jpg"
        else:
            encode_params = []
            ext = ".png"
        
        success, buffer = cv2.imencode(ext, annotated_image, encode_params)
        if not success:
            raise ValueError("Failed to encode image")
        
        return base64.b64encode(buffer).decode("utf-8")
    
    def get_detection_by_id(
        self, 
        detections: List[Detection], 
        target_id: str
    ) -> Optional[Detection]:
        """Find detection by ID."""
        target_upper = target_id.upper().strip()
        for det in detections:
            if det.id.upper() == target_upper:
                return det
        return None
    
    def warmup(self) -> None:
        """
        Force-load the model and run a single dummy inference to warm up
        CUDA/CPU kernels so the first real request has no cold-start delay.
        """
        start = time.time()
        logger.info("OmniParser: warming up model...")
        _ = self.model  # triggers _load_model() if not already done
        dummy = np.zeros((self.image_size, self.image_size, 3), dtype=np.uint8)
        try:
            self.model(
                dummy,
                imgsz=self.image_size,
                conf=self.confidence_threshold,
                iou=self.iou_threshold,
                verbose=False,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"OmniParser warmup inference failed (non-fatal): {e}")
        logger.info(f"OmniParser: warmup done in {(time.time() - start) * 1000:.0f}ms")

    def clear_cache(self):
        """Clear the detection cache."""
        self._detection_cache.clear()
        logger.debug("Detection cache cleared")


# Factory function for easy initialization
def create_detector(
    model_path: Optional[str] = None,
    device: str = "auto",
    confidence: float = 0.2,
    iou: float = 0.5,
) -> OmniParserDetector:
    """
    Factory function to create OmniParserDetector with common defaults.
    
    Args:
        model_path: Custom model path. None = auto-download from HuggingFace.
        device: Inference device.
        confidence: Detection confidence threshold (lower = more detections).
        iou: IoU threshold for NMS (higher = allow more overlapping boxes).
        
    Returns:
        Configured OmniParserDetector instance.
    """
    return OmniParserDetector(
        model_path=model_path,
        device=device,
        confidence_threshold=confidence,
        iou_threshold=iou,
    )
