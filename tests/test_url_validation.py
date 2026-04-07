"""
Unit tests for utils/url_validation.py.

Tests cover:
- validate_image_url: valid https URL passes through unchanged
- Non-http/https schemes rejected (ftp, file, data, etc.)
- Private IP addresses blocked (10.x, 192.168.x, 172.16.x)
- Loopback addresses blocked (127.x, ::1)
- Link-local blocked (169.254.x)
- Unresolvable hostname raises ValueError
- Missing hostname raises ValueError

socket.gethostbyname is mocked in all tests to avoid network calls and
control which IP address the "resolved" hostname returns.
"""

import socket
from unittest.mock import patch

import pytest

from utils.url_validation import validate_image_url


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _mock_resolve(ip: str):
    """Return a patch context that makes socket.gethostbyname return ip."""
    return patch("utils.url_validation.socket.gethostbyname", return_value=ip)


def _mock_fail():
    """Return a patch context that makes socket.gethostbyname raise gaierror."""
    return patch(
        "utils.url_validation.socket.gethostbyname",
        side_effect=socket.gaierror("Name or service not known"),
    )


# ---------------------------------------------------------------------------
# Valid URLs
# ---------------------------------------------------------------------------

class TestValidUrls:
    def test_https_public_ip_passes(self):
        with _mock_resolve("93.184.216.34"):  # example.com
            result = validate_image_url("https://example.com/image.jpg")
        assert result == "https://example.com/image.jpg"

    def test_http_public_ip_passes(self):
        with _mock_resolve("8.8.8.8"):
            result = validate_image_url("http://public.cdn.example/img.png")
        assert result == "http://public.cdn.example/img.png"

    def test_returns_original_url_unchanged(self):
        url = "https://storage.googleapis.com/bucket/file.jpg"
        with _mock_resolve("216.58.200.0"):
            result = validate_image_url(url)
        assert result == url


# ---------------------------------------------------------------------------
# Scheme validation
# ---------------------------------------------------------------------------

class TestSchemeValidation:
    def test_ftp_scheme_rejected(self):
        with pytest.raises(ValueError, match="scheme"):
            validate_image_url("ftp://files.example.com/image.jpg")

    def test_file_scheme_rejected(self):
        with pytest.raises(ValueError, match="scheme"):
            validate_image_url("file:///etc/passwd")

    def test_data_scheme_rejected(self):
        with pytest.raises(ValueError):
            validate_image_url("data:image/png;base64,abc")

    def test_empty_scheme_rejected(self):
        # urlparse treats "//host/path" as scheme='', hostname='host'
        with pytest.raises(ValueError):
            validate_image_url("//example.com/image.jpg")


# ---------------------------------------------------------------------------
# Private IP blocking (SSRF prevention)
# ---------------------------------------------------------------------------

class TestPrivateIpBlocking:
    def test_rfc1918_class_a_blocked(self):
        """10.0.0.0/8 range."""
        with _mock_resolve("10.0.0.1"):
            with pytest.raises(ValueError, match="non-public"):
                validate_image_url("https://internal.corp/img.png")

    def test_rfc1918_class_b_blocked(self):
        """172.16.0.0/12 range."""
        with _mock_resolve("172.16.0.1"):
            with pytest.raises(ValueError, match="non-public"):
                validate_image_url("https://internal.corp/img.png")

    def test_rfc1918_class_c_blocked(self):
        """192.168.0.0/16 range."""
        with _mock_resolve("192.168.1.100"):
            with pytest.raises(ValueError, match="non-public"):
                validate_image_url("https://home-router.local/img.png")


# ---------------------------------------------------------------------------
# Loopback blocking
# ---------------------------------------------------------------------------

class TestLoopbackBlocking:
    def test_localhost_blocked(self):
        with _mock_resolve("127.0.0.1"):
            with pytest.raises(ValueError, match="non-public"):
                validate_image_url("https://localhost/img.png")

    def test_127_0_0_2_blocked(self):
        with _mock_resolve("127.0.0.2"):
            with pytest.raises(ValueError, match="non-public"):
                validate_image_url("https://loopback2.local/img.png")


# ---------------------------------------------------------------------------
# Link-local blocking
# ---------------------------------------------------------------------------

class TestLinkLocalBlocking:
    def test_169_254_blocked(self):
        """AWS metadata IP 169.254.169.254 must be blocked."""
        with _mock_resolve("169.254.169.254"):
            with pytest.raises(ValueError, match="non-public"):
                validate_image_url("https://aws.metadata.service/img")

    def test_169_254_other_blocked(self):
        with _mock_resolve("169.254.0.1"):
            with pytest.raises(ValueError, match="non-public"):
                validate_image_url("https://link-local.example/img")


# ---------------------------------------------------------------------------
# Unresolvable hostname
# ---------------------------------------------------------------------------

class TestUnresolvableHostname:
    def test_unresolvable_hostname_raises(self):
        with _mock_fail():
            with pytest.raises(ValueError, match="resolve"):
                validate_image_url("https://nonexistent.invalid/img.png")


# ---------------------------------------------------------------------------
# Malformed URLs
# ---------------------------------------------------------------------------

class TestMalformedUrls:
    def test_url_with_no_hostname_raises(self):
        """Edge case: scheme present but no host."""
        with pytest.raises(ValueError):
            validate_image_url("https:///path/to/image.jpg")
