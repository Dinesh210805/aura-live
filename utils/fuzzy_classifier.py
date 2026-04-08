"""
AI-Powered Intent Classifier using Groq and Gemini APIs.

This module uses LLMs for intelligent intent classification with fallback mechanisms,
caching, and confidence scoring for optimal agent routing.
"""

import hashlib
import json
import os
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

try:
    from groq import Groq

    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False

try:
    import google.generativeai as genai

    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

from utils.logger import get_logger

logger = get_logger(__name__)
CLASSIFIER_MODEL_TIMEOUT_S = 8.0


class RequiredAgents(Enum):
    """Agent configurations for different task types."""

    RESPONDER_ONLY = "responder"
    COMMANDER_RESPONDER = "commander_responder"
    COMMANDER_NAVIGATOR_RESPONDER = "commander_navigator_responder"
    COMMANDER_EXECUTOR_RESPONDER = "commander_executor_responder"
    ALL_AGENTS = "all_agents"


AGENT_MAPPING = {
    RequiredAgents.RESPONDER_ONLY: ["responder"],
    RequiredAgents.COMMANDER_RESPONDER: ["commander", "responder"],
    RequiredAgents.COMMANDER_NAVIGATOR_RESPONDER: [
        "commander",
        "navigator",
        "responder",
    ],
    RequiredAgents.COMMANDER_EXECUTOR_RESPONDER: ["commander", "executor", "responder"],
    RequiredAgents.ALL_AGENTS: ["commander", "navigator", "executor", "responder"],
}


class ClassificationCache:
    """Simple in-memory cache for classification results."""

    def __init__(self, ttl_seconds: int = 3600, max_size: int = 1000):
        self.cache: Dict[str, Tuple[Dict[str, Any], datetime]] = {}
        self.ttl = timedelta(seconds=ttl_seconds)
        self.max_size = max_size

    def _generate_key(self, intent: Dict[str, Any], transcript: str) -> str:
        """Generate cache key from intent and transcript."""
        content = f"{intent.get('action', '')}{intent.get('content', '')}{transcript}"
        return hashlib.md5(content.encode()).hexdigest()

    def get(self, intent: Dict[str, Any], transcript: str) -> Optional[Dict[str, Any]]:
        """Retrieve cached classification if valid."""
        key = self._generate_key(intent, transcript)
        if key in self.cache:
            result, timestamp = self.cache[key]
            if datetime.now() - timestamp < self.ttl:
                logger.debug(f"Cache hit for key: {key[:8]}...")
                return result
            else:
                del self.cache[key]
        return None

    def set(self, intent: Dict[str, Any], transcript: str, result: Dict[str, Any]):
        """Store classification result in cache."""
        if len(self.cache) >= self.max_size:
            # Remove oldest entry
            oldest_key = min(self.cache.keys(), key=lambda k: self.cache[k][1])
            del self.cache[oldest_key]

        key = self._generate_key(intent, transcript)
        self.cache[key] = (result, datetime.now())
        logger.debug(f"Cached result for key: {key[:8]}...")


class AIIntentClassifier:
    """
    AI-powered intent classifier using Groq (primary) and Gemini (fallback).
    """

    def __init__(self):
        """Initialize AI clients and configuration."""
        self.groq_client = None
        self.gemini_model = None
        self.cache = ClassificationCache(ttl_seconds=1800, max_size=500)

        # Initialize Groq
        if GROQ_AVAILABLE:
            try:
                from config.settings import get_settings as _get_settings
                groq_key = _get_settings().groq_api_key
                if groq_key:
                    self.groq_client = Groq(api_key=groq_key)
                    logger.info("Groq client initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize Groq: {e}")

        # Initialize Gemini as fallback
        if GEMINI_AVAILABLE:
            try:
                from config.settings import get_settings as _get_settings
                gemini_key = _get_settings().gemini_api_key
                if gemini_key:
                    genai.configure(api_key=gemini_key)
                    self.gemini_model = genai.GenerativeModel("gemini-2.0-flash-lite")
                    logger.info("Gemini client initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize Gemini: {e}")

        if not self.groq_client and not self.gemini_model:
            logger.error(
                "No AI clients available! Classification will use fallback logic."
            )

        self.classification_prompt = self._build_classification_prompt()

    def _build_classification_prompt(self) -> str:
        """Build the system prompt for intent classification."""
        return """You are an expert intent classifier for a mobile voice assistant.

Analyze the user's request and classify it into one of these categories:

**CONVERSATIONAL**: Pure conversation - NO device action needed, just respond naturally
- Examples: 
  * Greetings: "hi", "hello", "hey there", "good morning"
  * Help/Info: "what can you do", "help me", "tell me about yourself"
  * Status: "how are you", "are you working"
  * Thanks: "thank you", "thanks"
- Key indicator: User wants to TALK, not interact with their device screen
- Requires: Only responder (no device interaction)

**SIMPLE**: Single, direct device command (no UI reading needed)
- Examples: "take screenshot", "scroll down", "press back", "turn on WiFi", "increase volume", "open WhatsApp"
- Key indicator: One clear action, no need to analyze what's on screen
- Requires: Commander → Executor → Responder

**MEDIUM**: Needs to see/understand screen OR describe what's visible
- Examples: 
  * "read the screen", "what's on my screen", "what is on my screen"
  * "describe this page", "describe my screen", "what do you see"
  * "tell me what is on screen", "read screen for me"
  * "find settings button", "where is the back button"
- Key indicator: User asks about SCREEN CONTENT or needs UI context
- IMPORTANT: "what is on my screen" = MEDIUM (needs screen capture), NOT conversational
- Requires: Commander → Navigator/ScreenReader → Responder

**COMPLEX**: Multi-step workflows with planning
- Examples: "send John a WhatsApp message saying I'll be late", "search for bluetooth in settings"
- Key indicator: Multiple steps, conditions, or complex logic
- Requires: Full pipeline with planning

CRITICAL RULE: If user asks "what is on my screen", "describe screen", "read screen", etc. - this is MEDIUM, not conversational!
These require capturing and analyzing the actual device screen.

Respond ONLY with valid JSON:
{
  "complexity": "conversational|simple|medium|complex",
  "reasoning": "Brief explanation",
  "confidence": 0.0-1.0,
  "requires_ui_analysis": true|false,
  "requires_execution": true|false,
  "suggested_agents": ["responder"] or ["commander", "executor", "responder"] etc.
}"""

    def classify_intent(
        self,
        intent: Dict[str, Any],
        transcript: str = "",
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Classify an intent using AI with caching and fallback.

        Args:
            intent: Parsed intent object
            transcript: Original user transcript
            context: Optional context (conversation history, device state)

        Returns:
            Classification with complexity, agents, and routing info
        """
        # Check cache first
        cached = self.cache.get(intent, transcript)
        if cached:
            return cached

        try:
            # Try AI classification
            classification = self._classify_with_ai(intent, transcript, context)

            if classification:
                result = self._build_classification_result(
                    classification, intent, transcript
                )
                self.cache.set(intent, transcript, result)
                return result

        except Exception as e:
            logger.error(f"AI classification failed: {e}")

        # Fallback to rule-based classification
        logger.warning("Using fallback rule-based classification")
        result = self._fallback_classification(intent, transcript)
        self.cache.set(intent, transcript, result)
        return result

    def _classify_with_ai(
        self, intent: Dict[str, Any], transcript: str, context: Optional[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Use AI to classify the intent."""
        user_message = self._build_user_message(intent, transcript, context)

        # Try Groq first (faster)
        if self.groq_client:
            try:
                # Use default LLM model from settings
                from config.settings import Settings

                settings = Settings()
                model = settings.default_llm_model

                request_client = self.groq_client
                if hasattr(self.groq_client, "with_options"):
                    try:
                        request_client = self.groq_client.with_options(
                            timeout=CLASSIFIER_MODEL_TIMEOUT_S
                        )
                    except Exception as timeout_opt_error:
                        logger.debug(
                            f"Could not apply Groq timeout options: {timeout_opt_error}"
                        )

                response = request_client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": self.classification_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    temperature=0.1,
                    max_tokens=500,
                    response_format={"type": "json_object"},
                )

                result = json.loads(response.choices[0].message.content)
                logger.info(
                    f"Groq classification: {result.get('complexity')} (confidence: {result.get('confidence')})"
                )
                return result

            except Exception as e:
                logger.error(f"Groq classification failed: {e}")

        # Fallback to Gemini
        if self.gemini_model:
            try:
                full_prompt = f"{self.classification_prompt}\n\nUser Request:\n{user_message}\n\nRespond with JSON only."
                response = self.gemini_model.generate_content(
                    full_prompt,
                    request_options={"timeout": CLASSIFIER_MODEL_TIMEOUT_S},
                )

                # Extract JSON from response
                text = (response.text or "").strip()
                if text.startswith("```json"):
                    text = text[7:]
                if text.endswith("```"):
                    text = text[:-3]
                text = text.strip()

                result = json.loads(text)
                logger.info(
                    f"Gemini classification: {result.get('complexity')} (confidence: {result.get('confidence')})"
                )
                return result

            except Exception as e:
                logger.error(f"Gemini classification failed: {e}")

        return None

    def _build_user_message(
        self, intent: Dict[str, Any], transcript: str, context: Optional[Dict[str, Any]]
    ) -> str:
        """Build the user message for AI classification."""
        parts = [
            f"Original Request: {transcript}",
            "\nParsed Intent:",
            f"- Action: {intent.get('action', 'N/A')}",
            f"- Content: {intent.get('content', 'N/A')}",
        ]

        if intent.get("recipients"):
            parts.append(f"- Recipients: {', '.join(intent['recipients'])}")

        if intent.get("app"):
            parts.append(f"- Target App: {intent['app']}")

        if context:
            if context.get("previous_action"):
                parts.append(f"\nPrevious Action: {context['previous_action']}")
            if context.get("current_screen"):
                parts.append(f"Current Screen: {context['current_screen']}")

        return "\n".join(parts)

    def _build_classification_result(
        self, ai_result: Dict[str, Any], intent: Dict[str, Any], transcript: str
    ) -> Dict[str, Any]:
        """Build final classification result from AI response."""
        complexity = ai_result.get("complexity", "medium")
        confidence = float(ai_result.get("confidence", 0.7))
        requires_ui = ai_result.get("requires_ui_analysis", True)
        requires_exec = ai_result.get("requires_execution", True)

        # Determine required agents based on AI suggestion or complexity
        if "suggested_agents" in ai_result:
            required_agents = ai_result["suggested_agents"]
        else:
            required_agents = self._determine_agents_from_complexity(
                complexity, requires_ui, requires_exec
            )

        # Determine execution path
        execution_path = self._determine_execution_path(
            complexity, requires_ui, requires_exec
        )

        return {
            "complexity": complexity,
            "required_agents": required_agents,
            "execution_path": execution_path,
            "confidence": confidence,
            "skip_ui_analysis": not requires_ui,
            "skip_planning": complexity in ["conversational", "simple"],
            "skip_execution": not requires_exec,
            "direct_response": complexity == "conversational",
            "reasoning": ai_result.get("reasoning", ""),
            "classifier": "ai",
            "timestamp": datetime.now().isoformat(),
        }

    def _determine_agents_from_complexity(
        self, complexity: str, requires_ui: bool, requires_exec: bool
    ) -> List[str]:
        """Determine required agents based on complexity and requirements."""
        if complexity == "conversational":
            return AGENT_MAPPING[RequiredAgents.RESPONDER_ONLY]
        elif complexity == "simple":
            return AGENT_MAPPING[RequiredAgents.COMMANDER_EXECUTOR_RESPONDER]
        elif complexity == "medium":
            if requires_ui and not requires_exec:
                return AGENT_MAPPING[RequiredAgents.COMMANDER_NAVIGATOR_RESPONDER]
            elif requires_exec:
                return AGENT_MAPPING[RequiredAgents.COMMANDER_EXECUTOR_RESPONDER]
            else:
                return AGENT_MAPPING[RequiredAgents.COMMANDER_RESPONDER]
        else:  # complex
            return AGENT_MAPPING[RequiredAgents.ALL_AGENTS]

    def _determine_execution_path(
        self, complexity: str, requires_ui: bool, requires_exec: bool
    ) -> str:
        """Determine optimal execution path."""
        if complexity == "conversational":
            return "direct_response"
        elif complexity == "simple":
            return "simple_execution"
        elif complexity == "medium":
            if requires_ui and not requires_exec:
                return "analysis_only"
            else:
                return "medium_execution"
        else:
            return "full_workflow"

    def _fallback_classification(
        self, intent: Dict[str, Any], transcript: str
    ) -> Dict[str, Any]:
        """Rule-based fallback classification when AI is unavailable."""
        action = intent.get("action", "").lower()
        content = intent.get("content", "").lower()
        text = f"{action} {content} {transcript}".lower()

        # Conversational patterns
        conversational_keywords = [
            "hello",
            "hi",
            "hey",
            "thanks",
            "thank you",
            "bye",
            "goodbye",
            "how are you",
            "what can you do",
            "help",
            "who are you",
            "what are you",
            "capabilities",
            "features",
            "tell me about yourself",
        ]

        # More flexible conversational detection - check if it's primarily conversational
        conversational_score = sum(1 for kw in conversational_keywords if kw in text)
        has_task_keywords = any(
            kw in text for kw in ["open", "send", "call", "launch", "close", "install"]
        )

        # If it's conversational and doesn't have clear task keywords, treat as conversation
        if conversational_score >= 1 and not has_task_keywords:
            complexity = "conversational"
            agents = AGENT_MAPPING[RequiredAgents.RESPONDER_ONLY]
            exec_path = "direct_response"

        # Simple commands
        elif action in [
            "screenshot",
            "scroll",
            "swipe",
            "back",
            "press",
            "tap",
            "click",
        ]:
            complexity = "simple"
            agents = AGENT_MAPPING[RequiredAgents.COMMANDER_EXECUTOR_RESPONDER]
            exec_path = "simple_execution"

        # Information queries / Screen reading
        elif any(
            kw in text
            for kw in [
                "what's on screen",
                "what is on my screen",
                "what is on screen",
                "describe",
                "read the screen",
                "read my screen",
                "what do you see",
                "tell me what",
                "screen",
            ]
        ):
            complexity = "medium"
            agents = AGENT_MAPPING[RequiredAgents.COMMANDER_NAVIGATOR_RESPONDER]
            exec_path = "analysis_only"

        # Complex operations
        elif " and " in text or "send message" in text or "install" in text:
            complexity = "complex"
            agents = AGENT_MAPPING[RequiredAgents.ALL_AGENTS]
            exec_path = "full_workflow"

        else:
            # Default to medium
            complexity = "medium"
            agents = AGENT_MAPPING[RequiredAgents.COMMANDER_EXECUTOR_RESPONDER]
            exec_path = "medium_execution"

        return {
            "complexity": complexity,
            "required_agents": agents,
            "execution_path": exec_path,
            "confidence": 0.6,
            "skip_ui_analysis": complexity in ["conversational", "simple"],
            "skip_planning": complexity in ["conversational", "simple"],
            "skip_execution": complexity == "conversational",
            "direct_response": complexity == "conversational",
            "reasoning": "Fallback rule-based classification",
            "classifier": "fallback",
            "timestamp": datetime.now().isoformat(),
        }
