# Sensitive Action Blocking System

## Overview

Aura now blocks dangerous/sensitive operations automatically to protect your device and data.

## Blocked Action Categories

### 🏦 Banking & Finance
- Opening banking apps (Chase, Bank of America, PayPal, etc.)
- Payment apps (Venmo, Google Pay, PhonePe, etc.)
- Cryptocurrency apps (Coinbase, Binance, etc.)
- Password managers (LastPass, 1Password, etc.)

**Examples:**
- ❌ "Open Bank of America"
- ❌ "Launch PayPal"
- ❌ "Transfer money via Google Pay"

### ⚠️ System Shutdown/Reset
- Shutting down device
- Restarting phone
- Factory reset
- Hard reset

**Examples:**
- ❌ "Shutdown my phone"
- ❌ "Restart the device"
- ❌ "Factory reset"

### 🗑️ Destructive Operations
- Deleting files
- Removing apps
- Clearing data
- Uninstalling packages

**Examples:**
- ❌ "Delete all my photos"
- ❌ "Uninstall WhatsApp"
- ❌ "Clear app data"

### 🔐 Security Modifications
- Disabling security features
- Removing locks/passwords
- Disabling fingerprint/face unlock

**Examples:**
- ❌ "Turn off password protection"
- ❌ "Disable fingerprint lock"
- ❌ "Remove PIN"

### 🔓 Permission Changes
- Granting all permissions
- Enabling unknown sources
- Developer mode activation

**Examples:**
- ❌ "Grant all permissions"
- ❌ "Enable developer mode"

## User Experience

When a blocked command is detected:

1. **Immediate block** - Action never executes
2. **Clear message** - User gets explanation why
3. **Safe alternative** - Suggested manual approach

**Example Response:**
```
User: "Open Bank of America app"
Aura: "I cannot access banking or financial apps for your 
      security. Please handle financial transactions manually 
      on your device."
```

## API Endpoints

### Check if Command is Sensitive
```bash
POST /api/v1/sensitive-policy/check
{
    "command": "shutdown my phone"
}

Response:
{
    "is_sensitive": true,
    "reason": "system_shutdown",
    "message": "I cannot perform system shutdown...",
    "would_block": true
}
```

### Get Policy Statistics
```bash
GET /api/v1/sensitive-policy/stats

Response:
{
    "enabled": true,
    "blocked_count": 5,
    "categories": {
        "banking": 25,
        "shutdown": 7,
        "destructive": 10,
        ...
    }
}
```

### Add Custom Keyword
```bash
POST /api/v1/sensitive-policy/keywords/add
{
    "category": "banking",
    "keyword": "my custom bank"
}
```

### Toggle Policy On/Off
```bash
POST /api/v1/sensitive-policy/toggle?enabled=false
```

### List All Keywords
```bash
GET /api/v1/sensitive-policy/keywords
```

## Customization

### Add Your Own Bank/App
```python
from policies.sensitive_actions import sensitive_action_policy

# Add custom banking app
sensitive_action_policy.add_custom_keyword("banking", "my local bank")

# Add sensitive app
sensitive_action_policy.add_custom_keyword("apps", "my password vault")
```

### Disable Protection (Testing Only)
```python
from policies.sensitive_actions import sensitive_action_policy

# Disable for testing
sensitive_action_policy.enabled = False

# Re-enable
sensitive_action_policy.enabled = True
```

## Testing Commands

Test these commands to verify blocking works:

```bash
# Should be blocked
curl -X POST http://localhost:8000/api/v1/tasks/execute \
  -H "Content-Type: application/json" \
  -d '{"input_type": "text", "text_input": "open paypal"}'

# Should work normally
curl -X POST http://localhost:8000/api/v1/tasks/execute \
  -H "Content-Type: application/json" \
  -d '{"input_type": "text", "text_input": "open youtube"}'
```

## Monitoring

View blocked attempts:
```bash
# Terminal logs show:
🚫 Blocked sensitive command: open paypal (reason: sensitive_app_access)

# Debug dashboard:
http://localhost:8000/api/v1/debug/unified-logs/export/html

# Policy stats:
http://localhost:8000/api/v1/sensitive-policy/stats
```

## Architecture

```
User Command → Intent Parsing → Sensitive Check → Block/Continue
                                       ↓
                                  If Sensitive:
                                  - Block execution
                                  - Return error message
                                  - Log blocked attempt
```

## Safety Notes

- **Never disabled in production** - Keep policy enabled
- **No bypass mechanism** - Intentionally hard to override
- **Audit trail** - All blocks are logged
- **User education** - Clear messages explain why

## Future Enhancements

- [ ] User-specific whitelists
- [ ] Time-based restrictions
- [ ] Biometric confirmation for sensitive apps
- [ ] Rate limiting on blocked attempts
- [ ] Admin override with 2FA
