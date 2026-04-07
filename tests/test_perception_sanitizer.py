"""
Unit tests for perception/sanitizer.py.

Tests cover:
- sanitize_text: redaction of credit cards, SSNs, phones, emails, passwords,
  PINs, OTPs, CVVs, Aadhaar numbers, PAN cards
- sanitize_text edge cases: None, empty string, no sensitive data
- sanitize_ui_tree: element-level sanitization, contentDescription redaction
- is_sensitive_app: known packages, unknown packages
- _redact_all_text path: triggered for sensitive app packages

No I/O or external calls are made.
"""

import pytest

from perception.sanitizer import (
    SENSITIVE_PACKAGES,
    is_sensitive_app,
    sanitize_text,
    sanitize_ui_tree,
)


# ---------------------------------------------------------------------------
# sanitize_text — basic PII patterns
# ---------------------------------------------------------------------------

class TestSanitizeTextCreditCard:
    def test_plain_16_digit_card(self):
        result = sanitize_text("card number 4111111111111111")
        assert "4111111111111111" not in result
        assert "[REDACTED_CC]" in result

    def test_card_with_dashes(self):
        result = sanitize_text("card: 4111-1111-1111-1111")
        assert "4111-1111-1111-1111" not in result

    def test_card_with_spaces(self):
        result = sanitize_text("4111 1111 1111 1111")
        assert "4111 1111 1111 1111" not in result


class TestSanitizeTextSSN:
    def test_ssn_dashes(self):
        result = sanitize_text("SSN: 123-45-6789")
        assert "123-45-6789" not in result
        assert "[REDACTED_SSN]" in result

    def test_ssn_no_separator(self):
        result = sanitize_text("ssn 123456789")
        assert "123456789" not in result


class TestSanitizeTextEmail:
    def test_standard_email(self):
        result = sanitize_text("email is user@example.com")
        assert "user@example.com" not in result
        assert "[REDACTED_EMAIL]" in result

    def test_email_with_subdomain(self):
        result = sanitize_text("contact: name@mail.domain.org please")
        assert "name@mail.domain.org" not in result


class TestSanitizeTextPassword:
    def test_password_colon(self):
        result = sanitize_text("password: mysecretpass")
        assert "mysecretpass" not in result

    def test_password_field_label(self):
        result = sanitize_text("Enter your password here")
        # The word "password" triggers field redaction
        assert "password" not in result.lower() or "[REDACTED" in result


class TestSanitizeTextPIN:
    def test_pin_with_colon(self):
        result = sanitize_text("PIN: 1234")
        assert "1234" not in result or "PIN: [REDACTED]" in result

    def test_pin_6_digit(self):
        result = sanitize_text("pin: 123456")
        assert "123456" not in result or "PIN: [REDACTED]" in result


class TestSanitizeTextOTP:
    def test_otp_code(self):
        result = sanitize_text("otp: 567890")
        assert "567890" not in result
        assert "[REDACTED_OTP]" in result

    def test_verify_code(self):
        result = sanitize_text("verify: 123456")
        assert "123456" not in result


class TestSanitizeTextCVV:
    def test_cvv_3_digit(self):
        result = sanitize_text("cvv: 123")
        assert "[REDACTED_CVV]" in result

    def test_cvc_4_digit(self):
        result = sanitize_text("CVC: 1234")
        assert "[REDACTED_CVV]" in result


class TestSanitizeTextAadhaar:
    def test_aadhaar_12_digits(self):
        result = sanitize_text("aadhaar 1234 5678 9012")
        assert "1234 5678 9012" not in result
        assert "[REDACTED_AADHAAR]" in result


class TestSanitizeTextPAN:
    def test_pan_format(self):
        result = sanitize_text("PAN: ABCDE1234F")
        assert "ABCDE1234F" not in result
        assert "[REDACTED_PAN]" in result


class TestSanitizeTextEdgeCases:
    def test_none_returns_empty_string(self):
        assert sanitize_text(None) == ""

    def test_empty_string_returns_empty_string(self):
        assert sanitize_text("") == ""

    def test_plain_text_unchanged(self):
        result = sanitize_text("Hello world how are you")
        assert result == "Hello world how are you"

    def test_multiple_pii_in_one_string(self):
        text = "email: user@example.com card: 4111111111111111"
        result = sanitize_text(text)
        assert "user@example.com" not in result
        assert "4111111111111111" not in result


# ---------------------------------------------------------------------------
# sanitize_ui_tree
# ---------------------------------------------------------------------------

class TestSanitizeUiTree:
    def _elem(self, text="", desc=""):
        return {"text": text, "contentDescription": desc}

    def test_pii_in_text_field_redacted(self):
        elements = [self._elem(text="card 4111111111111111")]
        result = sanitize_ui_tree(elements)
        assert "4111111111111111" not in result[0]["text"]

    def test_pii_in_content_description_redacted(self):
        elements = [self._elem(desc="user@example.com")]
        result = sanitize_ui_tree(elements)
        assert "user@example.com" not in result[0]["contentDescription"]

    def test_clean_elements_unchanged(self):
        elements = [self._elem(text="Settings", desc="Open settings")]
        result = sanitize_ui_tree(elements)
        assert result[0]["text"] == "Settings"
        assert result[0]["contentDescription"] == "Open settings"

    def test_elements_count_preserved(self):
        elements = [self._elem("a"), self._elem("b"), self._elem("c")]
        result = sanitize_ui_tree(elements)
        assert len(result) == 3

    def test_non_text_fields_preserved(self):
        elem = {"bounds": {"left": 0, "top": 0, "right": 100, "bottom": 50},
                "clickable": True, "text": "Settings"}
        result = sanitize_ui_tree([elem])
        assert result[0]["bounds"] == {"left": 0, "top": 0, "right": 100, "bottom": 50}
        assert result[0]["clickable"] is True

    def test_sensitive_app_redacts_all_text(self):
        """Google Pay package → all text replaced with [REDACTED_SENSITIVE_APP]."""
        elements = [
            {"text": "My Balance: $5000", "contentDescription": "wallet balance"},
            {"text": "Recent Transactions", "contentDescription": ""},
        ]
        result = sanitize_ui_tree(
            elements, package_name="com.google.android.apps.walletnfcrel"
        )
        for elem in result:
            if elem.get("text"):
                assert elem["text"] == "[REDACTED_SENSITIVE_APP]"

    def test_none_text_field_skipped(self):
        elements = [{"text": None, "contentDescription": None}]
        result = sanitize_ui_tree(elements)
        # Should not raise; None values are left as-is or handled gracefully
        assert len(result) == 1


# ---------------------------------------------------------------------------
# is_sensitive_app
# ---------------------------------------------------------------------------

class TestIsSensitiveApp:
    def test_known_sensitive_package(self):
        assert is_sensitive_app("com.google.android.apps.walletnfcrel") is True

    def test_lastpass_sensitive(self):
        assert is_sensitive_app("com.lastpass.lpandroid") is True

    def test_coinbase_sensitive(self):
        assert is_sensitive_app("com.coinbase.android") is True

    def test_benign_app_not_sensitive(self):
        assert is_sensitive_app("com.spotify.music") is False

    def test_none_package_not_sensitive(self):
        assert is_sensitive_app(None) is False

    def test_empty_package_not_sensitive(self):
        assert is_sensitive_app("") is False

    def test_sensitive_packages_constant_non_empty(self):
        assert len(SENSITIVE_PACKAGES) > 0
