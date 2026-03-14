# AURA Rate Limiting Policy
# Prevents runaway automation loops

package aura.rate

import future.keywords.if
import future.keywords.in

default allow := true

# Rate limits per action type (actions per minute)
rate_limits := {
    "tap": 30,
    "swipe": 30,
    "type": 20,
    "send_message": 10,
    "open_app": 20,
    "call": 5,
    "delete": 5,
    "default": 60,
}

# Get limit for action type
get_limit(action_type) := limit if {
    limit := rate_limits[action_type]
} else := rate_limits.default

# Check rate limit exceeded
deny[msg] if {
    limit := get_limit(input.action_type)
    input.action_count_last_minute >= limit
    msg := sprintf("Rate limit exceeded: %d/%d %s actions per minute", 
                   [input.action_count_last_minute, limit, input.action_type])
}

# Allow if under rate limit
allow if {
    limit := get_limit(input.action_type)
    input.action_count_last_minute < limit
}

# Burst detection - too many actions too fast
deny[msg] if {
    count(input.previous_actions) > 10
    time_window := 5  # seconds
    msg := "Burst detected: Too many actions in short time window"
}
