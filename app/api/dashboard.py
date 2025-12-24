# app/api/dashboard.py
from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from typing import Any, Dict, List, Iterable, Tuple
from urllib.request import Request, urlopen
from urllib.error import URLError

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

ANKI_CONNECT_URL = os.getenv("ANKI_CONNECT_URL", "http://127.0.0.1:8765")
ANKI_CONNECT_VERSION = int(os.getenv("ANKI_CONNECT_VERSION", "6"))
DEFAULT_TIMEOUT_SEC = float(os.getenv("ANKI_CONNECT_TIMEOUT", "6"))


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
            detail=f"Não consegui conectar no AnkiConnect em {ANKI_CONNECT_URL}. "
                   f"Abra o Anki com o add-on AnkiConnect ativo. Erro: {e}",
        )

    if data.get("error"):
        raise HTTPException(status_code=500, detail=str(data["error"]))
    return data.get("result")


def chunked(items: List[int], size: int = 500) -> Iterable[List[int]]:
    for i in range(0, len(items), size):
        yield items[i:i + size]


def bucket_interval_days(days: int) -> str:
    # buckets simples e úteis p/ gráfico
    if days <= 0:
        return "0"
    if days <= 1:
        return "1"
    if days <= 7:
        return "2-7"
    if days <= 30:
        return "8-30"
    if days <= 90:
        return "31-90"
    if days <= 365:
        return "91-365"
    return "365+"


@router.get("/overview")
def dashboard_overview() -> Dict[str, Any]:
    # Contadores rápidos via query do Anki (barato)
    total_cards_ids = anki_invoke("findCards", {"query": "deck:*"})
    due_ids = anki_invoke("findCards", {"query": "is:due"})
    new_ids = anki_invoke("findCards", {"query": "is:new"})
    learn_ids = anki_invoke("findCards", {"query": "is:learn"})
    review_ids = anki_invoke("findCards", {"query": "is:review"})
    suspended_ids = anki_invoke("findCards", {"query": "is:suspended"})

    total_cards = len(total_cards_ids or [])
    counts = {
        "total_cards": total_cards,
        "due": len(due_ids or []),
        "new": len(new_ids or []),
        "learn": len(learn_ids or []),
        "review": len(review_ids or []),
        "suspended": len(suspended_ids or []),
    }

    # Se a coleção for grande, ainda funciona: a gente “amostra”/resume tudo em batches
    by_deck = Counter()
    by_model = Counter()
    interval_buckets = Counter()
    ease_buckets = Counter()
    lapses_sum = 0
    reps_sum = 0

    ids = total_cards_ids or []
    for batch in chunked(ids, size=500):
        infos = anki_invoke("cardsInfo", {"cards": batch}) or []
        for c in infos:
            deck = c.get("deckName") or "Unknown"
            model = c.get("modelName") or "Unknown"
            by_deck[deck] += 1
            by_model[model] += 1

            # interval (dias) e ease/factor
            ivl = int(c.get("interval") or 0)
            interval_buckets[bucket_interval_days(ivl)] += 1

            # factor costuma vir em "factor" (ex: 2500 = 2.5)
            factor = c.get("factor")
            if factor is not None:
                ef = int(factor)
                # buckets em “escala de 1000”: 1300-1999, 2000-2499, etc.
                if ef < 1300:
                    ease_buckets["<1.3"] += 1
                elif ef < 2000:
                    ease_buckets["1.3-2.0"] += 1
                elif ef < 2500:
                    ease_buckets["2.0-2.5"] += 1
                elif ef < 3000:
                    ease_buckets["2.5-3.0"] += 1
                else:
                    ease_buckets["3.0+"] += 1

            lapses_sum += int(c.get("lapses") or 0)
            reps_sum += int(c.get("reps") or 0)

    # Top N para UI
    top_decks = [{"name": k, "cards": v} for k, v in by_deck.most_common(12)]
    top_models = [{"name": k, "cards": v} for k, v in by_model.most_common(12)]

    # Mantém ordem “bonita” dos buckets
    interval_order = ["0", "1", "2-7", "8-30", "31-90", "91-365", "365+"]
    interval_series = [{"bucket": b, "cards": int(interval_buckets.get(b, 0))} for b in interval_order]

    ease_order = ["<1.3", "1.3-2.0", "2.0-2.5", "2.5-3.0", "3.0+"]
    ease_series = [{"bucket": b, "cards": int(ease_buckets.get(b, 0))} for b in ease_order]

    return {
        "counts": counts,
        "top_decks": top_decks,
        "top_models": top_models,
        "intervals": interval_series,
        "ease": ease_series,
        "totals": {
            "reps_sum": reps_sum,
            "lapses_sum": lapses_sum,
        },
    }
