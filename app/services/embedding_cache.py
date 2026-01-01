# app/services/embedding_cache.py
"""
Cache de embeddings para evitar recomputar embeddings para textos já processados.
Usa cache em memória com LRU e persistência opcional em DuckDB.
"""
import hashlib
import time
from collections import OrderedDict
from typing import List, Optional, Tuple
import threading

# Configuration
CACHE_MAX_SIZE = 1000  # Maximum entries in memory cache
CACHE_TTL_SECONDS = 3600 * 24  # 24 hours TTL

class EmbeddingCache:
    """
    Thread-safe LRU cache for embeddings with optional TTL.
    """
    
    def __init__(self, max_size: int = CACHE_MAX_SIZE, ttl_seconds: int = CACHE_TTL_SECONDS):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: OrderedDict[str, Tuple[List[float], float]] = OrderedDict()
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0
    
    def _make_key(self, model: str, text: str) -> str:
        """Generate a unique cache key from model and text."""
        content = f"{model}:{text}"
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
    
    def _is_expired(self, timestamp: float) -> bool:
        """Check if a cache entry has expired."""
        return (time.time() - timestamp) > self.ttl_seconds
    
    def get(self, model: str, text: str) -> Optional[List[float]]:
        """
        Get embedding from cache if available and not expired.
        
        Args:
            model: The embedding model name
            text: The text that was embedded
            
        Returns:
            The embedding vector or None if not in cache
        """
        key = self._make_key(model, text)
        
        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None
            
            embedding, timestamp = self._cache[key]
            
            if self._is_expired(timestamp):
                del self._cache[key]
                self._misses += 1
                return None
            
            # Move to end (most recently used)
            self._cache.move_to_end(key)
            self._hits += 1
            return embedding
    
    def set(self, model: str, text: str, embedding: List[float]) -> None:
        """
        Store embedding in cache.
        
        Args:
            model: The embedding model name
            text: The text that was embedded
            embedding: The embedding vector
        """
        key = self._make_key(model, text)
        
        with self._lock:
            # Remove oldest if at capacity
            while len(self._cache) >= self.max_size:
                self._cache.popitem(last=False)
            
            self._cache[key] = (embedding, time.time())
    
    def get_batch(self, model: str, texts: List[str]) -> Tuple[List[Optional[List[float]]], List[int]]:
        """
        Get multiple embeddings from cache.
        
        Args:
            model: The embedding model name
            texts: List of texts to look up
            
        Returns:
            Tuple of (list of embeddings/None, list of indices that need computation)
        """
        results = []
        missing_indices = []
        
        for i, text in enumerate(texts):
            embedding = self.get(model, text)
            results.append(embedding)
            if embedding is None:
                missing_indices.append(i)
        
        return results, missing_indices
    
    def set_batch(self, model: str, texts: List[str], embeddings: List[List[float]]) -> None:
        """
        Store multiple embeddings in cache.
        
        Args:
            model: The embedding model name
            texts: List of texts
            embeddings: List of corresponding embeddings
        """
        for text, embedding in zip(texts, embeddings):
            self.set(model, text, embedding)
    
    def clear(self) -> None:
        """Clear all cached embeddings."""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0
    
    def stats(self) -> dict:
        """Get cache statistics."""
        with self._lock:
            total = self._hits + self._misses
            hit_rate = (self._hits / total * 100) if total > 0 else 0
            return {
                "size": len(self._cache),
                "max_size": self.max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate_pct": round(hit_rate, 2),
                "ttl_seconds": self.ttl_seconds
            }
    
    def prune_expired(self) -> int:
        """Remove expired entries. Returns count of removed entries."""
        removed = 0
        with self._lock:
            expired_keys = [
                key for key, (_, ts) in self._cache.items()
                if self._is_expired(ts)
            ]
            for key in expired_keys:
                del self._cache[key]
                removed += 1
        return removed


# Global cache instance
_embedding_cache: Optional[EmbeddingCache] = None

def get_embedding_cache() -> EmbeddingCache:
    """Get the global embedding cache instance."""
    global _embedding_cache
    if _embedding_cache is None:
        _embedding_cache = EmbeddingCache()
    return _embedding_cache


async def cached_embed(model: str, text: str, embed_func) -> List[float]:
    """
    Get embedding with caching.
    
    Args:
        model: The embedding model name
        text: The text to embed
        embed_func: Async function to call for computing embedding
        
    Returns:
        The embedding vector
    """
    cache = get_embedding_cache()
    
    # Check cache first
    cached = cache.get(model, text)
    if cached is not None:
        return cached
    
    # Compute embedding
    embedding = await embed_func(model, text)
    
    # Store in cache
    cache.set(model, text, embedding)
    
    return embedding


async def cached_embed_batch(
    model: str, 
    texts: List[str], 
    embed_func
) -> List[List[float]]:
    """
    Get embeddings for multiple texts with caching.
    Computes only missing embeddings.
    
    Args:
        model: The embedding model name
        texts: List of texts to embed
        embed_func: Async function that takes (model, text) and returns embedding
        
    Returns:
        List of embedding vectors
    """
    cache = get_embedding_cache()
    
    # Check cache for all texts
    results, missing_indices = cache.get_batch(model, texts)
    
    # If all cached, return immediately
    if not missing_indices:
        return results
    
    # Compute missing embeddings
    for idx in missing_indices:
        embedding = await embed_func(model, texts[idx])
        results[idx] = embedding
        cache.set(model, texts[idx], embedding)
    
    return results
