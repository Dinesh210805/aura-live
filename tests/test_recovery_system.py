"""
Tests for Phase 3: Adaptive Recovery System.

Tests FailureAnalyzer, RecoveryStrategist, and their integration with UniversalAgent.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch

from services.failure_analyzer import (
    FailureAnalyzer,
    FailureCategory,
    FailureAnalysis,
)
from services.recovery_strategist import (
    RecoveryStrategist,
    RecoveryAction,
    RecoveryPlan,
)
from services.reasoning_engine import ReasonedAction, ActionType


# --- FailureAnalyzer Tests ---

class TestFailureAnalyzer:
    """Tests for the FailureAnalyzer service."""

    @pytest.fixture
    def mock_vlm_service(self):
        """Create mock VLM service."""
        service = Mock()
        return service

    @pytest.fixture
    def analyzer(self, mock_vlm_service):
        """Create FailureAnalyzer with mocked dependencies."""
        return FailureAnalyzer(mock_vlm_service)

    @pytest.fixture
    def sample_action(self):
        """Create a sample failed action."""
        return ReasonedAction(
            action_type=ActionType.TAP,
            target="Settings button",
            confidence=0.8,
        )

    @pytest.fixture
    def mock_bundle(self):
        """Create mock perception bundle."""
        bundle = Mock()
        bundle.ui_tree = Mock()
        bundle.ui_tree.elements = [
            {"text": "Home", "class": "Button"},
            {"text": "Profile", "class": "Button"},
        ]
        bundle.screenshot_base64 = "fake_base64"
        bundle.screen_meta = Mock(width=1080, height=2400)
        return bundle

    def test_analyze_element_not_found(self, analyzer, sample_action, mock_bundle):
        """Test detection of element not found failures."""
        report = analyzer.analyze_failure(
            action=sample_action,
            before_bundle=mock_bundle,
            after_bundle=mock_bundle,
            error_message="Could not locate target element",
        )

        assert isinstance(report, FailureAnalysis)
        assert report.category == FailureCategory.ELEMENT_NOT_FOUND
        assert report.confidence > 0

    def test_analyze_timeout(self, analyzer, sample_action, mock_bundle):
        """Test detection of timeout failures."""
        # Create a different after_bundle to avoid triggering "UI unchanged" heuristic
        after_bundle = Mock()
        after_bundle.ui_tree = Mock()
        after_bundle.ui_tree.elements = [{"text": "Different", "class": "TextView"}]
        after_bundle.screenshot_base64 = "different_base64"
        after_bundle.screen_meta = Mock(width=1080, height=2400)
        
        report = analyzer.analyze_failure(
            action=sample_action,
            before_bundle=mock_bundle,
            after_bundle=after_bundle,
            error_message="timeout waiting for response",
        )

        assert isinstance(report, FailureAnalysis)
        assert report.category == FailureCategory.TIMING_ISSUE

    def test_analyze_permission_denied(self, analyzer, sample_action, mock_bundle):
        """Test detection of permission denied failures."""
        report = analyzer.analyze_failure(
            action=sample_action,
            before_bundle=mock_bundle,
            after_bundle=mock_bundle,
            error_message="Permission denied for camera",
        )

        assert isinstance(report, FailureAnalysis)
        assert report.category == FailureCategory.PERMISSION_DENIED
        assert report.requires_user_input is True

    def test_analyze_no_effect(self, analyzer, sample_action, mock_bundle):
        """Test detection when action has no effect on UI."""
        # Same bundle before/after means no UI change
        report = analyzer.analyze_failure(
            action=sample_action,
            before_bundle=mock_bundle,
            after_bundle=mock_bundle,
            error_message=None,
        )

        assert isinstance(report, FailureAnalysis)
        # Should detect action had no effect
        assert report.confidence > 0


# --- RecoveryStrategist Tests ---

class TestRecoveryStrategist:
    """Tests for the RecoveryStrategist service."""

    @pytest.fixture
    def strategist(self):
        """Create RecoveryStrategist."""
        return RecoveryStrategist()

    @pytest.fixture
    def sample_action(self):
        """Create a sample action."""
        return ReasonedAction(
            action_type=ActionType.TAP,
            target="Settings button",
            confidence=0.8,
        )

    @pytest.fixture
    def element_not_found_failure(self):
        """Create element not found failure report."""
        return FailureAnalysis(
            category=FailureCategory.ELEMENT_NOT_FOUND,
            description="Target element not visible on screen",
            confidence=0.9,
            context={"visible_elements": ["Home", "Profile"]},
        )

    @pytest.fixture
    def wrong_screen_failure(self):
        """Create wrong screen failure report."""
        return FailureAnalysis(
            category=FailureCategory.WRONG_SCREEN,
            description="Currently on home screen, expected settings",
            confidence=0.85,
            context={"current_app": "launcher"},
        )

    @pytest.fixture
    def permission_failure(self):
        """Create permission denied failure report."""
        return FailureAnalysis(
            category=FailureCategory.PERMISSION_DENIED,
            description="Camera permission denied",
            confidence=0.95,
            context={"dialog_text": "Allow camera access?"},
            requires_user_input=True,
        )

    def test_plan_for_element_not_found(self, strategist, element_not_found_failure, sample_action):
        """Test recovery plan for element not found."""
        plan = strategist.get_recovery_plan(
            failure=element_not_found_failure,
            original_action=sample_action,
        )

        assert isinstance(plan, RecoveryPlan)
        assert len(plan.actions) > 0
        # Should include scroll actions for element not found
        scroll_actions = [RecoveryAction.SCROLL_DOWN, RecoveryAction.SCROLL_UP]
        assert any(action in plan.actions for action in scroll_actions)

    def test_plan_for_wrong_screen(self, strategist, wrong_screen_failure, sample_action):
        """Test recovery plan for wrong screen."""
        plan = strategist.get_recovery_plan(
            failure=wrong_screen_failure,
            original_action=sample_action,
        )

        assert isinstance(plan, RecoveryPlan)
        assert RecoveryAction.GO_BACK in plan.actions

    def test_plan_for_permission_denied(self, strategist, permission_failure, sample_action):
        """Test recovery plan for permission denied."""
        plan = strategist.get_recovery_plan(
            failure=permission_failure,
            original_action=sample_action,
        )

        assert isinstance(plan, RecoveryPlan)
        # Permission denied should ask user or abort
        assert RecoveryAction.ASK_USER in plan.actions or RecoveryAction.ABORT in plan.actions

    def test_plan_for_popup(self, strategist, sample_action):
        """Test recovery plan for unexpected popup."""
        failure = FailureAnalysis(
            category=FailureCategory.UNEXPECTED_POPUP,
            description="Popup dialog appeared",
            confidence=0.9,
            context={"dialog_buttons": ["Cancel", "OK"]},
        )

        plan = strategist.get_recovery_plan(
            failure=failure,
            original_action=sample_action,
        )

        assert isinstance(plan, RecoveryPlan)
        assert RecoveryAction.DISMISS_POPUP in plan.actions

    def test_plan_for_loading_state(self, strategist, sample_action):
        """Test recovery plan for loading state."""
        failure = FailureAnalysis(
            category=FailureCategory.LOADING_STATE,
            description="App is loading content",
            confidence=0.8,
            context={},
        )

        plan = strategist.get_recovery_plan(
            failure=failure,
            original_action=sample_action,
        )

        assert isinstance(plan, RecoveryPlan)
        assert RecoveryAction.WAIT_FOR_LOADING in plan.actions

    def test_plan_has_description(self, strategist, element_not_found_failure, sample_action):
        """Test that recovery plans have descriptions."""
        plan = strategist.get_recovery_plan(
            failure=element_not_found_failure,
            original_action=sample_action,
        )

        assert plan.description


# --- Integration Tests ---

class TestRecoveryIntegration:
    """Integration tests for the recovery system."""

    def test_analyzer_to_strategist_flow(self):
        """Test end-to-end flow from failure analysis to recovery strategy."""
        # Create components
        mock_vlm = Mock()
        
        analyzer = FailureAnalyzer(mock_vlm)
        strategist = RecoveryStrategist()

        # Simulate failure
        action = ReasonedAction(
            action_type=ActionType.TAP,
            target="Send button",
            confidence=0.8,
        )

        bundle = Mock()
        bundle.ui_tree = Mock()
        bundle.ui_tree.elements = [{"text": "Message", "class": "EditText"}]
        bundle.screenshot_base64 = None
        bundle.screen_meta = Mock(width=1080, height=2400)

        # Analyze failure
        failure_report = analyzer.analyze_failure(
            action=action,
            before_bundle=bundle,
            after_bundle=bundle,
            error_message="Could not find Send button",
        )

        # Get recovery plan
        plan = strategist.get_recovery_plan(
            failure=failure_report,
            original_action=action,
        )

        # Verify flow completed
        assert failure_report.category is not None
        assert len(plan.actions) > 0

    def test_multiple_failure_categories(self):
        """Test that different failures get different strategies."""
        strategist = RecoveryStrategist()
        sample_action = ReasonedAction(
            action_type=ActionType.TAP,
            target="test",
            confidence=0.8,
        )

        # Test multiple categories
        strategies_by_category = {}
        
        for category in [
            FailureCategory.ELEMENT_NOT_FOUND,
            FailureCategory.WRONG_SCREEN,
            FailureCategory.UNEXPECTED_POPUP,
            FailureCategory.LOADING_STATE,
        ]:
            failure = FailureAnalysis(
                category=category,
                description=f"Test failure: {category.value}",
                confidence=0.9,
                context={},
            )
            
            plan = strategist.get_recovery_plan(
                failure=failure,
                original_action=sample_action,
            )
            
            strategies_by_category[category] = plan.actions[0] if plan.actions else None

        # Verify different categories get different primary strategies
        unique_strategies = set(strategies_by_category.values())
        assert len(unique_strategies) > 1, "Different failure types should have different strategies"
