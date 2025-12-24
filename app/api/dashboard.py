# app/api/dashboard.py
from __future__ import annotations

import json
import os
import random
import time
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List
from urllib.error import URLError
from urllib.request import Request, urlopen

import numpy as np
from fastapi import APIRouter, HTTPException, Query
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

ANKI_CONNECT_URL = os.getenv("ANKI_CONNECT_URL", "http://127.0.0.1:8765")
ANKI_CONNECT_VERSION = int(os.getenv("ANKI_CONNECT_VERSION", "6"))
DEFAULT_TIMEOUT_SEC = float(os.getenv("ANKI_CONNECT_TIMEOUT", "10"))

# cache simples p/ não recalcular tudo 4x quando a página carrega
_CACHE_TTL_SEC = float(os.getenv("DASHBOARD_CACHE_TTL", "15"))
_cache_ts: float = 0.0
_cache_payload: Dict[str, Any] | None = None

# segmentação (scikit-learn)
SEG_K = int(os.getenv("DASHBOARD_SEGMENTS_K", "4"))
SEG_MAX_SAMPLE = int(os.getenv("DASHBOARD_SEGMENTS_MAX_SAMPLE", "12000"))
SEG_RANDOM_SEED = int(os.getenv("DASHBOARD_SEGMENTS_SEED", "42"))


def anki_invoke(action: str, params: Dict[str, Any] | None = None) -> Any:
    payload = {"action": action, "version": ANKI_CONNECT_VERSION, "params": params or {}}
    req = Request(
        ANKI_CONNECT_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(req, timeout=DEFAULT_TIMEOUT_SEC) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except URLError as e:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Não consegui conectar no AnkiConnect em {ANKI_CONNECT_URL}. "
                f"Abra o Anki com o add-on AnkiConnect ativo. Erro: {e}"
            ),
        )

    if data.get("error"):
        raise HTTPException(status_code=500, detail=str(data["error"]))
    return data.get("result")


def chunked(items: List[int], size: int = 500) -> Iterable[List[int]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _card_created_day(card_info: Dict[str, Any]) -> str | None:
    raw = card_info.get("cardId") or card_info.get("id") or card_info.get("note")
    if raw is None:
        return None
    try:
        n = int(raw)
    except Exception:
        return None

    ts_sec = (n / 1000.0) if n > 10_000_000_000 else float(n)
    try:
        dt = datetime.fromtimestamp(ts_sec, tz=timezone.utc)
        return dt.date().isoformat()
    except Exception:
        return None


def _status_counts() -> Dict[str, int]:
    # queries baratas e bem úteis pro gráfico de rosca
    def q(query: str) -> int:
        ids = anki_invoke("findCards", {"query": query}) or []
        return int(len(ids))

    return {
        "new": q("is:new"),
        "learn": q("is:learn"),
        "review": q("is:review"),
        "due": q("is:due"),
        "suspended": q("is:suspended"),
    }


def _format_status_items(sc: Dict[str, int]) -> List[Dict[str, Any]]:
    # labels pt-br
    order = [
        ("new", "Novos"),
        ("learn", "Aprendendo"),
        ("review", "Revisão"),
        ("due", "Vencidos"),
        ("suspended", "Suspensos"),
    ]
    return [{"status": lbl, "key": key, "count": int(sc.get(key, 0))} for key, lbl in order]


def _kmeans_segments(features: List[List[float]], k: int) -> Dict[str, Any]:
    # features: [interval_days, ease, lapses, reps]
    if len(features) < max(2, k):
        return {"success": True, "k": k, "sampled": len(features), "items": []}

    X = np.array(features, dtype=float)

    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)

    km = KMeans(n_clusters=k, n_init="auto", random_state=SEG_RANDOM_SEED)
    labels = km.fit_predict(Xs)

    # agrega métricas por cluster no espaço original
    clusters = []
    for c in range(k):
        idx = np.where(labels == c)[0]
        if idx.size == 0:
            continue
        Xc = X[idx]
        clusters.append(
            {
                "cluster": int(c),
                "count": int(idx.size),
                "avgInterval": float(np.mean(Xc[:, 0])),
                "avgEase": float(np.mean(Xc[:, 1])),
                "avgLapses": float(np.mean(Xc[:, 2])),
                "avgReps": float(np.mean(Xc[:, 3])),
            }
        )

    # ordena por maturidade (intervalo médio)
    clusters.sort(key=lambda d: d["avgInterval"])

    # rótulos interpretáveis (k=4 default)
    default_names_4 = ["Instáveis", "Em consolidação", "Maduros", "Muito maduros"]
    default_names_3 = ["Instáveis", "Em consolidação", "Maduros"]

    if k == 4:
        names = default_names_4
    elif k == 3:
        names = default_names_3
    else:
        names = [f"Segmento {i+1}" for i in range(len(clusters))]

    items = []
    for i, c in enumerate(clusters):
        items.append(
            {
                "segment": names[i] if i < len(names) else f"Segmento {i+1}",
                "count": c["count"],
                "avgInterval": c["avgInterval"],
                "avgEase": c["avgEase"],
                "avgLapses": c["avgLapses"],
                "avgReps": c["avgReps"],
            }
        )

    return {"success": True, "k": k, "sampled": len(features), "items": items}


def _build_all_stats() -> Dict[str, Any]:
    random.seed(SEG_RANDOM_SEED)

    # 1) IDs de todos os cards
    all_card_ids = anki_invoke("findCards", {"query": "deck:*"}) or []
    total_cards = len(all_card_ids)

    # 2) decks (rápido)
    try:
        deck_names = anki_invoke("deckNames") or []
        total_decks = len(deck_names)
    except Exception:
        total_decks = 0

    # 3) distribuição por deck + criação por dia + features p/ clustering
    by_deck = Counter()
    by_day = Counter()

    # reservoir sample p/ features (mantém “dataset completo” no resto, mas controla custo do ML)
    feat_sample: List[List[float]] = []
    seen = 0

    for batch in chunked(all_card_ids, size=500):
        infos = anki_invoke("cardsInfo", {"cards": batch}) or []
        for c in infos:
            deck = c.get("deckName") or "Unknown"
            by_deck[deck] += 1

            d = _card_created_day(c)
            if d:
                by_day[d] += 1

            # features: interval (dias), ease(factor/1000), lapses, reps
            ivl = float(int(c.get("interval") or 0))
            factor_raw = c.get("factor")
            ease = float(int(factor_raw) / 1000.0) if factor_raw is not None else 0.0
            lapses = float(int(c.get("lapses") or 0))
            reps = float(int(c.get("reps") or 0))

            vec = [ivl, ease, lapses, reps]

            seen += 1
            if len(feat_sample) < SEG_MAX_SAMPLE:
                feat_sample.append(vec)
            else:
                j = random.randrange(seen)
                if j < SEG_MAX_SAMPLE:
                    feat_sample[j] = vec

    # 4) status breakdown (para rosca)
    sc = _status_counts()
    status_items = _format_status_items(sc)

    # 5) avg/dia all-time
    avg_per_day = None
    if by_day:
        days_sorted = sorted(by_day.keys())
        d0 = datetime.fromisoformat(days_sorted[0]).date()
        d1 = datetime.fromisoformat(days_sorted[-1]).date()
        span = (d1 - d0).days + 1
        if span > 0:
            avg_per_day = total_cards / float(span)

    # 6) segmentação (scikit-learn)
    segments = _kmeans_segments(feat_sample, k=SEG_K)

    # payloads no formato esperado
    top_decks = [{"deckName": k, "count": int(v)} for k, v in by_deck.most_common(12)]
    by_day_items = [{"day": k, "created": int(by_day[k])} for k in sorted(by_day.keys())]

    summary = {
        "success": True,
        "totalCards": total_cards,
        "totalDecks": total_decks if total_decks > 0 else len(by_deck.keys()),
        "createdTotal": total_cards,
        "avgPerDay": avg_per_day,
        "statusBreakdown": status_items,         # <- NOVO
        "segmentsMeta": {"k": segments.get("k"), "sampled": segments.get("sampled")},  # <- NOVO
    }

    return {
        "summary": summary,
        "by_day": {"success": True, "items": by_day_items},
        "top_decks": {"success": True, "items": top_decks},
        "segments": segments,                    # <- NOVO
    }


def _get_cached_or_build() -> Dict[str, Any]:
    global _cache_ts, _cache_payload
    now = time.time()
    if _cache_payload is not None and (now - _cache_ts) < _CACHE_TTL_SEC:
        return _cache_payload
    payload = _build_all_stats()
    _cache_payload = payload
    _cache_ts = now
    return payload


@router.get("/summary")
def dashboard_summary() -> Dict[str, Any]:
    payload = _get_cached_or_build()
    return payload["summary"]


@router.get("/by-day")
def dashboard_by_day() -> Dict[str, Any]:
    payload = _get_cached_or_build()
    return payload["by_day"]


@router.get("/top-decks")
def dashboard_top_decks(limit: int = Query(12, ge=1, le=200)) -> Dict[str, Any]:
    payload = _get_cached_or_build()
    items = payload["top_decks"]["items"][: int(limit)]
    return {"success": True, "items": items}


@router.get("/segments")
def dashboard_segments() -> Dict[str, Any]:
    payload = _get_cached_or_build()
    return payload["segments"]
