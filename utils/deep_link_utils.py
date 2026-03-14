"""
Deep Link Utility Module for AURA Agent System.

Provides intelligent deep link resolution and URI construction
for direct app actions, bypassing UI navigation when possible.
"""

import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

from utils.app_inventory_utils import get_app_inventory_manager
from utils.logger import get_logger
from utils.types import IntentObject

logger = get_logger(__name__)


class DeepLinkManager:
    """
    Manager for intelligent deep link resolution and usage.

    Provides methods to:
    - Detect when deep links can be used instead of UI navigation
    - Build proper deep link URIs for various actions
    - Query app inventory for deep link capabilities
    - Match intents to appropriate deep link schemes
    """

    # Standard URI schemes and their typical use cases
    STANDARD_SCHEMES = {
        "tel": "direct_call",
        "sms": "send_sms",
        "mailto": "send_email",
        "http": "open_web",
        "https": "open_web",
        "geo": "open_location",
        "content": "open_content",
        "file": "open_file",
    }

    # App-specific deep link patterns (discovered from device)
    APP_SPECIFIC_PATTERNS = {
        "whatsapp": {
            "schemes": ["whatsapp", "https"],
            "patterns": [
                "whatsapp://send?phone={phone}&text={text}",
                "https://wa.me/{phone}?text={text}",
            ],
            "actions": ["send_message", "call", "video_call"],
        },
        "zoom": {
            "schemes": ["zoomus", "tel", "geo"],
            "patterns": [
                "zoomus://zoom.us/join?confno={meeting_id}",
                "tel:{phone_number}",
            ],
            "actions": ["join_meeting", "call"],
        },
        "truecaller": {
            "schemes": ["tel", "sms"],
            "patterns": ["tel:{phone_number}", "sms:{phone_number}?body={message}"],
            "actions": ["call", "send_sms"],
        },
        "gmail": {
            "schemes": ["mailto"],
            "patterns": ["mailto:{email}?subject={subject}&body={body}"],
            "actions": ["send_email", "compose"],
        },
        "messages": {
            "schemes": ["sms", "content"],
            "patterns": [
                "sms:{phone_number}?body={message}",
                "content://sms/{conversation_id}",
            ],
            "actions": ["send_sms", "send_message"],
        },
        "brave": {
            "schemes": ["http", "https"],
            "patterns": ["https://{domain}/{path}"],
            "actions": ["open_url", "search"],
        },
        "maps": {
            "schemes": ["geo"],
            "patterns": ["geo:{latitude},{longitude}?q={query}", "geo:0,0?q={address}"],
            "actions": ["navigate", "show_location"],
        },
    }

    def __init__(self):
        """Initialize the deep link manager with app inventory access."""
        self.inventory_manager = get_app_inventory_manager()
        logger.info("🔗 DeepLinkManager initialized")

    def can_use_deep_link(self, intent) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Determine if a deep link can be used for this intent.

        Args:
            intent: User intent (IntentObject or dict)

        Returns:
            Tuple of (can_use, app_package, scheme):
                - can_use: True if deep link is viable
                - app_package: Package name to use
                - scheme: URI scheme to use
        """
        try:
            # Support both dict and IntentObject
            if isinstance(intent, dict):
                action = (intent.get("action") or "").lower()
                recipient = intent.get("recipient")
                content = intent.get("content")
                parameters = intent.get("parameters") or {}
            else:
                action = intent.action.lower()
                recipient = intent.recipient
                content = intent.content
                parameters = intent.parameters or {}

            # Check for direct call (include common variants)
            if action in ["make_call", "call", "phone", "dial"]:
                if self._has_phone_number_from_data(recipient, content, parameters):
                    # Prefer user's default phone app from inventory order
                    phone_apps = self.inventory_manager.get_phone_apps()
                    package = (
                        phone_apps[0]["package_name"]
                        if phone_apps
                        else "com.android.dialer"
                    )
                    logger.debug(f"Using dialer app: {package}")
                    return True, package, "tel"

            # Check for SMS
            if action in ["send_sms", "text", "message", "send_message"]:
                logger.debug(f"SMS check: action={action}, has_phone={self._has_phone_number_from_data(recipient, content, parameters)}")
                if self._has_phone_number_from_data(recipient, content, parameters):
                    # WhatsApp explicitly requested via app parameter or recipient string
                    requested_app = (parameters.get("app", "") if parameters else "").lower()
                    logger.debug(f"Requested app from parameters: '{requested_app}', parameters={parameters}")
                    if "whatsapp" in requested_app or (recipient and "whatsapp" in str(recipient).lower()):
                        whatsapp_pkg = self._get_whatsapp_package()
                        if whatsapp_pkg:
                            logger.info(f"✅ WhatsApp explicitly requested, using package: {whatsapp_pkg}")
                            return True, whatsapp_pkg, "whatsapp"
                        else:
                            logger.warning("WhatsApp requested but package not found!")
                    logger.debug(f"Falling back to SMS package")
                    return True, self._get_sms_package(), "sms"

            # Check for email
            if action in ["send_email", "email", "compose_email"]:
                if self._has_email_address_from_data(recipient, content, parameters):
                    return True, self._get_email_package(), "mailto"

            # Check for web URLs
            if action in ["open_url", "browse", "open_web", "search"]:
                if self._has_url_from_data(recipient, content, parameters):
                    return True, self._get_browser_package(), "https"

            # Check for location/maps
            if action in [
                "navigate",
                "show_location",
                "map",
                "navigate_to",
                "directions",
            ]:
                if self._has_location_from_data(recipient, content, parameters):
                    return True, self._get_maps_package(), "geo"

            # Check for app-specific deep links by recipient name
            if recipient:
                app_name = str(recipient).lower()
                if app_name in self.APP_SPECIFIC_PATTERNS:
                    pattern_info = self.APP_SPECIFIC_PATTERNS[app_name]
                    if action in pattern_info["actions"]:
                        packages = self.inventory_manager.get_package_candidates(
                            app_name
                        )
                        if packages:
                            return True, packages[0], pattern_info["schemes"][0]

            return False, None, None

        except Exception as e:
            logger.error(f"Error checking deep link viability: {e}")
            return False, None, None

    def build_deep_link_uri(
        self, intent: IntentObject, scheme: str, app_package: Optional[str] = None
    ) -> Optional[str]:
        """
        Build a deep link URI for the given intent.

        Args:
            intent: User intent to build URI for
            scheme: URI scheme to use (tel, sms, mailto, etc.)
            app_package: Optional package name for app-specific links

        Returns:
            Constructed deep link URI or None if construction fails
        """
        try:
            intent.action.lower()

            # Build tel: URIs for calls
            if scheme == "tel":
                phone = self._extract_phone_number(intent)
                if phone:
                    return f"tel:{phone}"

            # Build sms: URIs
            if scheme == "sms":
                phone = self._extract_phone_number(intent)
                message = intent.content or ""
                if phone:
                    if message:
                        return f"sms:{phone}?body={quote(message)}"
                    return f"sms:{phone}"

            # Build WhatsApp URIs
            if scheme == "whatsapp":
                phone = self._extract_phone_number(intent)
                message = intent.content or ""
                if phone:
                    # Remove + and format for WhatsApp
                    wa_phone = phone.replace("+", "").replace("-", "").replace(" ", "")
                    if message:
                        return f"https://wa.me/{wa_phone}?text={quote(message)}"
                    return f"https://wa.me/{wa_phone}"

            # Build mailto: URIs
            if scheme == "mailto":
                email = self._extract_email_address(intent)
                if email:
                    subject = (
                        intent.parameters.get("subject", "")
                        if intent.parameters
                        else ""
                    )
                    body = intent.content or ""

                    uri = f"mailto:{email}"
                    params = []
                    if subject:
                        params.append(f"subject={quote(subject)}")
                    if body:
                        params.append(f"body={quote(body)}")

                    if params:
                        uri += "?" + "&".join(params)
                    return uri

            # Build https: URIs for web
            if scheme in ["http", "https"]:
                url = self._extract_url(intent)
                if url:
                    if not url.startswith(("http://", "https://")):
                        url = "https://" + url
                    return url

            # Build geo: URIs for locations
            if scheme == "geo":
                location = self._extract_location(intent)
                if location:
                    query = intent.content or intent.recipient or ""
                    if query:
                        return f"geo:0,0?q={quote(query)}"
                    return "geo:0,0"

            # App-specific deep links
            if app_package and intent.recipient:
                app_name = intent.recipient.lower()
                if app_name in self.APP_SPECIFIC_PATTERNS:
                    pattern_info = self.APP_SPECIFIC_PATTERNS[app_name]
                    if pattern_info["patterns"]:
                        pattern = pattern_info["patterns"][0]
                        return self._fill_pattern(pattern, intent)

            logger.warning(f"Could not build deep link URI for scheme: {scheme}")
            return None

        except Exception as e:
            logger.error(f"Error building deep link URI: {e}")
            return None

    def get_deep_link_context(self, intent: IntentObject) -> Dict[str, Any]:
        """
        Get comprehensive deep link context for the given intent.

        This provides agents with information about available deep links,
        their viability, and recommended usage.

        Args:
            intent: User intent to analyze

        Returns:
            Dictionary with deep link context and recommendations
        """
        can_use, package, scheme = self.can_use_deep_link(intent)

        context = {
            "deep_link_viable": can_use,
            "recommended_package": package,
            "recommended_scheme": scheme,
            "alternative_schemes": [],
            "benefits": [],
            "limitations": [],
        }

        if can_use:
            # Build the URI
            uri = self.build_deep_link_uri(intent, scheme, package)
            context["deep_link_uri"] = uri
            context["benefits"] = [
                "Bypasses UI navigation",
                "Faster execution",
                "More reliable",
                "Direct system integration",
            ]

            # Check for alternative schemes
            if scheme in ["sms", "whatsapp"]:
                context["alternative_schemes"] = ["sms", "whatsapp", "tel"]
            elif scheme == "tel":
                context["alternative_schemes"] = ["tel", "sms"]

            # Get apps supporting this scheme
            apps_with_scheme = self.inventory_manager.get_apps_with_deep_link(scheme)
            context["available_apps"] = [
                {"package": app["package_name"], "name": app["app_name"]}
                for app in apps_with_scheme[:5]  # Top 5
            ]
        else:
            context["limitations"] = [
                "No deep link available for this action",
                "Requires UI navigation",
                "May need contact resolution",
            ]
            context["fallback_strategy"] = "UI_NAVIGATION"

        return context

    def get_apps_with_scheme(self, scheme: str) -> List[Dict[str, Any]]:
        """
        Get all apps that support a specific URI scheme.

        Args:
            scheme: URI scheme to search for (tel, sms, mailto, etc.)

        Returns:
            List of app dictionaries with package names and capabilities
        """
        return self.inventory_manager.get_apps_with_deep_link(scheme)

    # Helper methods for data extraction

    def _has_phone_number_from_data(self, recipient, content, parameters) -> bool:
        """Check if raw data contains a phone number."""
        phone_pattern = r"[\+\d][\d\s\-\(\)]{8,}"
        if parameters and isinstance(parameters, dict) and parameters.get("phone"):
            return True
        if recipient and re.search(phone_pattern, str(recipient)):
            return True
        if content and re.search(phone_pattern, str(content)):
            return True
        return False

    def _has_email_address_from_data(self, recipient, content, parameters) -> bool:
        """Check if raw data contains an email address."""
        email_pattern = r"[\w\.-]+@[\w\.-]+\.\w+"
        if parameters and isinstance(parameters, dict) and parameters.get("email"):
            return True
        if recipient and re.search(email_pattern, str(recipient)):
            return True
        if content and re.search(email_pattern, str(content)):
            return True
        return False

    def _has_url_from_data(self, recipient, content, parameters) -> bool:
        """Check if raw data contains a URL/domain."""
        text_to_search = f"{recipient or ''} {content or ''}"
        url_pattern = r"https?://[^\s]+"
        domain_pattern = r"[\w-]+\.[\w.-]+\.\w+"
        return bool(
            re.search(url_pattern, text_to_search)
            or re.search(domain_pattern, text_to_search)
        )

    def _has_location_from_data(self, recipient, content, parameters) -> bool:
        """Check if raw data contains location info."""
        if (
            parameters
            and isinstance(parameters, dict)
            and {"latitude", "longitude"}.issubset(parameters.keys())
        ):
            return True
        if content or recipient:
            return True
        return False

    def _has_phone_number(self, intent: IntentObject) -> bool:
        """Check if intent contains a phone number."""
        return self._extract_phone_number(intent) is not None

    def _extract_phone_number(self, intent: IntentObject) -> Optional[str]:
        """Extract phone number from intent."""
        # Check parameters first
        if intent.parameters and "phone" in intent.parameters:
            return intent.parameters["phone"]

        # Check recipient for phone pattern
        if intent.recipient:
            phone_match = re.search(r"[\+\d][\d\s\-\(\)]{8,}", intent.recipient)
            if phone_match:
                return phone_match.group().strip()

        # Check content for phone pattern
        if intent.content:
            phone_match = re.search(r"[\+\d][\d\s\-\(\)]{8,}", intent.content)
            if phone_match:
                return phone_match.group().strip()

        return None

    def _has_email_address(self, intent: IntentObject) -> bool:
        """Check if intent contains an email address."""
        return self._extract_email_address(intent) is not None

    def _extract_email_address(self, intent: IntentObject) -> Optional[str]:
        """Extract email address from intent."""
        # Check parameters
        if intent.parameters and "email" in intent.parameters:
            return intent.parameters["email"]

        # Check recipient for email pattern
        if intent.recipient:
            email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", intent.recipient)
            if email_match:
                return email_match.group()

        return None

    def _has_url(self, intent: IntentObject) -> bool:
        """Check if intent contains a URL."""
        return self._extract_url(intent) is not None

    def _extract_url(self, intent: IntentObject) -> Optional[str]:
        """Extract URL from intent."""
        # Check content for URL pattern
        text_to_search = f"{intent.recipient or ''} {intent.content or ''}"

        url_pattern = r"https?://[^\s]+"
        url_match = re.search(url_pattern, text_to_search)
        if url_match:
            return url_match.group()

        # Check for domain without protocol
        domain_pattern = r"[\w-]+\.[\w.-]+\.\w+"
        domain_match = re.search(domain_pattern, text_to_search)
        if domain_match:
            return domain_match.group()

        return None

    def _has_location_data(self, intent: IntentObject) -> bool:
        """Check if intent contains location data."""
        return self._extract_location(intent) is not None

    def _extract_location(self, intent: IntentObject) -> Optional[str]:
        """Extract location from intent."""
        # Check for coordinates
        if intent.parameters:
            if "latitude" in intent.parameters and "longitude" in intent.parameters:
                return (
                    f"{intent.parameters['latitude']},{intent.parameters['longitude']}"
                )

        # Check for address/place name
        if intent.content or intent.recipient:
            return intent.content or intent.recipient

        return None

    def _fill_pattern(self, pattern: str, intent: IntentObject) -> str:
        """Fill a URI pattern with intent data."""
        result = pattern

        # Fill phone number
        phone = self._extract_phone_number(intent)
        if phone:
            result = result.replace("{phone}", quote(phone))
            result = result.replace("{phone_number}", quote(phone))

        # Fill email
        email = self._extract_email_address(intent)
        if email:
            result = result.replace("{email}", quote(email))

        # Fill text/message
        if intent.content:
            result = result.replace("{text}", quote(intent.content))
            result = result.replace("{message}", quote(intent.content))
            result = result.replace("{body}", quote(intent.content))

        # Fill subject
        if intent.parameters and "subject" in intent.parameters:
            result = result.replace("{subject}", quote(intent.parameters["subject"]))

        return result

    # Package resolution helpers

    def _get_dialer_package(self) -> str:
        """Get the best dialer/phone app package."""
        candidates = self.inventory_manager.get_phone_apps()
        return candidates[0]["package_name"] if candidates else "com.android.dialer"

    def _get_sms_package(self) -> str:
        """Get the best SMS app package."""
        candidates = self.inventory_manager.get_messaging_apps()
        return candidates[0]["package_name"] if candidates else "com.android.mms"

    def _get_whatsapp_package(self) -> Optional[str]:
        """Get WhatsApp package if installed."""
        candidates = self.inventory_manager.get_package_candidates("whatsapp")
        return candidates[0] if candidates else None

    def _get_email_package(self) -> str:
        """Get the best email app package."""
        candidates = self.inventory_manager.get_email_apps()
        return candidates[0]["package_name"] if candidates else "com.google.android.gm"

    def _get_browser_package(self) -> str:
        """Get the best browser package."""
        candidates = self.inventory_manager.get_browser_apps()
        return candidates[0]["package_name"] if candidates else "com.android.chrome"

    def _get_maps_package(self) -> str:
        """Get the best maps app package."""
        candidates = self.inventory_manager.get_package_candidates("maps")
        return candidates[0] if candidates else "com.google.android.apps.maps"


# Singleton instance
_deep_link_manager: Optional[DeepLinkManager] = None


def get_deep_link_manager() -> DeepLinkManager:
    """
    Get the singleton DeepLinkManager instance.

    Returns:
        Singleton DeepLinkManager instance
    """
    global _deep_link_manager
    if _deep_link_manager is None:
        _deep_link_manager = DeepLinkManager()
    return _deep_link_manager
