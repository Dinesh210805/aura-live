# Agent: Commander

**File**: `agents/commander.py`

---

## Role

`CommanderAgent` parses the user's transcript into a structured intent dict. It uses a **rule-based classifier first**, falling back to LLM only when rules fail.

---

## Intent Output

The commander produces a dict like:
```python
{
    "action": "open_app",
    "target": "Spotify",
    "parameters": {},
    "confidence": 0.95,
    "intent_type": "simple",      # conversational / simple / medium / complex
    "requires_device": True,
    "raw_utterance": "Open Spotify"
}
```

---

## Parsing Pipeline

```
Transcript
    │
    ▼ Rule-based classifier (get_rule_classifier())
    │   Pattern matching on common commands
    │   Returns intent if confidence ≥ threshold
    │
    ├── High confidence → return directly (no LLM call)
    │
    └── Low confidence or unknown
            │
            ▼ LLM fallback (_parse_direct())
            │   Sends INTENT_PARSING_PROMPT or
            │   INTENT_PARSING_PROMPT_WITH_CONTEXT (if history)
            │   JSON response, strips markdown fences
            │
            └── Returns parsed intent dict
```

---

## Token Attribution (G11 Fix)

All LLM calls through Commander are attributed to `"commander"` as the caller agent. This feeds into `TokenTracker` so per-agent token costs are visible in observability dashboards.

Previously, only coordinator and reactive calls tracked tokens.

---

## Conversation Context

When `ConversationManager` has prior turns (up to 5), the commander uses `INTENT_PARSING_PROMPT_WITH_CONTEXT` which includes the recent conversation history. This enables pronouns and references: "now open its settings" correctly resolves "its" to the previously mentioned app.

---

## Intent Classification Tiers

From `utils/fuzzy_classifier.py` (used before Commander):

| Tier | Example | Routing |
|------|---------|---------|
| `conversational` | "What time is it?" | Direct to speak (no device) |
| `simple` | "Open Chrome" | Coordinator (single action) |
| `medium` | "Open Spotify and play liked songs" | Coordinator (2-3 actions) |
| `complex` | "Find me a restaurant and make a reservation" | Coordinator (multi-step) |

The fuzzy classifier uses Groq Llama 3.1 8B Instant (560 tps) for its speed. Gemini 1.5 Flash is the fallback, and rule-based pattern matching is the last resort.
