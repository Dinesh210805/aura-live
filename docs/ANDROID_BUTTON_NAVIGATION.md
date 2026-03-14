# Android Button Navigation Implementation Guide

## Critical Issue Fixed

**Problem:** System was using swipe gestures for back navigation, which is unreliable and inconsistent.

**Solution:** Use Android keyevents (hardware button simulation) for navigation buttons.

## Proper Android Button Commands

### Back Button
```python
from services.gesture_builder import build_back_button

# Correct way - uses keyevent 4 (KEYCODE_BACK)
back_command = build_back_button()
```

**Android Implementation Required:**
```java
// Method 1: Shell command (recommended)
Runtime.getRuntime().exec("input keyevent 4");

// Method 2: Instrumentation (if available)
getInstrumentation().sendKeyDownUpSync(KeyEvent.KEYCODE_BACK);

// Method 3: Accessibility Service
performGlobalAction(AccessibilityService.GLOBAL_ACTION_BACK);
```

### Home Button
```python
from services.gesture_builder import build_home_button

# Correct way - uses keyevent 3 (KEYCODE_HOME)
home_command = build_home_button()
```

**Android Implementation Required:**
```java
// Method 1: Shell command
Runtime.getRuntime().exec("input keyevent 3");

// Method 2: Accessibility Service
performGlobalAction(AccessibilityService.GLOBAL_ACTION_HOME);
```

### Recent Apps Button
```python
from services.gesture_builder import build_recent_apps_button

# Uses AccessibilityService.GLOBAL_ACTION_RECENTS
recent_command = build_recent_apps_button()
```

**Android Implementation Required:**
```java
performGlobalAction(AccessibilityService.GLOBAL_ACTION_RECENTS);
```

## Android Keycodes Reference

| Button | Keycode | Constant | Command |
|--------|---------|----------|---------|
| Back | 4 | KEYCODE_BACK | `input keyevent 4` |
| Home | 3 | KEYCODE_HOME | `input keyevent 3` |
| Menu | 82 | KEYCODE_MENU | `input keyevent 82` |
| Power | 26 | KEYCODE_POWER | `input keyevent 26` |
| Volume Up | 24 | KEYCODE_VOLUME_UP | `input keyevent 24` |
| Volume Down | 25 | KEYCODE_VOLUME_DOWN | `input keyevent 25` |

## WebSocket Payload Format

When backend sends navigation command:

```json
{
  "type": "execute_gesture",
  "gesture": {
    "command_id": "cmd_back_1234567890",
    "gesture_type": "system_action",
    "action": "back",
    "method": "keyevent",
    "keycode": 4,
    "timestamp": 1234567890.123
  }
}
```

## Android Side Implementation (Pseudo-code)

```kotlin
// In your AccessibilityService WebSocket handler:

fun handleGestureCommand(gesture: JsonObject) {
    val action = gesture.getString("action")
    val method = gesture.getString("method", "")
    
    when (action) {
        "back" -> {
            if (method == "keyevent") {
                val keycode = gesture.getInt("keycode", 4)
                executeKeyEvent(keycode)
            } else {
                // Fallback to global action
                performGlobalAction(GLOBAL_ACTION_BACK)
            }
        }
        
        "home" -> {
            if (method == "keyevent") {
                val keycode = gesture.getInt("keycode", 3)
                executeKeyEvent(keycode)
            } else {
                performGlobalAction(GLOBAL_ACTION_HOME)
            }
        }
        
        "recent_apps" -> {
            performGlobalAction(GLOBAL_ACTION_RECENTS)
        }
    }
}

fun executeKeyEvent(keycode: Int) {
    // Method 1: Shell command (most reliable)
    try {
        Runtime.getRuntime().exec("input keyevent $keycode")
        Log.d("AURA", "Executed keyevent $keycode")
    } catch (e: Exception) {
        Log.e("AURA", "Failed to execute keyevent", e)
    }
}
```

## Why Keyevents > Swipe Gestures

| Aspect | Keyevent | Swipe Gesture |
|--------|----------|---------------|
| **Reliability** | ✅ Always works | ❌ Depends on screen position |
| **Speed** | ✅ Instant | ❌ Animation delay |
| **Compatibility** | ✅ Works everywhere | ❌ Blocked by some apps |
| **Intent** | ✅ Clear navigation | ❌ Ambiguous |
| **System Recognition** | ✅ Registered as button press | ❌ Just a touch event |

## Common Mistakes to Avoid

### ❌ Wrong: Using Swipe for Back
```python
# DON'T DO THIS
back_gesture = build_swipe(0.1, 0.5, 0.9, 0.5)  # Swipe right
```

**Problems:**
- Only works on screens with gesture navigation enabled
- Position-dependent
- Can accidentally trigger UI elements
- Not recognized as "back" by system

### ✅ Correct: Using Keyevent for Back
```python
# DO THIS INSTEAD
back_command = build_back_button()  # Keyevent 4
```

**Benefits:**
- Works on ALL Android devices
- Works with 3-button navigation
- Works with gesture navigation
- Recognized as proper back action by system

## Testing

Test all navigation buttons:

```python
from services.gesture_builder import (
    build_back_button,
    build_home_button,
    build_recent_apps_button
)
from services.real_device_executor import real_device_executor

async def test_navigation():
    # Test back button
    await real_device_executor.execute_gesture(build_back_button())
    await asyncio.sleep(1)
    
    # Test home button
    await real_device_executor.execute_gesture(build_home_button())
    await asyncio.sleep(1)
    
    # Test recent apps
    await real_device_executor.execute_gesture(build_recent_apps_button())
```

## Android App Update Checklist

To implement this fix on the Android side:

- [ ] Update `GestureHandler.java` or equivalent to recognize `method: "keyevent"`
- [ ] Add `executeKeyEvent(int keycode)` function using `Runtime.exec()`
- [ ] Update WebSocket gesture handler to check for `keycode` parameter
- [ ] Add fallback to `performGlobalAction()` if shell command fails
- [ ] Test on devices with 3-button navigation
- [ ] Test on devices with gesture navigation
- [ ] Add logging for successful keyevent execution
- [ ] Handle permissions (SYSTEM_ALERT_WINDOW if needed)

## Debugging

Enable verbose logging:

```python
import logging
logging.getLogger("services.gesture_builder").setLevel(logging.DEBUG)
logging.getLogger("services.real_accessibility").setLevel(logging.DEBUG)
```

Check logs for:
- `Built BACK button press (keyevent 4)`
- `⚡ Sending gesture via WebSocket: back, command_id=xyz`
- `✅ Gesture acknowledged: command_id=xyz`

On Android side, check for:
- `Received gesture command: back`
- `Executing keyevent 4`
- `Keyevent executed successfully`
