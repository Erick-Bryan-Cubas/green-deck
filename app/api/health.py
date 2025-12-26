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
    url = (ANKI_CONNECT_URL or "http://127.0.0.1:8765").rstrip("/")
    payload = {"action": "version", "version": 6}

    try:
        async with httpx.AsyncClient(timeout=2.5) as client:
            r = await client.post(url, json=payload)
            r.raise_for_status()
            data = r.json() or {}

            ok = (data.get("error") is None) and (data.get("result") is not None)
            if ok:
                return {"connected": True, "version": data["result"], "url": url}

            return {"connected": False, "url": url, "error": data.get("error")}
    except Exception as e:
        return {"connected": False, "url": url, "error": str(e)}


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
