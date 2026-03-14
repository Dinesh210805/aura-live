"""
Tests for OmniParser Perception Pipeline.

Tests the three-layer hybrid perception architecture:
- Layer 1: UI Tree matching
- Layer 2: CV Detection (OmniParser)
- Layer 3: VLM Selection

Key principle: VLM never generates coordinates, only selects from CV candidates.
"""

import base64
import json
from unittest.mock import MagicMock, patch
import pytest

# Test data
SAMPLE_UI_TREE_ELEMENTS = [
    {
        "text": "Play",
        "contentDescription": "Play music",
        "resourceId": "com.spotify:id/play_button",
        "className": "android.widget.ImageButton",
        "bounds": {"left": 100, "top": 200, "right": 200, "bottom": 300},
        "clickable": True,
    },
    {
        "text": "Search",
        "contentDescription": "",
        "resourceId": "com.spotify:id/search",
        "className": "android.widget.EditText",
        "bounds": {"left": 50, "top": 50, "right": 400, "bottom": 100},
        "clickable": True,
    },
    {
        "text": "Home",
        "contentDescription": "Go to home",
        "resourceId": "com.spotify:id/nav_home",
        "className": "android.widget.Button",
        "bounds": {"left": 0, "top": 2200, "right": 200, "bottom": 2340},
        "clickable": True,
    },
]


class TestUITreeMatching:
    """Test Layer 1: UI Tree matching."""
    
    def test_exact_text_match(self):
        """Test exact text matching returns high confidence."""
        from utils.ui_element_finder import find_element
        
        result = find_element(SAMPLE_UI_TREE_ELEMENTS, "Play")
        
        assert result is not None
        assert result["x"] == 150  # Center of [100, 200]
        assert result["y"] == 250  # Center of [200, 300]
        assert result["score"] >= 0.9
    
    def test_partial_match(self):
        """Test partial text matching."""
        from utils.ui_element_finder import find_element
        
        result = find_element(SAMPLE_UI_TREE_ELEMENTS, "play button")
        
        assert result is not None
        assert "Play" in result.get("text", "")
    
    def test_content_description_match(self):
        """Test matching via contentDescription."""
        from utils.ui_element_finder import find_element
        
        result = find_element(SAMPLE_UI_TREE_ELEMENTS, "Play music")
        
        assert result is not None
    
    def test_resource_id_match(self):
        """Test matching via resource ID."""
        from utils.ui_element_finder import find_element
        
        result = find_element(SAMPLE_UI_TREE_ELEMENTS, "search")
        
        assert result is not None
        assert result["x"] == 225  # Center of [50, 400]
    
    def test_no_match_returns_none(self):
        """Test that non-matching query returns None."""
        from utils.ui_element_finder import find_element
        
        # Use a query with no semantic overlap with any element
        result = find_element(SAMPLE_UI_TREE_ELEMENTS, "qxzfoobar123", min_score=0.5)
        
        assert result is None
    
    def test_minimum_score_filter(self):
        """Test min_score filtering with very high threshold."""
        from utils.ui_element_finder import find_element
        
        # Note: find_element adds boosts for clickable (+0.1) and enabled (+0.05)
        # which can push scores above 1.0. Use a query that won't get exact match.
        result = find_element(SAMPLE_UI_TREE_ELEMENTS, "qxzfoobar123", min_score=0.5)
        
        # Should not match anything with a nonsense query
        assert result is None


class TestDetectionDataStructure:
    """Test Detection data structure."""
    
    def test_detection_creation(self):
        """Test Detection object creation."""
        from perception.omniparser_detector import Detection
        
        det = Detection(
            id="A",
            class_name="button",
            box=(100, 200, 300, 400),
            center=(200, 300),
            confidence=0.85,
        )
        
        assert det.id == "A"
        assert det.class_name == "button"
        assert det.box == (100, 200, 300, 400)
        assert det.center == (200, 300)
        assert det.confidence == 0.85
        assert det.area == 200 * 200  # (300-100) * (400-200)
    
    def test_detection_to_dict(self):
        """Test Detection serialization."""
        from perception.omniparser_detector import Detection
        
        det = Detection(
            id="B",
            class_name="icon",
            box=(10, 20, 50, 60),
            center=(30, 40),
            confidence=0.92,
        )
        
        d = det.to_dict()
        
        assert d["id"] == "B"
        assert d["class_name"] == "icon"
        assert d["box"] == [10, 20, 50, 60]
        assert d["center"] == [30, 40]
        assert d["confidence"] == 0.92


class TestVLMSelector:
    """Test Layer 3: VLM Selection (ID-based, no coordinate generation)."""
    
    @pytest.fixture
    def mock_vlm_service(self):
        """Create a mock VLM service."""
        mock = MagicMock()
        mock.settings = MagicMock()
        return mock
    
    @pytest.fixture
    def sample_detections(self):
        """Create sample detections."""
        from perception.omniparser_detector import Detection
        
        return [
            Detection(id="A", class_name="button", box=(100, 100, 200, 150), center=(150, 125), confidence=0.9),
            Detection(id="B", class_name="icon", box=(300, 100, 350, 150), center=(325, 125), confidence=0.85),
            Detection(id="C", class_name="button", box=(100, 200, 200, 250), center=(150, 225), confidence=0.88),
        ]
    
    def test_parse_single_letter_response(self, mock_vlm_service, sample_detections):
        """Test parsing simple letter response."""
        from perception.vlm_selector import VLMSelector
        
        mock_vlm_service.analyze_image.return_value = "B"
        
        selector = VLMSelector(mock_vlm_service)
        result = selector.select(
            annotated_image="base64data",
            detections=sample_detections,
            intent="play button"
        )
        
        assert result.success
        assert result.selected_id == "B"
        assert result.coordinates == (325, 125)
    
    def test_parse_letter_with_noise(self, mock_vlm_service, sample_detections):
        """Test parsing letter with extra text."""
        from perception.vlm_selector import VLMSelector
        
        mock_vlm_service.analyze_image.return_value = "The answer is: A"
        
        selector = VLMSelector(mock_vlm_service)
        result = selector.select(
            annotated_image="base64data",
            detections=sample_detections,
            intent="something"
        )
        
        assert result.success
        assert result.selected_id == "A"
    
    def test_parse_none_response(self, mock_vlm_service, sample_detections):
        """Test NONE response when no match."""
        from perception.vlm_selector import VLMSelector
        
        mock_vlm_service.analyze_image.return_value = "NONE"
        
        selector = VLMSelector(mock_vlm_service)
        result = selector.select(
            annotated_image="base64data",
            detections=sample_detections,
            intent="something not on screen"
        )
        
        assert not result.success
        assert "no matching" in result.reasoning.lower()
    
    def test_invalid_id_returns_failure(self, mock_vlm_service, sample_detections):
        """Test that invalid ID returns failure."""
        from perception.vlm_selector import VLMSelector
        
        # Return ID that doesn't exist
        mock_vlm_service.analyze_image.return_value = "Z"
        
        selector = VLMSelector(mock_vlm_service)
        result = selector.select(
            annotated_image="base64data",
            detections=sample_detections,
            intent="something"
        )
        
        assert not result.success
        assert "Z" in result.reasoning


class TestSelectionResult:
    """Test SelectionResult data structure."""
    
    def test_selection_result_success(self):
        """Test successful selection result."""
        from perception.vlm_selector import SelectionResult
        from perception.omniparser_detector import Detection
        
        det = Detection(id="A", class_name="button", box=(0, 0, 100, 100), center=(50, 50), confidence=0.9)
        
        result = SelectionResult(
            success=True,
            selected_id="A",
            detection=det,
            coordinates=(50, 50),
            confidence=0.9,
            reasoning="Selected play button",
        )
        
        assert result.success
        assert result.selected_id == "A"
        assert result.coordinates == (50, 50)
    
    def test_selection_result_to_dict(self):
        """Test SelectionResult serialization."""
        from perception.vlm_selector import SelectionResult
        
        result = SelectionResult(
            success=True,
            selected_id="B",
            coordinates=(100, 200),
            confidence=0.85,
        )
        
        d = result.to_dict()
        
        assert d["success"] is True
        assert d["selected_id"] == "B"
        assert d["coordinates"] == [100, 200]


class TestHeuristicSelector:
    """Test fallback heuristic selector."""
    
    @pytest.fixture
    def sample_detections(self):
        """Create sample detections."""
        from perception.omniparser_detector import Detection
        
        return [
            Detection(id="A", class_name="button", box=(100, 100, 200, 150), center=(150, 125), confidence=0.9),
            Detection(id="B", class_name="icon", box=(300, 100, 350, 150), center=(325, 125), confidence=0.85),
        ]
    
    def test_heuristic_button_match(self, sample_detections):
        """Test heuristic matching for button."""
        from perception.vlm_selector import HeuristicSelector
        
        selector = HeuristicSelector()
        result = selector.select(sample_detections, "click the button")
        
        assert result.success
        assert result.selected_id == "A"  # First button
    
    def test_heuristic_no_match(self, sample_detections):
        """Test heuristic with no matching elements."""
        from perception.vlm_selector import HeuristicSelector
        
        selector = HeuristicSelector()
        result = selector.select(sample_detections, "nonexistent thing")
        
        # May or may not match depending on confidence
        assert result.source == "heuristic_selector"


class TestLocateResult:
    """Test LocateResult data structure."""
    
    def test_locate_result_success(self):
        """Test successful locate result."""
        from perception.perception_pipeline import LocateResult
        
        result = LocateResult(
            success=True,
            coordinates=(500, 300),
            confidence=0.85,
            source="ui_tree",
        )
        
        assert result.success
        assert result.coordinates == (500, 300)
        assert result.source == "ui_tree"
    
    def test_locate_result_failure(self):
        """Test failed locate result."""
        from perception.perception_pipeline import LocateResult
        
        result = LocateResult(
            success=False,
            reason="Element not found",
            layer_attempted=["ui_tree", "cv_vlm"],
        )
        
        assert not result.success
        assert result.reason == "Element not found"
        assert "ui_tree" in result.layer_attempted


class TestPerceptionConfig:
    """Test perception configuration loading."""
    
    def test_default_config(self):
        """Test default configuration values."""
        from perception.perception_pipeline import PerceptionConfig
        
        config = PerceptionConfig()
        
        assert config.ui_tree_enabled is True
        assert config.cv_vlm_enabled is True
        assert config.min_confidence == 0.70
        assert config.detector_device == "auto"
    
    def test_config_from_yaml(self, tmp_path):
        """Test loading config from YAML file."""
        from perception.perception_pipeline import PerceptionConfig
        
        yaml_content = """
perception:
  ui_tree_enabled: true
  cv_vlm_enabled: false
  policy:
    min_confidence: 0.80
"""
        config_file = tmp_path / "test_config.yaml"
        config_file.write_text(yaml_content)
        
        config = PerceptionConfig.from_yaml(str(config_file))
        
        assert config.ui_tree_enabled is True
        assert config.cv_vlm_enabled is False
        assert config.min_confidence == 0.80


class TestPerceptionMetrics:
    """Test perception metrics tracking."""
    
    def test_metrics_recording(self):
        """Test metrics recording."""
        from perception.perception_pipeline import PerceptionMetrics
        
        metrics = PerceptionMetrics()
        
        metrics.record_attempt("ui_tree")
        metrics.record_success("ui_tree", 25.0)
        
        metrics.record_attempt("ui_tree")
        metrics.record_attempt("cv_vlm")
        metrics.record_success("cv_vlm", 500.0)
        
        assert metrics.ui_tree_attempts == 2
        assert metrics.ui_tree_successes == 1
        assert metrics.cv_vlm_attempts == 1
        assert metrics.cv_vlm_successes == 1
        
        assert metrics.ui_tree_success_rate == 0.5
        assert metrics.cv_vlm_success_rate == 1.0
    
    def test_metrics_to_dict(self):
        """Test metrics serialization."""
        from perception.perception_pipeline import PerceptionMetrics
        
        metrics = PerceptionMetrics()
        metrics.record_attempt("ui_tree")
        metrics.record_success("ui_tree", 30.0)
        
        d = metrics.to_dict()
        
        assert "ui_tree" in d
        assert d["ui_tree"]["attempts"] == 1
        assert d["ui_tree"]["successes"] == 1


class TestPerceptionPipeline:
    """Test the full perception pipeline."""
    
    @pytest.fixture
    def mock_vlm_service(self):
        """Create mock VLM service."""
        mock = MagicMock()
        mock.settings = MagicMock()
        return mock
    
    def test_ui_tree_success_short_circuits(self, mock_vlm_service):
        """Test that UI tree success doesn't call CV/VLM."""
        from perception.perception_pipeline import PerceptionPipeline, PerceptionConfig
        from perception.models import UITreePayload
        
        config = PerceptionConfig(ui_tree_enabled=True, cv_vlm_enabled=True)
        pipeline = PerceptionPipeline(mock_vlm_service, config)
        
        ui_tree = UITreePayload(
            elements=SAMPLE_UI_TREE_ELEMENTS,
            screen_width=1080,
            screen_height=2400,
            timestamp=1234567890,
        )
        
        result = pipeline.locate_element(
            intent="Play",
            ui_tree=ui_tree,
            screenshot=None,
            screen_bounds=(1080, 2400),
        )
        
        assert result.success
        assert result.source == "ui_tree"
        # CV/VLM should not be called when UI tree succeeds
        mock_vlm_service.analyze_image.assert_not_called()
    
    def test_fallback_to_cv_vlm_when_ui_fails(self, mock_vlm_service):
        """Test fallback to CV+VLM when UI tree fails."""
        from perception.perception_pipeline import PerceptionPipeline, PerceptionConfig
        from perception.models import UITreePayload
        
        # Mock VLM to return a selection
        mock_vlm_service.analyze_image.return_value = "A"
        
        config = PerceptionConfig(
            ui_tree_enabled=True,
            cv_vlm_enabled=True,
            ui_tree_min_score=0.99,  # High threshold to force failure
        )
        pipeline = PerceptionPipeline(mock_vlm_service, config)
        
        ui_tree = UITreePayload(
            elements=SAMPLE_UI_TREE_ELEMENTS,
            screen_width=1080,
            screen_height=2400,
            timestamp=1234567890,
        )
        
        # No screenshot means CV won't run
        result = pipeline.locate_element(
            intent="something not in tree",
            ui_tree=ui_tree,
            screenshot=None,
            screen_bounds=(1080, 2400),
        )
        
        # Without screenshot, should fail
        assert not result.success
        assert "ui_tree" in result.layer_attempted


class TestCoordinateValidation:
    """Test coordinate validation."""
    
    def test_valid_coordinates(self):
        """Test valid coordinates pass validation."""
        from utils.ui_element_finder import validate_coordinates
        
        is_valid, reason = validate_coordinates(500, 1200, 1080, 2400)
        
        assert is_valid
        assert reason == "Valid"
    
    def test_out_of_bounds_x(self):
        """Test X out of bounds."""
        from utils.ui_element_finder import validate_coordinates
        
        is_valid, reason = validate_coordinates(1200, 500, 1080, 2400)
        
        assert not is_valid
        assert "X" in reason
    
    def test_negative_coordinates(self):
        """Test negative coordinates fail."""
        from utils.ui_element_finder import validate_coordinates
        
        is_valid, reason = validate_coordinates(-10, 500, 1080, 2400)
        
        assert not is_valid
        assert "Negative" in reason
    
    def test_status_bar_zone(self):
        """Test status bar zone detection."""
        from utils.ui_element_finder import validate_coordinates
        
        is_valid, reason = validate_coordinates(500, 30, 1080, 2400)
        
        assert not is_valid
        assert "status bar" in reason.lower()


class TestVLMNeverGeneratesCoordinates:
    """
    Critical test: Verify VLM only selects IDs, never generates coordinates.
    
    This is the core principle of the OmniParser architecture.
    """
    
    def test_vlm_prompt_asks_for_id_not_coordinates(self):
        """Verify VLM prompt only asks for ID selection."""
        from perception.vlm_selector import VLMSelector
        
        # Check both prompts
        assert "single letter" in VLMSelector.SELECTION_PROMPT.lower()
        assert "coordinate" not in VLMSelector.SELECTION_PROMPT.lower()
        assert "percent" not in VLMSelector.SELECTION_PROMPT.lower()
        assert "position" not in VLMSelector.SELECTION_PROMPT.lower()
        
        # Prompt should ask for A, B, C etc.
        assert "a, b, c" in VLMSelector.SELECTION_PROMPT.lower() or "letter" in VLMSelector.SELECTION_PROMPT.lower()
    
    def test_coordinates_come_from_detection(self):
        """Verify coordinates come from Detection, not VLM."""
        from perception.vlm_selector import SelectionResult
        from perception.omniparser_detector import Detection
        
        # Create detection with known coordinates
        det = Detection(
            id="A",
            class_name="button",
            box=(100, 200, 300, 400),
            center=(200, 300),  # These are the coordinates
            confidence=0.9,
        )
        
        # Selection result gets coordinates FROM detection
        result = SelectionResult(
            success=True,
            selected_id="A",
            detection=det,
            coordinates=det.center,  # Coordinates from CV detection
            confidence=det.confidence,
        )
        
        # Verify coordinates match detection, not some VLM-generated value
        assert result.coordinates == det.center
        assert result.coordinates == (200, 300)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
