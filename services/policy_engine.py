"""
OPA Policy Engine for AURA Guardrails.

Evaluates actions against Rego policies before execution to enforce:
- Safety guardrails (block destructive actions)
- App restrictions (blocklist sensitive apps)
- Rate limiting (prevent runaway loops)
- Confirmation requirements (high-risk actions need user approval)
"""

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from utils.logger import get_logger

logger = get_logger(__name__)

# Try to import OPA library
try:
    from opa_python_client import OpaClient
    OPA_AVAILABLE = True
except ImportError:
    try:
        # Alternative: regopy (pure Python Rego interpreter)
        import regopy
        OPA_AVAILABLE = True
        USE_REGOPY = True
    except ImportError:
        OPA_AVAILABLE = False
        USE_REGOPY = False
        logger.warning("⚠️ OPA not available - guardrails running in permissive mode")


@dataclass
class PolicyDecision:
    """Result of policy evaluation."""
    allowed: bool
    reason: str = ""
    requires_confirmation: bool = False
    confirmation_message: str = ""
    policy_violated: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ActionContext:
    """Context passed to policy engine for evaluation."""
    action_type: str
    target: Optional[str] = None
    app_name: Optional[str] = None
    package_name: Optional[str] = None
    text_content: Optional[str] = None
    coordinates: Optional[Dict[str, int]] = None
    user_id: str = "default"
    session_id: str = ""
    timestamp: float = field(default_factory=time.time)
    previous_actions: List[str] = field(default_factory=list)
    action_count_last_minute: int = 0


class PolicyEngine:
    """
    OPA-based policy enforcement for AURA actions.
    
    Supports two modes:
    1. Embedded mode: Uses regopy for pure Python Rego evaluation
    2. Server mode: Connects to OPA server for policy decisions
    
    Falls back to built-in Python policies if OPA is unavailable.
    """
    
    # Actions that are always blocked
    BLOCKED_ACTIONS = {
        "factory_reset",
        "wipe_data", 
        "delete_all",
        "format_storage",
        "root_device",
        "install_unknown_apk",
    }
    
    # Financial/Payment apps - BLOCKED for MVP (safety reasons)
    BLOCKED_FINANCIAL_APPS = {
        "com.google.android.apps.walletnfcrel",  # Google Pay
        "com.samsung.android.spay",               # Samsung Pay
        "com.paypal.android.p2pmobile",          # PayPal
        "com.venmo",                              # Venmo
        "com.zellepay.zelle",                     # Zelle
        "com.cashapp",                            # Cash App
        "com.squareup.cash",                      # Cash App (alt)
    }
    
    # Authenticator apps - BLOCKED for MVP (security reasons)
    BLOCKED_AUTH_APPS = {
        "com.google.android.apps.authenticator2", # Google Authenticator
        "com.authy.authy",                        # Authy
        "com.microsoft.msa",                      # MS Authenticator
        "com.lastpass.lpandroid",                 # LastPass
        "com.onepassword.android",                # 1Password
        "com.bitwarden.vault",                    # Bitwarden
    }
    
    # Banking app patterns (partial match) - BLOCKED for MVP
    BANKING_PATTERNS = [
        "bank", "chase", "wellsfargo", "citi", "bofa", "capitalone",
        "finance", "trading", "invest", "crypto", "wallet",
        "fidelity", "schwab", "robinhood", "coinbase", "binance",
        "etrade", "ameritrade", "vanguard",
    ]
    
    # Friendly denial message for financial apps
    FINANCIAL_DENIAL_MESSAGE = (
        "I'm not able to help with banking or payment apps for safety reasons. "
        "Please use those apps directly to protect your financial information."
    )
    
    # Actions requiring confirmation
    CONFIRMATION_ACTIONS = {
        "send_money",
        "transfer",
        "payment",
        "delete",
        "uninstall",
        "clear_data",
    }
    
    # Rate limits per minute
    RATE_LIMITS = {
        "default": 60,          # 60 actions/minute default
        "tap": 30,              # 30 taps/minute
        "send_message": 10,     # 10 messages/minute
        "open_app": 20,         # 20 app launches/minute
    }
    
    def __init__(self, policy_dir: Optional[Path] = None, opa_url: Optional[str] = None):
        """
        Initialize policy engine.
        
        Args:
            policy_dir: Directory containing .rego policy files
            opa_url: URL of OPA server (if using server mode)
        """
        self.policy_dir = policy_dir or Path(__file__).parent.parent / "policies"
        self.opa_url = opa_url
        self.opa_client = None
        self.policies_loaded = False
        self.action_history: List[Dict[str, Any]] = []
        self.enabled = True
        
        self._initialize_opa()
        logger.info(f"🛡️ Policy engine initialized (OPA available: {OPA_AVAILABLE})")
    
    def _initialize_opa(self):
        """Initialize OPA client or load policies."""
        if not OPA_AVAILABLE:
            logger.info("📋 Using built-in Python policy rules")
            return
        
        if self.opa_url:
            # Server mode
            try:
                self.opa_client = OpaClient(url=self.opa_url)
                self.policies_loaded = True
                logger.info(f"🔗 Connected to OPA server: {self.opa_url}")
            except Exception as e:
                logger.warning(f"⚠️ Failed to connect to OPA server: {e}")
        else:
            # Embedded mode - policies evaluated inline
            self.policies_loaded = self.policy_dir.exists()
            if self.policies_loaded:
                logger.info(f"📁 Policy directory: {self.policy_dir}")
            else:
                logger.info(f"📁 Creating policy directory: {self.policy_dir}")
                self.policy_dir.mkdir(parents=True, exist_ok=True)
    
    def enable(self):
        """Enable policy enforcement."""
        self.enabled = True
        logger.info("🛡️ Policy enforcement ENABLED")
    
    def disable(self):
        """Disable policy enforcement (for testing)."""
        self.enabled = False
        logger.warning("⚠️ Policy enforcement DISABLED")
    
    async def evaluate(self, context: ActionContext) -> PolicyDecision:
        """
        Evaluate an action against all policies.
        
        Args:
            context: Action context with all relevant information
            
        Returns:
            PolicyDecision indicating if action is allowed
        """
        if not self.enabled:
            return PolicyDecision(allowed=True, reason="Policy enforcement disabled")
        
        # Track action for rate limiting
        self._record_action(context)
        
        # Run policy checks
        checks = [
            self._check_blocked_actions(context),
            self._check_sensitive_apps(context),
            self._check_confirmation_required(context),
            self._check_rate_limits(context),
            self._check_dangerous_content(context),
        ]
        
        for check in checks:
            if not check.allowed:
                logger.warning(f"🚫 Policy violation: {check.reason}")
                return check
            if check.requires_confirmation:
                return check
        
        return PolicyDecision(allowed=True, reason="All policies passed")
    
    def _record_action(self, context: ActionContext):
        """Record action for rate limiting."""
        self.action_history.append({
            "action": context.action_type,
            "timestamp": context.timestamp,
            "app": context.package_name,
        })
        
        # Prune old entries (keep last 5 minutes)
        cutoff = time.time() - 300
        self.action_history = [a for a in self.action_history if a["timestamp"] > cutoff]
    
    def _check_blocked_actions(self, context: ActionContext) -> PolicyDecision:
        """Check if action is in blocklist."""
        if context.action_type.lower() in self.BLOCKED_ACTIONS:
            return PolicyDecision(
                allowed=False,
                reason=f"Action '{context.action_type}' is blocked for safety",
                policy_violated="safety.blocked_actions"
            )
        return PolicyDecision(allowed=True)
    
    def _check_sensitive_apps(self, context: ActionContext) -> PolicyDecision:
        """Check if target app is blocked (financial/auth apps)."""
        if not context.package_name:
            # Also check app_name for banking keywords
            if context.app_name:
                app_lower = context.app_name.lower()
                for pattern in self.BANKING_PATTERNS:
                    if pattern in app_lower:
                        return PolicyDecision(
                            allowed=False,
                            reason=self.FINANCIAL_DENIAL_MESSAGE,
                            policy_violated="apps.banking_blocked"
                        )
            return PolicyDecision(allowed=True)
        
        package = context.package_name.lower()
        
        # Check financial apps - BLOCKED
        if package in self.BLOCKED_FINANCIAL_APPS:
            return PolicyDecision(
                allowed=False,
                reason=self.FINANCIAL_DENIAL_MESSAGE,
                policy_violated="apps.financial_blocked"
            )
        
        # Check authenticator apps - BLOCKED
        if package in self.BLOCKED_AUTH_APPS:
            return PolicyDecision(
                allowed=False,
                reason="I can't help with authenticator or password manager apps for security reasons. Please use those apps directly.",
                policy_violated="apps.auth_blocked"
            )
        
        # Check banking patterns - BLOCKED
        for pattern in self.BANKING_PATTERNS:
            if pattern in package:
                return PolicyDecision(
                    allowed=False,
                    reason=self.FINANCIAL_DENIAL_MESSAGE,
                    policy_violated="apps.banking_blocked"
                )
        
        return PolicyDecision(allowed=True)
    
    def _check_confirmation_required(self, context: ActionContext) -> PolicyDecision:
        """Check if action requires user confirmation."""
        action = context.action_type.lower()
        
        for confirm_action in self.CONFIRMATION_ACTIONS:
            if confirm_action in action:
                return PolicyDecision(
                    allowed=True,
                    requires_confirmation=True,
                    confirmation_message=f"Action '{context.action_type}' requires confirmation. Continue?",
                    policy_violated="safety.confirmation_required"
                )
        
        return PolicyDecision(allowed=True)
    
    def _check_rate_limits(self, context: ActionContext) -> PolicyDecision:
        """Check rate limits for action type."""
        cutoff = time.time() - 60  # Last minute
        
        # Count actions of same type
        action_type = context.action_type.lower()
        recent_count = sum(
            1 for a in self.action_history 
            if a["timestamp"] > cutoff and a["action"].lower() == action_type
        )
        
        limit = self.RATE_LIMITS.get(action_type, self.RATE_LIMITS["default"])
        
        if recent_count >= limit:
            return PolicyDecision(
                allowed=False,
                reason=f"Rate limit exceeded: {recent_count}/{limit} {action_type} actions per minute",
                policy_violated="rate.rate_limit_exceeded"
            )
        
        return PolicyDecision(allowed=True)
    
    def _check_dangerous_content(self, context: ActionContext) -> PolicyDecision:
        """Check for dangerous content in text input."""
        if not context.text_content:
            return PolicyDecision(allowed=True)
        
        text = context.text_content.lower()
        
        # Block potential credential phishing
        dangerous_patterns = [
            "password is",
            "pin is",
            "ssn is",
            "social security",
            "credit card",
            "cvv",
        ]
        
        for pattern in dangerous_patterns:
            if pattern in text:
                return PolicyDecision(
                    allowed=False,
                    reason="Blocked: Text contains potentially sensitive information",
                    policy_violated="safety.sensitive_content"
                )
        
        return PolicyDecision(allowed=True)
    
    def get_action_stats(self) -> Dict[str, Any]:
        """Get action statistics for monitoring."""
        cutoff = time.time() - 60
        recent = [a for a in self.action_history if a["timestamp"] > cutoff]
        
        action_counts: Dict[str, int] = {}
        for action in recent:
            action_type = action["action"]
            action_counts[action_type] = action_counts.get(action_type, 0) + 1
        
        return {
            "total_actions_last_minute": len(recent),
            "action_counts": action_counts,
            "policies_loaded": self.policies_loaded,
            "enabled": self.enabled,
        }


# Global instance
_policy_engine: Optional[PolicyEngine] = None


def get_policy_engine() -> PolicyEngine:
    """Get global policy engine instance."""
    global _policy_engine
    if _policy_engine is None:
        _policy_engine = PolicyEngine()
    return _policy_engine
