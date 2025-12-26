import httpx
from app.config import OLLAMA_HOST

@router.get("/api/ollama-status")
async def ollama_status():
    base = (OLLAMA_HOST or "").rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=1.5) as client:
            r = await client.get(f"{base}/api/tags")
            r.raise_for_status()
            data = r.json() or {}
            models = [
                m.get("name")
                for m in (data.get("models") or [])
                if isinstance(m, dict) and m.get("name")
            ]
            return {"connected": True, "host": base, "models": models}
    except Exception as e:
        return {"connected": False, "host": base, "models": [], "error": str(e)}
