# app/api/health.py

from fastapi import APIRouter
import httpx

from app.config import (
    OLLAMA_MODEL,
    OLLAMA_ANALYSIS_MODEL,
    ANKI_CONNECT_URL,
    OLLAMA_HOST,
)

router = APIRouter(prefix="/api", tags=["health"])

@router.get("/ollama-status")
async def ollama_status():
    base = (OLLAMA_HOST or "").rstrip("/")
    if not base:
        return {"connected": False, "models": [], "host": ""}

    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            # Ollama: lista modelos disponíveis
            resp = await client.get(f"{base}/api/tags")
            resp.raise_for_status()
            data = resp.json() or {}

        raw = data.get("models") or []
        models = []
        for m in raw:
            name = (m or {}).get("name") or (m or {}).get("model")
            if name:
                models.append(name)

        return {"connected": True, "models": models, "host": base}
    except Exception:
        return {"connected": False, "models": [], "host": base}
