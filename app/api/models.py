from fastapi import APIRouter, Header
from typing import Optional
import httpx
import re
import asyncio

from app.config import OLLAMA_HOST

router = APIRouter()

PERPLEXITY_MODEL_DOC_PAGES = [
    "https://docs.perplexity.ai/getting-started/models/models/sonar",
    "https://docs.perplexity.ai/getting-started/models/models/sonar-pro",
    "https://docs.perplexity.ai/getting-started/models/models/sonar-reasoning-pro",
]

# fallback seguro (caso scraping falhe)
PERPLEXITY_FALLBACK_MODELS = [
    "sonar",
    "sonar-pro",
    "sonar-reasoning-pro",
]

async def fetch_perplexity_models_from_docs() -> list[str]:
    async with httpx.AsyncClient(timeout=6.0, follow_redirects=True) as client:
        tasks = [client.get(url) for url in PERPLEXITY_MODEL_DOC_PAGES]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    found = set()
    pattern = re.compile(r'"model"\s*:\s*"([^"]+)"')

    for r in results:
        if isinstance(r, Exception):
            continue
        if r.status_code != 200:
            continue
        for m in pattern.findall(r.text):
            found.add(m)

    return sorted(found)

@router.get("/api/all-models")
async def get_all_models(
    openai_api_key: Optional[str] = Header(None, alias="X-OpenAI-Key"),
    perplexity_api_key: Optional[str] = Header(None, alias="X-Perplexity-Key"),
):
    models = []

    # Ollama models
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(f"{OLLAMA_HOST}/api/tags")
            if r.status_code == 200:
                data = r.json()
                models.extend(
                    {"name": m["name"], "provider": "ollama"}
                    for m in data.get("models", [])
                )
    except:
        pass

    # OpenAI models
    if openai_api_key:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {openai_api_key}"},
                )
                if r.status_code == 200:
                    data = r.json()
                    models.extend(
                        {"name": m["id"], "provider": "openai"}
                        for m in data.get("data", [])
                        if "gpt" in m["id"].lower()
                    )
        except:
            pass

    # Perplexity models (best-effort via docs + fallback)
    if perplexity_api_key:
        try:
            p_models = await fetch_perplexity_models_from_docs()
            if not p_models:
                p_models = PERPLEXITY_FALLBACK_MODELS
        except:
            p_models = PERPLEXITY_FALLBACK_MODELS

        models.extend({"name": name, "provider": "perplexity"} for name in p_models)

    return {"models": models}
