"""
WebSearchService — wraps Tavily for real-time web lookups.

Used when the Commander classifies a request as `web_search`
(weather, news, current facts, etc.) so AURA can answer without
requiring a device screen interaction.
"""

import asyncio
import re
from typing import Optional

from utils.logger import get_logger

logger = get_logger(__name__)

_FALLBACK_UNAVAILABLE = (
    "Web search is not available right now. "
    "Set TAVILY_API_KEY in your .env file to enable it."
)

_instance: Optional["WebSearchService"] = None


def get_web_search_service() -> "WebSearchService":
    """Return the process-level WebSearchService singleton."""
    global _instance
    if _instance is None:
        from config.settings import get_settings
        settings = get_settings()
        _instance = WebSearchService(api_key=settings.tavily_api_key)
    return _instance


class WebSearchService:
    """Thin async wrapper around the Tavily Python SDK."""

    def __init__(self, api_key: Optional[str] = None):
        self._client = None
        if api_key:
            try:
                from tavily import TavilyClient
                self._client = TavilyClient(api_key=api_key)
                logger.info("✅ WebSearchService: Tavily client initialized")
            except ImportError:
                logger.warning(
                    "tavily-python not installed — run: pip install tavily-python"
                )
        else:
            logger.warning(
                "WebSearchService: TAVILY_API_KEY not set — web search disabled"
            )

    @property
    def available(self) -> bool:
        return self._client is not None

    # Keywords that indicate developer/SDK content — not useful for end-user navigation
    _DEV_KEYWORDS = ("sdk", "codelab", "api key", "gradle", "import com.", "build.gradle",
                     "android studio", "implementation '", "implementation \"")

    # Known apps and their canonical names for query construction
    _APP_MAP = {
        "google maps": "Google Maps",
        "whatsapp": "WhatsApp",
        "spotify": "Spotify",
        "youtube": "YouTube",
        "gmail": "Gmail",
        "instagram": "Instagram",
        "chrome": "Chrome",
        "android settings": "Android Settings",
        "settings": "Android Settings",
        "google photos": "Google Photos",
        "photos": "Google Photos",
        "camera": "Camera",
        "maps": "Google Maps",
        "telegram": "Telegram",
        "netflix": "Netflix",
        "amazon": "Amazon",
        "zomato": "Zomato",
        "swiggy": "Swiggy",
    }

    def _build_guide_query(self, utterance: str) -> str:
        """
        Convert a raw AURA utterance into a human-like how-to search query.

        Examples:
          "Open Google Maps, search for Chennai and start navigation"
          → "how to search and navigate to a location in Google Maps android"

          "send live location to appa in WhatsApp"
          → "how to send live location in WhatsApp android"

          "play my liked songs from Spotify"
          → "how to play liked songs in Spotify android"
        """
        utt_lower = utterance.lower()

        # 1. Detect app name
        detected_app = ""
        for keyword, name in self._APP_MAP.items():
            if keyword in utt_lower:
                detected_app = name
                break

        # 2. Strip "Open [App]," / "Open [App] and" prefix — it's always noise
        query = re.sub(r'^[Oo]pen\s+[\w\s]+?,\s*', '', utterance).strip()
        query = re.sub(r'^[Oo]pen\s+[\w\s]+?\s+and\s+', '', query).strip()

        # 3. Strip quoted strings (contact names, media titles, place names in quotes)
        query = re.sub(r"'[^']{1,60}'", '[name]', query)
        query = re.sub(r'"[^"]{1,60}"', '[name]', query)

        # 4. Replace specific place names after "to/for" (CapitalizedWord = proper noun)
        #    e.g. "to Chennai" → "to a location"  |  "for Park Street" → "for a place"
        query = re.sub(r'\bto\s+[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,2}', 'to a location', query)
        query = re.sub(r'\bfor\s+[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,2}', 'for a place', query)

        # 5. Strip "named [name]" patterns (contact lookup patterns)
        query = re.sub(r'\bnamed\s+\S+', '', query)
        query = re.sub(r'\bcalled\s+\S+', '', query)

        # 6. Clean up whitespace/punctuation
        query = re.sub(r'\s+', ' ', query).strip().strip(',').strip()

        # 7. Build final query
        query_lower = query.lower()
        if detected_app and detected_app.lower() not in query_lower:
            return f"how to {query} in {detected_app} android"
        return f"how to {query} android"

    async def search_for_guide(self, utterance: str) -> str:
        """
        Search official docs/guides to assist skeleton planning and RSG.

        Constructs a human-like query from the utterance, then fetches
        step-by-step navigation instructions from Tavily.

        Returns a how-to string (up to 1500 chars), or "" if unavailable.
        """
        if not self._client:
            return ""

        query = self._build_guide_query(utterance)
        logger.info(f"[WebGuide] Query → Tavily: '{query}'")

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self._client.search(
                    query=query,
                    search_depth="basic",
                    topic="general",
                    include_answer=True,
                    max_results=5,
                ),
            )

            # Log raw Tavily answer
            answer = (response.get("answer") or "").strip()
            logger.debug(f"[WebGuide] Tavily answer: {answer[:200]!r}")

            parts = []
            if answer:
                parts.append(answer)

            # Include non-developer result snippets
            for r in (response.get("results") or [])[:4]:
                content = (r.get("content") or "").strip()
                url = (r.get("url") or "").lower()
                # Skip developer/SDK results
                content_lower = content.lower()
                if any(kw in content_lower for kw in self._DEV_KEYWORDS):
                    logger.debug(f"[WebGuide] Skipping dev result: {url[:60]}")
                    continue
                snippet = content[:500]
                if snippet and snippet not in answer:
                    logger.debug(f"[WebGuide] + snippet from {url[:60]}: {snippet[:80]!r}...")
                    parts.append(snippet)
                if len(parts) >= 3:  # answer + 2 quality snippets is enough
                    break

            combined = "\n# ".join(parts).strip()
            logger.info(f"[WebGuide] Response ({len(combined)} chars): {combined[:120]!r}...")
            return combined[:1500]

        except Exception as e:
            logger.debug(f"search_for_guide failed (non-fatal): {e}")
            return ""

    async def search(self, query: str, topic: str = "general") -> str:
        """
        Run a Tavily search and return a clean answer string ready for TTS.

        Args:
            query: Natural-language search query.
            topic: "general" (default) or "news" for news-focused queries.

        Returns:
            Answer string, or a graceful error message.
        """
        if not self._client:
            return _FALLBACK_UNAVAILABLE

        try:
            # Tavily SDK is synchronous — run in thread pool so we don't block
            # the async event loop during the HTTP round-trip.
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self._client.search(
                    query=query,
                    search_depth="basic",
                    topic=topic,
                    include_answer=True,
                    max_results=3,
                ),
            )

            # `answer` is Tavily's pre-synthesized summary — ideal for TTS.
            answer = (response.get("answer") or "").strip()
            if answer:
                logger.info(
                    f"Web search OK: query='{query[:50]}' "
                    f"answer='{answer[:80]}...'"
                )
                return answer

            # Fallback: stitch top-2 result snippets together.
            results = response.get("results", [])
            if results:
                snippets = [
                    r.get("content", "")[:200]
                    for r in results[:2]
                    if r.get("content")
                ]
                joined = " ".join(snippets).strip()
                if joined:
                    return joined

            return "I searched the web but couldn't find a clear answer for that."

        except Exception as e:
            logger.error(f"Tavily search error for '{query[:50]}': {e}")
            return f"I had trouble searching the web. {str(e)}"
