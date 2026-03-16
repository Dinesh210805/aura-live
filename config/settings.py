"""
AURA Backend Configuration Settings.

This module provides centralized configuration management using Pydantic for
validating and loading environment variables.
"""

from typing import List, Literal, Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Centralized configuration settings for the AURA backend.

    This class loads and validates all environment variables needed for the
    application, including API keys, model configurations, and server settings.

    TRI-PROVIDER MODEL ARCHITECTURE:
    - Intent Parsing: Groq Llama 3.1 8B Instant (560 tps, fast classification)
    - UI Analysis/Vision: Groq Llama 4 Scout 17B (750 tps, primary), Gemini 2.5 Flash (fallback)
    - Planning/Reasoning: Groq Llama 4 Maverick 17B (multimodal, 128 experts), Gemini fallback
    - Response Generation: Groq Llama 3.3 70B
    - STT: Groq Whisper Large v3 Turbo (faster than v3)
    - TTS: Edge-TTS (local Microsoft library, no API key)
    - Safety Guard: Llama Prompt Guard 2 86M (specialized)
    
    FALLBACK STRATEGY:
    - Groq models → Gemini 2.5 Flash fallback
    - Vision: Scout 17B → Maverick 17B → Gemini 2.5 Flash
    """

    # API Keys
    groq_api_key: str = Field(
        ..., env="GROQ_API_KEY", description="Groq API key for LLM and STT services"
    )
    gemini_api_key: str = Field(
        ..., env="GEMINI_API_KEY", description="Google Gemini API key for VLM services"
    )
    openrouter_api_key: Optional[str] = Field(
        default=None,
        env="OPENROUTER_API_KEY",
        description="OpenRouter API key for intent classification (optional, falls back to patterns)"
    )
    nvidia_api_key: Optional[str] = Field(
        default=None,
        env="NVIDIA_API_KEY",
        description="NVIDIA NIM API key for vision and planning models",
    )

    # LangSmith Observability
    langchain_tracing_v2: bool = Field(
        default=True,
        env="LANGCHAIN_TRACING_V2",
        description="Enable LangChain tracing for observability",
    )
    langchain_endpoint: str = Field(
        default="https://api.smith.langchain.com",
        env="LANGCHAIN_ENDPOINT",
        description="LangChain Smith endpoint URL",
    )
    langchain_api_key: Optional[str] = Field(
        default=None, env="LANGCHAIN_API_KEY", description="LangChain Smith API key"
    )
    langchain_project: str = Field(
        default="aura-agent-visualization",
        env="LANGCHAIN_PROJECT",
        description="LangChain Smith project name",
    )
    langchain_project_id: Optional[str] = Field(
        default=None,
        env="LANGCHAIN_PROJECT_ID",
        description="LangChain Smith project UUID (optional, used for public trace links)",
    )

    # Default Provider Selection (Tri-Provider Architecture)
    default_llm_provider: Literal["groq", "gemini", "nvidia"] = Field(
        default="groq",
        env="DEFAULT_LLM_PROVIDER",
        description="Default LLM provider (fast tasks)",
    )
    default_vlm_provider: Literal["groq", "gemini", "nvidia"] = Field(
        default="groq",
        env="DEFAULT_VLM_PROVIDER",
        description="Default VLM provider (vision tasks)",
    )
    default_stt_provider: Literal["groq", "gemini"] = Field(
        default="groq", env="DEFAULT_STT_PROVIDER", description="Default STT provider"
    )
    default_tts_provider: Literal["edge-tts"] = Field(
        default="edge-tts",
        env="DEFAULT_TTS_PROVIDER",
        description="Default TTS provider (Edge-TTS — local Microsoft library, no API key)",
    )

    # Planning provider (separate from fast LLM)
    planning_provider: Literal["groq", "gemini", "nvidia"] = Field(
        default="groq",
        env="PLANNING_PROVIDER",
        description="Provider for planning/reasoning tasks (Groq Llama 4 Scout)",
    )
    planning_model: str = Field(
        default="meta-llama/llama-4-scout-17b-16e-instruct",
        env="PLANNING_MODEL",
        description="Model for planning/reasoning tasks (Llama 4 Scout 17B, multimodal, 16 experts)",
    )
    planning_fallback_model: str = Field(
        default="gemini-2.5-flash",
        env="PLANNING_FALLBACK_MODEL",
        description="Fallback model for planning when primary fails",
    )
    planning_fallback_provider: Literal["groq", "gemini", "nvidia"] = Field(
        default="gemini",
        env="PLANNING_FALLBACK_PROVIDER",
        description="Fallback provider for planning when primary fails",
    )
    safety_model: str = Field(
        default="meta-llama/llama-prompt-guard-2-86m",
        env="SAFETY_MODEL",
        description="Safety guard model for content screening (specialized prompt guard)",
    )
    crewai_model: str = Field(
        default="meta-llama/llama-4-scout-17b-16e-instruct",
        env="CREWAI_MODEL",
        description="Model for CrewAI agent responses (Responder agent) - Only used for complex queries",
    )
    
    # Intent Classification Models (Tiny LLMs via OpenRouter + Groq)
    intent_classification_model: str = Field(
        default="z-ai/glm-4.5-air:free",
        env="INTENT_CLASSIFICATION_MODEL",
        description="Primary model for intent classification (fast, agent-optimized)",
    )
    intent_classification_fallback: str = Field(
        default="meta-llama/llama-3.3-70b-instruct:free",
        env="INTENT_CLASSIFICATION_FALLBACK",
        description="Fallback model for intent classification (reliable)",
    )
    intent_classification_fallback_groq: str = Field(
        default="llama-3.3-70b-versatile",
        env="INTENT_CLASSIFICATION_FALLBACK_GROQ",
        description="Second fallback via Groq (fast, reliable, no rate limits)",
    )

    # Model Selection (Optimized for Tri-Provider Architecture)
    default_llm_model: str = Field(
        default="llama-3.1-8b-instant",
        env="DEFAULT_LLM_MODEL",
        description="Default LLM model (intent parsing - Llama 3.1 8B, 560 T/s)",
    )
    llm_fallback_model: str = Field(
        default="llama-3.3-70b-versatile",
        env="LLM_FALLBACK_MODEL",
        description="Fallback LLM model for low-confidence intent parsing",
    )
    default_vlm_model: str = Field(
        default="meta-llama/llama-4-scout-17b-16e-instruct",
        env="DEFAULT_VLM_MODEL",
        description="Default VLM model (primary model for selected VLM provider)",
    )
    vlm_secondary_model: str = Field(
        default="meta-llama/llama-4-scout-17b-16e-instruct",
        env="VLM_SECONDARY_MODEL",
        description="Secondary VLM model (Scout 16 experts, higher quality fallback)",
    )
    # Fallback VLM model for the non-default provider
    fallback_vlm_model: str = Field(
        default="gemini-2.5-flash",
        env="FALLBACK_VLM_MODEL",
        description="Fallback VLM model used when primary VLM provider fails",
    )
    fallback_vlm_provider: Literal["groq", "gemini", "nvidia"] = Field(
        default="gemini",
        env="FALLBACK_VLM_PROVIDER",
        description="Provider for fallback VLM model",
    )
    default_stt_model: str = Field(
        default="whisper-large-v3-turbo",
        env="DEFAULT_STT_MODEL",
        description="Default STT model (turbo is faster)",
    )
    default_stt_language: Optional[str] = Field(
        default=None,
        env="DEFAULT_STT_LANGUAGE",
        description="Optional spoken language code passed to the STT provider",
    )
    default_tts_model: str = Field(
        default="en-US-AriaNeural",
        env="DEFAULT_TTS_MODEL",
        description="Edge-TTS voice (e.g., en-US-AriaNeural, en-US-GuyNeural) or PlayAI name (Fritz-PlayAI)",
    )

    # Parallel Execution Settings
    enable_parallel_execution: bool = Field(
        default=True,
        env="ENABLE_PARALLEL_EXECUTION",
        description="Enable parallel execution of independent graph nodes",
    )
    max_parallel_tasks: int = Field(
        default=3,
        env="MAX_PARALLEL_TASKS",
        description="Maximum number of parallel tasks to run",
    )

    # Auto Routing Configuration
    enable_provider_fallback: bool = Field(
        default=True,
        env="ENABLE_PROVIDER_FALLBACK",
        description="Enable automatic fallback to alternative providers on failure",
    )
    
    # Universal Agent Migration (Phase 5)
    use_universal_agent: bool = Field(
        default=True,
        env="USE_UNIVERSAL_AGENT",
        description="Route UI actions through UniversalAgent instead of Navigator",
    )

    # Perception Configuration
    default_perception_modality: Literal["ui_tree", "hybrid", "vision", "auto"] = Field(
        default="hybrid",
        env="DEFAULT_PERCEPTION_MODALITY",
        description="Default perception modality when both screenshot and UI tree are available",
    )
    fast_perception_apps: List[str] = Field(
        default_factory=list,
        env="FAST_PERCEPTION_APPS",
        description="Package names where UI_TREE is sufficient (e.g., com.android.settings)",
    )

    # Performance Enhancements Configuration
    perception_cache_enabled: bool = Field(
        default=True,
        env="PERCEPTION_CACHE_ENABLED",
        description="Enable perception caching to reduce redundant screen captures",
    )
    perception_cache_ttl: float = Field(
        default=2.0,
        env="PERCEPTION_CACHE_TTL",
        description="Cache lifetime in seconds",
    )
    perception_cache_max_actions: int = Field(
        default=1,
        env="PERCEPTION_CACHE_MAX_ACTIONS",
        description="Invalidate cache after N actions",
    )
    adaptive_delays_enabled: bool = Field(
        default=True,
        env="ADAPTIVE_DELAYS_ENABLED",
        description="Enable adaptive delays based on action confidence and history",
    )
    adaptive_delays_min_samples: int = Field(
        default=5,
        env="ADAPTIVE_DELAYS_MIN_SAMPLES",
        description="Minimum samples before adapting delays",
    )
    agent_monitor_enabled: bool = Field(
        default=True,
        env="AGENT_MONITOR_ENABLED",
        description="Enable real-time agent performance monitoring",
    )
    agent_monitor_history_size: int = Field(
        default=100,
        env="AGENT_MONITOR_HISTORY_SIZE",
        description="Number of recent goals to track",
    )
    agent_monitor_alert_success_rate: float = Field(
        default=0.5,
        env="AGENT_MONITOR_ALERT_SUCCESS_RATE",
        description="Alert if success rate drops below this threshold",
    )
    agent_monitor_alert_loop_rate: float = Field(
        default=0.3,
        env="AGENT_MONITOR_ALERT_LOOP_RATE",
        description="Alert if loop detection rate exceeds this threshold",
    )
    vlm_proactive_enabled: bool = Field(
        default=True,
        env="VLM_PROACTIVE_ENABLED",
        description="Enable proactive VLM usage for visual-only targets",
    )
    vlm_cache_ttl: float = Field(
        default=5.0,
        env="VLM_CACHE_TTL",
        description="VLM result cache lifetime in seconds",
    )

    # Server Configuration
    host: str = Field(default="0.0.0.0", env="HOST", description="Server host address")
    port: int = Field(default=8000, env="PORT", description="Server port number")
    reload: bool = Field(
        default=True, env="RELOAD", description="Enable auto-reload for development"
    )
    cors_origins: List[str] = Field(
        default_factory=lambda: ["*"],
        env="CORS_ORIGINS",
        description="Allowed CORS origins",
    )

    # Security settings
    require_api_key: bool = Field(
        default=True, env="REQUIRE_API_KEY", description="Require API key for device endpoints (default: enabled)"
    )
    device_api_key: Optional[str] = Field(
        default=None,
        env="DEVICE_API_KEY",
        description="API key for device authentication",
    )

    # System Settings
    log_level: Literal["TRACE", "DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="DEBUG",
        env="LOG_LEVEL",
        description="Logging level (TRACE=5, DEBUG=10, INFO=20, WARNING=30, ERROR=40)",
    )
    environment: Literal["development", "production"] = Field(
        default="development", env="ENVIRONMENT", description="Application environment"
    )

    # ------------------------------------------------------------------ #
    # Google Cloud Platform — required for Gemini Live Agent Challenge   #
    # ------------------------------------------------------------------ #
    # GOOGLE_API_KEY is the canonical key for the google-genai SDK.
    # GEMINI_API_KEY (above) is kept for backward-compatibility with the
    # existing Groq-fallback path; both are accepted.
    google_api_key: str = Field(
        default="",
        env="GOOGLE_API_KEY",
        description="Google AI Studio API key for GenAI SDK / ADK (competition requirement)",
    )
    google_cloud_project: str = Field(
        default="",
        env="GOOGLE_CLOUD_PROJECT",
        description="GCP project ID (Cloud Run deployment + optional Vertex AI routing)",
    )
    google_cloud_region: str = Field(
        default="us-central1",
        env="GOOGLE_CLOUD_REGION",
        description="GCP region for Cloud Run and Vertex AI",
    )

    # Cloud Storage — execution log upload
    gcs_logs_bucket: str = Field(
        default="aura-execution-logs",
        env="GCS_LOGS_BUCKET",
        description="GCS bucket name for uploading HTML execution logs",
    )
    gcs_logs_enabled: bool = Field(
        default=False,
        env="GCS_LOGS_ENABLED",
        description="Enable automatic upload of execution logs to Cloud Storage",
    )

    # ADK application name
    adk_app_name: str = Field(
        default="AURA",
        env="ADK_APP_NAME",
        description="Application name registered with Google ADK session service",
    )

    # Gemini Live bidirectional audio+vision streaming
    gemini_live_model: str = Field(
        default="gemini-2.0-flash-live-001",
        env="GEMINI_LIVE_MODEL",
        description="Gemini Live model for bidirectional audio+vision streaming",
    )
    gemini_live_enabled: bool = Field(
        default=False,
        env="GEMINI_LIVE_ENABLED",
        description="Enable /ws/live endpoint with Gemini Live bidi streaming (Phase 2)",
    )
    gemini_live_voice: str = Field(
        default="Charon",
        env="GEMINI_LIVE_VOICE",
        description=(
            "Prebuilt voice name for Gemini Live responses. "
            "Available: Aoede, Charon, Fenrir, Kore, Puck, Schedar, Gacrux, Pulcherrima, Achird, Zubenelgenubi"
        ),
    )
    gemini_live_transcription_language: str = Field(
        default="en-US",
        env="GEMINI_LIVE_TRANSCRIPTION_LANGUAGE",
        description=(
            "Language code for Gemini Live input/output audio transcription. "
            "Set to en-US to keep English speech transcribed in English script; use auto for automatic detection."
        ),
    )

    # Vertex AI routing (optional second GCP service for scoring)
    use_vertex_ai: bool = Field(
        default=False,
        env="USE_VERTEX_AI",
        description="Route VLM calls through Vertex AI instead of AI Studio",
    )

    # LangGraph execution limits
    graph_recursion_limit: int = Field(
        default=100,
        env="GRAPH_RECURSION_LIMIT",
        description="LangGraph max node transitions per run. Formula: 4 nodes/step × 10 steps × 2.5x retry buffer",
    )
    graph_timeout_seconds: float = Field(
        default=120.0,
        env="GRAPH_TIMEOUT_SECONDS",
        description="Hard timeout for LangGraph execution per user command",
    )

    # Perception tuning
    ui_tree_max_retries: int = Field(
        default=1,
        env="UI_TREE_MAX_RETRIES",
        description="Max retries for empty UI tree before escalating to VISION",
    )
    ui_tree_retry_delay_seconds: float = Field(
        default=0.3,
        env="UI_TREE_RETRY_DELAY_SECONDS",
        description="Delay between UI tree retries in seconds",
    )

    # Reactive step generator history window
    step_history_window: int = Field(
        default=6,
        env="STEP_HISTORY_WINDOW",
        description="Number of recent steps to show in full; older steps are summarized",
    )

    class Config:
        """Pydantic configuration."""

        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# Global settings instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """
    Get the global settings instance.

    Returns:
        Settings: Configured settings instance.
    """
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
