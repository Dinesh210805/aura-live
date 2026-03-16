# ─────────────────────────────────────────────────────────────────────────────
# AURA Backend — Cloud Run Dockerfile
#
# Build:  docker build -t aura-backend .
# Run:    docker run -p 8080:8080 --env-file .env aura-backend
#
# Deploy to Cloud Run:
#   gcloud run deploy aura-backend \
#     --source . \
#     --region us-central1 \
#     --allow-unauthenticated \
#     --memory 2Gi \
#     --cpu 2 \
#     --timeout 3600 \
#     --set-secrets="GOOGLE_API_KEY=google-api-key:latest,GROQ_API_KEY=groq-api-key:latest,GEMINI_API_KEY=gemini-api-key:latest"
#
# Cloud Run notes:
#   • The PORT env variable is injected automatically by Cloud Run.
#     The Pydantic Settings class already reads PORT via env="PORT".
#   • WebSockets are supported natively on Cloud Run (HTTP/2 upgrade).
#   • Timeout 3600 is required for long-running device automation sessions.
# ─────────────────────────────────────────────────────────────────────────────

FROM python:3.12-slim

# Prevent Python from buffering stdout/stderr (critical for Cloud Run logs)
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Cloud Run injects PORT at runtime; default to 8080 at build time.
# The application reads this via Pydantic Settings (env="PORT").
ENV PORT=8080

# System dependencies required by:
#   • opencv-python  → libgl1-mesa-glx, libglib2.0-0
#   • pyaudio        → portaudio19-dev, libasound2-dev
#   • pydub          → ffmpeg
#   • ultralytics    → libgomp1 (OpenMP for YOLO CPU inference)
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libgomp1 \
    ffmpeg \
    portaudio19-dev \
    libasound2-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (layer-cached until requirements change)
COPY ["requirements copy.txt", "requirements.txt"]
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Pre-warm OmniParser YOLOv8 weights during build so the first request
# does not bear model-load latency (download from HuggingFace Hub).
# The || true ensures the build succeeds even if download fails (e.g., no network).
RUN python -c "\
import os; \
os.environ.setdefault('GROQ_API_KEY', 'placeholder'); \
os.environ.setdefault('GEMINI_API_KEY', 'placeholder'); \
os.environ.setdefault('GOOGLE_API_KEY', 'placeholder'); \
try: \
    from perception.omniparser_detector import OmniParserDetector; \
    OmniParserDetector(); \
    print('OmniParser pre-warmed successfully'); \
except Exception as e: \
    print(f'OmniParser pre-warm skipped: {e}'); \
" || true

# Create logs directory (mounted as a volume in production for persistence)
RUN mkdir -p /app/logs

# Expose the port Cloud Run will route traffic to
EXPOSE 8080

# Use exec form to guarantee SIGTERM propagates to uvicorn for graceful shutdown.
# --ws websockets: use the websockets library (vs wsproto) for /ws/* endpoints.
# --workers 1: Cloud Run scales via instances, not in-process workers.
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT} --ws websockets --workers 1 --timeout-keep-alive 600"]
