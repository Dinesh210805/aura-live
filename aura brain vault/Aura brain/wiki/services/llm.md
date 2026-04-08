---
last_verified: 2026-04-08
source_files: [services/llm.py]
status: current
---

# LLM Service

**File:** `services/llm.py` (596 lines)

---

## Overview

`LLMService` provides a unified `run()` interface over three LLM providers: **Groq** (primary), **Gemini** (fallback), and **NVIDIA NIM** (optional). All agents call this service — never the provider SDKs directly.

---

## Initialization

```python
LLMService.__init__(settings: Settings)
```
Initializes clients for all three providers at startup. Provider availability is determined by which API keys are present in `settings`.

---

## `run()` Signature

```python
async def run(
    prompt: str,
    provider: Optional[str] = None,      # "groq" | "gemini" | "nvidia"; defaults to settings.default_llm_provider
    model: Optional[str] = None,          # overrides provider default
    caller_agent: Optional[str] = None,   # G11 fix: for per-agent token attribution
    system_prompt: Optional[str] = None,  # G15 fix: custom system prompt injection
    **kwargs                              # passed to provider call (temperature, max_tokens, etc.)
) -> str
```

---

## Per-Provider Implementation

### Groq (`_call_groq`)
- Pops internal kwargs `_caller_agent`, `_system_prompt` before passing to API
- If `system_prompt` is set: prepends `{"role": "system", "content": system_prompt}` to messages list
- Calls `groq_client.chat.completions.create()`
- Fastest provider: 560–750 tokens/second

### Gemini (`_call_gemini`)
- Sets `thinking_budget=0` via `ThinkingConfig` — **always disables CoT** to reduce latency
- If `system_prompt` is set: passed as `system_instruction` in `GenerateContentConfig`
- **429 Retry loop**: exponential backoff with `_extract_gemini_retry_delay()`:
  - Parses `retryDelay` field from the error response (e.g., `"retryDelay": "30s"`)
  - Falls back to `base_delay * (2 ** attempt)`, capped at `_GEMINI_MAX_DELAY=60.0`
  - Up to `_GEMINI_MAX_RETRIES=3` attempts
- Filters out `thought=True` parts from response (Gemini sometimes returns reasoning fragments)

### NVIDIA NIM (`_call_nvidia`)
- Routes to `call_nvidia_chat()` or `call_nvidia_reasoning()` based on `thinking` kwarg
- Optional — only active when `nvidia_api_key` is set

---

## Model Normalization (`_normalize_model_for_provider`)
Prevents model/provider mismatch from environment variable overrides. For example, if `DEFAULT_LLM_MODEL=llama-3.3-70b` but provider is forced to `"gemini"`, the normalizer substitutes the appropriate Gemini model. Catches the common mistake of accidentally running a Groq model string against the Gemini API.

---

## G11 Fix — Per-Agent Token Attribution
The `caller_agent` parameter was added so `token_tracker.track(tokens, agent=caller_agent)` records which agent consumed which tokens. Previously, all LLM calls were attributed to a generic bucket. Now you can see "coordinator consumed 45k tokens, verifier consumed 8k" in observability logs.

---

## G15 Fix — Custom System Prompt
The `system_prompt` parameter enables the verifier agent to inject `PromptMode.MINIMAL` as the system instruction rather than the default AURA agent prompt. This keeps verifier responses compact (verification pass/fail) rather than verbose.

---

## Integration Points
- All agents import `from services.llm import LLMService` (injected via `AppModule`)
- `TokenTracker` is called inside `run()` after every successful response
- `config/settings.py` controls `default_llm_provider`, `default_llm_model`, `groq_api_key`, `gemini_api_key`
