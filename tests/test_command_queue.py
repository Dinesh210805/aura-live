"""
Unit tests for services/command_queue.py.

Tests cover:
- add_command: returns cmd_ prefixed ID, stores command as pending
- get_pending_commands: returns only pending cmds for that device, marks as executing
- get_pending_commands: does not return cmds for other devices
- mark_completed / mark_failed: update status correctly
- get_command_status: returns correct status, None for unknown
- Expiry: expired commands marked as expired during cleanup
- Multi-device isolation: each device only sees its own commands
- CommandQueue is stateful: each test gets a fresh instance

No I/O or external calls — asyncio.Lock is tested purely in-process.
"""

import asyncio
from datetime import datetime, timedelta

import pytest

from services.command_queue import CommandQueue


@pytest.fixture()
def q():
    """Fresh CommandQueue per test."""
    return CommandQueue()


# ---------------------------------------------------------------------------
# add_command
# ---------------------------------------------------------------------------

class TestAddCommand:
    @pytest.mark.asyncio
    async def test_returns_cmd_prefixed_id(self, q):
        cmd_id = await q.add_command("pixel7", "tap", {"x": 100, "y": 200})
        assert cmd_id.startswith("cmd_")

    @pytest.mark.asyncio
    async def test_unique_ids(self, q):
        id1 = await q.add_command("device1", "tap", {})
        id2 = await q.add_command("device1", "swipe", {})
        assert id1 != id2

    @pytest.mark.asyncio
    async def test_command_stored_as_pending(self, q):
        cmd_id = await q.add_command("pixel7", "launch_app", {"app": "Camera"})
        status = await q.get_command_status(cmd_id)
        assert status == "pending"

    @pytest.mark.asyncio
    async def test_multiple_commands_stored(self, q):
        id1 = await q.add_command("dev", "tap", {})
        id2 = await q.add_command("dev", "swipe", {})
        assert await q.get_command_status(id1) == "pending"
        assert await q.get_command_status(id2) == "pending"


# ---------------------------------------------------------------------------
# get_pending_commands
# ---------------------------------------------------------------------------

class TestGetPendingCommands:
    @pytest.mark.asyncio
    async def test_returns_pending_for_device(self, q):
        await q.add_command("pixel7", "tap", {"x": 10, "y": 20})
        cmds = await q.get_pending_commands("pixel7")
        assert len(cmds) == 1
        assert cmds[0]["command_type"] == "tap"
        assert cmds[0]["payload"] == {"x": 10, "y": 20}

    @pytest.mark.asyncio
    async def test_returns_empty_for_other_device(self, q):
        await q.add_command("pixel7", "tap", {})
        cmds = await q.get_pending_commands("galaxy_s24")
        assert cmds == []

    @pytest.mark.asyncio
    async def test_marks_as_executing_after_fetch(self, q):
        cmd_id = await q.add_command("pixel7", "tap", {})
        await q.get_pending_commands("pixel7")
        status = await q.get_command_status(cmd_id)
        assert status == "executing"

    @pytest.mark.asyncio
    async def test_second_fetch_does_not_return_executing(self, q):
        await q.add_command("pixel7", "tap", {})
        first = await q.get_pending_commands("pixel7")
        second = await q.get_pending_commands("pixel7")
        assert len(first) == 1
        assert len(second) == 0

    @pytest.mark.asyncio
    async def test_response_includes_required_fields(self, q):
        cmd_id = await q.add_command("pixel7", "launch_app", {"app": "Maps"})
        cmds = await q.get_pending_commands("pixel7")
        assert cmds[0]["command_id"] == cmd_id
        assert "command_type" in cmds[0]
        assert "payload" in cmds[0]
        assert "created_at" in cmds[0]

    @pytest.mark.asyncio
    async def test_multiple_pending_commands(self, q):
        await q.add_command("pixel7", "tap", {"x": 1})
        await q.add_command("pixel7", "swipe", {"x": 2})
        cmds = await q.get_pending_commands("pixel7")
        assert len(cmds) == 2


# ---------------------------------------------------------------------------
# mark_completed
# ---------------------------------------------------------------------------

class TestMarkCompleted:
    @pytest.mark.asyncio
    async def test_status_becomes_completed(self, q):
        cmd_id = await q.add_command("dev", "tap", {})
        await q.mark_completed(cmd_id, {"result": "success"})
        assert await q.get_command_status(cmd_id) == "completed"

    @pytest.mark.asyncio
    async def test_unknown_id_does_not_raise(self, q):
        # Should silently ignore unknown command IDs
        await q.mark_completed("cmd_nonexistent", {})

    @pytest.mark.asyncio
    async def test_completed_not_returned_as_pending(self, q):
        cmd_id = await q.add_command("dev", "tap", {})
        await q.mark_completed(cmd_id, {})
        cmds = await q.get_pending_commands("dev")
        assert cmds == []


# ---------------------------------------------------------------------------
# mark_failed
# ---------------------------------------------------------------------------

class TestMarkFailed:
    @pytest.mark.asyncio
    async def test_status_becomes_failed(self, q):
        cmd_id = await q.add_command("dev", "tap", {})
        await q.mark_failed(cmd_id, "timeout")
        assert await q.get_command_status(cmd_id) == "failed"

    @pytest.mark.asyncio
    async def test_unknown_id_does_not_raise(self, q):
        await q.mark_failed("cmd_nonexistent", "error msg")

    @pytest.mark.asyncio
    async def test_failed_not_returned_as_pending(self, q):
        cmd_id = await q.add_command("dev", "tap", {})
        await q.mark_failed(cmd_id, "error")
        cmds = await q.get_pending_commands("dev")
        assert cmds == []


# ---------------------------------------------------------------------------
# get_command_status
# ---------------------------------------------------------------------------

class TestGetCommandStatus:
    @pytest.mark.asyncio
    async def test_returns_none_for_unknown_id(self, q):
        status = await q.get_command_status("cmd_unknown")
        assert status is None

    @pytest.mark.asyncio
    async def test_initial_status_pending(self, q):
        cmd_id = await q.add_command("dev", "tap", {})
        assert await q.get_command_status(cmd_id) == "pending"


# ---------------------------------------------------------------------------
# Expiry
# ---------------------------------------------------------------------------

class TestExpiry:
    @pytest.mark.asyncio
    async def test_expired_command_not_returned_as_pending(self, q):
        """Commands that have passed their expiry time should be marked expired, not returned."""
        cmd_id = await q.add_command("dev", "tap", {})
        # Manually set expires_at to the past
        q._commands[cmd_id].expires_at = datetime.now() - timedelta(seconds=1)
        cmds = await q.get_pending_commands("dev")
        assert cmds == []

    @pytest.mark.asyncio
    async def test_expired_command_status_becomes_expired(self, q):
        cmd_id = await q.add_command("dev", "tap", {})
        q._commands[cmd_id].expires_at = datetime.now() - timedelta(seconds=1)
        await q.get_pending_commands("dev")  # triggers cleanup
        assert await q.get_command_status(cmd_id) == "expired"

    @pytest.mark.asyncio
    async def test_completed_command_not_re_expired(self, q):
        """Completed commands should not be overwritten by the expiry cleaner."""
        cmd_id = await q.add_command("dev", "tap", {})
        await q.mark_completed(cmd_id, {})
        # Force expiry time to past — cleanup should skip it (status != "pending"/"executing")
        q._commands[cmd_id].expires_at = datetime.now() - timedelta(seconds=1)
        await q.get_pending_commands("dev")
        # Completed commands are preserved per the implementation comment
        # (status "completed" is excluded from expiry)
        assert await q.get_command_status(cmd_id) == "completed"


# ---------------------------------------------------------------------------
# Multi-device isolation
# ---------------------------------------------------------------------------

class TestMultiDeviceIsolation:
    @pytest.mark.asyncio
    async def test_two_devices_isolated(self, q):
        await q.add_command("device_a", "tap", {"x": 1})
        await q.add_command("device_b", "swipe", {"x": 2})
        cmds_a = await q.get_pending_commands("device_a")
        cmds_b = await q.get_pending_commands("device_b")
        assert len(cmds_a) == 1
        assert cmds_a[0]["command_type"] == "tap"
        assert len(cmds_b) == 1
        assert cmds_b[0]["command_type"] == "swipe"

    @pytest.mark.asyncio
    async def test_completing_device_a_does_not_affect_device_b(self, q):
        id_a = await q.add_command("device_a", "tap", {})
        await q.add_command("device_b", "tap", {})
        await q.mark_completed(id_a, {})
        cmds_b = await q.get_pending_commands("device_b")
        assert len(cmds_b) == 1
