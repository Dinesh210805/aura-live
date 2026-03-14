"""
Tests for Phase 4: Experience Memory and Pattern Learning.

Tests ExperienceMemory, PatternExtractor, and learning integration.
"""

import pytest
import tempfile
import os
from unittest.mock import Mock

from services.experience_memory import (
    ExperienceMemory,
    ActionRecord,
    GoalPattern,
)
from services.pattern_extractor import (
    PatternExtractor,
    ActionRecommendation,
    GoalHint,
)


# --- ExperienceMemory Tests ---

class TestExperienceMemory:
    """Tests for the ExperienceMemory service."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database."""
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        yield path
        os.unlink(path)

    @pytest.fixture
    def memory(self, temp_db):
        """Create ExperienceMemory with temp database."""
        return ExperienceMemory(db_path=temp_db)

    def test_record_action(self, memory):
        """Test recording a single action."""
        record = ActionRecord(
            session_id="test-session",
            goal="send message to John",
            subgoal="tap compose button",
            action_type="tap",
            target="compose",
            app_package="com.android.messaging",
            screen_signature="home|messages",
            success=True,
        )

        record_id = memory.record_action(record)
        assert record_id > 0

    def test_record_goal_completion(self, memory):
        """Test recording a goal completion."""
        memory.record_goal_completion(
            goal="send message to John",
            app_package="com.android.messaging",
            action_sequence=["tap:compose", "tap:recipient", "type:John"],
            success=True,
        )

        # Should create a pattern
        pattern = memory.get_pattern_for_goal("send message to Mary")
        assert pattern is not None
        assert pattern.success_count == 1

    def test_goal_normalization(self, memory):
        """Test that similar goals match the same pattern."""
        # Record first goal
        memory.record_goal_completion(
            goal="send message to John",
            app_package="com.android.messaging",
            action_sequence=["tap:compose", "type:hello"],
            success=True,
        )

        # Record similar goal
        memory.record_goal_completion(
            goal="send message to Mary",
            app_package="com.android.messaging",
            action_sequence=["tap:compose", "type:hi"],
            success=True,
        )

        # Should update same pattern
        pattern = memory.get_pattern_for_goal("send message to Jane")
        assert pattern is not None
        assert pattern.success_count == 2

    def test_get_similar_failures(self, memory):
        """Test retrieving similar failure records."""
        # Record some failures
        for i in range(3):
            record = ActionRecord(
                session_id=f"session-{i}",
                goal="open camera",
                subgoal="tap camera icon",
                action_type="tap",
                target="camera",
                app_package="com.android.camera",
                success=False,
                failure_category="PERMISSION_BLOCKED",
            )
            memory.record_action(record)

        failures = memory.get_similar_failures(
            goal="open camera",
            failure_category="PERMISSION_BLOCKED",
        )

        assert len(failures) == 3

    def test_get_success_rate(self, memory):
        """Test success rate calculation."""
        # Record mixed results
        for success in [True, True, True, False, False]:
            record = ActionRecord(
                session_id="test",
                goal="test goal",
                action_type="tap",
                success=success,
            )
            memory.record_action(record)

        stats = memory.get_success_rate()
        assert stats["total_actions"] == 5
        assert stats["success_rate"] == 0.6

    def test_record_shortcut(self, memory):
        """Test recording and retrieving shortcuts."""
        memory.record_shortcut(
            app_package="com.android.settings",
            from_screen="home",
            to_screen="wifi",
            action_sequence=["tap:network", "tap:wifi"],
        )

        shortcut = memory.get_shortcut(
            app_package="com.android.settings",
            from_screen="home",
            to_screen="wifi",
        )

        # Needs 2 successes to be returned
        assert shortcut is None

        # Record again
        memory.record_shortcut(
            app_package="com.android.settings",
            from_screen="home",
            to_screen="wifi",
            action_sequence=["tap:network", "tap:wifi"],
        )

        shortcut = memory.get_shortcut(
            app_package="com.android.settings",
            from_screen="home",
            to_screen="wifi",
        )

        assert shortcut == ["tap:network", "tap:wifi"]


# --- PatternExtractor Tests ---

class TestPatternExtractor:
    """Tests for the PatternExtractor service."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database."""
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        yield path
        os.unlink(path)

    @pytest.fixture
    def memory(self, temp_db):
        """Create ExperienceMemory with temp database."""
        return ExperienceMemory(db_path=temp_db)

    @pytest.fixture
    def extractor(self, memory):
        """Create PatternExtractor with memory."""
        return PatternExtractor(memory=memory)

    def test_get_hints_no_pattern(self, extractor):
        """Test hints when no pattern exists."""
        hints = extractor.get_hints_for_goal("do something new")

        assert isinstance(hints, GoalHint)
        assert hints.known_pattern is None
        assert hints.expected_steps == 5  # Default

    def test_get_hints_with_pattern(self, extractor, memory):
        """Test hints when pattern exists."""
        # Create a pattern
        memory.record_goal_completion(
            goal="open settings",
            app_package="com.android.settings",
            action_sequence=["tap:settings"],
            success=True,
        )

        hints = extractor.get_hints_for_goal("open settings")

        assert hints.known_pattern is not None
        assert hints.recommended_app == "com.android.settings"

    def test_recommend_next_action(self, extractor, memory):
        """Test action recommendation from pattern."""
        # Create reliable pattern (2+ successes)
        for _ in range(2):
            memory.record_goal_completion(
                goal="send email",
                app_package="com.google.gmail",
                action_sequence=["tap:compose", "tap:to", "type:test@email.com"],
                success=True,
            )

        # Get recommendation
        rec = extractor.recommend_next_action(
            goal="send email",
            current_screen="inbox",
            actions_taken=[],
            app_package="com.google.gmail",
        )

        assert rec is not None
        assert rec.action_type == "tap"
        assert rec.target == "compose"
        assert rec.source == "pattern"

    def test_recommend_next_action_mid_sequence(self, extractor, memory):
        """Test recommendation in middle of sequence."""
        for _ in range(2):
            memory.record_goal_completion(
                goal="send email",
                app_package="com.google.gmail",
                action_sequence=["tap:compose", "tap:to", "type:test"],
                success=True,
            )

        # Already did first action
        rec = extractor.recommend_next_action(
            goal="send email",
            current_screen="compose",
            actions_taken=["tap:compose"],
            app_package="com.google.gmail",
        )

        assert rec is not None
        assert rec.action_type == "tap"
        assert rec.target == "to"

    def test_learn_from_session(self, extractor, memory):
        """Test learning from session."""
        # Record some actions
        for i in range(3):
            record = ActionRecord(
                session_id="learn-session",
                goal="test learning",
                subgoal=f"step {i}",
                action_type="tap",
                target=f"button{i}",
                app_package="com.test",
                success=True,
            )
            memory.record_action(record)

        # Learn from session
        extractor.learn_from_session(
            session_id="learn-session",
            goal="test learning",
            success=True,
        )

        # Should have created pattern
        pattern = memory.get_pattern_for_goal("test learning")
        assert pattern is not None

    def test_get_statistics(self, extractor, memory):
        """Test statistics retrieval."""
        # Add some data
        memory.record_goal_completion(
            goal="test",
            app_package="com.test",
            action_sequence=["tap:button"],
            success=True,
        )

        stats = extractor.get_statistics()

        assert "total_patterns" in stats
        assert "total_shortcuts" in stats
        assert stats["total_patterns"] >= 1

    def test_cache_behavior(self, extractor, memory):
        """Test that patterns are cached."""
        memory.record_goal_completion(
            goal="cached goal",
            app_package="com.test",
            action_sequence=["tap:button"],
            success=True,
        )

        # First call populates cache
        hints1 = extractor.get_hints_for_goal("cached goal", "com.test")
        
        # Second call should use cache
        hints2 = extractor.get_hints_for_goal("cached goal", "com.test")

        assert hints1.known_pattern is not None
        assert hints2.known_pattern is not None

        # Clear cache and verify
        extractor.clear_cache()
        assert len(extractor._pattern_cache) == 0


# --- Integration Tests ---

class TestLearningIntegration:
    """Integration tests for the learning system."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database."""
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        yield path
        os.unlink(path)

    def test_full_learning_cycle(self, temp_db):
        """Test complete learning cycle: record -> extract -> recommend."""
        memory = ExperienceMemory(db_path=temp_db)
        extractor = PatternExtractor(memory=memory)

        # Simulate first execution
        session1 = "session-1"
        actions = ["tap:app", "tap:menu", "tap:settings"]
        
        for i, action in enumerate(actions):
            parts = action.split(":")
            record = ActionRecord(
                session_id=session1,
                goal="open app settings",
                subgoal=f"step {i}",
                action_type=parts[0],
                target=parts[1],
                app_package="com.example.app",
                success=True,
            )
            memory.record_action(record)

        memory.record_goal_completion(
            goal="open app settings",
            app_package="com.example.app",
            action_sequence=actions,
            success=True,
        )

        # Simulate second execution (reinforces pattern)
        session2 = "session-2"
        for i, action in enumerate(actions):
            parts = action.split(":")
            record = ActionRecord(
                session_id=session2,
                goal="open app settings",
                subgoal=f"step {i}",
                action_type=parts[0],
                target=parts[1],
                app_package="com.example.app",
                success=True,
            )
            memory.record_action(record)

        memory.record_goal_completion(
            goal="open app settings",
            app_package="com.example.app",
            action_sequence=actions,
            success=True,
        )

        # Now pattern should be reliable
        hints = extractor.get_hints_for_goal("open app settings")
        assert hints.known_pattern is not None
        assert hints.known_pattern.success_count == 2

        # Should recommend first action
        rec = extractor.recommend_next_action(
            goal="open app settings",
            current_screen="home",
            actions_taken=[],
            app_package="com.example.app",
        )

        assert rec is not None
        assert rec.action_type == "tap"
        assert rec.target == "app"
        assert rec.confidence >= 0.5
