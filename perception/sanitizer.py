"""
Data Sanitizer - Remove sensitive data from perception payloads.

Strips passwords, credit cards, SSNs, and other sensitive patterns
from UI tree text before processing.
"""

import re
from typing import Dict, List, Optional

from utils.logger import get_logger

logger = get_logger(__name__)


# Sensitive patterns to redact
SENSITIVE_PATTERNS = [
    # Credit card numbers (16 digits with optional separators)
    (re.compile(r'\b(?:\d{4}[-\s]?){3}\d{4}\b'), '[REDACTED_CC]'),
    
    # SSN (XXX-XX-XXXX)
    (re.compile(r'\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b'), '[REDACTED_SSN]'),
    
    # Phone numbers (various formats)
    (re.compile(r'\b(?:\+?\d{1,3}[-\s]?)?\(?\d{3}\)?[-\s]?\d{3}[-\s]?\d{4}\b'), '[REDACTED_PHONE]'),
    
    # Email addresses
    (re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'), '[REDACTED_EMAIL]'),
    
    # Password fields (case insensitive)
    (re.compile(r'\bpassword\s*[:=]\s*\S+', re.IGNORECASE), 'password: [REDACTED]'),
    (re.compile(r'\bpassword\b.*', re.IGNORECASE), '[REDACTED_PASSWORD_FIELD]'),
    
    # PIN codes (4-6 digits often labeled as PIN)
    (re.compile(r'\bpin\s*[:=]?\s*\d{4,6}\b', re.IGNORECASE), 'PIN: [REDACTED]'),
    
    # OTP/verification codes
    (re.compile(r'\b(?:otp|code|verify|verification)\s*[:=]?\s*\d{4,8}\b', re.IGNORECASE), '[REDACTED_OTP]'),
    
    # CVV/CVC (3-4 digits)
    (re.compile(r'\b(?:cvv|cvc|security code)\s*[:=]?\s*\d{3,4}\b', re.IGNORECASE), '[REDACTED_CVV]'),
    
    # Aadhaar numbers (12 digits, India)
    (re.compile(r'\b\d{4}\s?\d{4}\s?\d{4}\b'), '[REDACTED_AADHAAR]'),
    
    # PAN numbers (India: AAAAA9999A)
    (re.compile(r'\b[A-Z]{5}\d{4}[A-Z]\b'), '[REDACTED_PAN]'),
]

# Sensitive package names (banking, password managers, etc.)
SENSITIVE_PACKAGES = {
    # Banking apps
    'com.google.android.apps.walletnfcrel',  # Google Pay
    'com.phonepe.app',
    'net.one97.paytm',
    'com.paytm.pgateway',
    'com.whatsapp.payments',
    'com.amazon.mShop.android.shopping',
    'in.org.npci.upiapp',  # BHIM
    'com.bankofamerica.mobilebanking',
    'com.chase.sig.android',
    'com.paypal.android.p2pmobile',
    'com.venmo',
    
    # Password managers
    'com.lastpass.lpandroid',
    'com.onepassword.android',
    'com.dashlane',
    'com.bitwarden.authenticator',
    'com.x8bit.bitwarden',
    'com.authy.authy',
    'com.google.android.apps.authenticator2',
    
    # Crypto
    'com.coinbase.android',
    'com.binance.dev',
}


def sanitize_text(text: Optional[str]) -> str:
    """
    Sanitize a text string by redacting sensitive patterns.
    
    Args:
        text: Text to sanitize
    
    Returns:
        Sanitized text
    """
    if not text:
        return ""
    
    sanitized = text
    for pattern, replacement in SENSITIVE_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
    
    return sanitized


def sanitize_ui_tree(elements: List[Dict], package_name: Optional[str] = None) -> List[Dict]:
    """
    Sanitize UI tree elements by redacting sensitive information.
    
    Args:
        elements: List of UI element dictionaries
        package_name: Current app package name
    
    Returns:
        Sanitized elements list
    """
    # If this is a sensitive app, redact ALL text
    if package_name and package_name.lower() in SENSITIVE_PACKAGES:
        logger.warning(f"🔒 Sensitive app detected ({package_name}), redacting all text")
        return _redact_all_text(elements)
    
    # Otherwise, apply pattern-based sanitization
    sanitized_elements = []
    redaction_count = 0
    
    for elem in elements:
        sanitized_elem = elem.copy()
        
        # Sanitize text field
        if "text" in sanitized_elem and sanitized_elem["text"]:
            original = sanitized_elem["text"]
            sanitized = sanitize_text(original)
            if sanitized != original:
                redaction_count += 1
                logger.debug(f"Redacted text: '{original[:20]}...' → '{sanitized[:20]}...'")
            sanitized_elem["text"] = sanitized
        
        # Sanitize contentDescription
        if "contentDescription" in sanitized_elem and sanitized_elem["contentDescription"]:
            sanitized_elem["contentDescription"] = sanitize_text(sanitized_elem["contentDescription"])
        
        sanitized_elements.append(sanitized_elem)
    
    if redaction_count > 0:
        logger.info(f"🔒 Sanitized {redaction_count} elements with sensitive data")
    
    return sanitized_elements


def _redact_all_text(elements: List[Dict]) -> List[Dict]:
    """Redact all text fields for sensitive apps."""
    redacted = []
    for elem in elements:
        redacted_elem = elem.copy()
        
        # Keep structural info, redact text
        if "text" in redacted_elem and redacted_elem["text"]:
            redacted_elem["text"] = "[REDACTED_SENSITIVE_APP]"
        if "contentDescription" in redacted_elem and redacted_elem["contentDescription"]:
            redacted_elem["contentDescription"] = "[REDACTED_SENSITIVE_APP]"
        
        redacted.append(redacted_elem)
    
    return redacted


def is_sensitive_app(package_name: Optional[str]) -> bool:
    """Check if an app is classified as sensitive."""
    if not package_name:
        return False
    return package_name.lower() in SENSITIVE_PACKAGES
