"""
GCS Log Uploader — Cloud Storage execution log upload utility.

Uploads HTML execution logs produced by CommandLogger to a Google Cloud
Storage bucket after each task completes, enabling judges to inspect full
execution traces via a public URL without running the code locally.

Usage (non-blocking fire-and-forget pattern):
    asyncio.create_task(upload_log_to_gcs_async(log_path, session_id))

The upload is intentionally non-fatal: any failure is logged as a warning
and the task result is unchanged.
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# GCS SDK import is guarded — the package may not be installed in dev.
try:
    from google.cloud import storage as _gcs

    _GCS_AVAILABLE = True
except ImportError:
    _gcs = None  # type: ignore[assignment]
    _GCS_AVAILABLE = False


def _resolve_api_key() -> Optional[str]:
    """Return the best available Google API / application credentials key."""
    from config.settings import get_settings

    s = get_settings()
    # Prefer GOOGLE_API_KEY; fall back to GEMINI_API_KEY for back-compat.
    return s.google_api_key or s.gemini_api_key or None


def upload_log_to_gcs(log_path: str, session_id: str) -> Optional[str]:
    """
    Upload an HTML execution log file to Cloud Storage.

    This is a synchronous implementation intended to be called from an
    executor thread via asyncio.get_event_loop().run_in_executor().

    Args:
        log_path: Absolute path to the local HTML log file.
        session_id: Used to construct the GCS object name.

    Returns:
        Public URL of the uploaded log, or None if disabled / failed.
    """
    from config.settings import get_settings

    settings = get_settings()

    if not settings.gcs_logs_enabled:
        logger.debug("GCS log upload disabled (GCS_LOGS_ENABLED=false)")
        return None

    if not _GCS_AVAILABLE:
        logger.warning(
            "google-cloud-storage not installed; skipping GCS upload. "
            "Run: pip install google-cloud-storage"
        )
        return None

    log_file = Path(log_path)
    if not log_file.exists():
        logger.warning(f"Log file not found, skipping GCS upload: {log_path}")
        return None

    if not settings.google_cloud_project:
        logger.warning(
            "GOOGLE_CLOUD_PROJECT not set; GCS upload requires a project ID."
        )
        return None

    try:
        client = _gcs.Client(project=settings.google_cloud_project)
        bucket = client.bucket(settings.gcs_logs_bucket)

        # Sanitise session_id so it is safe as an object name
        safe_id = "".join(c if c.isalnum() or c in "-_." else "_" for c in session_id)
        blob_name = f"logs/{safe_id}.html"

        blob = bucket.blob(blob_name)
        blob.upload_from_filename(str(log_file), content_type="text/html; charset=utf-8")

        # Make publicly readable so judges can open the link directly
        blob.make_public()
        url = blob.public_url

        logger.info(f"Execution log uploaded to GCS: {url}")
        return url

    except Exception as exc:
        # Non-fatal — task result must not depend on log availability.
        logger.warning(f"GCS log upload failed (non-fatal): {exc}")
        return None


async def upload_log_to_gcs_async(log_path: str, session_id: str) -> Optional[str]:
    """
    Async wrapper: runs the synchronous GCS upload in a thread pool executor
    so it does not block the FastAPI event loop.

    Args:
        log_path: Absolute path to the local HTML log file.
        session_id: Used to construct the GCS object name.

    Returns:
        Public URL of the uploaded log, or None if disabled / failed.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, upload_log_to_gcs, log_path, session_id)
