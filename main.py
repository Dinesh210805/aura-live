"""
Main FastAPI application for the AURA backend.

This module sets up the FastAPI server with all endpoints
for voice command processing and device control.
"""

# Load environment variables FIRST before any other imports
from dotenv import load_dotenv

load_dotenv(override=True)

import logging  # noqa: E402
import os  # noqa: E402
from contextlib import asynccontextmanager  # noqa: E402

import uvicorn  # noqa: E402
from fastapi import FastAPI, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.middleware.trustedhost import TrustedHostMiddleware  # noqa: E402
from fastapi.responses import HTMLResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from api import config_api, device, graph, health, tasks, websocket, workflow  # noqa: E402
from config.settings import get_settings  # noqa: E402
from constants import API_PREFIX, REQUEST_ID_HEADER  # noqa: E402
from exceptions.handlers import register_exception_handlers  # noqa: E402
from middleware.rate_limit import limiter, setup_rate_limiting  # noqa: E402
from middleware.request_id import add_request_id  # noqa: E402
from static.ui import get_fallback_ui  # noqa: E402
from utils.logger import get_logger  # noqa: E402
from validators.config import validate_configuration  # noqa: E402

# Initialize logger and settings
logger = get_logger(__name__)
settings = get_settings()

# Filter out verbose logs from uvicorn
uvicorn_access = logging.getLogger("uvicorn.access")
uvicorn_access.addFilter(
    lambda record: "/device/commands/pending" not in record.getMessage()
)

# Disable websocket protocol debug logs (BINARY/TEXT messages)
logging.getLogger("uvicorn.error").setLevel(logging.INFO)
logging.getLogger("websockets.protocol").setLevel(logging.WARNING)

# Global services (initialized at startup)
graph_app = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage application startup and shutdown.

    Args:
        app: FastAPI application instance.
    """
    # Startup
    logger.info("Initializing AURA backend server...")

    try:
        # Attach CommandLogger handler to capture all log output
        from services.command_logger import attach_command_logger_handler
        attach_command_logger_handler()
        
        # LiteLLM logging — only verbose in development
        import litellm

        if settings.environment != "production":
            os.environ["LITELLM_LOG"] = "DEBUG"
        else:
            os.environ.pop("LITELLM_LOG", None)

        # SSL verification: use custom cert bundle if provided, otherwise keep default
        ssl_cert = os.getenv("SSL_CERT_FILE")
        if ssl_cert:
            litellm.ssl_verify = ssl_cert
            logger.info(f"LiteLLM SSL using custom cert bundle: {ssl_cert}")
        else:
            litellm.ssl_verify = True
            logger.info("LiteLLM SSL verification enabled (default CA bundle)")

        # Ensure GROQ_API_KEY is set
        if not os.getenv("GROQ_API_KEY") and settings.groq_api_key:
            os.environ["GROQ_API_KEY"] = settings.groq_api_key
            logger.info("GROQ_API_KEY set in environment")

        # LangSmith tracing — only when explicitly enabled with a valid key
        if settings.langchain_tracing_v2 and settings.langchain_api_key:
            os.environ["LANGCHAIN_TRACING_V2"] = "true"
            os.environ["LANGCHAIN_ENDPOINT"] = settings.langchain_endpoint
            os.environ["LANGCHAIN_API_KEY"] = settings.langchain_api_key
            os.environ["LANGCHAIN_PROJECT"] = settings.langchain_project
            logger.info(f"LangSmith tracing enabled: {settings.langchain_project}")
        else:
            os.environ["LANGCHAIN_TRACING_V2"] = "false"
            logger.info("LangSmith tracing disabled")

        # Initialize graph application
        global graph_app
        logger.info("Compiling LangGraph application...")

        from aura_graph.graph import compile_aura_graph

        graph_app = compile_aura_graph()
        app.state.graph_app = graph_app
        logger.info("LangGraph application compiled")

        # Initialize accessibility service (singleton, already created)
        from services.real_accessibility import real_accessibility_service

        logger.info("Accessibility service initialized")

        # Validate configuration
        validate_configuration()

        logger.info("AURA backend startup completed")

    except Exception as e:
        logger.error(f" Failed to start AURA backend: {e}")
        raise

    yield

    # Shutdown
    logger.info("Shutting down AURA backend server")

    # Graceful shutdown
    try:
        from services.real_accessibility import real_accessibility_service

        real_accessibility_service.disconnect_device()
        logger.info("Device disconnected on shutdown")
    except Exception as e:
        logger.error(f" Error during shutdown: {e}")


# Create FastAPI application — disable OpenAPI docs in production
_is_production = settings.environment == "production"
app = FastAPI(
    title="AURA Backend API",
    description="Voice-controlled Android device automation backend",
    version="1.0.0",
    docs_url=None if _is_production else f"{API_PREFIX}/docs",
    redoc_url=None if _is_production else f"{API_PREFIX}/redoc",
    openapi_url=None if _is_production else f"{API_PREFIX}/openapi.json",
    lifespan=lifespan,
)

# Mount static files
try:
    app.mount("/static", StaticFiles(directory="static"), name="static")
    logger.info("Mounted /static directory")
except Exception as e:
    logger.warning(f"Could not mount static directory: {e}")

# Setup rate limiting
setup_rate_limiting(app)

# CORS - enforce safe defaults in production
allowed_origins = getattr(settings, "cors_origins", ["*"])
if _is_production and "*" in allowed_origins:
    logger.warning("⚠️ Overriding wildcard CORS origins in production to localhost only")
    allowed_origins = ["http://localhost:3000", "http://localhost:8080"]

# allow_credentials=True is incompatible with allow_origins=["*"] per CORS spec
_allow_credentials = "*" not in allowed_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
    expose_headers=[REQUEST_ID_HEADER],
)

# Add trusted host middleware for production
if settings.environment == "production":
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=getattr(settings, "allowed_hosts", ["*"])
    )

# Request ID middleware
app.middleware("http")(add_request_id)

# Register API routers (NEW STANDARD)
app.include_router(health.router, prefix=API_PREFIX, tags=["Health"])
app.include_router(graph.router, prefix=API_PREFIX, tags=["Graph"])
app.include_router(tasks.router, prefix=API_PREFIX, tags=["Tasks"])
app.include_router(device.router, prefix=API_PREFIX, tags=["Device"])
app.include_router(config_api.router, prefix=API_PREFIX, tags=["Config"])
app.include_router(workflow.router)  # Already has prefix
app.include_router(websocket.router, tags=["WebSocket"])

# Debug router — only available in development (exposes internal state)
if not _is_production:
    from api.debug import router as debug_router  # noqa: E402
    app.include_router(debug_router, prefix=API_PREFIX, tags=["Debug"])
    logger.info("Debug endpoints enabled (development mode)")
else:
    logger.info("Debug endpoints disabled (production mode)")

# Sensitive action policy router
from api.sensitive_policy import router as sensitive_policy_router  # noqa: E402
app.include_router(sensitive_policy_router, prefix=API_PREFIX, tags=["Security Policy"])

# Register modular routers from api_handlers
from api_handlers.device_router import router as device_router  # noqa: E402
from api_handlers.task_router import router as task_router  # noqa: E402
from api_handlers.websocket_router import router as websocket_router  # noqa: E402

# Optional test router (for local development only)
try:
    from test_ui_justfortest.test_router_justfortest import (
        router as test_router,
    )  # noqa: E402

    _test_router_available = True
except ImportError:
    _test_router_available = False

# BACKWARD COMPATIBILITY: Register at root for legacy Android app
app.include_router(device_router, prefix="", tags=["Device Management (Legacy)"])
app.include_router(task_router, prefix="", tags=["Task Execution (Legacy)"])
app.include_router(websocket_router)

if _test_router_available:
    app.include_router(test_router)

logger.info(" Modular API routers registered (with legacy support)")

# Register Real Accessibility API routes
try:
    from api_handlers.real_accessibility_api import (
        router as accessibility_router,
    )  # noqa: E402

    # Register at /accessibility for Android app compatibility
    app.include_router(
        accessibility_router, prefix="/accessibility", tags=["Real Accessibility"]
    )
    # Also register with API prefix for new standard
    app.include_router(
        accessibility_router,
        prefix=f"{API_PREFIX}/accessibility",
        tags=["Real Accessibility (Versioned)"],
    )
    logger.info(" Real Accessibility API routes registered (legacy + versioned)")
except ImportError as e:
    logger.warning(f"Could not register Real Accessibility API routes: {e}")

# Register exception handlers
register_exception_handlers(app)


@app.get("/")
@limiter.limit("30/minute")
async def root(request: Request):
    """Root endpoint - serve AURA Professional UI"""
    try:
        import aiofiles

        try:
            async with aiofiles.open(
                "aura_professional_ui.html", "r", encoding="utf-8"
            ) as f:
                content = await f.read()
            logger.info("Served AURA Professional UI successfully")
            return HTMLResponse(content=content)
        except FileNotFoundError:
            logger.warning("UI file not found, serving fallback")
            return HTMLResponse(content=get_fallback_ui(), status_code=200)

    except Exception as e:
        logger.error(f"Root endpoint error: {e}")
        return HTMLResponse(content=get_fallback_ui(), status_code=200)


# Legacy health endpoint for backward compatibility
@app.get("/health")
@limiter.limit("60/minute")
async def health_check_legacy(request: Request):
    """Legacy health check endpoint (redirects to versioned endpoint)."""
    from api.health import health_check

    return await health_check(request)


@app.get("/test")
async def test_suite(request: Request):
    """Serve the AURA Testing Suite dashboard."""
    try:
        import aiofiles
        async with aiofiles.open("static/test_suite.html", "r", encoding="utf-8") as f:
            content = await f.read()
        return HTMLResponse(content=content)
    except FileNotFoundError:
        return HTMLResponse(content="<h1>Test suite not found</h1>", status_code=404)


def run_server() -> None:
    """Run the AURA backend server with production-ready configuration."""
    try:
        logger.info(f"🚀 Starting AURA server on {settings.host}:{settings.port}")
        logger.info(f"   Environment: {settings.environment}")
        logger.info("   API Version: v1")

        uvicorn.run(
            "main:app",
            host=settings.host,
            port=settings.port,
            reload=settings.reload and settings.environment != "production",
            log_level=settings.log_level.lower(),
            workers=1,
            access_log=True,
            use_colors=True,
            loop="asyncio",
            timeout_keep_alive=30,
            limit_concurrency=100,
        )

    except KeyboardInterrupt:
        logger.info(" Server shutdown requested")
    except Exception as e:
        logger.error(f" Failed to start server: {e}")
        raise


if __name__ == "__main__":
    run_server()
