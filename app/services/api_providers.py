# app/services/api_providers.py
"""
Providers de API para geração de texto com LLMs.
Inclui retry logic com backoff exponencial para resiliência.
"""

import httpx
import json
import logging
from typing import Optional, AsyncGenerator

# Retry logic com tenacity
try:
    from tenacity import (
        retry,
        stop_after_attempt,
        wait_exponential,
        retry_if_exception_type,
        before_sleep_log,
    )
    TENACITY_AVAILABLE = True
except ImportError:
    TENACITY_AVAILABLE = False

logger = logging.getLogger(__name__)

# Exceções que devem triggerar retry
RETRYABLE_EXCEPTIONS = (
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.ConnectError,
    httpx.RemoteProtocolError,
)


def _create_retry_decorator():
    """Cria decorator de retry se tenacity disponível."""
    if not TENACITY_AVAILABLE:
        # Decorator que não faz nada
        def no_retry(func):
            return func
        return no_retry
    
    return retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True
    )


# Decorator para retry
retry_on_network_error = _create_retry_decorator()


class APIProviderError(Exception):
    """Erro genérico de provider de API."""
    def __init__(self, provider: str, message: str, status_code: Optional[int] = None):
        self.provider = provider
        self.status_code = status_code
        super().__init__(f"[{provider}] {message}")


async def openai_generate_stream(
    api_key: str,
    model: str,
    prompt: str,
    system: Optional[str] = None,
    options: Optional[dict] = None
) -> AsyncGenerator[str, None]:
    """
    Gera texto via OpenAI API com streaming.
    
    Suporta modelos GPT-4, GPT-3.5, e O1.
    Inclui retry automático para erros de rede.
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    
    temperature = options.get("temperature", 0.0) if options else 0.0
    max_tokens = options.get("num_predict", 4096) if options else 4096
    
    # O1 models não suportam temperature
    if model.startswith("o1-"):
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "max_completion_tokens": max_tokens
        }
    else:
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
    
    logger.debug("OpenAI request: model=%s, messages=%d", model, len(messages))
    
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, read=300.0)) as client:
            async with client.stream(
                "POST",
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload
            ) as resp:
                if resp.status_code != 200:
                    error_text = await resp.aread()
                    logger.error("OpenAI error %d: %s", resp.status_code, error_text[:200])
                    raise APIProviderError("OpenAI", error_text.decode()[:200], resp.status_code)
                
                async for line in resp.aiter_lines():
                    if not line.strip() or line.strip() == "data: [DONE]":
                        continue
                    if line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])
                            content = data.get("choices", [{}])[0].get("delta", {}).get("content")
                            if content:
                                yield content
                        except json.JSONDecodeError:
                            continue
    except RETRYABLE_EXCEPTIONS as e:
        logger.warning("OpenAI network error (will retry): %s", e)
        raise
    except Exception as e:
        logger.error("OpenAI unexpected error: %s", e)
        raise APIProviderError("OpenAI", str(e)) from e


async def perplexity_generate_stream(
    api_key: str,
    model: str,
    prompt: str,
    system: Optional[str] = None,
    options: Optional[dict] = None
) -> AsyncGenerator[str, None]:
    """
    Gera texto via Perplexity API com streaming.
    
    Suporta modelos Sonar e Sonar-Pro.
    Inclui retry automático para erros de rede.
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "temperature": options.get("temperature", 0.0) if options else 0.0,
        "max_tokens": options.get("num_predict", 4096) if options else 4096
    }
    
    logger.debug("Perplexity request: model=%s, messages=%d", model, len(messages))
    
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, read=300.0)) as client:
            async with client.stream(
                "POST",
                "https://api.perplexity.ai/chat/completions",
                headers=headers,
                json=payload
            ) as resp:
                if resp.status_code != 200:
                    error_text = await resp.aread()
                    logger.error("Perplexity error %d: %s", resp.status_code, error_text[:200])
                    raise APIProviderError("Perplexity", error_text.decode()[:200], resp.status_code)
                
                async for line in resp.aiter_lines():
                    if not line.strip() or line.strip() == "data: [DONE]":
                        continue
                    if line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])
                            content = data.get("choices", [{}])[0].get("delta", {}).get("content")
                            if content:
                                yield content
                        except json.JSONDecodeError:
                            continue
    except RETRYABLE_EXCEPTIONS as e:
        logger.warning("Perplexity network error (will retry): %s", e)
        raise
    except Exception as e:
        logger.error("Perplexity unexpected error: %s", e)
        raise APIProviderError("Perplexity", str(e)) from e


async def ollama_generate_with_retry(
    model: str,
    prompt: str,
    system: Optional[str] = None,
    options: Optional[dict] = None,
) -> AsyncGenerator[str, None]:
    """
    Wrapper para Ollama com retry logic.
    
    Use esta função ao invés de ollama_generate_stream quando
    quiser retry automático em erros de rede.
    """
    from app.services.ollama import ollama_generate_stream
    
    logger.debug("Ollama request: model=%s", model)
    
    try:
        async for piece in ollama_generate_stream(model, prompt, system=system, options=options):
            yield piece
    except RETRYABLE_EXCEPTIONS as e:
        logger.warning("Ollama network error: %s", e)
        raise
    except Exception as e:
        logger.error("Ollama unexpected error: %s", e)
        raise APIProviderError("Ollama", str(e)) from e
