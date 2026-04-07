# VLM Service

**File:** `services/vlm.py`

---

## Overview

`VLMService` provides vision-language model inference for the Set-of-Marks (SoM) element selection step in the perception pipeline. It supports four providers: **Groq** (primary), **Gemini**, **NVIDIA NIM**, and **OpenRouter**.

---

## Initialization

```python
VLMService.__init__(settings: Settings)
```
Initializes clients for all configured providers. `_build_provider_models()` maps each provider to its appropriate model strings:
- **Primary model**: `settings.default_vlm_model` — used for the initial selection attempt
- **Fallback model**: `settings.fallback_vlm_model` — used when primary fails

---

## Provider Model Mapping (`_build_provider_models`)
Each provider uses different model identifiers. This method centralizes the mapping so the pipeline doesn't need to know which provider is active — it just calls `select()` or `select_with_fallback()`.

---

## 429 Retry Policy
Same config as `LLMService`:
```python
_GEMINI_MAX_RETRIES = 3
_GEMINI_BASE_DELAY = 2.0
_GEMINI_MAX_DELAY = 60.0
```
Rate-limit errors from Gemini Vision API trigger the same exponential backoff with `retryDelay` parsing.

---

## SoM Integration

### How selection works
1. Annotated screenshot with numbered labels (A, B, C…) is passed as image content
2. VLM receives the image + target description prompt
3. VLM responds with a single letter identifying the target element
4. Letter is mapped back to the corresponding `Detection` object's bounding box center

### The SoM Invariant
> **VLM never returns pixel coordinates.** It only selects among pre-labeled elements. All coordinates come from bounding box centers of CV-detected elements.

This invariant is enforced in `_try_cv_vlm()` in the perception pipeline — if the VLM response cannot be parsed as a valid label letter, the result is treated as a failure and falls through to heuristic selection.

---

## `select_with_fallback()`
The main entry point called by `perception_pipeline.py`:
1. Attempts selection with primary provider/model
2. On failure (timeout, error, invalid response): tries fallback provider/model
3. Returns `Optional[str]` — the selected label letter, or `None` on complete failure

This is the call that runs inside `ThreadPoolExecutor` for timeout enforcement (see `wiki/perception/pipeline.md`).

---

## Integration Points
- Called exclusively from `perception/perception_pipeline.py:_try_cv_vlm()`
- Provider controlled by `settings.default_vlm_provider` (should be `"gemini"` for hackathon)
- Model controlled by `settings.default_vlm_model` and `settings.fallback_vlm_model`
