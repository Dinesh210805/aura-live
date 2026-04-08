---
last_verified: 2026-04-08
source_files: [agents/responder.py]
status: current
---

# Agent: Responder

**File**: `agents/responder.py`

---

## Role

`ResponderAgent` generates the natural language text that AURA speaks back to the user after a task completes or fails. It is context-aware — the response changes based on what happened.

---

## Response Generation

The responder calls the LLM with:
- The `AURA_PERSONALITY` system prompt (AURA's voice/tone guidelines)
- Task outcome: success/failure/partial
- What was accomplished (executed steps summary)
- Any errors that occurred
- The original utterance

It returns a conversational `spoken_response` string that the TTS service then speaks.

---

## PANEL_ACTION_RESPONSES

Some Android actions (quick settings panel, notification shade, etc.) are restricted on Android 10+ and cannot be automated via accessibility services. For these, the responder uses pre-written responses from the `PANEL_ACTION_RESPONSES` dict rather than generating a new response.

Example entries:
- `"open_quick_settings"` → "I can guide you to swipe down from the top of your screen to open Quick Settings."
- `"open_notifications"` → "Swipe down from the top of your screen to see your notifications."

This prevents the LLM from claiming it executed an action it couldn't actually perform.

---

## TTS Delivery

The `speak` node (not the responder itself) handles TTS:
- `ANDROID_TTS_ENABLED=true` (default): sends JSON message over WebSocket
- `ANDROID_TTS_ENABLED=false`: synthesizes WAV with Edge-TTS server-side

The responder only produces text. TTS delivery is the `speak` node's responsibility.
