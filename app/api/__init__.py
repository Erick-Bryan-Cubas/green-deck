from .health import router as health_router
from .anki import router as anki_router
from .flashcards import router as flashcards_router
from .history import router as history_router
from .dashboard import router as dashboard_router
from .models import router as models_router
from .websocket import router as websocket_router, start_broadcaster, stop_broadcaster

__all__ = [
    "health_router",
    "anki_router",
    "flashcards_router",
    "history_router",
    "dashboard_router",
    "models_router",
    "websocket_router",
    "start_broadcaster",
    "stop_broadcaster",
]
