# AURA Safety Policy
# Blocks dangerous actions and requires confirmation for high-risk operations

package aura.safety

import future.keywords.if
import future.keywords.in

# Default deny
default allow := false

# Block dangerous actions unconditionally
blocked_actions := {
    "factory_reset",
    "wipe_data",
    "delete_all",
    "format_storage",
    "root_device",
    "install_unknown_apk",
    "disable_security",
    "grant_root",
}

# Actions requiring user confirmation
confirmation_required := {
    "send_money",
    "transfer",
    "payment",
    "delete",
    "uninstall",
    "clear_data",
    "remove_account",
}

# Allow if action is not blocked
allow if {
    not input.action_type in blocked_actions
}

# Check if action is blocked
deny[msg] if {
    input.action_type in blocked_actions
    msg := sprintf("Action '%s' is blocked for safety", [input.action_type])
}

# Check if confirmation needed
needs_confirmation[msg] if {
    some action in confirmation_required
    contains(input.action_type, action)
    msg := sprintf("Action '%s' requires user confirmation", [input.action_type])
}

# Dangerous text patterns
sensitive_patterns := [
    "password is",
    "pin is",
    "ssn is",
    "social security",
    "credit card number",
    "cvv is",
]

# Block sensitive content in text
deny[msg] if {
    input.text_content != null
    some pattern in sensitive_patterns
    contains(lower(input.text_content), pattern)
    msg := "Text contains potentially sensitive information"
}
