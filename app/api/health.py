from fastapi import APIRouter
import httpx
import os
from app.config import OLLAMA_MODEL, OLLAMA_ANALYSIS_MODEL, ANKI_CONNECT_URL

router = APIRouter(prefix="/api", tags=["health"])

@router.get("/health")
async def health():
    return {
        "status": "ok",
        "llm_model": OLLAMA_MODEL,
        "analysis_model": OLLAMA_ANALYSIS_MODEL,
        "anki_connect_url": ANKI_CONNECT_URL,  # ajuda debug
    }

@router.get("/anki-status")
async def anki_status():
    try:
        async with httpx.AsyncClient(timeout=1.5) as client:
            r = await client.post(ANKI_CONNECT_URL, json={"action": "version", "version": 6})
            data = r.json()
            if data.get("result"):
                return {"connected": True, "version": data["result"]}
    except:
        pass
    return {"connected": False}

@router.get("/ollama-status")
async def ollama_status():
    # padrão do Ollama local
    host = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(f"{host}/api/tags")
            r.raise_for_status()
            data = r.json() or {}
            models = []
            for m in (data.get("models") or []):
                name = m.get("name")
                if name:
                    models.append(name)
            return {"connected": True, "host": host, "models": models}
    except Exception as e:
        return {"connected": False, "host": host, "models": [], "error": str(e)}
