from fastapi import APIRouter
import httpx
from app.config import OLLAMA_MODEL, OLLAMA_ANALYSIS_MODEL, ANKI_CONNECT_URL

router = APIRouter(prefix="/api", tags=["health"])

@router.get("/health")
async def health():
    return {
        "status": "ok",
        "llm_model": OLLAMA_MODEL,
        "analysis_model": OLLAMA_ANALYSIS_MODEL,
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
