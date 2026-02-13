import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import (
    anki_router,
    dashboard_router,
    documents_router,
    flashcards_router,
    health_router,
    history_router,
    models_router,
    questions_router,
    start_broadcaster,
    stop_broadcaster,
    websocket_router,
)
from app.config import CORS_ORIGINS, ENVIRONMENT
from app.middleware.security import SecurityHeadersMiddleware
from app.middleware.rate_limit import setup_rate_limiting


class AnkiStatusFilter(logging.Filter):
    def filter(self, record):
        msg = record.getMessage()
        return (
            "/api/anki-status" not in msg
            and "/api/ollama-status" not in msg
            and "/api/health/anki" not in msg
            and "/api/health/ollama" not in msg
            and "/ws/status" not in msg
            and "http://127.0.0.1:8765" not in msg
            and "http://host.docker.internal:8765" not in msg
            and "http://127.0.0.1:11434/api/tags" not in msg
            and "http://host.docker.internal:11434" not in msg
        )

logging.basicConfig(level=logging.INFO)
logging.getLogger("uvicorn.access").addFilter(AnkiStatusFilter())
logging.getLogger("httpx").addFilter(AnkiStatusFilter())

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: start WebSocket broadcaster
    await start_broadcaster()
    yield
    # Shutdown: stop WebSocket broadcaster
    await stop_broadcaster()

app = FastAPI(title="Green Deck", version="1.3.2-beta", lifespan=lifespan)

# Rate Limiting (must be configured before middlewares)
setup_rate_limiting(app)

# Security Headers Middleware (must be added before CORS)
app.add_middleware(SecurityHeadersMiddleware)

# CORS - Configured with specific origins instead of wildcard
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "X-API-Key",
        "X-OpenAI-Key",
        "X-Perplexity-Key",
        "X-Anthropic-Key",
    ],
)

# Routers
app.include_router(health_router)
app.include_router(anki_router)
app.include_router(flashcards_router)
app.include_router(questions_router)
app.include_router(history_router)
app.include_router(dashboard_router)
app.include_router(models_router)
app.include_router(websocket_router)
app.include_router(documents_router)

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Handle uncaught exceptions with sanitized error messages."""
    logger.exception("Unhandled exception on %s: %s", request.url.path, exc)

    # In development, show full error details
    if ENVIRONMENT == "development":
        return JSONResponse(
            status_code=500,
            content={"detail": str(exc), "type": type(exc).__name__},
        )

    # In production, return generic error message
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal error occurred. Please try again later."},
    )


@app.exception_handler(StarletteHTTPException)
async def spa_fallback(request: Request, exc: StarletteHTTPException):
    """Handle HTTP exceptions and SPA routing fallback."""
    if exc.status_code == 404 and not request.url.path.startswith("/api"):
        return FileResponse("frontend/dist/index.html", headers={"Cache-Control": "no-cache"})

    # Sanitize error details in production
    detail = exc.detail
    if ENVIRONMENT != "development" and isinstance(detail, str):
        # Remove potentially sensitive information
        sensitive_patterns = ["traceback", "file", "path", "line", "stack"]
        if any(pattern in detail.lower() for pattern in sensitive_patterns):
            detail = "Request could not be processed"

    return JSONResponse(status_code=exc.status_code, content={"detail": detail})

# Static files
app.mount("/", StaticFiles(directory="frontend/dist"), name="static")
