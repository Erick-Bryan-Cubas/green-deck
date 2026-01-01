# app/services/llm_cache.py
"""
Cache de respostas LLM para evitar chamadas repetidas.
Usa hash do prompt + modelo para identificar respostas cacheadas.
"""

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict
from threading import Lock

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Entrada do cache com metadados."""
    response: str
    model: str
    prompt_hash: str
    created_at: float
    hit_count: int = 0
    last_accessed: float = 0.0


class LLMResponseCache:
    """
    Cache em memória para respostas de LLM.
    
    Features:
    - TTL configurável
    - Limite de tamanho com eviction LRU
    - Persistência opcional em disco
    - Thread-safe
    """
    
    def __init__(
        self,
        max_entries: int = 500,
        ttl_seconds: float = 3600 * 24,  # 24 horas
        persist_path: Optional[Path] = None
    ):
        self._cache: Dict[str, CacheEntry] = {}
        self._max_entries = max_entries
        self._ttl = ttl_seconds
        self._persist_path = persist_path
        self._lock = Lock()
        self._stats = {"hits": 0, "misses": 0, "evictions": 0}
        
        # Carrega cache persistido se existir
        if persist_path:
            self._load_from_disk()
    
    def _compute_hash(self, model: str, prompt: str, system: Optional[str] = None) -> str:
        """Gera hash único para a combinação modelo + prompt + system."""
        content = f"{model}|{system or ''}|{prompt}"
        return hashlib.sha256(content.encode()).hexdigest()[:32]
    
    def get(self, model: str, prompt: str, system: Optional[str] = None) -> Optional[str]:
        """
        Busca resposta no cache.
        
        Returns:
            Resposta cacheada ou None se não encontrada/expirada.
        """
        key = self._compute_hash(model, prompt, system)
        
        with self._lock:
            entry = self._cache.get(key)
            
            if entry is None:
                self._stats["misses"] += 1
                return None
            
            # Verifica TTL
            if time.time() - entry.created_at > self._ttl:
                del self._cache[key]
                self._stats["misses"] += 1
                logger.debug("Cache entry expired: %s", key[:8])
                return None
            
            # Atualiza acesso
            entry.hit_count += 1
            entry.last_accessed = time.time()
            self._stats["hits"] += 1
            
            logger.debug(
                "Cache hit (hits=%d): %s",
                entry.hit_count,
                key[:8]
            )
            return entry.response
    
    def set(
        self,
        model: str,
        prompt: str,
        response: str,
        system: Optional[str] = None
    ) -> None:
        """Armazena resposta no cache."""
        key = self._compute_hash(model, prompt, system)
        
        with self._lock:
            # Eviction LRU se necessário
            if len(self._cache) >= self._max_entries:
                self._evict_lru()
            
            entry = CacheEntry(
                response=response,
                model=model,
                prompt_hash=key,
                created_at=time.time(),
                last_accessed=time.time(),
                hit_count=0
            )
            self._cache[key] = entry
            
            logger.debug("Cache set: %s (entries=%d)", key[:8], len(self._cache))
            
            # Persiste se configurado
            if self._persist_path:
                self._save_to_disk()
    
    def _evict_lru(self) -> None:
        """Remove a entrada menos recentemente usada."""
        if not self._cache:
            return
        
        # Encontra entrada com menor last_accessed
        oldest_key = min(
            self._cache.keys(),
            key=lambda k: self._cache[k].last_accessed
        )
        del self._cache[oldest_key]
        self._stats["evictions"] += 1
        logger.debug("Cache evicted: %s", oldest_key[:8])
    
    def _load_from_disk(self) -> None:
        """Carrega cache do disco."""
        if not self._persist_path or not self._persist_path.exists():
            return
        
        try:
            data = json.loads(self._persist_path.read_text(encoding="utf-8"))
            for key, entry_data in data.get("cache", {}).items():
                self._cache[key] = CacheEntry(**entry_data)
            logger.info("Loaded %d cache entries from disk", len(self._cache))
        except Exception as e:
            logger.warning("Failed to load cache from disk: %s", e)
    
    def _save_to_disk(self) -> None:
        """Salva cache no disco."""
        if not self._persist_path:
            return
        
        try:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "cache": {k: asdict(v) for k, v in self._cache.items()},
                "stats": self._stats,
                "saved_at": time.time()
            }
            self._persist_path.write_text(
                json.dumps(data, ensure_ascii=False),
                encoding="utf-8"
            )
        except Exception as e:
            logger.warning("Failed to save cache to disk: %s", e)
    
    def clear(self) -> None:
        """Limpa todo o cache."""
        with self._lock:
            self._cache.clear()
            if self._persist_path and self._persist_path.exists():
                self._persist_path.unlink()
            logger.info("Cache cleared")
    
    def stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do cache."""
        with self._lock:
            total = self._stats["hits"] + self._stats["misses"]
            hit_rate = (self._stats["hits"] / total * 100) if total > 0 else 0.0
            return {
                **self._stats,
                "entries": len(self._cache),
                "max_entries": self._max_entries,
                "hit_rate_percent": round(hit_rate, 2)
            }


# Singleton global
_llm_cache: Optional[LLMResponseCache] = None


def get_llm_cache() -> LLMResponseCache:
    """Retorna instância singleton do cache de LLM."""
    global _llm_cache
    if _llm_cache is None:
        # Cache com persistência no diretório data/
        persist_path = Path(__file__).resolve().parents[2] / "data" / "llm_cache.json"
        _llm_cache = LLMResponseCache(
            max_entries=500,
            ttl_seconds=3600 * 24 * 7,  # 7 dias
            persist_path=persist_path
        )
    return _llm_cache


def get_cached_response(
    model: str,
    prompt: str,
    system: Optional[str] = None
) -> Optional[str]:
    """Helper para buscar resposta cacheada."""
    return get_llm_cache().get(model, prompt, system)


def cache_response(
    model: str,
    prompt: str,
    response: str,
    system: Optional[str] = None
) -> None:
    """Helper para cachear resposta."""
    get_llm_cache().set(model, prompt, response, system)


def get_llm_cache_stats() -> Dict[str, Any]:
    """Retorna estatísticas do cache."""
    return get_llm_cache().stats()
