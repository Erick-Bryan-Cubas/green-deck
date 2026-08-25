# app/api/dashboard.py
from __future__ import annotations

import hashlib
import html as _html
import json
import os
import random
import re
import threading
import time
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional
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

# cache simples p/ não recalcular tudo quando a página carrega 6 endpoints em paralelo
_CACHE_TTL_SEC = float(os.getenv("DASHBOARD_CACHE_TTL", "15"))
_cache: Dict[str, Dict[str, Any]] = {}  # key -> {ts, payload}
_cache_lock = threading.Lock()

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
        ) from e

    if data.get("error"):
        raise HTTPException(status_code=500, detail=str(data["error"]))
    return data.get("result")


def chunked(items: List[int], size: int = 500) -> Iterable[List[int]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


# A partir de quantos lapsos um cartão entra na lista de problemáticos.
# O padrão do próprio Anki para marcar leech é 8.
LEECH_MIN_LAPSES = int(os.getenv("DASHBOARD_LEECH_MIN_LAPSES", "8"))
LEECH_MAX_ITEMS = 25

_TAG_RE = re.compile(r"<[^>]+>")
_STYLE_RE = re.compile(r"<(style|script)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)


def _plain_preview(html: Any, limit: int = 90) -> str:
    """Texto curto e legível a partir do HTML renderizado de um cartão."""
    raw = str(html or "")
    if not raw:
        return ""
    text = _STYLE_RE.sub(" ", raw)
    text = _TAG_RE.sub(" ", text)
    text = _html.unescape(text)
    text = " ".join(text.split())
    return text[: limit - 1] + "…" if len(text) > limit else text


# Faixas de intervalo usadas tanto no histograma da coleção quanto na
# retenção por intervalo — manter uma lista só garante que os dois gráficos
# possam ser lidos lado a lado.
INTERVAL_BUCKETS = ["1 dia", "2-6 d", "7-29 d", "30-89 d", "90-179 d", "180-364 d", "1 ano+"]


def _interval_bucket(days: int) -> str:
    if days <= 1:
        return INTERVAL_BUCKETS[0]
    if days < 7:
        return INTERVAL_BUCKETS[1]
    if days < 30:
        return INTERVAL_BUCKETS[2]
    if days < 90:
        return INTERVAL_BUCKETS[3]
    if days < 180:
        return INTERVAL_BUCKETS[4]
    if days < 365:
        return INTERVAL_BUCKETS[5]
    return INTERVAL_BUCKETS[6]


EASE_BUCKETS = ["<1.5", "1.5-1.9", "2.0-2.4", "2.5-2.9", "3.0+"]


def _ease_bucket(ease: float) -> str:
    if ease < 1.5:
        return EASE_BUCKETS[0]
    if ease < 2.0:
        return EASE_BUCKETS[1]
    if ease < 2.5:
        return EASE_BUCKETS[2]
    if ease < 3.0:
        return EASE_BUCKETS[3]
    return EASE_BUCKETS[4]


def _due_forecast(deck_filter: Optional[str], days: int = 30) -> List[Dict[str, Any]]:
    """
    Carga futura: quantos cartões vencem em cada um dos próximos `days` dias.

    `cardsInfo` devolve `due` no formato bruto do agendador (dias desde a criação
    da coleção), que não dá para converter em data sem o `crt`. Em vez disso
    perguntamos ao próprio Anki com `prop:due=N`, empacotando todos os dias num
    único `multi` para não fazer N idas e voltas.
    """
    # _build_query já devolve o grupo de decks entre parênteses
    scope = f"{deck_filter} " if deck_filter else ""
    actions = [
        {"action": "findCards", "params": {"query": f"{scope}prop:due={d} -is:suspended"}}
        for d in range(days)
    ]

    try:
        results = anki_invoke("multi", {"actions": actions}) or []
    except Exception:
        return []

    out: List[Dict[str, Any]] = []
    for d, res in enumerate(results):
        # cada item do multi pode vir como lista (ok) ou dict de erro
        count = len(res) if isinstance(res, list) else 0
        out.append({"dayOffset": d, "count": int(count)})
    return out


def _aggregate_review_stats(
    all_reviews: Dict[str, List[Dict[str, Any]]],
    start_ts: Optional[int] = None,
    end_ts: Optional[int] = None,
) -> Dict[str, Any]:
    """Aggregate review data from getReviewsOfCards into daily metrics and KPIs.

    all_reviews: {cardId: [{id, usn, ease, ivl, lastIvl, factor, time, type}, ...]}
    start_ts/end_ts: optional timestamp filters in milliseconds.
    """
    from collections import defaultdict

    reviews_per_day: Counter = Counter()
    time_per_day: Dict[str, float] = defaultdict(float)
    correct_per_day: Counter = Counter()
    total_per_day: Counter = Counter()

    # --- novas agregações ---
    button_counts: Counter = Counter()          # 1=Again 2=Hard 3=Good 4=Easy
    per_hour: Counter = Counter()               # hora local do dia (0-23)
    per_weekday: Counter = Counter()            # 0=segunda ... 6=domingo
    # retenção por faixa do intervalo ANTERIOR à resposta (lastIvl)
    retention_bucket_total: Counter = Counter()
    retention_bucket_correct: Counter = Counter()

    for _card_id, review_list in all_reviews.items():
        for r in review_list:
            review_time_ms = r.get("id", 0)
            if start_ts and review_time_ms < start_ts:
                continue
            if end_ts and review_time_ms > end_ts:
                continue

            button_pressed = r.get("ease", 0)  # 1=Again, 2=Hard, 3=Good, 4=Easy
            duration_ms = r.get("time", 0)

            dt = datetime.fromtimestamp(review_time_ms / 1000.0, tz=timezone.utc)
            day = dt.date().isoformat()

            reviews_per_day[day] += 1
            time_per_day[day] += duration_ms
            total_per_day[day] += 1
            is_correct = button_pressed >= 2
            if is_correct:
                correct_per_day[day] += 1

            if 1 <= button_pressed <= 4:
                button_counts[button_pressed] += 1

            # Hora/dia-da-semana usam o fuso LOCAL: "às 22h" só faz sentido no
            # relógio de quem estudou. (As séries por dia acima seguem em UTC,
            # como já era antes desta agregação existir.)
            local_dt = datetime.fromtimestamp(review_time_ms / 1000.0)
            per_hour[local_dt.hour] += 1
            per_weekday[local_dt.weekday()] += 1

            # Só revisões de cartões já aprendidos dizem algo sobre retenção
            last_ivl = int(r.get("lastIvl") or 0)
            if last_ivl > 0:
                bucket = _interval_bucket(last_ivl)
                retention_bucket_total[bucket] += 1
                if is_correct:
                    retention_bucket_correct[bucket] += 1

    all_days = sorted(reviews_per_day.keys())

    reviews_by_day = [{"day": d, "reviews": reviews_per_day[d]} for d in all_days]

    study_time_by_day = [
        {"day": d, "minutes": round(time_per_day[d] / 60_000.0, 2)} for d in all_days
    ]

    success_rate_by_day = [
        {
            "day": d,
            "rate": round((correct_per_day[d] / total_per_day[d] * 100) if total_per_day[d] > 0 else 0, 1),
            "correct": correct_per_day[d],
            "total": total_per_day[d],
        }
        for d in all_days
    ]

    total_reviews = sum(reviews_per_day.values())
    total_study_ms = sum(time_per_day.values())
    total_correct = sum(correct_per_day.values())
    total_answered = sum(total_per_day.values())

    if all_days:
        d0 = datetime.fromisoformat(all_days[0]).date()
        d1 = datetime.fromisoformat(all_days[-1]).date()
        days_span = (d1 - d0).days + 1
    else:
        days_span = 1

    review_kpis = {
        "totalReviews": total_reviews,
        "avgReviewsPerDay": round(total_reviews / max(days_span, 1), 2),
        "totalStudyTimeMin": round(total_study_ms / 60_000.0, 1),
        "successRate": round(
            (total_correct / total_answered * 100) if total_answered > 0 else 0, 1
        ),
    }

    button_labels = {1: "Again", 2: "Hard", 3: "Good", 4: "Easy"}
    total_buttons = sum(button_counts.values())
    answer_buttons = [
        {
            "button": button_labels[b],
            "count": int(button_counts.get(b, 0)),
            "pct": round(100 * button_counts.get(b, 0) / total_buttons, 1) if total_buttons else 0.0,
        }
        for b in (1, 2, 3, 4)
    ]

    reviews_by_hour = [{"hour": h, "reviews": int(per_hour.get(h, 0))} for h in range(24)]

    weekday_labels = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
    reviews_by_weekday = [
        {"weekday": weekday_labels[i], "reviews": int(per_weekday.get(i, 0))} for i in range(7)
    ]

    retention_by_interval = [
        {
            "bucket": label,
            "total": int(retention_bucket_total.get(label, 0)),
            "correct": int(retention_bucket_correct.get(label, 0)),
            "rate": round(
                100 * retention_bucket_correct.get(label, 0) / retention_bucket_total[label], 1
            )
            if retention_bucket_total.get(label, 0)
            else 0.0,
        }
        for label in INTERVAL_BUCKETS
        if retention_bucket_total.get(label, 0) > 0
    ]

    return {
        "reviews_by_day": reviews_by_day,
        "study_time_by_day": study_time_by_day,
        "success_rate_by_day": success_rate_by_day,
        "review_kpis": review_kpis,
        "answer_buttons": answer_buttons,
        "reviews_by_hour": reviews_by_hour,
        "reviews_by_weekday": reviews_by_weekday,
        "retention_by_interval": retention_by_interval,
    }


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


def _status_counts_for_decks(decks: List[str]) -> Dict[str, int]:
    """Status counts filtered by specific decks."""
    deck_query = " OR ".join([f'deck:"{d}"' for d in decks])

    def q(status_query: str) -> int:
        query = f"({deck_query}) {status_query}"
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


def _build_query(
    decks: Optional[List[str]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> str:
    """Build Anki query string from filters."""
    parts = []

    # Deck filter
    if decks and len(decks) > 0:
        deck_queries = [f'deck:"{d}"' for d in decks]
        parts.append(f"({' OR '.join(deck_queries)})")
    else:
        parts.append("deck:*")

    # Note: Anki doesn't support date range filtering on card creation
    # The date filtering will be done in Python after fetching cards

    return " ".join(parts)


def _build_all_stats(
    decks: Optional[List[str]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Dict[str, Any]:
    random.seed(SEG_RANDOM_SEED)

    # Parse date filters into ms timestamps for review filtering
    start_ts = None
    end_ts = None
    if start_date:
        try:
            start_ts = int(
                datetime.fromisoformat(start_date)
                .replace(tzinfo=timezone.utc)
                .timestamp() * 1000
            )
        except ValueError:
            pass
    if end_date:
        try:
            end_ts = int(
                datetime.fromisoformat(end_date)
                .replace(tzinfo=timezone.utc)
                .timestamp() * 1000
            ) + 86_400_000  # end of that day
        except ValueError:
            pass

    # 1) Build query and get card IDs
    query = _build_query(decks=decks)
    all_card_ids = anki_invoke("findCards", {"query": query}) or []
    total_cards = len(all_card_ids)

    # 2) decks (rápido)
    try:
        deck_names = anki_invoke("deckNames") or []
        total_decks = len(deck_names)
    except Exception:
        total_decks = 0

    # 3) distribuição por deck + features p/ clustering + reviews
    #    Usa "multi" para buscar cardsInfo + getReviewsOfCards em 1 request por batch
    by_deck = Counter()
    all_reviews: Dict[str, List[Dict[str, Any]]] = {}

    # reservoir sample p/ features (mantém "dataset completo" no resto, mas controla custo do ML)
    feat_sample: List[List[float]] = []
    seen = 0

    # Histogramas da coleção e leeches — tudo derivado do mesmo cardsInfo que já
    # é buscado, sem requisição extra ao AnkiConnect.
    interval_hist: Counter = Counter()
    ease_hist: Counter = Counter()
    leeches: List[Dict[str, Any]] = []

    for batch in chunked(all_card_ids, size=500):
        results = anki_invoke("multi", {"actions": [
            {"action": "cardsInfo", "params": {"cards": batch}},
            {"action": "getReviewsOfCards", "params": {"cards": batch}},
        ]})

        infos = results[0] if results and len(results) > 0 else []
        review_map = results[1] if results and len(results) > 1 else {}

        # Process card info (deck distribution + ML features)
        for c in (infos or []):
            deck = c.get("deckName") or "Unknown"
            by_deck[deck] += 1

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

            # Cartões novos ainda não têm intervalo/ease para distribuir
            if ivl > 0:
                interval_hist[_interval_bucket(int(ivl))] += 1
            if ease > 0:
                ease_hist[_ease_bucket(ease)] += 1

            if lapses >= LEECH_MIN_LAPSES:
                leeches.append({
                    "cardId": c.get("cardId"),
                    "deckName": deck,
                    "lapses": int(lapses),
                    "reps": int(reps),
                    "interval": int(ivl),
                    "ease": round(ease, 2),
                    "question": _plain_preview(c.get("question")),
                })

        # Accumulate reviews
        if review_map:
            for card_id, rev_list in (review_map or {}).items():
                all_reviews[str(card_id)] = rev_list or []

    # 4) status breakdown (para rosca) - only for filtered decks if specified
    if decks and len(decks) > 0:
        sc = _status_counts_for_decks(decks)
    else:
        sc = _status_counts()
    status_items = _format_status_items(sc)

    # 5) segmentação (scikit-learn)
    segments = _kmeans_segments(feat_sample, k=SEG_K)

    # 6) review analytics (aggregation with date filtering)
    review_stats = _aggregate_review_stats(all_reviews, start_ts=start_ts, end_ts=end_ts)

    # 7) carga futura (uma request "multi" com um findCards por dia)
    forecast = _due_forecast(_build_query(decks=decks) if decks else None, days=30)

    # payloads no formato esperado
    top_decks = [{"deckName": k, "count": int(v)} for k, v in by_deck.most_common(12)]

    interval_distribution = [
        {"bucket": b, "count": int(interval_hist.get(b, 0))}
        for b in INTERVAL_BUCKETS
        if interval_hist.get(b, 0) > 0
    ]
    ease_distribution = [
        {"bucket": b, "count": int(ease_hist.get(b, 0))}
        for b in EASE_BUCKETS
        if ease_hist.get(b, 0) > 0
    ]
    top_leeches = sorted(leeches, key=lambda x: x["lapses"], reverse=True)[:LEECH_MAX_ITEMS]

    summary = {
        "success": True,
        "totalCards": total_cards,
        "totalDecks": total_decks if total_decks > 0 else len(by_deck.keys()),
        "statusBreakdown": status_items,
        "segmentsMeta": {"k": segments.get("k"), "sampled": segments.get("sampled")},
        "reviewKpis": review_stats["review_kpis"],
        "leechCount": len(leeches),
        "dueNext7": sum(x["count"] for x in forecast[:7]),
    }

    return {
        "summary": summary,
        "top_decks": {"success": True, "items": top_decks},
        "segments": segments,
        "reviews_by_day": {"success": True, "items": review_stats["reviews_by_day"]},
        "study_time_by_day": {"success": True, "items": review_stats["study_time_by_day"]},
        "success_rate_by_day": {"success": True, "items": review_stats["success_rate_by_day"]},
        # --- novas análises ---
        "answer_buttons": {"success": True, "items": review_stats["answer_buttons"]},
        "reviews_by_hour": {"success": True, "items": review_stats["reviews_by_hour"]},
        "reviews_by_weekday": {"success": True, "items": review_stats["reviews_by_weekday"]},
        "retention_by_interval": {"success": True, "items": review_stats["retention_by_interval"]},
        "interval_distribution": {"success": True, "items": interval_distribution},
        "ease_distribution": {"success": True, "items": ease_distribution},
        "due_forecast": {"success": True, "items": forecast},
        "leeches": {"success": True, "items": top_leeches},
    }


def _get_cache_key(
    decks: Optional[List[str]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> str:
    """Generate cache key from filter parameters."""
    key_parts = [
        ",".join(sorted(decks)) if decks else "",
        start_date or "",
        end_date or "",
    ]
    key_str = "|".join(key_parts)
    return hashlib.sha256(key_str.encode()).hexdigest()


def _get_cached_or_build(
    decks: Optional[List[str]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Dict[str, Any]:
    global _cache
    cache_key = _get_cache_key(decks, start_date, end_date)

    # Fast path: check cache without lock
    now = time.time()
    if cache_key in _cache:
        cached = _cache[cache_key]
        if (now - cached["ts"]) < _CACHE_TTL_SEC:
            return cached["payload"]

    # Serialize builds so parallel requests don't all hit AnkiConnect at once
    with _cache_lock:
        # Re-check cache (another thread may have built it while we waited)
        now = time.time()
        if cache_key in _cache:
            cached = _cache[cache_key]
            if (now - cached["ts"]) < _CACHE_TTL_SEC:
                return cached["payload"]

        payload = _build_all_stats(decks=decks, start_date=start_date, end_date=end_date)
        _cache[cache_key] = {"ts": now, "payload": payload}

        # Cleanup old cache entries (keep max 10)
        if len(_cache) > 10:
            oldest_key = min(_cache.keys(), key=lambda k: _cache[k]["ts"])
            del _cache[oldest_key]

    return payload


@router.get("/summary")
def dashboard_summary(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    decks: Optional[str] = Query(None, description="Comma-separated deck names"),
) -> Dict[str, Any]:
    deck_list = decks.split(",") if decks else None
    payload = _get_cached_or_build(decks=deck_list, start_date=start_date, end_date=end_date)
    return payload["summary"]


@router.get("/reviews-by-day")
def dashboard_reviews_by_day(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    decks: Optional[str] = Query(None, description="Comma-separated deck names"),
) -> Dict[str, Any]:
    deck_list = decks.split(",") if decks else None
    payload = _get_cached_or_build(decks=deck_list, start_date=start_date, end_date=end_date)
    return payload["reviews_by_day"]


@router.get("/study-time-by-day")
def dashboard_study_time_by_day(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    decks: Optional[str] = Query(None, description="Comma-separated deck names"),
) -> Dict[str, Any]:
    deck_list = decks.split(",") if decks else None
    payload = _get_cached_or_build(decks=deck_list, start_date=start_date, end_date=end_date)
    return payload["study_time_by_day"]


@router.get("/success-rate-by-day")
def dashboard_success_rate_by_day(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    decks: Optional[str] = Query(None, description="Comma-separated deck names"),
) -> Dict[str, Any]:
    deck_list = decks.split(",") if decks else None
    payload = _get_cached_or_build(decks=deck_list, start_date=start_date, end_date=end_date)
    return payload["success_rate_by_day"]


@router.get("/top-decks")
def dashboard_top_decks(
    limit: int = Query(12, ge=1, le=200),
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    decks: Optional[str] = Query(None, description="Comma-separated deck names"),
) -> Dict[str, Any]:
    deck_list = decks.split(",") if decks else None
    payload = _get_cached_or_build(decks=deck_list, start_date=start_date, end_date=end_date)
    items = payload["top_decks"]["items"][: int(limit)]
    return {"success": True, "items": items}


@router.get("/segments")
def dashboard_segments(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    decks: Optional[str] = Query(None, description="Comma-separated deck names"),
) -> Dict[str, Any]:
    deck_list = decks.split(",") if decks else None
    payload = _get_cached_or_build(decks=deck_list, start_date=start_date, end_date=end_date)
    return payload["segments"]


@router.get("/all")
def dashboard_all(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    decks: Optional[str] = Query(None, description="Comma-separated deck names"),
    top_decks_limit: int = Query(12, ge=1, le=200),
) -> Dict[str, Any]:
    """
    Devolve o payload inteiro do dashboard numa única resposta.

    `_build_all_stats` já calcula tudo de uma vez — os seis endpoints acima
    apenas recortam esse mesmo payload, o que fazia a página baixar o conjunto
    completo seis vezes (e ocupar seis threads, cinco delas só esperando o lock
    do cache). Este endpoint existe para a página buscar uma vez só; os outros
    seguem disponíveis para consumo individual.
    """
    deck_list = decks.split(",") if decks else None
    payload = _get_cached_or_build(decks=deck_list, start_date=start_date, end_date=end_date)
    return {
        "success": True,
        "summary": payload["summary"],
        "reviews_by_day": payload["reviews_by_day"],
        "study_time_by_day": payload["study_time_by_day"],
        "success_rate_by_day": payload["success_rate_by_day"],
        "top_decks": {"success": True, "items": payload["top_decks"]["items"][:top_decks_limit]},
        "segments": payload["segments"],
        "answer_buttons": payload["answer_buttons"],
        "reviews_by_hour": payload["reviews_by_hour"],
        "reviews_by_weekday": payload["reviews_by_weekday"],
        "retention_by_interval": payload["retention_by_interval"],
        "interval_distribution": payload["interval_distribution"],
        "ease_distribution": payload["ease_distribution"],
        "due_forecast": payload["due_forecast"],
        "leeches": payload["leeches"],
    }
