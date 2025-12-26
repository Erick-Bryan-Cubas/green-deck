from .health import router as health_router
from .anki import router as anki_router
from .flashcards import router as flashcards_router
from .history import router as history_router
from .dashboard import router as dashboard_router

__all__ = [
    "health_router",
    "anki_router",
    "flashcards_router",
    "history_router",
    "dashboard_router",
]
