from fastapi import APIRouter
import httpx
import os
from app.config import OLLAMA_MODEL, OLLAMA_ANALYSIS_MODEL, ANKI_CONNECT_URL
from app.services.ollama import get_embedding_cache_stats

router = APIRouter(prefix="/api", tags=["health"])

@router.get("/health")
async def health():
    return {
        "status": "ok",
        "llm_model": OLLAMA_MODEL or "(auto-detect)",
        "analysis_model": OLLAMA_ANALYSIS_MODEL or "(auto-detect)",
        "anki_connect_url": ANKI_CONNECT_URL,  # ajuda debug
    }

@router.get("/cache-stats")
async def cache_stats():
    """Get embedding cache statistics for monitoring."""
    return {
        "embedding_cache": get_embedding_cache_stats()
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


@router.get("/ollama-info")
async def ollama_info():
    """
    Retorna informações detalhadas do Ollama:
    - Modelos disponíveis (via /api/tags)
    - Modelos em execução com uso de VRAM (via /api/ps)
    - Detecção de GPU vs CPU
    """
    host = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
    result = {
        "connected": False,
        "host": host,
        "models": [],
        "running_models": [],
        "gpu_info": {
            "using_gpu": False,
            "vram_used_mb": 0
        }
    }

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            # 1. Buscar modelos disponíveis via /api/tags
            tags_resp = await client.get(f"{host}/api/tags")
            if tags_resp.status_code == 200:
                tags_data = tags_resp.json() or {}
                result["connected"] = True
                for m in tags_data.get("models", []):
                    model_info = {
                        "name": m.get("name"),
                        "size": m.get("size"),
                        "parameter_size": m.get("details", {}).get("parameter_size"),
                        "quantization": m.get("details", {}).get("quantization_level"),
                        "family": m.get("details", {}).get("family"),
                    }
                    result["models"].append(model_info)

            # 2. Buscar modelos em execução via /api/ps (info de VRAM)
            ps_resp = await client.get(f"{host}/api/ps")
            if ps_resp.status_code == 200:
                ps_data = ps_resp.json() or {}
                for model in ps_data.get("models", []):
                    size_vram = model.get("size_vram", 0)
                    size_total = model.get("size", 0)

                    running_info = {
                        "name": model.get("name"),
                        "size_vram_bytes": size_vram,
                        "size_vram_mb": round(size_vram / (1024 * 1024), 1) if size_vram else 0,
                        "size_total_bytes": size_total,
                        "expires_at": model.get("expires_at"),
                        "using_gpu": size_vram > 0
                    }
                    result["running_models"].append(running_info)

                    # Atualizar info de GPU agregada
                    if size_vram > 0:
                        result["gpu_info"]["using_gpu"] = True
                        result["gpu_info"]["vram_used_mb"] += running_info["size_vram_mb"]

    except Exception as e:
        result["error"] = str(e)

    return result
