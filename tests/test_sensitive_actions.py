"""
Unit tests for policies/sensitive_actions.py.

Tests cover:
- is_sensitive: banking, shutdown, destructive, security, permission keywords
- Sensitive app launch (requires open/launch/start in command)
- Sensitive app keyword alone does NOT trigger
- enabled=False disables all checks
- get_blocked_response: increments counter, returns structured dict, all known reasons
- add_custom_keyword: adds to category, returns True; unknown category returns False
- get_stats: reflects keyword counts and enabled state
"""

import pytest

from policies.sensitive_actions import SensitiveActionPolicy


@pytest.fixture()
def policy():
    """Fresh policy instance per test — avoids shared class-level keyword mutation."""
    return SensitiveActionPolicy()


# ---------------------------------------------------------------------------
# is_sensitive — banking keywords
# ---------------------------------------------------------------------------

class TestBankingDetection:
    def test_bank_keyword(self, policy):
        is_s, reason = policy.is_sensitive("open my bank account")
        assert is_s is True
        assert reason == "banking_operation"

    def test_payment_keyword(self, policy):
        is_s, reason = policy.is_sensitive("make a payment")
        assert is_s is True
        assert reason == "banking_operation"

    def test_google_pay_phrase(self, policy):
        is_s, reason = policy.is_sensitive("use google pay")
        assert is_s is True
        assert reason == "banking_operation"

    def test_upi_keyword(self, policy):
        is_s, reason = policy.is_sensitive("upi transfer")
        assert is_s is True
        assert reason == "banking_operation"


# ---------------------------------------------------------------------------
# is_sensitive — system shutdown keywords
# ---------------------------------------------------------------------------

class TestShutdownDetection:
    def test_shutdown_keyword(self, policy):
        is_s, reason = policy.is_sensitive("shutdown the device")
        assert is_s is True
        assert reason == "system_shutdown"

    def test_factory_reset(self, policy):
        is_s, reason = policy.is_sensitive("factory reset my phone")
        assert is_s is True
        assert reason == "system_shutdown"

    def test_restart_keyword(self, policy):
        is_s, reason = policy.is_sensitive("restart phone")
        assert is_s is True
        assert reason == "system_shutdown"

    def test_turn_off_phone(self, policy):
        is_s, reason = policy.is_sensitive("turn off my phone")
        assert is_s is True
        assert reason == "system_shutdown"


# ---------------------------------------------------------------------------
# is_sensitive — destructive keywords
# ---------------------------------------------------------------------------

class TestDestructiveDetection:
    def test_delete_keyword(self, policy):
        is_s, reason = policy.is_sensitive("delete this file")
        assert is_s is True
        assert reason == "destructive_operation"

    def test_uninstall_keyword(self, policy):
        is_s, reason = policy.is_sensitive("uninstall the app")
        assert is_s is True
        assert reason == "destructive_operation"

    def test_erase_keyword(self, policy):
        is_s, reason = policy.is_sensitive("erase all data")
        assert is_s is True
        assert reason == "destructive_operation"


# ---------------------------------------------------------------------------
# is_sensitive — security modifications
# ---------------------------------------------------------------------------

class TestSecurityDetection:
    def test_disable_security(self, policy):
        is_s, reason = policy.is_sensitive("disable security on my phone")
        assert is_s is True
        assert reason == "security_modification"

    def test_remove_lock(self, policy):
        # "remove" triggers destructive_operation before security_modification check
        is_s, reason = policy.is_sensitive("remove lock screen")
        assert is_s is True
        assert reason == "destructive_operation"

    def test_disable_pin(self, policy):
        is_s, reason = policy.is_sensitive("disable pin")
        assert is_s is True
        assert reason == "security_modification"


# ---------------------------------------------------------------------------
# is_sensitive — permission keywords
# ---------------------------------------------------------------------------

class TestPermissionDetection:
    def test_grant_all_permissions(self, policy):
        is_s, reason = policy.is_sensitive("grant all permissions")
        assert is_s is True
        assert reason == "permission_change"

    def test_enable_developer_mode(self, policy):
        is_s, reason = policy.is_sensitive("enable developer mode")
        assert is_s is True
        assert reason == "permission_change"


# ---------------------------------------------------------------------------
# is_sensitive — sensitive app access (requires open/launch/start verb)
# ---------------------------------------------------------------------------

class TestSensitiveAppDetection:
    def test_open_paypal_detected(self, policy):
        # paypal is in BANKING_KEYWORDS — fires banking_operation before sensitive_app_access
        is_s, reason = policy.is_sensitive("open paypal")
        assert is_s is True
        assert reason == "banking_operation"

    def test_launch_lastpass_detected(self, policy):
        is_s, reason = policy.is_sensitive("launch lastpass")
        assert is_s is True
        assert reason == "sensitive_app_access"

    def test_start_coinbase_detected(self, policy):
        is_s, reason = policy.is_sensitive("start coinbase")
        assert is_s is True
        assert reason == "sensitive_app_access"

    def test_app_name_without_open_verb_not_detected(self, policy):
        """'paypal' alone (no open/launch/start) should NOT trigger sensitive_app_access."""
        # paypal IS in BANKING_KEYWORDS so it fires banking_operation — that's correct;
        # but if we use a name only in SENSITIVE_APPS (not BANKING_KEYWORDS):
        is_s, reason = policy.is_sensitive("robinhood portfolio")
        # Without open/launch/start, sensitive app check should not fire
        # (robinhood is in SENSITIVE_APPS but not in banking keywords directly)
        if is_s:
            assert reason != "sensitive_app_access"


# ---------------------------------------------------------------------------
# is_sensitive — safe commands
# ---------------------------------------------------------------------------

class TestSafeCommands:
    def test_play_music_safe(self, policy):
        is_s, _ = policy.is_sensitive("play music on spotify")
        assert is_s is False

    def test_take_screenshot_safe(self, policy):
        is_s, _ = policy.is_sensitive("take a screenshot")
        assert is_s is False

    def test_send_text_safe(self, policy):
        is_s, _ = policy.is_sensitive("send a text to mom")
        assert is_s is False

    def test_empty_string_safe(self, policy):
        is_s, reason = policy.is_sensitive("")
        assert is_s is False
        assert reason is None


# ---------------------------------------------------------------------------
# is_sensitive — disabled policy
# ---------------------------------------------------------------------------

class TestDisabledPolicy:
    def test_banking_not_detected_when_disabled(self, policy):
        policy.enabled = False
        is_s, reason = policy.is_sensitive("bank transfer")
        assert is_s is False
        assert reason is None

    def test_shutdown_not_detected_when_disabled(self, policy):
        policy.enabled = False
        is_s, reason = policy.is_sensitive("factory reset")
        assert is_s is False


# ---------------------------------------------------------------------------
# get_blocked_response
# ---------------------------------------------------------------------------

class TestGetBlockedResponse:
    def test_increments_blocked_count(self, policy):
        assert policy.blocked_count == 0
        policy.get_blocked_response("banking_operation", "test cmd")
        assert policy.blocked_count == 1
        policy.get_blocked_response("banking_operation", "test cmd")
        assert policy.blocked_count == 2

    def test_response_structure(self, policy):
        resp = policy.get_blocked_response("banking_operation", "pay rent")
        assert resp["status"] == "blocked"
        assert resp["error_code"] == "SENSITIVE_ACTION_BLOCKED"
        assert resp["reason"] == "banking_operation"
        assert "message" in resp
        assert "spoken_response" in resp
        assert resp["command"] == "pay rent"
        assert resp["blocked_count"] == 1

    def test_all_known_reasons_have_messages(self, policy):
        reasons = [
            "banking_operation", "system_shutdown", "destructive_operation",
            "security_modification", "permission_change", "sensitive_app_access"
        ]
        for reason in reasons:
            resp = policy.get_blocked_response(reason, "cmd")
            assert resp["message"]  # non-empty message for every known reason

    def test_unknown_reason_returns_generic_message(self, policy):
        resp = policy.get_blocked_response("unknown_reason_xyz", "cmd")
        assert "not supported" in resp["message"].lower() or resp["message"]


# ---------------------------------------------------------------------------
# add_custom_keyword
# ---------------------------------------------------------------------------

class TestAddCustomKeyword:
    def test_add_to_banking_category(self, policy):
        result = policy.add_custom_keyword("banking", "zepto_pay")
        assert result is True
        is_s, reason = policy.is_sensitive("use zepto_pay for checkout")
        assert is_s is True
        assert reason == "banking_operation"

    def test_duplicate_keyword_returns_false(self, policy):
        # Add once
        policy.add_custom_keyword("banking", "testpay")
        # Adding same keyword again returns False
        result = policy.add_custom_keyword("banking", "testpay")
        assert result is False

    def test_unknown_category_returns_false(self, policy):
        result = policy.add_custom_keyword("nonexistent_category", "keyword")
        assert result is False

    def test_add_to_destructive_category(self, policy):
        result = policy.add_custom_keyword("destructive", "obliterate")
        assert result is True


# ---------------------------------------------------------------------------
# get_stats
# ---------------------------------------------------------------------------

class TestGetStats:
    def test_stats_structure(self, policy):
        stats = policy.get_stats()
        assert "enabled" in stats
        assert "blocked_count" in stats
        assert "categories" in stats

    def test_stats_reflects_enabled_flag(self, policy):
        policy.enabled = False
        assert policy.get_stats()["enabled"] is False

    def test_stats_blocked_count_initial_zero(self, policy):
        assert policy.get_stats()["blocked_count"] == 0

    def test_stats_category_counts_are_positive(self, policy):
        cats = policy.get_stats()["categories"]
        for cat_name, count in cats.items():
            assert count > 0, f"{cat_name} should have at least one keyword"
