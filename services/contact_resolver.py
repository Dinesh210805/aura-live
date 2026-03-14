"""
Contact resolver service - Resolves contact names to phone numbers.

Used for deep linking to messaging apps like WhatsApp.
"""

from typing import Optional
from utils.logger import get_logger

logger = get_logger(__name__)


class ContactResolver:
    """
    Resolves contact names to phone numbers for deep linking.
    
    Currently a stub - requires Android contacts API integration.
    """
    
    def __init__(self):
        """Initialize contact resolver."""
        self._contacts_cache: dict[str, str] = {}
    
    def resolve(self, name: str) -> Optional[str]:
        """
        Resolve a contact name to a phone number.
        
        Args:
            name: Contact name to resolve
            
        Returns:
            Phone number or None if not found
        """
        # Check cache
        if name.lower() in self._contacts_cache:
            return self._contacts_cache[name.lower()]
        
        # TODO: Query Android contacts API via WebSocket
        logger.debug(f"Contact resolution not implemented for: {name}")
        return None
    
    def cache_contact(self, name: str, phone: str) -> None:
        """
        Cache a contact for future resolution.
        
        Args:
            name: Contact name
            phone: Phone number
        """
        self._contacts_cache[name.lower()] = phone


# Global instance
_contact_resolver: Optional[ContactResolver] = None


def get_contact_resolver() -> ContactResolver:
    """Get or create the contact resolver singleton."""
    global _contact_resolver
    if _contact_resolver is None:
        _contact_resolver = ContactResolver()
    return _contact_resolver