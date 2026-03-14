# Model Provider Comparison & Recommendations

**Date:** February 2026  
**Analysis:** Free Tier API Services (NVIDIA NIM, Groq, Gemini)

---

## Executive Summary

After analyzing all three providers, here are the **optimal model choices** for AURA agent system:

### 🏆 Recommended Architecture

| Task | Provider | Model | Reason |
|------|----------|-------|--------|
| **Intent Parsing** | Groq | `llama-3.3-70b-versatile` | 280 T/s, proven performance |
| **Vision/UI Analysis** | Gemini | `gemini-2.5-flash` | Best multimodal, 1M context |
| **Planning/Reasoning** | Gemini | `gemini-2.5-flash` | Superior reasoning, thinking mode |
| **Speech-to-Text** | Groq | `whisper-large-v3-turbo` | Faster, proven performance |
| **Fallback Vision** | NVIDIA NIM | `meta/llama-4-maverick-17b-128e` | 1200 T/s vision support |
| **Code Tasks** | Groq | `openai/gpt-oss-20b` | 1000 T/s, specialized for code |

---

## 1. GROQ Models (Currently Using ✅)

### Free Tier Limits
- **Rate Limits:** 1K RPM, 250K-300K TPM
- **Price:** $0 (Free tier)
- **No credit card required**

### Available Models

#### 🔥 Production Models (Recommended)

| Model | Speed | Context | Max Output | Best For |
|-------|-------|---------|------------|----------|
| `llama-3.1-8b-instant` | 560 T/s | 131K | 131K | Ultra-fast simple tasks |
| `llama-3.3-70b-versatile` | 280 T/s | 131K | 32K | **Current choice - perfect** |
| `openai/gpt-oss-120b` | 500 T/s | 131K | 65K | Complex reasoning |
| `openai/gpt-oss-20b` | 1000 T/s | 131K | 65K | **Code generation** |
| `whisper-large-v3-turbo` | - | - | - | **STT - Current choice** |

#### 🧪 Preview Models (Experimental)

| Model | Speed | Context | Vision | Notes |
|-------|-------|---------|--------|-------|
| `meta-llama/llama-4-maverick-17b-128e` | 600 T/s | 131K | ✅ 20MB | **Vision fallback option** |
| `meta-llama/llama-4-scout-17b-16e` | 750 T/s | 131K | ✅ 20MB | Faster, lighter vision |

#### Systems (Agentic)
- `groq/compound` - 450 T/s with tools
- `groq/compound-mini` - 450 T/s lighter version

### ✅ Keep Using Groq For:
- Intent parsing (current: `llama-3.3-70b-versatile`)
- Speech-to-Text (`whisper-large-v3-turbo`)
- Fast text generation tasks

---

## 2. GEMINI Models (Currently Using ✅)

### Free Tier Limits
- **Rate Limits:** 15 RPM, 1M TPM (free), 4M TPM (paid)
- **Context:** Up to 1M tokens
- **Price:** $0 (Free tier generous)

### Available Models

#### 🚀 Latest Generation (2.5 & 3.0)

| Model | Context | Output | Capabilities | Best For |
|-------|---------|--------|--------------|----------|
| `gemini-2.5-flash` | 1M | 65K | Multimodal, Thinking, Tools | **Current choice - perfect** |
| `gemini-2.5-flash-lite` | 1M | 65K | Ultra-fast, cost-efficient | High-volume tasks |
| `gemini-2.5-pro` | 1M | 65K | Advanced thinking, STEM | Complex reasoning |
| `gemini-3-flash-preview` | 1M | 65K | Next-gen, faster | Worth testing |
| `gemini-3-pro-preview` | 1M | 65K | Most intelligent | Premium tasks |

#### 🎨 Specialized Models
- `gemini-2.5-flash-image` - Image generation
- `gemini-2.5-flash-native-audio-preview` - Live audio/video (131K context)
- `gemini-2.5-flash-preview-tts` - Text-to-speech

### ✅ Keep Using Gemini For:
- Vision/UI analysis (`gemini-2.5-flash`)
- Planning/reasoning (`gemini-2.5-flash`)
- Multimodal tasks requiring image+text understanding

### 🆕 Consider Upgrading To:
- `gemini-3-flash-preview` - Faster, newer
- `gemini-2.5-pro` - Complex STEM/math reasoning

---

## 3. NVIDIA NIM (NEW Discovery 🆕)

### Free Tier Limits
- **Rate Limits:** Varies by model (typically 30 RPM)
- **Price:** $0 (Free tier available)
- **Credits:** 1,000 free credits/month

### Notable Models

#### 🔥 Best Performance Models

| Model | Provider | Context | Notes |
|-------|----------|---------|-------|
| `meta/llama-4-maverick-17b-128e` | Meta | 131K | **Vision support, 1200 T/s** |
| `mistralai/mistral-large-2-instruct` | Mistral | - | Strong reasoning |
| `nvidia/nemotron-4-340b-instruct` | NVIDIA | - | Massive model |
| `deepseek-ai/deepseek-r1` | DeepSeek | - | Advanced reasoning |

#### 💻 Code Specialists
- `bigcode/starcoder2-15b` - Code completion
- `mistralai/codestral-22b-instruct-v0.1` - Code generation
- `google/codegemma-1.1-7b` - Google's code model

#### 🎯 Multimodal Options
Multiple models support vision tasks, including Llama 4 variants

### ⚠️ NVIDIA NIM Limitations
- Lower rate limits (30 RPM typical)
- Requires credit management
- More complex authentication
- Less documentation vs Groq/Gemini

### 🤔 Should You Use NVIDIA NIM?

**YES, as fallback only:**
- Third-tier fallback for vision (`llama-4-maverick-17b-128e`)
- Specialized code generation tasks
- When both Groq & Gemini fail

**NO, as primary:**
- Lower rate limits than Groq
- More complex setup
- Gemini already provides superior vision
- Groq provides faster text generation

---

## 🎯 Recommended Implementation Plan

### Current Setup (Keep This)
```python
# LLM (Text)
default_llm_provider = "groq"
default_llm_model = "llama-3.3-70b-versatile"

# Vision
default_vlm_provider = "gemini"
default_vlm_model = "gemini-2.5-flash"

# Planning
planning_provider = "gemini"
planning_model = "gemini-2.5-flash"

# STT
default_stt_provider = "groq"
default_stt_model = "whisper-large-v3-turbo"
```

### 🆕 Proposed Enhancements

#### 1. Add NVIDIA NIM as Third-Tier Fallback
```python
# config/settings.py
nvidia_nim_api_key: Optional[str] = Field(
    default=None,
    env="NVIDIA_NIM_API_KEY",
    description="NVIDIA NIM API key for third-tier fallback"
)

# Fallback chain for vision:
# 1. Gemini 2.5 Flash (primary)
# 2. Groq Llama 4 Maverick (secondary)
# 3. NVIDIA NIM Llama 4 Maverick (tertiary)
```

#### 2. Add Fast Code Generation Path
```python
# For code generation specifically
code_generation_provider = "groq"
code_generation_model = "openai/gpt-oss-20b"  # 1000 T/s
```

#### 3. Upgrade Gemini Models (Optional)
```python
# Test newer models
planning_model = "gemini-3-flash-preview"  # Faster, newer
advanced_reasoning_model = "gemini-2.5-pro"  # For complex tasks
```

---

## 📊 Speed Comparison

| Model | Provider | Speed (T/s) | Task Type |
|-------|----------|-------------|-----------|
| `openai/gpt-oss-20b` | Groq | **1000** | Code |
| `llama-4-scout-17b-16e` | Groq | 750 | Vision (light) |
| `llama-4-maverick-17b-128e` | Groq/NVIDIA | 600 | Vision |
| `llama-3.1-8b-instant` | Groq | 560 | Text |
| `openai/gpt-oss-120b` | Groq | 500 | Reasoning |
| `llama-3.3-70b-versatile` | Groq | 280 | Text |
| `gemini-2.5-flash` | Gemini | N/A* | Multimodal |
| `gemini-3-flash-preview` | Gemini | N/A* | Multimodal |

*Gemini doesn't publish T/s but is optimized for latency

---

## 💰 Cost Analysis (Free Tier)

### Groq
- ✅ Highest rate limits (1K RPM)
- ✅ No credit card required
- ✅ Production-ready models
- ❌ Limited vision support (preview only)

### Gemini
- ✅ Best multimodal capabilities
- ✅ 1M token context window
- ✅ Generous free tier
- ⚠️ Lower RPM (15) but high TPM

### NVIDIA NIM
- ✅ Unique models (Nemotron, DeepSeek)
- ⚠️ Credit-based (1K credits/month)
- ⚠️ Lower rate limits (30 RPM typical)
- ❌ More complex setup

---

## 🎬 Action Items

### Immediate (No Changes Needed)
Your current setup is **optimal** for production:
- ✅ Groq for fast text (intent parsing)
- ✅ Gemini for vision/reasoning
- ✅ Groq for STT

### Short-Term (Worth Testing)
1. **Test Groq's Llama 4 Maverick** as vision fallback
   - 600 T/s with 20MB image support
   - Keep Gemini as primary, Groq Llama 4 as secondary

2. **Add NVIDIA NIM** as tertiary fallback
   - Only triggers if both Groq and Gemini fail
   - Provides additional redundancy

3. **Test `openai/gpt-oss-20b`** for code generation
   - 1000 T/s specifically for code tasks
   - Use when generating tool execution code

### Long-Term (Optional Upgrades)
1. **Upgrade to Gemini 3 Flash** when stable
   - Next-gen capabilities
   - Better performance

2. **Test Gemini 2.5 Pro** for complex reasoning
   - Advanced STEM/math tasks
   - Deep code analysis

3. **Monitor Groq's new models**
   - They're rapidly adding capabilities
   - Watch for production-ready vision models

---

## 🔐 API Key Setup

```bash
# .env file additions
NVIDIA_NIM_API_KEY=nvapi-xxx  # Optional, for fallback

# Verify existing keys still work
GROQ_API_KEY=gsk_xxx
GEMINI_API_KEY=AIza_xxx
```

---

## 🧪 Testing Recommendations

### Phase 1: Verify Current Setup
```python
# Test current providers work well
pytest tests/test_providers.py -v
```

### Phase 2: Add Vision Fallback
```python
# Test Groq Llama 4 Maverick vision
# Compare quality vs Gemini 2.5 Flash
```

### Phase 3: Add NVIDIA Tertiary
```python
# Only add if you need extra redundancy
# Monitor rate limits carefully
```

---

## 📝 Conclusion

### Your Current Setup: ⭐⭐⭐⭐⭐ (5/5)
You're already using the **best models** from each provider:
- **Groq `llama-3.3-70b-versatile`** - Perfect for intent parsing
- **Gemini `gemini-2.5-flash`** - Best for vision/reasoning
- **Groq `whisper-large-v3-turbo`** - Optimal for STT

### NVIDIA NIM Value: ⭐⭐⭐ (3/5)
- **Good as:** Tertiary fallback, specialized tasks
- **Not ideal as:** Primary provider (rate limits, complexity)
- **Best use:** Add for redundancy, not replacement

### Final Recommendation: 
**Keep your current setup, optionally add NVIDIA NIM as safety net.**

Your hybrid Groq + Gemini architecture is already optimal for free-tier performance.
