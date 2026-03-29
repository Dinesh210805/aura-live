"""
Smoke test: verify Gemini LLM + VLM calls return non-empty text.

Run:  python scripts/test_gemini_calls.py

Requires GEMINI_API_KEY in .env or environment.
"""

import os
import sys
import base64
from io import BytesIO
from pathlib import Path

# Ensure project root is on the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from config.settings import Settings
from utils.logger import get_logger

settings = Settings()

logger = get_logger("test_gemini_calls")

PASS = "[PASS]"
FAIL = "[FAIL]"


# ---------------------------------------------------------------------------
# Helper: tiny 1×1 white JPEG in base64 (valid image, no external deps)
# ---------------------------------------------------------------------------
def _tiny_white_jpeg_b64() -> str:
    try:
        from PIL import Image
        img = Image.new("RGB", (64, 64), color=(255, 255, 255))
        buf = BytesIO()
        img.save(buf, format="JPEG")
        return base64.b64encode(buf.getvalue()).decode()
    except Exception as e:
        logger.warning(f"PIL not available for test image: {e}")
        return ""


def run_llm_test() -> bool:
    """Test LLMService._call_gemini returns non-empty text."""
    print("\n[1/3] LLMService Gemini text generation ...", end=" ", flush=True)
    try:
        from services.llm import LLMService
        svc = LLMService(settings)
        if not svc.gemini_client:
            print(f"{FAIL}  SKIP — Gemini client not initialised (check GEMINI_API_KEY)")
            return False

        result = svc.run(
            prompt="Reply with exactly the word: HELLO",
            provider="gemini",
            model=settings.default_vlm_model,  # gemini-2.5-flash
        )
        if result and result.strip():
            print(f"{PASS}  got: {result.strip()[:80]!r}")
            return True
        else:
            print(f"{FAIL}  returned empty: {result!r}")
            return False
    except Exception as e:
        print(f"{FAIL}  exception: {e}")
        return False


def run_vlm_test() -> bool:
    """Test VLMService._call_gemini returns non-empty text for image analysis."""
    print("[2/3] VLMService Gemini image analysis ...", end=" ", flush=True)
    try:
        from services.vlm import VLMService
        svc = VLMService(settings)
        if not svc.gemini_client:
            print(f"{FAIL}  SKIP — Gemini VLM client not initialised (check GEMINI_API_KEY)")
            return False

        b64 = _tiny_white_jpeg_b64()
        if not b64:
            print(f"{FAIL}  SKIP — could not create test image")
            return False

        result = svc.analyze_image(
            image_data=b64,
            prompt="Describe this image in one short sentence.",
            provider="gemini",
            model=settings.default_vlm_model,
        )
        if result and result.strip():
            print(f"{PASS}  got: {result.strip()[:80]!r}")
            return True
        else:
            print(f"{FAIL}  returned empty: {result!r}")
            return False
    except Exception as e:
        print(f"{FAIL}  exception: {e}")
        return False


def run_two_image_test() -> bool:
    """Test VLMService._call_gemini_two_images returns non-empty text."""
    print("[3/3] VLMService Gemini two-image comparison ...", end=" ", flush=True)
    try:
        from services.vlm import VLMService
        svc = VLMService(settings)
        if not svc.gemini_client:
            print(f"{FAIL}  SKIP — Gemini VLM client not initialised (check GEMINI_API_KEY)")
            return False

        b64 = _tiny_white_jpeg_b64()
        if not b64:
            print(f"{FAIL}  SKIP — could not create test image")
            return False

        result = svc.analyze_two_images(
            before_b64=b64,
            after_b64=b64,
            prompt="Are these two images identical? Answer yes or no.",
            provider="gemini",
            model=settings.default_vlm_model,
        )
        if result and result.strip():
            print(f"{PASS}  got: {result.strip()[:80]!r}")
            return True
        else:
            print(f"{FAIL}  returned empty: {result!r}")
            return False
    except Exception as e:
        print(f"{FAIL}  exception: {e}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("Gemini call smoke tests")
    print(f"  model : {settings.default_vlm_model}")
    print(f"  key   : {'set' if settings.gemini_api_key and settings.gemini_api_key != '...' else 'MISSING'}")
    print("=" * 60)

    results = [
        run_llm_test(),
        run_vlm_test(),
        run_two_image_test(),
    ]

    passed = sum(results)
    total = len(results)
    print(f"\n{'=' * 60}")
    print(f"Result: {passed}/{total} passed")
    sys.exit(0 if passed == total else 1)
