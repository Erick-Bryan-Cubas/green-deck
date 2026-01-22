"""Rate limiting middleware for FastAPI using slowapi."""

import logging
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.requests import Request

from app.config import RATE_LIMIT_DEFAULT, RATE_LIMIT_GENERATE

logger = logging.getLogger(__name__)


def get_client_ip(request: Request) -> str:
    """
    Get client IP address from request.
    Handles X-Forwarded-For header for proxied requests.
    """
    # Check for X-Forwarded-For header (from proxy/load balancer)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # Take the first IP in the chain (original client)
        return forwarded_for.split(",")[0].strip()

    # Check for X-Real-IP header
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip

    # Fallback to direct connection IP
    return get_remote_address(request)


# Create limiter instance with default rate limits
limiter = Limiter(
    key_func=get_client_ip,
    default_limits=[RATE_LIMIT_DEFAULT],
    storage_uri="memory://",
    strategy="fixed-window",
)


def setup_rate_limiting(app):
    """
    Configure rate limiting for the FastAPI application.

    Args:
        app: FastAPI application instance
    """
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
    logger.info("Rate limiting configured with default limit: %s", RATE_LIMIT_DEFAULT)


# Export limiter for use with @limiter.limit() decorator in routes
__all__ = ["limiter", "setup_rate_limiting", "RATE_LIMIT_DEFAULT", "RATE_LIMIT_GENERATE"]
