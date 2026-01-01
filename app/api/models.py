from fastapi import APIRouter, Header
from typing import Optional
import httpx
import re
import asyncio

from app.config import OLLAMA_HOST

router = APIRouter()

# Padrões conhecidos de modelos de embedding
EMBEDDING_MODEL_PATTERNS = [
    r"embed",
    r"nomic",
    r"mxbai",
    r"bge-",
    r"gte-",
    r"e5-",
    r"multilingual-e5",
    r"sentence-",
    r"all-minilm",
    r"instructor",
    r"jina-embeddings",
    r"snowflake-arctic-embed",
]

def is_embedding_model(model_name: str) -> bool:
    """Detecta se um modelo é de embedding baseado no nome."""
    name_lower = model_name.lower()
    for pattern in EMBEDDING_MODEL_PATTERNS:
        if re.search(pattern, name_lower):
            return True
    return False

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
                for m in data.get("models", []):
                    name = m["name"]
                    model_type = "embedding" if is_embedding_model(name) else "llm"
                    models.append({
                        "name": name,
                        "provider": "ollama",
                        "type": model_type
                    })
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
                    for m in data.get("data", []):
                        model_id = m["id"]
                        # OpenAI: text-embedding-* são modelos de embedding
                        if "embedding" in model_id.lower():
                            models.append({
                                "name": model_id,
                                "provider": "openai",
                                "type": "embedding"
                            })
                        elif "gpt" in model_id.lower():
                            models.append({
                                "name": model_id,
                                "provider": "openai",
                                "type": "llm"
                            })
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

        # Perplexity models são todos LLMs (não têm modelos de embedding)
        models.extend({
            "name": name,
            "provider": "perplexity",
            "type": "llm"
        } for name in p_models)

    return {"models": models}
