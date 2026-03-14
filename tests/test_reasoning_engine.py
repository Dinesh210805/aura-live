"""
Tests for Phase 2: ReasoningEngine, GoalDecomposer, UniversalAgent.

Tests the reasoning-based execution system.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from dataclasses import asdict

from services.reasoning_engine import (
    ReasoningEngine,
    ReasonedAction,
    ActionType,
    ThoughtStep,
)
from services.goal_decomposer import GoalDecomposer, decompose_simple_command
from aura_graph.agent_state import Goal, Subgoal, AgentState


class TestReasoningEngine:
    """Test ReasoningEngine service."""

    @pytest.fixture
    def engine(self):
        """Create engine with mocked services."""
        mock_llm = Mock()
        mock_vlm = Mock()
        return ReasoningEngine(mock_llm, mock_vlm), mock_llm, mock_vlm

    def test_parse_action_type(self, engine):
        """Test action type parsing."""
        eng, _, _ = engine
        
        assert eng._parse_action_type("tap") == ActionType.TAP
        assert eng._parse_action_type("click") == ActionType.TAP
        assert eng._parse_action_type("type") == ActionType.TYPE
        assert eng._parse_action_type("swipe") == ActionType.SWIPE
        assert eng._parse_action_type("scroll") == ActionType.SCROLL
        assert eng._parse_action_type("back") == ActionType.BACK
        assert eng._parse_action_type("done") == ActionType.DONE
        assert eng._parse_action_type("stuck") == ActionType.STUCK
        assert eng._parse_action_type("unknown_action") == ActionType.STUCK

    def test_reason_with_llm_success(self, engine):
        """Test LLM reasoning returns valid action."""
        eng, mock_llm, _ = engine
        
        mock_llm.generate.return_value = '''
        {
            "thought": "Need to tap the send button to complete the message",
            "action": "tap",
            "target": "send button",
            "confidence": 0.85,
            "alternatives": ["try mic button if send fails"]
        }
        '''
        
        # Create mock goal
        goal = Goal(
            original_utterance="send a message",
            description="Send a message",
            subgoals=[Subgoal(description="Tap send", action_type="tap", target="send")],
        )
        
        result = eng._reason_with_llm(
            observation="Screen: WhatsApp chat | Visible: message field, send button",
            context="Goal: Send message",
            goal=goal,
        )
        
        assert result.action_type == ActionType.TAP
        assert result.target == "send button"
        assert result.confidence == 0.85
        assert "send button" in result.reasoning

    def test_thought_trace_recorded(self, engine):
        """Test that thought trace is recorded."""
        eng, mock_llm, _ = engine
        
        # Start fresh
        eng.reset_for_new_goal()
        assert len(eng.thought_trace) == 0
        
        mock_llm.generate.return_value = '{"thought": "test", "action": "tap", "target": "x", "confidence": 0.8}'
        
        goal = Goal(
            original_utterance="test",
            description="Test",
            subgoals=[Subgoal(description="Test", action_type="tap")],
        )
        
        # Create mock bundle
        mock_bundle = Mock()
        mock_bundle.screen_meta.width = 1080
        mock_bundle.screen_meta.height = 2400
        mock_bundle.ui_tree = None
        
        eng.reason_next_action(goal, mock_bundle)
        
        # Should have recorded one thought step
        assert len(eng.thought_trace) == 1
        assert isinstance(eng.thought_trace[0], ThoughtStep)

    def test_action_history_bounded(self, engine):
        """Test action history stays bounded."""
        eng, _, _ = engine
        
        # Add many actions
        for i in range(25):
            eng.record_action_result(
                ReasonedAction(action_type=ActionType.TAP, target=f"element_{i}"),
                success=True,
            )
        
        # Should be capped at 20
        assert len(eng.action_history) == 20
        # Should have most recent
        assert eng.action_history[-1]["target"] == "element_24"


class TestGoalDecomposer:
    """Test GoalDecomposer service."""

    @pytest.fixture
    def decomposer(self):
        """Create decomposer with mocked LLM."""
        mock_llm = Mock()
        return GoalDecomposer(mock_llm), mock_llm

    def test_decompose_with_llm(self, decomposer):
        """Test LLM-based goal decomposition."""
        decomp, mock_llm = decomposer
        
        mock_llm.generate.return_value = '''
        {
            "goal_summary": "Send WhatsApp message to John",
            "subgoals": [
                {
                    "description": "Open WhatsApp",
                    "action_type": "open_app",
                    "target": "WhatsApp",
                    "success_hint": "WhatsApp home visible"
                },
                {
                    "description": "Find and tap John's chat",
                    "action_type": "tap",
                    "target": "John",
                    "success_hint": "Chat with John opens"
                },
                {
                    "description": "Type the message",
                    "action_type": "type",
                    "target": "Hello there!",
                    "success_hint": "Message appears in input"
                },
                {
                    "description": "Tap send button",
                    "action_type": "tap",
                    "target": "send",
                    "success_hint": "Message sent"
                }
            ]
        }
        '''
        
        goal = decomp.decompose("Send 'Hello there!' to John on WhatsApp")
        
        assert goal is not None
        assert len(goal.subgoals) == 4
        assert goal.subgoals[0].action_type == "open_app"
        assert goal.subgoals[0].target == "WhatsApp"
        assert goal.subgoals[3].action_type == "tap"
        assert goal.subgoals[3].target == "send"

    def test_decompose_simple_command(self):
        """Test simple command decomposition (no LLM)."""
        goal = decompose_simple_command(
            utterance="scroll down",
            action="scroll",
            target="down",
        )
        
        assert goal is not None
        assert len(goal.subgoals) == 1
        assert goal.subgoals[0].action_type == "scroll"
        assert goal.subgoals[0].target == "down"

    def test_summarize_goal(self, decomposer):
        """Test goal summarization."""
        decomp, _ = decomposer
        
        assert decomp._summarize_goal("please open settings") == "Open settings"
        assert decomp._summarize_goal("can you tap on profile") == "Tap on profile"
        assert decomp._summarize_goal("i want to send a message") == "Send a message"

    def test_replan_from_obstacle(self, decomposer):
        """Test replanning when stuck."""
        decomp, mock_llm = decomposer
        
        mock_llm.generate.return_value = '''
        {
            "analysis": "Contact not found in visible list, need to scroll",
            "subgoals": [
                {
                    "description": "Scroll down to find contact",
                    "action_type": "scroll",
                    "target": "down"
                },
                {
                    "description": "Tap on John when visible",
                    "action_type": "tap",
                    "target": "John"
                }
            ]
        }
        '''
        
        goal = Goal(
            original_utterance="Message John",
            description="Message John",
            subgoals=[Subgoal(description="Tap John", action_type="tap", target="John")],
        )
        
        new_subgoals = decomp.replan_from_obstacle(
            goal=goal,
            obstacle="Could not find John in visible contacts",
        )
        
        assert len(new_subgoals) == 2
        assert new_subgoals[0].action_type == "scroll"


class TestAgentState:
    """Test AgentState management."""

    def test_check_abort_conditions(self):
        """Test abort condition detection."""
        state = AgentState()
        
        # No abort initially
        assert state.check_abort_conditions() is None
        
        # Exceed max attempts
        state.total_attempts = 20
        abort = state.check_abort_conditions()
        assert abort is not None
        assert abort.value == "max_retries_exceeded"

    def test_same_screen_loop_detection(self):
        """Test same screen loop detection."""
        state = AgentState()
        
        # Record same signature multiple times
        # Counter: 0 (first) -> 1 (2nd match) -> 2 (3rd match) -> 3 (4th match)
        state.record_ui_signature("screen_A")
        state.record_ui_signature("screen_A")
        state.record_ui_signature("screen_A")
        state.record_ui_signature("screen_A")
        
        assert state.consecutive_same_screen == 3  # After 4th same (threshold reached)
        abort = state.check_abort_conditions()
        assert abort is not None
        assert abort.value == "same_screen_loop"

    def test_ui_signature_history_bounded(self):
        """Test UI signature history stays bounded."""
        state = AgentState()
        
        for i in range(15):
            state.record_ui_signature(f"screen_{i}")
        
        # Should keep only last 10
        assert len(state.ui_signature_history) == 10
        assert state.ui_signature_history[0] == "screen_5"

    def test_goal_subgoal_advancement(self):
        """Test subgoal advancement."""
        goal = Goal(
            original_utterance="test",
            description="Test",
            subgoals=[
                Subgoal(description="Step 1", action_type="tap"),
                Subgoal(description="Step 2", action_type="type"),
                Subgoal(description="Step 3", action_type="tap"),
            ],
        )
        
        assert goal.current_subgoal.description == "Step 1"
        
        goal.advance_subgoal()
        assert goal.current_subgoal.description == "Step 2"
        assert goal.subgoals[0].completed
        
        goal.advance_subgoal()
        goal.advance_subgoal()
        assert goal.completed
        assert goal.current_subgoal is None


class TestReasonedAction:
    """Test ReasonedAction dataclass."""

    def test_creation(self):
        """Test creating a reasoned action."""
        action = ReasonedAction(
            action_type=ActionType.TAP,
            target="send button",
            reasoning="Found send button in bottom right",
            confidence=0.9,
            x=950,
            y=2200,
        )
        
        assert action.action_type == ActionType.TAP
        assert action.target == "send button"
        assert action.confidence == 0.9
        assert action.x == 950
        assert action.y == 2200

    def test_defaults(self):
        """Test default values."""
        action = ReasonedAction(action_type=ActionType.STUCK)
        
        assert action.target is None
        assert action.reasoning == ""
        assert action.confidence == 0.0
        assert action.alternatives == []
        assert action.x is None
        assert action.y is None
