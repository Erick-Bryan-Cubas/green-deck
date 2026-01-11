from fastapi import APIRouter, Header
from typing import Optional
import httpx
import re
import asyncio
import time
import logging

from app.config import OLLAMA_HOST

router = APIRouter()
logger = logging.getLogger(__name__)

# =============================================================================
# Cache de modelos por provider
# =============================================================================

_MODELS_CACHE: dict[str, set[str]] = {
    "ollama": set(),
    "openai": set(),
    "perplexity": set(),
    "anthropic": set(),
}
_CACHE_TIMESTAMP: float = 0
_CACHE_TTL: float = 300  # 5 minutos

# Armazena as chaves API para refresh do cache
_API_KEYS: dict[str, Optional[str]] = {
    "openai": None,
    "perplexity": None,
    "anthropic": None,
}

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


# =============================================================================
# Funções de cache de modelos
# =============================================================================

async def _fetch_ollama_models() -> set[str]:
    """Busca modelos disponíveis no Ollama local."""
    models = set()
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(f"{OLLAMA_HOST}/api/tags")
            if r.status_code == 200:
                data = r.json()
                for m in data.get("models", []):
                    models.add(m["name"])
    except Exception as e:
        logger.debug("Failed to fetch Ollama models: %s", e)
    return models


async def _fetch_openai_models(api_key: str) -> set[str]:
    """Busca modelos disponíveis na API OpenAI."""
    models = set()
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            if r.status_code == 200:
                data = r.json()
                for m in data.get("data", []):
                    models.add(m["id"])
    except Exception as e:
        logger.debug("Failed to fetch OpenAI models: %s", e)
    return models


async def _fetch_perplexity_models() -> set[str]:
    """Busca modelos disponíveis na Perplexity."""
    try:
        p_models = await fetch_perplexity_models_from_docs()
        if p_models:
            return set(p_models)
    except Exception as e:
        logger.debug("Failed to fetch Perplexity models: %s", e)
    return set(PERPLEXITY_FALLBACK_MODELS)


async def refresh_models_cache(
    openai_key: Optional[str] = None,
    perplexity_key: Optional[str] = None,
    force: bool = False,
) -> None:
    """
    Atualiza o cache de modelos disponíveis por provider.

    Args:
        openai_key: Chave API da OpenAI (opcional)
        perplexity_key: Chave API da Perplexity (opcional)
        force: Se True, força atualização mesmo se cache ainda válido
    """
    global _MODELS_CACHE, _CACHE_TIMESTAMP, _API_KEYS

    # Atualiza chaves armazenadas
    if openai_key:
        _API_KEYS["openai"] = openai_key
    if perplexity_key:
        _API_KEYS["perplexity"] = perplexity_key

    # Verifica se cache ainda é válido
    now = time.time()
    if not force and (now - _CACHE_TIMESTAMP) < _CACHE_TTL and _MODELS_CACHE["ollama"]:
        return

    logger.debug("Refreshing models cache...")

    async def _empty_set() -> set[str]:
        return set()

    # Busca modelos em paralelo
    tasks = [_fetch_ollama_models()]

    if _API_KEYS["openai"]:
        tasks.append(_fetch_openai_models(_API_KEYS["openai"]))
    else:
        tasks.append(_empty_set())

    if _API_KEYS["perplexity"]:
        tasks.append(_fetch_perplexity_models())
    else:
        tasks.append(_empty_set())

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Atualiza cache
    if not isinstance(results[0], Exception):
        _MODELS_CACHE["ollama"] = results[0]
    if not isinstance(results[1], Exception) and results[1]:
        _MODELS_CACHE["openai"] = results[1]
    if not isinstance(results[2], Exception) and results[2]:
        _MODELS_CACHE["perplexity"] = results[2]

    _CACHE_TIMESTAMP = now
    logger.debug(
        "Models cache updated: ollama=%d, openai=%d, perplexity=%d",
        len(_MODELS_CACHE["ollama"]),
        len(_MODELS_CACHE["openai"]),
        len(_MODELS_CACHE["perplexity"]),
    )


def get_provider_for_model(
    model_name: str,
    openai_key: Optional[str] = None,
    perplexity_key: Optional[str] = None,
) -> str:
    """
    Determina o provider de um modelo baseado no cache.

    Ordem de verificação:
    1. Verifica se está no cache de cada provider
    2. Se não encontrar, usa heurística baseada no nome (fallback)

    Returns:
        "ollama", "openai" ou "perplexity"
    """
    if not model_name:
        return "ollama"

    # Verifica no cache (ordem: ollama primeiro, pois é local)
    if model_name in _MODELS_CACHE["ollama"]:
        return "ollama"
    if model_name in _MODELS_CACHE["openai"]:
        return "openai"
    if model_name in _MODELS_CACHE["perplexity"]:
        return "perplexity"

    # Fallback: heurística baseada no nome
    name_lower = model_name.lower()

    # Modelos OpenAI (gpt-*, o1-*, text-embedding-*)
    if openai_key and ("gpt" in name_lower or model_name.startswith("o1-") or "text-embedding" in name_lower):
        return "openai"

    # Modelos Perplexity (sonar*)
    if perplexity_key and "sonar" in name_lower:
        return "perplexity"

    # Default: assume Ollama (modelos locais)
    return "ollama"


# Modelos Anthropic conhecidos (fallback)
ANTHROPIC_FALLBACK_MODELS = [
    "claude-3-5-sonnet-20241022",
    "claude-3-5-haiku-20241022",
    "claude-3-opus-20240229",
    "claude-3-sonnet-20240229",
    "claude-3-haiku-20240307",
]


@router.get("/api/all-models")
async def get_all_models(
    openai_api_key: Optional[str] = Header(None, alias="X-OpenAI-Key"),
    perplexity_api_key: Optional[str] = Header(None, alias="X-Perplexity-Key"),
    anthropic_api_key: Optional[str] = Header(None, alias="X-Anthropic-Key"),
):
    global _MODELS_CACHE, _CACHE_TIMESTAMP, _API_KEYS

    models = []
    ollama_names = set()
    openai_names = set()
    perplexity_names = set()
    anthropic_names = set()

    # Armazena chaves API para uso futuro no cache
    if openai_api_key:
        _API_KEYS["openai"] = openai_api_key
    if perplexity_api_key:
        _API_KEYS["perplexity"] = perplexity_api_key
    if anthropic_api_key:
        _API_KEYS["anthropic"] = anthropic_api_key

    # Ollama models
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(f"{OLLAMA_HOST}/api/tags")
            if r.status_code == 200:
                data = r.json()
                for m in data.get("models", []):
                    name = m["name"]
                    ollama_names.add(name)
                    model_type = "embedding" if is_embedding_model(name) else "llm"
                    models.append({
                        "name": name,
                        "provider": "ollama",
                        "type": model_type
                    })
    except Exception:
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
                        openai_names.add(model_id)
                        # OpenAI: text-embedding-* são modelos de embedding
                        if "embedding" in model_id.lower():
                            models.append({
                                "name": model_id,
                                "provider": "openai",
                                "type": "embedding"
                            })
                        elif "gpt" in model_id.lower() or model_id.startswith("o1-"):
                            models.append({
                                "name": model_id,
                                "provider": "openai",
                                "type": "llm"
                            })
        except Exception:
            pass

    # Perplexity models (best-effort via docs + fallback)
    if perplexity_api_key:
        try:
            p_models = await fetch_perplexity_models_from_docs()
            if not p_models:
                p_models = PERPLEXITY_FALLBACK_MODELS
        except Exception:
            p_models = PERPLEXITY_FALLBACK_MODELS

        perplexity_names = set(p_models)

        # Perplexity models são todos LLMs (não têm modelos de embedding)
        models.extend({
            "name": name,
            "provider": "perplexity",
            "type": "llm"
        } for name in p_models)

    # Anthropic models (usa lista conhecida se chave fornecida)
    if anthropic_api_key:
        anthropic_names = set(ANTHROPIC_FALLBACK_MODELS)
        models.extend({
            "name": name,
            "provider": "anthropic",
            "type": "llm"
        } for name in ANTHROPIC_FALLBACK_MODELS)

    # Atualiza cache com os modelos encontrados
    _MODELS_CACHE["ollama"] = ollama_names
    if openai_names:
        _MODELS_CACHE["openai"] = openai_names
    if perplexity_names:
        _MODELS_CACHE["perplexity"] = perplexity_names
    if anthropic_names:
        _MODELS_CACHE["anthropic"] = anthropic_names
    _CACHE_TIMESTAMP = time.time()

    logger.debug(
        "Models cache updated via /all-models: ollama=%d, openai=%d, perplexity=%d, anthropic=%d",
        len(ollama_names), len(openai_names), len(perplexity_names), len(anthropic_names),
    )

    return {"models": models}
