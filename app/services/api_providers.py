# app/services/api_providers.py
import httpx
import json
from typing import Optional, AsyncGenerator

async def openai_generate_stream(
    api_key: str,
    model: str,
    prompt: str,
    system: Optional[str] = None,
    options: Optional[dict] = None
) -> AsyncGenerator[str, None]:
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
    
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream("POST", "https://api.openai.com/v1/chat/completions", headers=headers, json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.strip() or line.strip() == "data: [DONE]":
                    continue
                if line.startswith("data: "):
                    try:
                        data = json.loads(line[6:])
                        if data.get("choices") and data["choices"][0].get("delta", {}).get("content"):
                            yield data["choices"][0]["delta"]["content"]
                    except:
                        continue

async def perplexity_generate_stream(
    api_key: str,
    model: str,
    prompt: str,
    system: Optional[str] = None,
    options: Optional[dict] = None
) -> AsyncGenerator[str, None]:
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
    
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream("POST", "https://api.perplexity.ai/chat/completions", headers=headers, json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.strip() or line.strip() == "data: [DONE]":
                    continue
                if line.startswith("data: "):
                    try:
                        data = json.loads(line[6:])
                        if data.get("choices") and data["choices"][0].get("delta", {}).get("content"):
                            yield data["choices"][0]["delta"]["content"]
                    except:
                        continue
