"""
App Inventory Utilities.

Utilities for querying and using the device app inventory stored in
device_app_inventory.json to provide dynamic app package resolution.
"""

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from utils.logger import get_logger

logger = get_logger(__name__)

# Path to the inventory file
INVENTORY_FILE = Path(__file__).parent.parent / "device_app_inventory.json"

# Common app synonyms - maps user-spoken names to actual app names
# Key: lowercase spoken name, Value: list of possible app name matches
APP_SYNONYMS: Dict[str, List[str]] = {
    # ChatGPT variations
    "chat gpt": ["chatgpt", "chat"],
    "chatgpt": ["chatgpt", "chat"],
    "gpt": ["chatgpt", "chat"],
    "openai": ["chatgpt"],
    
    # Social media
    "insta": ["instagram"],
    "ig": ["instagram"],
    "fb": ["facebook"],
    "wa": ["whatsapp"],
    "twitter": ["x", "twitter"],
    "x": ["x", "twitter"],
    
    # Google apps
    "google": ["google", "chrome"],
    "chrome": ["chrome", "google chrome"],
    "gmail": ["gmail", "mail"],
    "maps": ["maps", "google maps"],
    "google maps": ["maps", "google maps"],
    "drive": ["google drive", "drive"],
    "docs": ["google docs", "docs"],
    "sheets": ["google sheets", "sheets"],
    "slides": ["google slides", "slides"],
    "youtube": ["youtube", "yt"],
    "yt": ["youtube"],
    
    # Microsoft
    "excel": ["microsoft excel", "excel"],
    "word": ["microsoft word", "word"],
    "powerpoint": ["microsoft powerpoint", "powerpoint"],
    "outlook": ["outlook", "microsoft outlook"],
    "teams": ["microsoft teams", "teams"],
    "onedrive": ["onedrive"],
    
    # Messaging
    "telegram": ["telegram"],
    "tg": ["telegram"],
    "messages": ["messages", "messaging", "sms"],
    "sms": ["messages", "messaging"],
    "text": ["messages", "messaging"],
    
    # Media
    "spotify": ["spotify"],
    "music": ["music", "spotify", "apple music", "youtube music"],
    "apple music": ["apple music", "music"],
    "apple": ["apple music"],  # "apple" alone should map to Apple Music, not Apple TV
    "netflix": ["netflix"],
    "prime": ["prime video", "amazon prime"],
    
    # Utilities
    "camera": ["camera"],
    "photos": ["photos", "gallery", "google photos"],
    "gallery": ["gallery", "photos"],
    "files": ["files", "file manager"],
    "calculator": ["calculator", "calc"],
    "calc": ["calculator"],
    "clock": ["clock", "alarm"],
    "alarm": ["clock", "alarm"],
    "calendar": ["calendar", "google calendar"],
    "notes": ["notes", "keep", "google keep"],
    "settings": ["settings"],
    
    # Browsers
    "browser": ["chrome", "brave", "firefox", "edge", "browser"],
    "web": ["chrome", "brave", "browser"],
    "brave": ["brave"],
    "firefox": ["firefox"],
    "edge": ["edge", "microsoft edge"],
    
    # Shopping
    "amazon": ["amazon", "amazon shopping"],
    "flipkart": ["flipkart"],
    
    # Others
    "zoom": ["zoom"],
    "meet": ["google meet", "meet"],
    "github": ["github"],
    "reddit": ["reddit"],
}


def normalize_app_name(name: str) -> str:
    """
    Normalize app name for comparison.
    Removes spaces, special chars, converts to lowercase.
    """
    # Remove common words and normalize
    name = name.lower().strip()
    # Remove "app", "application" suffixes
    name = re.sub(r'\s*(app|application)$', '', name)
    # Normalize spaces and special characters for comparison
    return name


def fuzzy_match_score(query: str, target: str) -> float:
    """
    Calculate fuzzy match score between query and target.
    Returns 0.0 to 1.0 (1.0 = perfect match).
    """
    query = normalize_app_name(query)
    target = normalize_app_name(target)
    
    if not query or not target:
        return 0.0
    
    # Exact match
    if query == target:
        return 1.0
    
    # Query without spaces matches target (e.g., "chat gpt" -> "chatgpt")
    query_no_space = query.replace(" ", "")
    target_no_space = target.replace(" ", "")
    if query_no_space == target_no_space:
        return 0.95
    
    # One contains the other
    if query in target:
        return 0.8 + (len(query) / len(target)) * 0.15
    if target in query:
        return 0.7 + (len(target) / len(query)) * 0.15
    
    # Word overlap
    query_words = set(query.split())
    target_words = set(target.split())
    if query_words and target_words:
        overlap = len(query_words & target_words)
        total = len(query_words | target_words)
        if overlap > 0:
            return 0.5 + (overlap / total) * 0.4
    
    # Character-level similarity (basic Levenshtein approximation)
    shorter = min(len(query_no_space), len(target_no_space))
    longer = max(len(query_no_space), len(target_no_space))
    if longer == 0:
        return 0.0
    
    # Count matching characters in order
    matches = 0
    t_idx = 0
    for c in query_no_space:
        while t_idx < len(target_no_space):
            if target_no_space[t_idx] == c:
                matches += 1
                t_idx += 1
                break
            t_idx += 1
    
    if matches >= shorter * 0.7:  # At least 70% of chars match in order
        return 0.3 + (matches / longer) * 0.3
    
    return 0.0


class AppInventoryManager:
    """Manager for device app inventory queries."""

    def __init__(self):
        """Initialize the app inventory manager."""
        self._inventory: Optional[Dict[str, Any]] = None
        self._last_loaded: float = 0
        self._cache_duration: float = 60.0  # Cache for 60 seconds

    def _load_inventory(self) -> Dict[str, Any]:
        """
        Load the app inventory from file with caching.

        Returns:
            App inventory dictionary
        """
        current_time = (
            os.path.getmtime(INVENTORY_FILE) if INVENTORY_FILE.exists() else 0
        )

        # Reload if cache expired or file modified
        if self._inventory is None or current_time > self._last_loaded:
            try:
                with open(INVENTORY_FILE, "r", encoding="utf-8") as f:
                    self._inventory = json.load(f)
                self._last_loaded = current_time
                logger.debug(f"📦 Loaded app inventory from {INVENTORY_FILE}")
            except FileNotFoundError:
                logger.warning(f"⚠️ App inventory file not found: {INVENTORY_FILE}")
                self._inventory = {"devices": {}}
            except json.JSONDecodeError as e:
                logger.error(f"❌ Failed to parse app inventory: {e}")
                self._inventory = {"devices": {}}

        return self._inventory

    def get_first_device_name(self) -> Optional[str]:
        """
        Get the name of the first device in the inventory.

        Returns:
            Device name or None if no devices
        """
        inventory = self._load_inventory()
        devices = inventory.get("devices", {})
        if devices:
            return list(devices.keys())[0]
        return None

    def get_device_apps(
        self, device_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all apps for a device.

        Args:
            device_name: Device name (uses first device if None)

        Returns:
            List of app info dictionaries
        """
        inventory = self._load_inventory()
        devices = inventory.get("devices", {})

        if not devices:
            logger.warning("⚠️ No devices in app inventory")
            return []

        # Use provided device or first available device
        if device_name and device_name in devices:
            device_data = devices[device_name]
        else:
            device_name = list(devices.keys())[0]
            device_data = devices[device_name]
            logger.debug(f"Using first available device: {device_name}")

        return device_data.get("apps", [])

    def find_app_by_name(
        self, app_name: str, device_name: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Find an app by name with intelligent fuzzy matching.
        
        Handles:
        - Case differences: "ChatGPT" = "chatgpt"
        - Spaces: "chat gpt" = "chatgpt"
        - Synonyms: "gpt" finds "ChatGPT"
        - Partial matches: "insta" finds "Instagram"

        Args:
            app_name: App name to search for
            device_name: Device name (uses first device if None)

        Returns:
            App info dictionary or None
        """
        apps = self.get_device_apps(device_name)
        query = normalize_app_name(app_name)
        query_no_space = query.replace(" ", "")
        
        # Check synonyms
        synonym_targets = APP_SYNONYMS.get(query, [])
        if not synonym_targets:
            synonym_targets = APP_SYNONYMS.get(query_no_space, [])
        
        best_match: Optional[Dict[str, Any]] = None
        best_score = 0.0

        for app in apps:
            current_name = app.get("app_name", "")
            current_lower = normalize_app_name(current_name)
            current_no_space = current_lower.replace(" ", "")
            
            # Skip system overlays
            pkg = app.get("package_name", "")
            if "overlay" in pkg.lower() or current_name == pkg:
                continue
            
            score = 0.0
            
            # Check synonym matches first
            for syn in synonym_targets:
                syn_lower = syn.lower()
                if syn_lower == current_lower or syn_lower == current_no_space:
                    score = max(score, 0.98)
                elif syn_lower in current_lower:
                    score = max(score, 0.85)
            
            # Direct matching
            if query == current_lower:
                score = max(score, 1.0)
            elif query_no_space == current_no_space:
                score = max(score, 0.95)
            elif query in current_lower or current_lower in query:
                score = max(score, 0.8)
            elif query_no_space in current_no_space:
                score = max(score, 0.75)
            else:
                # Fuzzy match
                score = max(score, fuzzy_match_score(query, current_lower))
            
            if score > best_score:
                best_score = score
                best_match = app

        if best_match and best_score >= 0.5:
            logger.debug(
                f"Found app '{app_name}' -> '{best_match.get('app_name')}' "
                f"(score: {best_score:.2f})"
            )
            return best_match
        
        logger.debug(f"App not found: {app_name}")
        return None

    def get_package_candidates(
        self, app_alias: str, device_name: Optional[str] = None
    ) -> List[str]:
        """
        Get package name candidates for an app alias with intelligent matching.
        
        Uses:
        1. Synonym dictionary for common spoken names
        2. Fuzzy matching for typos and variations
        3. Space-insensitive matching (e.g., "chat gpt" = "chatgpt")

        Args:
            app_alias: App alias/name (e.g., "camera", "whatsapp", "chat gpt")
            device_name: Device name (uses first device if None)

        Returns:
            List of package name candidates in priority order
        """
        apps = self.get_device_apps(device_name)
        alias_lower = normalize_app_name(app_alias)
        alias_no_space = alias_lower.replace(" ", "")
        
        # Collect candidates with scores
        scored_candidates: List[Tuple[float, str, str]] = []  # (score, package, app_name)
        
        # Check synonyms first
        synonym_targets = APP_SYNONYMS.get(alias_lower, [])
        if not synonym_targets:
            # Try without spaces
            synonym_targets = APP_SYNONYMS.get(alias_no_space, [])
        
        for app in apps:
            app_name = app.get("app_name", "")
            app_name_lower = normalize_app_name(app_name)
            app_name_no_space = app_name_lower.replace(" ", "")
            package_name = app.get("package_name", "")
            
            # Skip system overlays and internal packages
            if "overlay" in package_name.lower() or app_name == package_name:
                continue
            
            best_score = 0.0
            
            # Check synonym matches
            for syn_target in synonym_targets:
                syn_lower = syn_target.lower()
                if syn_lower == app_name_lower or syn_lower == app_name_no_space:
                    best_score = max(best_score, 0.98)
                elif syn_lower in app_name_lower:
                    best_score = max(best_score, 0.85)
            
            # Direct fuzzy match
            direct_score = fuzzy_match_score(alias_lower, app_name_lower)
            best_score = max(best_score, direct_score)
            
            # Space-normalized match (e.g., "chat gpt" vs "chatgpt")
            if alias_no_space == app_name_no_space:
                best_score = max(best_score, 0.95)
            elif alias_no_space in app_name_no_space or app_name_no_space in alias_no_space:
                best_score = max(best_score, 0.75)
            
            # Package name match (lower priority)
            pkg_lower = package_name.lower()
            if alias_no_space in pkg_lower:
                best_score = max(best_score, 0.5)
            
            if best_score > 0.3:  # Minimum threshold
                scored_candidates.append((best_score, package_name, app_name))
        
        # Sort by score descending
        scored_candidates.sort(key=lambda x: (-x[0], x[2]))
        
        # Extract package names
        candidates = [pkg for _, pkg, _ in scored_candidates]
        
        if candidates:
            top_matches = [(score, name) for score, _, name in scored_candidates[:3]]
            logger.info(
                f"App '{app_alias}' matched: {top_matches}"
            )
        else:
            logger.warning(f"No package candidates found for: {app_alias}")

        return candidates

    def get_apps_with_deep_link(
        self, scheme: str, device_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all apps that support a specific deep link scheme.

        Args:
            scheme: Deep link scheme (e.g., "tel", "mailto", "https")
            device_name: Device name (uses first device if None)

        Returns:
            List of app info dictionaries
        """
        apps = self.get_device_apps(device_name)
        matching_apps = []

        for app in apps:
            deep_links = app.get("deep_links", [])
            if scheme in deep_links:
                matching_apps.append(app)

        logger.debug(f"Found {len(matching_apps)} apps supporting '{scheme}' deep link")
        return matching_apps

    def get_messaging_apps(
        self, device_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all messaging apps (apps with 'sms' deep link).

        Args:
            device_name: Device name (uses first device if None)

        Returns:
            List of messaging app info dictionaries
        """
        return self.get_apps_with_deep_link("sms", device_name)

    def get_browser_apps(
        self, device_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all browser apps (apps with 'http' or 'https' deep link).

        Args:
            device_name: Device name (uses first device if None)

        Returns:
            List of browser app info dictionaries
        """
        http_apps = self.get_apps_with_deep_link("http", device_name)
        https_apps = self.get_apps_with_deep_link("https", device_name)

        # Combine and deduplicate
        all_browsers = {app["package_name"]: app for app in http_apps + https_apps}
        return list(all_browsers.values())

    def get_phone_apps(self, device_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all phone dialer apps (apps with 'tel' deep link).

        Args:
            device_name: Device name (uses first device if None)

        Returns:
            List of phone app info dictionaries
        """
        return self.get_apps_with_deep_link("tel", device_name)

    def get_email_apps(self, device_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all email apps (apps with 'mailto' deep link).

        Args:
            device_name: Device name (uses first device if None)

        Returns:
            List of email app info dictionaries
        """
        return self.get_apps_with_deep_link("mailto", device_name)

    def get_all_user_apps(
        self, device_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all user-installed apps (non-system apps).

        Args:
            device_name: Device name (uses first device if None)

        Returns:
            List of user app info dictionaries
        """
        apps = self.get_device_apps(device_name)
        return [app for app in apps if not app.get("is_system_app", True)]

    def get_app_summary(self, device_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Get summary statistics about installed apps.

        Args:
            device_name: Device name (uses first device if None)

        Returns:
            Summary statistics dictionary
        """
        apps = self.get_device_apps(device_name)

        total_apps = len(apps)
        user_apps = len([app for app in apps if not app.get("is_system_app", True)])
        system_apps = total_apps - user_apps
        apps_with_deep_links = len([app for app in apps if app.get("deep_links")])
        total_deep_links = sum(len(app.get("deep_links", [])) for app in apps)

        return {
            "total_apps": total_apps,
            "user_apps": user_apps,
            "system_apps": system_apps,
            "apps_with_deep_links": apps_with_deep_links,
            "total_deep_links": total_deep_links,
            "messaging_apps": len(self.get_messaging_apps(device_name)),
            "browser_apps": len(self.get_browser_apps(device_name)),
            "phone_apps": len(self.get_phone_apps(device_name)),
            "email_apps": len(self.get_email_apps(device_name)),
        }

    def get_installed_app_names(self, device_name: Optional[str] = None) -> str:
        """
        Return a compact, prompt-friendly comma-separated list of user-installed
        app names (non-system apps only).
        """
        user_apps = self.get_all_user_apps(device_name)
        names = sorted({a["app_name"] for a in user_apps if a.get("app_name")})
        return ", ".join(names)


# Global singleton instance
_app_inventory_manager: Optional[AppInventoryManager] = None


def get_app_inventory_manager() -> AppInventoryManager:
    """
    Get the global app inventory manager instance.

    Returns:
        AppInventoryManager singleton
    """
    global _app_inventory_manager
    if _app_inventory_manager is None:
        _app_inventory_manager = AppInventoryManager()
    return _app_inventory_manager
