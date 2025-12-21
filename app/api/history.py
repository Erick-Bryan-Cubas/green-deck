from fastapi import APIRouter
from app.services.storage import get_recent_analyses, get_recent_cards, get_stats

router = APIRouter(prefix="/api", tags=["history"])

@router.get("/history/analyses")
async def get_analyses_history(limit: int = 10):
    return {"analyses": get_recent_analyses(limit)}

@router.get("/history/cards")
async def get_cards_history(limit: int = 10):
    return {"cards": get_recent_cards(limit)}

@router.get("/history/stats")
async def get_history_stats():
    return get_stats()
