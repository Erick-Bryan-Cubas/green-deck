import httpx
import json
import re
import logging
import numpy as np
from typing import Optional, List

from app.config import OLLAMA_GENERATE_URL, OLLAMA_EMBED_URL
from app.services.embedding_cache import cached_embed, cached_embed_batch, get_embedding_cache

logger = logging.getLogger(__name__)

# =============================================================================
# Chunking Semântico com Overlap
# =============================================================================

try:
    import nltk
    from nltk.tokenize import sent_tokenize as _nltk_sent_tokenize
    
    # Tenta baixar o tokenizer se não existir
    try:
        nltk.data.find('tokenizers/punkt_tab')
    except LookupError:
        try:
            nltk.download('punkt_tab', quiet=True)
        except Exception:
            pass
    
    def _sent_tokenize(text: str, language: str = "portuguese") -> List[str]:
        """Tokeniza texto em sentenças usando NLTK."""
        try:
            return _nltk_sent_tokenize(text, language=language)
        except Exception:
            # Fallback para inglês se português falhar
            try:
                return _nltk_sent_tokenize(text, language="english")
            except Exception:
                # Fallback para regex simples
                return _regex_sent_tokenize(text)
except ImportError:
    _nltk_sent_tokenize = None
    
    def _sent_tokenize(text: str, language: str = "portuguese") -> List[str]:
        return _regex_sent_tokenize(text)


def _regex_sent_tokenize(text: str) -> List[str]:
    """Fallback: tokenização por regex quando NLTK não disponível."""
    text = re.sub(r'\s+', ' ', text).strip()
    if not text:
        return []
    # Split em pontuação final, mantendo abreviações comuns
    parts = re.split(r'(?<=[.!?])\s+(?=[A-ZÁÀÂÃÉÈÊÍÏÓÔÕÖÚÇ])', text)
    return [p.strip() for p in parts if p.strip()]


def chunk_text_semantic(
    text: str,
    max_words: int = 400,
    overlap_sentences: int = 2,
    language: str = "portuguese"
) -> List[str]:
    """
    Chunking semântico baseado em sentenças com overlap.
    
    Args:
        text: Texto a ser dividido
        max_words: Máximo de palavras por chunk
        overlap_sentences: Número de sentenças de overlap entre chunks
        language: Idioma para tokenização ('portuguese' ou 'english')
    
    Returns:
        Lista de chunks com overlap semântico
    """
    text = re.sub(r'\s+', ' ', (text or '')).strip()
    if not text:
        return []
    
    sentences = _sent_tokenize(text, language)
    if not sentences:
        # Fallback para chunking simples se não conseguir tokenizar
        return chunk_text(text, chunk_size=max_words)
    
    chunks: List[str] = []
    current_chunk: List[str] = []
    current_word_count = 0
    
    for sentence in sentences:
        sentence_words = len(sentence.split())
        
        # Se adicionar esta sentença exceder o limite
        if current_word_count + sentence_words > max_words and current_chunk:
            # Salva o chunk atual
            chunks.append(' '.join(current_chunk))
            
            # Mantém as últimas N sentenças para overlap
            if overlap_sentences > 0 and len(current_chunk) >= overlap_sentences:
                overlap = current_chunk[-overlap_sentences:]
                current_chunk = overlap.copy()
                current_word_count = sum(len(s.split()) for s in current_chunk)
            else:
                current_chunk = []
                current_word_count = 0
        
        current_chunk.append(sentence)
        current_word_count += sentence_words
    
    # Adiciona o último chunk
    if current_chunk:
        chunks.append(' '.join(current_chunk))
    
    # Remove chunks duplicados mantendo ordem
    seen = set()
    unique_chunks = []
    for chunk in chunks:
        chunk_key = chunk.strip().lower()
        if chunk_key not in seen:
            seen.add(chunk_key)
            unique_chunks.append(chunk)
    
    logger.debug(
        "Semantic chunking: %d sentences -> %d chunks (max_words=%d, overlap=%d)",
        len(sentences), len(unique_chunks), max_words, overlap_sentences
    )
    
    return unique_chunks


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

async def _ollama_embed_raw(model: str, text: str) -> List[float]:
    """Raw embedding call without caching."""
    payload = {"model": model, "input": text}
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(OLLAMA_EMBED_URL, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data.get("embeddings", [[]])[0]

async def ollama_embed(model: str, text: str) -> List[float]:
    """Get embedding with caching for improved performance."""
    return await cached_embed(model, text, _ollama_embed_raw)

async def ollama_embed_batch(model: str, texts: List[str]) -> List[List[float]]:
    """Get embeddings for multiple texts with caching."""
    return await cached_embed_batch(model, texts, _ollama_embed_raw)

def get_embedding_cache_stats() -> dict:
    """Get statistics about the embedding cache."""
    return get_embedding_cache().stats()

def cosine_similarity(a: List[float], b: List[float]) -> float:
    a_arr = np.array(a)
    b_arr = np.array(b)
    norm_a = np.linalg.norm(a_arr)
    norm_b = np.linalg.norm(b_arr)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a_arr, b_arr) / (norm_a * norm_b))


def chunk_text(text: str, chunk_size: int = 500) -> List[str]:
    """Chunking simples por palavras (legacy, para compatibilidade)."""
    words = text.split()
    chunks = []
    for i in range(0, len(words), chunk_size):
        chunks.append(" ".join(words[i:i + chunk_size]))
    return chunks
