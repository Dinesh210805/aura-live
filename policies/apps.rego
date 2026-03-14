# AURA App Policy
# Controls access to sensitive applications
# MVP: Banking and financial apps are BLOCKED (not just confirmation)

package aura.apps

import future.keywords.if
import future.keywords.in

default allow := true

# Financial/Payment apps - BLOCKED for MVP
blocked_financial_apps := {
    "com.google.android.apps.walletnfcrel",   # Google Pay
    "com.samsung.android.spay",                # Samsung Pay
    "com.paypal.android.p2pmobile",           # PayPal
    "com.venmo",                               # Venmo
    "com.zellepay.zelle",                      # Zelle
    "com.cashapp",                             # Cash App
    "com.squareup.cash",                       # Cash App (alt)
}

# Authenticator apps - BLOCKED for MVP
blocked_auth_apps := {
    "com.google.android.apps.authenticator2", # Google Authenticator
    "com.authy.authy",                         # Authy
    "com.microsoft.msa",                       # MS Authenticator
    "com.lastpass.lpandroid",                  # LastPass
    "com.onepassword.android",                 # 1Password
    "com.bitwarden.vault",                     # Bitwarden
}

# Banking app patterns - BLOCKED for MVP
banking_patterns := [
    "bank",
    "chase",
    "wellsfargo",
    "citi",
    "bofa",
    "capitalone",
    "finance",
    "trading",
    "invest",
    "crypto",
    "wallet",
    "fidelity",
    "schwab",
    "robinhood",
    "coinbase",
    "binance",
    "etrade",
    "ameritrade",
    "vanguard",
]

# Friendly denial message
financial_denial := "I'm not able to help with banking or payment apps for safety reasons. Please use those apps directly."
auth_denial := "I can't help with authenticator or password manager apps for security reasons."

# Block financial apps
deny[msg] if {
    input.package_name in blocked_financial_apps
    msg := financial_denial
}

# Block auth apps  
deny[msg] if {
    input.package_name in blocked_auth_apps
    msg := auth_denial
}

# Block apps matching banking patterns
is_banking_app if {
    some pattern in banking_patterns
    contains(lower(input.package_name), pattern)
}

deny[msg] if {
    is_banking_app
    msg := financial_denial
}

# Also check app_name for banking keywords
deny[msg] if {
    input.app_name != null
    some pattern in banking_patterns
    contains(lower(input.app_name), pattern)
    msg := financial_denial
}

# Allow apps that pass all checks
allow if {
    not input.package_name in blocked_financial_apps
    not input.package_name in blocked_auth_apps
    not is_banking_app
}
