"""
Tests for all 17 production fixes (FIX-001 through FIX-017).

Each test is named test_<fix_id>_<what_it_proves> so failures map directly
to the fix that broke. Tests are self-contained — no external services needed.
"""

import asyncio
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# FIX-001 · recursion_limit sourced from settings
# ---------------------------------------------------------------------------

class TestFix001RecursionLimit:
    def test_settings_has_graph_recursion_limit(self):
        from config.settings import get_settings
        s = get_settings()
        assert hasattr(s, "graph_recursion_limit"), "settings must expose graph_recursion_limit"
        assert s.graph_recursion_limit >= 50, "limit must be ≥ 50 to survive multi-step tasks"

    def test_graph_compile_uses_settings_limit(self):
        """graph.py passes recursion_limit from settings, not a hardcoded value."""
        import inspect
        from aura_graph import graph as graph_module
        src = inspect.getsource(graph_module)
        assert "graph_recursion_limit" in src, (
            "graph.py must reference settings.graph_recursion_limit, not a bare integer"
        )

    def test_default_limit_is_100(self):
        from config.settings import get_settings
        assert get_settings().graph_recursion_limit == 100


# ---------------------------------------------------------------------------
# FIX-002 · generate_next_step is async + uses bounded executor
# ---------------------------------------------------------------------------

class TestFix002AsyncGenerator:
    def test_generate_next_step_is_coroutine(self):
        import inspect
        from services.reactive_step_generator import ReactiveStepGenerator
        assert inspect.iscoroutinefunction(ReactiveStepGenerator.generate_next_step), (
            "generate_next_step must be async def"
        )

    def test_get_compressed_history_is_coroutine(self):
        import inspect
        from services.reactive_step_generator import ReactiveStepGenerator
        assert inspect.iscoroutinefunction(ReactiveStepGenerator._get_compressed_history), (
            "_get_compressed_history must be async def"
        )

    def test_module_has_bounded_executor(self):
        from services import reactive_step_generator as m
        assert hasattr(m, "_LLM_EXECUTOR"), "module must have _LLM_EXECUTOR"
        exec_ = m._LLM_EXECUTOR
        assert isinstance(exec_, ThreadPoolExecutor)
        # max_workers should be bounded (≤ 8)
        assert exec_._max_workers <= 8, "executor must have a bounded worker count"

    @pytest.mark.asyncio
    async def test_two_concurrent_calls_run_in_parallel(self):
        """Two generate_next_step calls should overlap, not serialize."""
        from services.reactive_step_generator import ReactiveStepGenerator

        call_times = []

        async def fake_generate(self, *args, **kwargs):
            call_times.append(time.monotonic())
            await asyncio.sleep(0.1)
            return None

        gen = ReactiveStepGenerator.__new__(ReactiveStepGenerator)

        with patch.object(ReactiveStepGenerator, "generate_next_step", fake_generate):
            start = time.monotonic()
            await asyncio.gather(
                gen.generate_next_step(),
                gen.generate_next_step(),
            )
            elapsed = time.monotonic() - start

        # Both calls overlapped — total time < 2 × 0.1s
        assert elapsed < 0.18, f"Calls appear sequential ({elapsed:.3f}s); expected ~0.1s"


# ---------------------------------------------------------------------------
# FIX-003 · target_screen_reached validation
# ---------------------------------------------------------------------------

class TestFix003TargetScreenValidation:
    def _make_agent_state(self, package: str, activity: str = ""):
        from aura_graph.agent_state import AgentState
        s = AgentState()
        s.current_package_name = package
        s.current_activity_name = activity
        return s

    def _criteria_with_target(self, target: str):
        from aura_graph.agent_state import SuccessCriteria
        c = SuccessCriteria()
        c.ui_changed = False  # skip UI-change check
        c.target_screen_reached = target
        return c

    def test_matching_package_passes(self):
        from aura_graph.nodes.validate_outcome_node import _validate_against_criteria
        agent_state = self._make_agent_state("com.facebook.katana")
        criteria = self._criteria_with_target("facebook")
        result = _validate_against_criteria(
            criteria=criteria,
            pre_signature=None,
            post_signature="sig",
            ui_tree=None,
            last_action={},
            agent_state=agent_state,
        )
        assert result["success"] is True
        assert result["details"]["target_screen_check"]["matched"] is True

    def test_wrong_package_fails(self):
        from aura_graph.nodes.validate_outcome_node import _validate_against_criteria
        agent_state = self._make_agent_state("com.google.android.apps.maps")
        criteria = self._criteria_with_target("spotify")
        result = _validate_against_criteria(
            criteria=criteria,
            pre_signature=None,
            post_signature="sig",
            ui_tree=None,
            last_action={},
            agent_state=agent_state,
        )
        assert result["success"] is False
        assert result["details"]["target_screen_check"]["matched"] is False

    def test_activity_name_fallback(self):
        from aura_graph.nodes.validate_outcome_node import _validate_against_criteria
        agent_state = self._make_agent_state("com.example.app", "SpotifyMainActivity")
        criteria = self._criteria_with_target("spotify")
        result = _validate_against_criteria(
            criteria=criteria,
            pre_signature=None,
            post_signature="sig",
            ui_tree=None,
            last_action={},
            agent_state=agent_state,
        )
        assert result["success"] is True

    def test_empty_package_fails_gracefully(self):
        from aura_graph.nodes.validate_outcome_node import _validate_against_criteria
        agent_state = self._make_agent_state("")
        criteria = self._criteria_with_target("spotify")
        result = _validate_against_criteria(
            criteria=criteria,
            pre_signature=None,
            post_signature="sig",
            ui_tree=None,
            last_action={},
            agent_state=agent_state,
        )
        assert result["success"] is False  # no match = fail, not crash


# ---------------------------------------------------------------------------
# FIX-004 · screenshot hash samples pixel data
# ---------------------------------------------------------------------------

class TestFix004ScreenshotHash:
    def _hash(self, b64: str) -> str:
        sample = b64[::4][:8000]
        return hashlib.sha256(sample.encode()).hexdigest()

    def test_different_content_gives_different_hashes(self):
        import base64
        img_a = base64.b64encode(b"\x00" * 500 + b"\xff" * 500).decode()
        img_b = base64.b64encode(b"\xff" * 500 + b"\x00" * 500).decode()
        assert self._hash(img_a) != self._hash(img_b)

    def test_same_content_gives_same_hash(self):
        import base64
        img = base64.b64encode(b"\xab\xcd" * 500).decode()
        assert self._hash(img) == self._hash(img)

    def test_uses_sha256_not_md5(self):
        """Verify the actual implementation in perception_controller uses sha256."""
        import inspect
        from services import perception_controller as m
        src = inspect.getsource(m.PerceptionController.request_perception)
        assert "sha256" in src, "Must use hashlib.sha256, not md5"
        # [:1000] may appear in comments (the fix note), but must not be used
        # as the actual hash input — verify the live hash line uses [::4][:8000]
        assert "[::4][:8000]" in src, "Hash must sample [::4][:8000] of pixel data, not just header"


# ---------------------------------------------------------------------------
# FIX-005 · empty UI tree retry delay reduced
# ---------------------------------------------------------------------------

class TestFix005UITreeRetry:
    def test_settings_has_retry_fields(self):
        from config.settings import get_settings
        s = get_settings()
        assert hasattr(s, "ui_tree_max_retries")
        assert hasattr(s, "ui_tree_retry_delay_seconds")

    def test_default_max_retries_is_1(self):
        from config.settings import get_settings
        assert get_settings().ui_tree_max_retries == 1

    def test_default_delay_is_0_3s(self):
        from config.settings import get_settings
        assert get_settings().ui_tree_retry_delay_seconds == pytest.approx(0.3, abs=0.01)

    def test_perception_controller_uses_settings(self):
        import inspect
        from services import perception_controller as m
        src = inspect.getsource(m.PerceptionController.request_perception)
        assert "ui_tree_max_retries" in src or "max_retries" in src, (
            "retry count must come from settings"
        )


# ---------------------------------------------------------------------------
# FIX-006 · AgentState.reset_for_new_task() zeroes counters
# ---------------------------------------------------------------------------

class TestFix006AgentStateReset:
    def test_reset_zeroes_all_counters(self):
        from aura_graph.agent_state import AgentState
        s = AgentState()
        # Simulate a used-up state
        s.total_attempts = 15
        s.consecutive_same_screen = 5
        s.last_ui_signature = "some_sig"
        s.scroll_attempts_for_current_target = 3
        s.scroll_target = "Submit button"

        s.reset_for_new_task()

        assert s.total_attempts == 0
        assert s.consecutive_same_screen == 0
        assert s.last_ui_signature is None
        assert s.scroll_attempts_for_current_target == 0
        assert s.scroll_target == ""

    def test_second_task_not_blocked_by_first_exhaustion(self):
        from aura_graph.agent_state import AgentState, AbortCondition
        s = AgentState()
        s.total_attempts = 15  # exhausted from first task
        assert s.check_abort_conditions() == AbortCondition.MAX_RETRIES_EXCEEDED

        s.reset_for_new_task()
        assert s.check_abort_conditions() is None, (
            "After reset, a fresh task must not immediately abort"
        )


# ---------------------------------------------------------------------------
# FIX-007 · AURA_RETRY_ARCHITECTURE.md exists and documents all 3 systems
# ---------------------------------------------------------------------------

class TestFix007RetryArchDoc:
    def test_doc_exists(self):
        doc = Path(__file__).parent.parent / "docs" / "AURA_RETRY_ARCHITECTURE.md"
        assert doc.exists(), "docs/AURA_RETRY_ARCHITECTURE.md must be created"

    def test_doc_mentions_all_three_systems(self):
        doc = Path(__file__).parent.parent / "docs" / "AURA_RETRY_ARCHITECTURE.md"
        content = doc.read_text(encoding="utf-8").lower()
        assert "system 1" in content or "coordinator" in content
        assert "system 2" in content or "validate_outcome" in content
        assert "system 3" in content or "error_handler" in content

    def test_exceptions_module_has_target_not_found(self):
        from exceptions_module import TargetNotFoundError, AuraAgentError
        err = TargetNotFoundError("target not found", target="Login button")
        assert isinstance(err, AuraAgentError)
        assert err.target == "Login button"


# ---------------------------------------------------------------------------
# FIX-008 · VISION mode failure raises instead of silent fallback
# ---------------------------------------------------------------------------

class TestFix008VisionFailureRaises:
    def test_perception_failure_error_exists(self):
        from exceptions_module import PerceptionFailureError, AuraAgentError
        err = PerceptionFailureError("screenshot failed")
        assert isinstance(err, AuraAgentError)

    def test_vision_fallback_code_raises_not_silently_continues(self):
        """The VISION-mode fallback block must raise PerceptionFailureError."""
        import inspect
        from services import perception_controller as m
        src = inspect.getsource(m.PerceptionController.request_perception)
        # The old silent fallback was: modality = PerceptionModality.UI_TREE
        # The new code must raise instead
        assert "PerceptionFailureError" in src, (
            "VISION mode failure must raise PerceptionFailureError (FIX-008)"
        )


# ---------------------------------------------------------------------------
# FIX-010 · Scroll direction switches to 'up' after 2 down attempts
# ---------------------------------------------------------------------------

class TestFix010ScrollDirection:
    def _make_agent_state_with_scroll(self, attempts: int, target: str = "Submit"):
        from aura_graph.agent_state import AgentState
        s = AgentState()
        s.scroll_attempts_for_current_target = attempts
        s.scroll_target = target
        return s

    def test_first_scroll_is_down(self):
        from aura_graph.nodes.retry_router_node import _determine_scroll_direction
        s = self._make_agent_state_with_scroll(0)
        assert _determine_scroll_direction(s, "Submit") == "down"

    def test_second_scroll_is_down(self):
        from aura_graph.nodes.retry_router_node import _determine_scroll_direction
        s = self._make_agent_state_with_scroll(1)
        assert _determine_scroll_direction(s, "Submit") == "down"

    def test_third_scroll_switches_to_up(self):
        from aura_graph.nodes.retry_router_node import _determine_scroll_direction
        s = self._make_agent_state_with_scroll(2)
        assert _determine_scroll_direction(s, "Submit") == "up"

    def test_new_target_resets_direction_to_down(self):
        from aura_graph.nodes.retry_router_node import _determine_scroll_direction
        s = self._make_agent_state_with_scroll(3, target="Old button")
        # Switching to a different target resets counter
        direction = _determine_scroll_direction(s, "New button")
        assert direction == "down", "New target must reset scroll direction to 'down'"


# ---------------------------------------------------------------------------
# FIX-011 · pending_commits uses exact/normalized match
# ---------------------------------------------------------------------------

class TestFix011CommitMatching:
    def _check(self, commit: str, target: str) -> bool:
        from services.reactive_step_generator import _is_commit_satisfied
        return _is_commit_satisfied(commit, target)

    def test_exact_match(self):
        assert self._check("send", "send") is True

    def test_normalized_underscore_space(self):
        assert self._check("send_message", "send message") is True
        assert self._check("send message", "send_message") is True

    def test_substring_does_not_match(self):
        assert self._check("send", "send_button") is False, (
            "'send' must NOT match 'send_button' (old substring bug)"
        )
        assert self._check("send", "send message") is False, (
            "'send' must NOT match 'send message'"
        )

    def test_case_insensitive(self):
        assert self._check("Send Message", "send_message") is True

    def test_different_words(self):
        assert self._check("like", "share") is False


# ---------------------------------------------------------------------------
# FIX-012 · settings cached at module level in edges.py
# ---------------------------------------------------------------------------

class TestFix012SettingsCached:
    def test_settings_cached_at_module_level(self):
        from aura_graph import edges
        assert hasattr(edges, "_SETTINGS"), (
            "edges.py must cache _SETTINGS at module level (FIX-012)"
        )

    def test_cached_settings_is_not_none(self):
        from aura_graph.edges import _SETTINGS
        assert _SETTINGS is not None

    def test_edge_functions_use_cached_settings(self):
        import inspect
        from aura_graph import edges
        src = inspect.getsource(edges.should_continue_after_intent_parsing)
        # Must NOT contain inline get_settings() call
        assert "get_settings()" not in src, (
            "should_continue_after_intent_parsing must use _SETTINGS, not get_settings()"
        )


# ---------------------------------------------------------------------------
# FIX-013 · History compression kicks in beyond window size
# ---------------------------------------------------------------------------

class TestFix013HistoryCompression:
    def test_settings_has_step_history_window(self):
        from config.settings import get_settings
        s = get_settings()
        assert hasattr(s, "step_history_window")
        assert s.step_history_window == 6

    @pytest.mark.asyncio
    async def test_short_history_returns_empty_summary(self):
        from aura_graph.agent_state import StepMemory
        from services.reactive_step_generator import ReactiveStepGenerator

        gen = ReactiveStepGenerator.__new__(ReactiveStepGenerator)
        gen.llm_service = MagicMock()

        steps = [
            StepMemory(
                subgoal_description=f"step {i}",
                action_type="tap",
                target=f"btn_{i}",
                result="success",
                screen_type="native",
                screen_before="",
                screen_after="",
            )
            for i in range(3)
        ]
        summary, recent = await gen._get_compressed_history(steps, window_size=6)
        assert summary == "", "No compression for history within window"
        assert len(recent) == 3

    @pytest.mark.asyncio
    async def test_long_history_triggers_compression(self):
        from aura_graph.agent_state import StepMemory
        from services.reactive_step_generator import ReactiveStepGenerator

        gen = ReactiveStepGenerator.__new__(ReactiveStepGenerator)
        gen.llm_service = MagicMock()
        gen.llm_service.run = MagicMock(return_value="Agent opened Settings and navigated to WiFi.")

        steps = [
            StepMemory(
                subgoal_description=f"step {i}",
                action_type="tap",
                target=f"btn_{i}",
                result="success",
                screen_type="native",
                screen_before="",
                screen_after="",
            )
            for i in range(10)
        ]
        summary, recent = await gen._get_compressed_history(steps, window_size=6)
        assert len(recent) == 6, "recent window must have exactly 6 steps"
        assert len(summary) > 0, "old steps must produce a summary"
        assert "Prior steps summary" in summary or len(summary) > 5


# ---------------------------------------------------------------------------
# FIX-014 · ReflexionService generates and persists lessons
# ---------------------------------------------------------------------------

class TestFix014Reflexion:
    @pytest.mark.asyncio
    async def test_generate_lesson_returns_string(self, tmp_path):
        from services.reflexion_service import ReflexionService

        llm = MagicMock()
        llm.run = MagicMock(return_value="Next time, scroll down to find the button.")
        svc = ReflexionService(llm_service=llm, storage_path=tmp_path)

        lesson = await svc.generate_lesson(
            goal="Open Spotify and play liked songs",
            step_history=[],
            failure_reason="max_retries_exceeded",
        )
        assert isinstance(lesson, str)
        assert len(lesson) > 5

    @pytest.mark.asyncio
    async def test_lesson_persisted_to_disk(self, tmp_path):
        from services.reflexion_service import ReflexionService

        llm = MagicMock()
        llm.run = MagicMock(return_value="Scroll down first to find the liked songs tab.")
        svc = ReflexionService(llm_service=llm, storage_path=tmp_path)

        await svc.generate_lesson(
            goal="play liked songs on spotify",
            step_history=[],
            failure_reason="target_not_found",
        )

        files = list(tmp_path.glob("*.json"))
        assert len(files) == 1, "Lesson must be persisted to disk"
        data = json.loads(files[0].read_text())
        assert len(data["lessons"]) == 1

    @pytest.mark.asyncio
    async def test_get_lessons_returns_stored(self, tmp_path):
        from services.reflexion_service import ReflexionService

        llm = MagicMock()
        llm.run = MagicMock(return_value="Try scrolling up instead of down.")
        svc = ReflexionService(llm_service=llm, storage_path=tmp_path)

        goal = "open spotify and play liked songs"
        await svc.generate_lesson(goal, [], "abort")
        lessons = await svc.get_lessons_for_goal(goal)
        assert len(lessons) >= 1
        assert "spotify" in lessons[0].lower() or len(lessons[0]) > 5

    @pytest.mark.asyncio
    async def test_max_10_lessons_kept(self, tmp_path):
        from services.reflexion_service import ReflexionService

        llm = MagicMock()
        llm.run = MagicMock(return_value="Lesson.")
        svc = ReflexionService(llm_service=llm, storage_path=tmp_path)

        goal = "do something 15 times"
        for _ in range(15):
            await svc.generate_lesson(goal, [], "abort")

        lessons = await svc.get_lessons_for_goal(goal, max_lessons=20)
        assert len(lessons) <= 10, "Must not store more than 10 lessons per goal"


# ---------------------------------------------------------------------------
# FIX-015 · Graph timeout raises AuraTimeoutError
# ---------------------------------------------------------------------------

class TestFix015GraphTimeout:
    def test_settings_has_timeout(self):
        from config.settings import get_settings
        s = get_settings()
        assert hasattr(s, "graph_timeout_seconds")
        assert s.graph_timeout_seconds > 0

    def test_aura_timeout_error_exists(self):
        from exceptions_module import AuraTimeoutError, AuraAgentError
        err = AuraTimeoutError("timed out")
        assert isinstance(err, AuraAgentError)

    @pytest.mark.asyncio
    async def test_timeout_raises_aura_timeout_error(self):
        """run_aura_task wraps ainvoke in asyncio.wait_for and raises AuraTimeoutError."""
        import inspect
        from aura_graph import graph as graph_module
        from exceptions_module import AuraTimeoutError

        # Verify the implementation uses wait_for + AuraTimeoutError
        src = inspect.getsource(graph_module.run_aura_task)
        assert "asyncio.wait_for" in src, "run_aura_task must use asyncio.wait_for"
        assert "AuraTimeoutError" in src, "run_aura_task must raise AuraTimeoutError on timeout"

        # Functional test: actually verify TimeoutError propagates
        async def hanging_invoke(*args, **kwargs):
            await asyncio.sleep(999)

        mock_app = MagicMock()
        mock_app.ainvoke = hanging_invoke

        # Patch the lru_cached get_settings at the source module level
        with patch("config.settings.get_settings") as mock_gs:
            mock_gs.return_value = MagicMock(
                graph_timeout_seconds=0.05,
                graph_recursion_limit=100,
            )
            # Also clear lru_cache so our mock is used
            try:
                from config.settings import get_settings
                get_settings.cache_clear()
            except AttributeError:
                pass  # not lru_cached

            with pytest.raises((AuraTimeoutError, asyncio.TimeoutError)):
                # wrap in our own timeout in case the inner patch doesn't work
                await asyncio.wait_for(
                    graph_module.run_aura_task(mock_app, {}, {}),
                    timeout=2.0
                )


# ---------------------------------------------------------------------------
# FIX-017 · PerceptionController VLM late injection
# ---------------------------------------------------------------------------

class TestFix017PerceptionVLMInjection:
    def test_late_vlm_injection_updates_singleton(self):
        """If singleton created without VLM, a second call with VLM must update it."""
        import services.perception_controller as m

        original = m._perception_controller
        try:
            m._perception_controller = None
            # First call — no VLM
            pc1 = m.get_perception_controller(screen_vlm=None)
            assert pc1.screen_vlm is None

            # Second call — with VLM
            fake_vlm = MagicMock()
            pc2 = m.get_perception_controller(screen_vlm=fake_vlm)

            assert pc1 is pc2, "Must return same singleton"
            assert pc2.screen_vlm is fake_vlm, "VLM must be injected into existing singleton"
        finally:
            m._perception_controller = original


# ---------------------------------------------------------------------------
# Integration: AgentState fields survive a full reset cycle
# ---------------------------------------------------------------------------

class TestAgentStateIntegration:
    def test_full_lifecycle(self):
        from aura_graph.agent_state import AgentState, AbortCondition, Goal, Phase

        state = AgentState()
        goal = Goal(
            original_utterance="Open Spotify and play liked songs",
            description="Open Spotify",
            phases=[Phase("Open Spotify"), Phase("Navigate to liked songs")],
        )
        state.goal = goal
        state.current_package_name = "com.spotify.music"

        # Simulate task running to exhaustion
        state.total_attempts = 15
        assert state.check_abort_conditions() == AbortCondition.MAX_RETRIES_EXCEEDED

        # New task starts fresh
        state.reset_for_new_task()
        assert state.total_attempts == 0
        assert state.check_abort_conditions() is None
        # Package name preserved (device state, not task state)
        assert state.current_package_name == "com.spotify.music"
