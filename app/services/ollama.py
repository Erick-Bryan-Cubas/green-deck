import httpx
import json
import numpy as np
from typing import Optional, List
from app.config import OLLAMA_GENERATE_URL, OLLAMA_EMBED_URL

async def ollama_generate_stream(model: str, prompt: str, *, system: Optional[str] = None, options: Optional[dict] = None):
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": True,
    }
    if system:
        payload["system"] = system
    if options:
        payload["options"] = options

    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream("POST", OLLAMA_GENERATE_URL, json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                data = json.loads(line)
                if data.get("response"):
                    yield data["response"]
                if data.get("done"):
                    break

async def ollama_embed(model: str, text: str) -> List[float]:
    payload = {"model": model, "input": text}
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(OLLAMA_EMBED_URL, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data.get("embeddings", [[]])[0]

def cosine_similarity(a: List[float], b: List[float]) -> float:
    a_arr = np.array(a)
    b_arr = np.array(b)
    return float(np.dot(a_arr, b_arr) / (np.linalg.norm(a_arr) * np.linalg.norm(b_arr)))

def chunk_text(text: str, chunk_size: int = 500) -> List[str]:
    words = text.split()
    chunks = []
    for i in range(0, len(words), chunk_size):
        chunks.append(" ".join(words[i:i + chunk_size]))
    return chunks
