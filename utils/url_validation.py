"""URL validation utilities to prevent SSRF attacks."""

import ipaddress
import socket
from urllib.parse import urlparse

from utils.logger import get_logger

logger = get_logger(__name__)

# Trusted image hosts — extend as needed
_TRUSTED_IMAGE_HOSTS: set[str] = {
    "storage.googleapis.com",
    "lh3.googleusercontent.com",
    "images.unsplash.com",
    "upload.wikimedia.org",
}


def validate_image_url(url: str) -> str:
    """
    Validate a URL is safe to fetch (prevents SSRF).

    Checks:
    1. Scheme is http or https only.
    2. Hostname resolves to a public (non-private, non-loopback) IP.

    Args:
        url: The URL string to validate.

    Returns:
        The validated URL if safe.

    Raises:
        ValueError: If the URL is unsafe or unresolvable.
    """
    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Unsupported URL scheme: {parsed.scheme}")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL has no hostname")

    # Resolve hostname → IP and check it is globally routable
    try:
        ip_str = socket.gethostbyname(hostname)
        ip_obj = ipaddress.ip_address(ip_str)
    except (socket.gaierror, ValueError) as exc:
        raise ValueError(f"Could not resolve hostname '{hostname}'") from exc

    if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local or ip_obj.is_reserved:
        raise ValueError(
            f"URL resolves to non-public IP ({ip_str}); request blocked"
        )

    return url
