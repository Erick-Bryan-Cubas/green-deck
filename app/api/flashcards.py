# app/api/flashcards.py

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, Tuple
import json
import re
import logging
from pathlib import Path

from app.config import OLLAMA_MODEL, OLLAMA_ANALYSIS_MODEL, OLLAMA_VALIDATION_MODEL
from app.services.ollama import ollama_generate_stream
from app.services.api_providers import openai_generate_stream, perplexity_generate_stream
from app.services.parser import (
    parse_flashcards_qa,
    parse_flashcards_json,
    normalize_cards,
    pick_default_deck,
)
from app.utils.text import (
    truncate_source,
    detect_language_pt_en_es,
)
from app.services.storage import (
    save_analysis,
    save_cards,
    save_llm_response,
    save_filter_result,
    save_generation_request,
    save_pipeline_stage,
    _get_connection,
)

from app.services.prompt_provider import PromptProvider, get_prompt_provider

router = APIRouter(prefix="/api", tags=["flashcards"])
logger = logging.getLogger(__name__)


class TextRequest(BaseModel):
    text: str
    analysisModel: Optional[str] = None  # Modelo para embeddings/análise
    analysisMode: Optional[str] = "auto"  # "embedding", "llm", ou "auto"


class CardsRequest(BaseModel):
    text: str
    textContext: Optional[str] = ""
    deckOptions: Optional[str] = "General"
    useRAG: Optional[bool] = False
    topK: Optional[int] = 0
    cardType: Optional[str] = "both"
    model: Optional[str] = None  # Modelo de geração
    validationModel: Optional[str] = None  # Modelo de validação de qualidade
    analysisModel: Optional[str] = None  # Modelo de análise de texto
    analysisId: Optional[str] = None
    anthropicApiKey: Optional[str] = None
    openaiApiKey: Optional[str] = None
    perplexityApiKey: Optional[str] = None


def _norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


# =============================================================================
# SuperMemo checklist injection (docs/supermemo_checklist.md)
# =============================================================================

_SUPERMEMO_CHECKLIST_CACHE: Optional[str] = None


def _project_root() -> Path:
    # app/api/flashcards.py -> parents: [api, app, project_root]
    return Path(__file__).resolve().parents[2]


def _load_supermemo_checklist(max_chars: int = 2500) -> str:
    """
    Carrega uma versão curta do checklist SuperMemo para injetar no prompt.
    - Mantém cache em memória.
    - Limita tamanho para não estourar o contexto de um SLM pequeno.
    """
    global _SUPERMEMO_CHECKLIST_CACHE
    if _SUPERMEMO_CHECKLIST_CACHE is not None:
        return _SUPERMEMO_CHECKLIST_CACHE

    try:
        p = _project_root() / "docs" / "supermemo_checklist.md"
        if not p.exists():
            _SUPERMEMO_CHECKLIST_CACHE = ""
            return _SUPERMEMO_CHECKLIST_CACHE

        txt = p.read_text(encoding="utf-8").strip()
        if len(txt) > max_chars:
            txt = txt[:max_chars].rstrip() + "\n\n[...truncado...]"

        _SUPERMEMO_CHECKLIST_CACHE = txt
        return _SUPERMEMO_CHECKLIST_CACHE
    except Exception:
        _SUPERMEMO_CHECKLIST_CACHE = ""
        return _SUPERMEMO_CHECKLIST_CACHE


def _format_checklist_block() -> str:
    checklist = _load_supermemo_checklist()
    if not checklist:
        return ""

    return f"""
DIRETRIZES DE QUALIDADE (SM20 Checklist) — NÃO é conteúdo do usuário.
- Use estas diretrizes APENAS para melhorar a formulação dos cards.
- NUNCA crie cards sobre estas diretrizes.
- NÃO adicione fatos que não estejam no CONTEÚDO-FONTE.

{checklist}
""".strip()


# =============================================================================
# Text Normalization Utils
# =============================================================================

def _normalize_text_for_matching(text: str) -> str:
    """
    Normaliza texto para comparações: minúsculas, remove pontuação extra,
    normaliza espaços.
    """
    import unicodedata
    text = unicodedata.normalize("NFKC", text.lower())
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# =============================================================================
# Card SRC validation with LLM
# =============================================================================

async def _validate_src_with_llm(
    cards,
    src_text: str,
    *,
    prompt_provider: PromptProvider,
    provider: str = "ollama",
    model: str = None,
    openai_key: Optional[str] = None,
    perplexity_key: Optional[str] = None,
    analysis_id: Optional[str] = None,
) -> list:
    """
    Valida rigorosamente se o campo SRC de cada card está presente no texto selecionado.
    """
    cards_input = list(cards or [])

    if not cards_input:
        return []

    # Usa modelo de validação se não especificado
    if not model:
        model = OLLAMA_VALIDATION_MODEL

    # Formata os cards para o prompt com front, back e src
    cards_text = ""
    for i, c in enumerate(cards_input):
        src = (c.get("src") or "").strip()
        front = (c.get("front") or "").strip()[:200]
        back = (c.get("back") or "").strip()[:200]
        cards_text += f"""[CARD {i+1}]
  FRONT: "{front}"
  BACK: "{back}"
  SRC: "{src}"
"""

    prompt = prompt_provider.build_src_validation_prompt(
        src_text=src_text[:4000],
        cards_text=cards_text,
    )
    system = prompt_provider.src_validation_system()

    options = {"num_predict": 512, "temperature": 0.0}

    logger.info("SRC validation using LLM model: %s (provider: %s)", model, provider)

    raw = ""
    try:
        if provider == "openai" and openai_key:
            async for piece in openai_generate_stream(openai_key, model, prompt, system=system, options=options):
                raw += piece
        elif provider == "perplexity" and perplexity_key:
            async for piece in perplexity_generate_stream(perplexity_key, model, prompt, system=system, options=options):
                raw += piece
        else:
            async for piece in ollama_generate_stream(model, prompt, system=system, options=options):
                raw += piece
    except Exception as e:
        logger.warning("LLM SRC validation failed: %s. Returning all cards without SRC filter.", e)
        return cards_input

    logger.debug("LLM SRC validation raw response: %s", raw[:500])

    kept = []
    approved_indices = set()
    rejection_reasons = {}

    for line in raw.strip().split("\n"):
        line = line.strip()
        if not line:
            continue

        match_new = re.match(r"CARD[_\s]*(\d+)\s*:\s*(SIM|NÃO|NAO|YES|NO)", line, re.IGNORECASE)
        match_old = re.match(r"(\d+)\s*:\s*(SIM|NÃO|NAO|YES|NO)", line, re.IGNORECASE)

        match = match_new or match_old
        if match:
            idx = int(match.group(1)) - 1
            verdict = match.group(2).upper()
            if verdict in ("SIM", "YES"):
                approved_indices.add(idx)
            else:
                reason_match = re.search(r"\|\s*(.+)$", line)
                if reason_match:
                    rejection_reasons[idx] = reason_match.group(1).strip()

    if not approved_indices and cards_input:
        logger.warning("LLM SRC validation returned no parseable results. Returning all cards without SRC filter.")
        return cards_input

    for i, c in enumerate(cards_input):
        if i in approved_indices:
            c["_src_validated_by"] = "llm"
            kept.append(c)
        else:
            reason = rejection_reasons.get(i, "não passou na validação")
            logger.info(
                "SRC rejected by LLM [card %d]: %s | Motivo: %s",
                i + 1,
                (c.get("src") or "")[:50],
                reason,
            )

    logger.info("SRC validation complete: %d/%d cards approved", len(kept), len(cards_input))

    try:
        save_filter_result(
            filter_type="src_validation_llm",
            cards_before=cards_input,
            cards_after=kept,
            analysis_id=analysis_id,
            metadata={
                "provider": provider,
                "model": model,
                "llm_raw_response": raw[:1000],
                "approved_indices": list(approved_indices),
                "rejection_reasons": rejection_reasons,
                "method": "llm_validation",
            },
        )
    except Exception as e:
        logger.warning("Failed to save LLM SRC filter result: %s", e)

    return kept


async def _filter_cards_by_content_relevance_llm(
    cards,
    src_text: str,
    *,
    prompt_provider: PromptProvider,
    provider: str = "ollama",
    model: str = None,
    openai_key: Optional[str] = None,
    perplexity_key: Optional[str] = None,
    analysis_id: Optional[str] = None,
) -> list:
    """
    Usa o LLM para filtrar cards cujo conteúdo não está diretamente relacionado ao texto fonte.
    """
    cards_input = list(cards or [])

    if not cards_input:
        return []

    if not model:
        logger.warning("No model specified for LLM relevance filter, using default OLLAMA_MODEL")
        model = OLLAMA_MODEL

    cards_text = ""
    for i, c in enumerate(cards_input):
        front = (c.get("front") or "").strip()
        back = (c.get("back") or "").strip()
        cards_text += f"[CARD {i+1}]\nQ: {front}\nA: {back}\n\n"

    prompt = prompt_provider.build_relevance_filter_prompt(
        src_text=src_text[:2000],
        cards_text=cards_text,
    )
    system = prompt_provider.relevance_filter_system()

    options = {"num_predict": 512, "temperature": 0.0}

    logger.info("LLM relevance filter using model: %s (provider: %s)", model, provider)

    raw = ""
    try:
        if provider == "openai" and openai_key:
            async for piece in openai_generate_stream(openai_key, model, prompt, system=system, options=options):
                raw += piece
        elif provider == "perplexity" and perplexity_key:
            async for piece in perplexity_generate_stream(perplexity_key, model, prompt, system=system, options=options):
                raw += piece
        else:
            async for piece in ollama_generate_stream(model, prompt, system=system, options=options):
                raw += piece
    except Exception as e:
        logger.warning("LLM relevance filter failed: %s. Keeping all cards.", e)
        return cards_input

    kept = []
    approved_indices = set()

    for line in raw.strip().split("\n"):
        line = line.strip()
        if not line:
            continue

        match = re.match(r"(\d+)\s*:\s*(SIM|NÃO|NAO|YES|NO)", line, re.IGNORECASE)
        if match:
            idx = int(match.group(1)) - 1
            verdict = match.group(2).upper()
            if verdict in ("SIM", "YES"):
                approved_indices.add(idx)

    if not approved_indices and cards_input:
        logger.warning("LLM relevance filter returned no parseable results. Keeping all cards.")
        return cards_input

    for i, c in enumerate(cards_input):
        if i in approved_indices:
            c["_llm_relevance"] = True
            kept.append(c)
        else:
            logger.debug("Card rejected by LLM relevance: %s", (c.get("front") or "")[:50])

    if len(kept) < len(cards_input) * 0.2 and len(cards_input) >= 3:
        logger.warning("LLM relevance filter too aggressive (kept %d/%d). Keeping all.", len(kept), len(cards_input))
        return cards_input

    try:
        save_filter_result(
            filter_type="llm_relevance",
            cards_before=cards_input,
            cards_after=kept,
            analysis_id=analysis_id,
            metadata={
                "provider": provider,
                "model": model,
                "llm_raw_response": raw[:1000],
                "approved_indices": list(approved_indices),
            },
        )
    except Exception as e:
        logger.warning("Failed to save llm relevance filter result: %s", e)

    return kept


def _filter_cards_by_content_relevance(cards, src_text: str, min_keyword_overlap: float = 0.3):
    """
    Filtra cards cujo conteúdo (front/back) não tem relação com o texto fonte.
    Versão síncrona usando heurísticas de palavras-chave (fallback).
    """
    if not cards:
        return []

    stopwords_pt = {
        "o", "e", "de", "da", "em", "um", "uma", "para", "com", "não", "que",
        "os", "dos", "das", "no", "na", "por", "mais", "se", "ou", "seu", "sua",
        "como", "mas", "ao", "ele", "ela", "entre", "quando", "muito", "nos", "já",
        "também", "só", "pelo", "pela", "até", "isso", "esse", "essa", "este", "esta",
        "são", "tem", "ser", "ter", "foi", "eram", "está", "pode", "podem",
        "the", "an", "is", "are", "was", "were", "be", "been", "being", "have",
        "has", "had", "does", "did", "will", "would", "could", "should", "may",
        "of", "to", "in", "for", "on", "with", "at", "by", "from", "into", "and", "or",
    }

    src_norm = _normalize_text_for_matching(src_text)
    src_words = set(src_norm.split()) - stopwords_pt

    kept = []
    for c in cards:
        front = _normalize_text_for_matching(c.get("front") or "")
        back = _normalize_text_for_matching(c.get("back") or "")

        card_words = (set(front.split()) | set(back.split())) - stopwords_pt
        card_words = {w for w in card_words if len(w) >= 3}

        if not card_words:
            kept.append(c)
            continue

        overlap = len(card_words & src_words) / len(card_words)

        if overlap >= min_keyword_overlap:
            c["_content_relevance"] = overlap
            kept.append(c)
        else:
            logger.debug("Card rejected (content relevance=%.2f): %s", overlap, front[:50])

    return kept


# =============================================================================
# Sistema de Scoring de Qualidade de Cards
# =============================================================================

def score_card_quality(card: dict) -> float:
    """
    Calcula um score de qualidade (0.0 a 1.0) para um flashcard.
    """
    score = 1.0
    front = (card.get("front") or "").strip()
    back = (card.get("back") or "").strip()
    src = (card.get("src") or "").strip()

    front_lower = front.lower()
    back_lower = back.lower()

    back_words = len(back.split())
    if back_words > 40:
        score -= 0.25
    elif back_words > 30:
        score -= 0.1

    if back_words < 5 and "{{c1::" not in front:
        score -= 0.15

    yes_no_patterns = [
        r"^(é verdade|é correto|existe|há|houve|foi|será|pode ser|é possível)",
        r"\?$.*\b(sim|não|verdadeiro|falso)\b",
        r"^(verdadeiro ou falso|v ou f)",
    ]
    for pattern in yes_no_patterns:
        if re.search(pattern, front_lower):
            score -= 0.3
            break

    vague_terms = ["coisa", "algo", "isso", "aquilo", "etc", "entre outros", "e assim por diante"]
    for term in vague_terms:
        if term in back_lower:
            score -= 0.1
            break

    if _normalize_text_for_matching(front) == _normalize_text_for_matching(back):
        score -= 0.4

    if src:
        score += 0.1
        src_score = card.get("_src_score", 0)
        if src_score >= 95:
            score += 0.05

    interrogatives = ["o que", "qual", "quais", "como", "por que", "quando", "onde", "quem"]
    for interr in interrogatives:
        if front_lower.startswith(interr):
            score += 0.05
            break

    if "{{c1::" in front:
        cloze_content = re.findall(r"\{\{c1::([^}]+)\}\}", front)
        if cloze_content:
            cloze_words = len(cloze_content[0].split())
            if 1 <= cloze_words <= 3:
                score += 0.1
            elif cloze_words > 5:
                score -= 0.15

    return max(0.0, min(1.0, score))


def filter_and_rank_by_quality(
    cards: list,
    min_score: float = 0.4,
    max_cards: Optional[int] = None,
    analysis_id: Optional[str] = None,
) -> list:
    """
    Filtra cards por score mínimo e retorna ordenados por qualidade.
    """
    cards_input = list(cards or [])
    scored_cards = []

    for card in cards_input:
        quality = score_card_quality(card)
        card["_quality_score"] = quality
        if quality >= min_score:
            scored_cards.append(card)
        else:
            logger.debug("Card rejected (quality=%.2f): %s", quality, (card.get("front") or "")[:50])

    scored_cards.sort(key=lambda c: c.get("_quality_score", 0), reverse=True)

    if max_cards and len(scored_cards) > max_cards:
        scored_cards = scored_cards[:max_cards]

    if cards_input:
        try:
            save_filter_result(
                filter_type="quality_score",
                cards_before=cards_input,
                cards_after=scored_cards,
                analysis_id=analysis_id,
                metadata={
                    "min_score": min_score,
                    "max_cards": max_cards,
                    "scores": {(c.get("front") or "")[:50]: c.get("_quality_score", 0) for c in cards_input},
                },
            )
        except Exception as e:
            logger.warning("Failed to save quality filter result: %s", e)

    return scored_cards


# =============================================================================
# Geração de Cards Refatorada (função reutilizável)
# =============================================================================

async def _generate_with_provider(
    provider: str,
    model: str,
    prompt: str,
    system: str,
    options: dict,
    *,
    openai_key: Optional[str] = None,
    perplexity_key: Optional[str] = None,
) -> str:
    """
    Executa geração com o provider apropriado e retorna a resposta completa.
    """
    raw = ""

    if provider == "openai" and openai_key:
        async for piece in openai_generate_stream(openai_key, model, prompt, system=system, options=options):
            raw += piece
    elif provider == "perplexity" and perplexity_key:
        async for piece in perplexity_generate_stream(perplexity_key, model, prompt, system=system, options=options):
            raw += piece
    else:
        async for piece in ollama_generate_stream(model, prompt, system=system, options=options):
            raw += piece

    return raw


def _parse_and_normalize_cards(raw: str, card_type: str, analysis_id: Optional[str] = None) -> Tuple[list, str]:
    """
    Parseia resposta do LLM e normaliza os cards.
    """
    cards_raw = normalize_cards(parse_flashcards_qa(raw))
    parse_mode = "qa"

    if not cards_raw:
        cards_raw = normalize_cards(parse_flashcards_json(raw))
        parse_mode = "json"

    cards_raw = _filter_by_card_type(cards_raw, card_type, analysis_id=analysis_id)

    return cards_raw, parse_mode


async def _apply_src_and_quality_filters_llm(
    cards_raw: list,
    src_text: str,
    target_min: int,
    target_max: int,
    *,
    prompt_provider: PromptProvider,
    provider: str = "ollama",
    validation_model: str = None,
    openai_key: Optional[str] = None,
    perplexity_key: Optional[str] = None,
    apply_quality_filter: bool = True,
    analysis_id: Optional[str] = None,
) -> list:
    """
    Aplica filtros de SRC (via LLM) e qualidade aos cards.
    """
    cards = await _validate_src_with_llm(
        cards_raw,
        src_text,
        prompt_provider=prompt_provider,
        provider=provider,
        model=validation_model,
        openai_key=openai_key,
        perplexity_key=perplexity_key,
        analysis_id=analysis_id,
    )

    if not cards and cards_raw:
        for c in cards_raw:
            c.pop("src", None)
        cards = cards_raw

    cards = _relax_src_if_needed(cards, cards_raw, target_min=target_min, target_max=target_max)

    if apply_quality_filter and cards:
        cards = filter_and_rank_by_quality(
            cards,
            min_score=0.35,
            max_cards=target_max,
            analysis_id=analysis_id,
        )

    return cards


# =============================================================================
# BÔNUS: relaxamento do SRC quando derruba demais
# =============================================================================

def _dedupe_key(card: dict) -> str:
    return (card.get("front") or "").strip() + "||" + (card.get("back") or "").strip()


def _relax_src_if_needed(cards_with_src, cards_raw, *, target_min: int, target_max: int):
    """
    Se o filtro SRC for restritivo demais, mantém os cards com SRC válido e completa até target_min com cards sem SRC.
    """
    if not cards_raw:
        return cards_with_src

    if len(cards_raw) < target_min:
        return cards_with_src

    if len(cards_with_src) >= target_min:
        return cards_with_src

    out = list(cards_with_src or [])
    seen = {_dedupe_key(c) for c in out}

    for c in cards_raw:
        if len(out) >= target_max:
            break
        k = _dedupe_key(c)
        if not k or k in seen:
            continue
        c2 = dict(c)
        c2.pop("src", None)
        out.append(c2)
        seen.add(k)
        if len(out) >= target_min:
            break

    return out


# =============================================================================
# Filtro por tipo de card (basic / cloze)
# =============================================================================

def _filter_by_card_type(cards, card_type: str, analysis_id: Optional[str] = None):
    """
    Garante que só passem cards do tipo solicitado.
    """
    cards_input = list(cards or [])

    if card_type == "cloze":
        result = [c for c in cards_input if "{{c1::" in (c.get("front") or "")]
    elif card_type == "basic":
        result = [c for c in cards_input if "{{c1::" not in (c.get("front") or "")]
    else:
        result = cards_input

    if card_type != "both" and cards_input:
        try:
            save_filter_result(
                filter_type="card_type",
                cards_before=cards_input,
                cards_after=result,
                analysis_id=analysis_id,
                metadata={"card_type_requested": card_type},
            )
        except Exception as e:
            logger.warning("Failed to save card type filter result: %s", e)

    return result


def _cards_lang_from_cards(cards) -> str:
    """
    Detecta o idioma a partir do conteúdo REAL que importa (front/back).
    """
    blob = "\n".join(((c.get("front") or "") + " " + (c.get("back") or "")).strip() for c in (cards or [])).strip()
    if not blob:
        return "unknown"
    return detect_language_pt_en_es(blob)


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


def _is_embedding_model(model_name: str) -> bool:
    """Detecta se um modelo é de embedding baseado no nome."""
    name_lower = model_name.lower()
    for pattern in EMBEDDING_MODEL_PATTERNS:
        if re.search(pattern, name_lower):
            return True
    return False


@router.post("/analyze-text-stream")
async def analyze_text_stream(
    request: TextRequest,
    prompt_provider: PromptProvider = Depends(get_prompt_provider),
):
    async def generate():
        try:
            analysis_model = request.analysisModel or OLLAMA_ANALYSIS_MODEL
            analysis_mode = request.analysisMode or "auto"

            if analysis_mode == "auto":
                analysis_mode = "embedding" if _is_embedding_model(analysis_model) else "llm"

            logger.info("Analysis model: %s, mode: %s", analysis_model, analysis_mode)

            from app.services.ollama import (
                ollama_embed,
                chunk_text_semantic,
                chunk_text,
                cosine_similarity,
            )

            yield f"event: progress\ndata: {json.dumps({'percent': 10, 'stage': 'preparing', 'mode': analysis_mode})}\n\n"

            src = truncate_source(request.text or "")

            detected_lang = detect_language_pt_en_es(src[:500])
            language = "portuguese" if detected_lang == "pt-br" else "english"

            chunks = chunk_text_semantic(
                src,
                max_words=400,
                overlap_sentences=2,
                language=language,
            )

            if not chunks:
                chunks = chunk_text(src, chunk_size=400)

            yield f"event: progress\ndata: {json.dumps({'percent': 20, 'stage': 'chunking', 'chunks': len(chunks)})}\n\n"

            if analysis_mode == "embedding":
                yield f"event: progress\ndata: {json.dumps({'percent': 30, 'stage': 'embedding', 'model': analysis_model})}\n\n"

                chunk_embeddings = []
                for i, chunk in enumerate(chunks):
                    try:
                        emb = await ollama_embed(analysis_model, chunk)
                        chunk_embeddings.append((chunk, emb))
                    except Exception as embed_error:
                        logger.warning("Embedding failed: %s. Falling back to LLM mode.", embed_error)
                        analysis_mode = "llm"
                        yield f"event: progress\ndata: {json.dumps({'percent': 35, 'stage': 'fallback_to_llm', 'reason': str(embed_error)})}\n\n"
                        break

                    if len(chunks) > 3:
                        progress = 30 + int((i + 1) / len(chunks) * 25)
                        yield f"event: progress\ndata: {json.dumps({'percent': progress, 'stage': 'embedding', 'chunk': i + 1, 'total': len(chunks)})}\n\n"

                if analysis_mode == "embedding" and chunk_embeddings:
                    if detected_lang == "pt-br":
                        query = "conceitos importantes, definições técnicas, contrastes e distinções"
                    else:
                        query = "important concepts, technical definitions, contrasts and distinctions"

                    query_emb = await ollama_embed(analysis_model, query)

                    yield f"event: progress\ndata: {json.dumps({'percent': 60, 'stage': 'ranking'})}\n\n"

                    scored = [(chunk, cosine_similarity(emb, query_emb)) for chunk, emb in chunk_embeddings]
                    scored.sort(key=lambda x: x[1], reverse=True)

                    min_similarity = 0.3
                    top_chunks = [chunk for chunk, score in scored[:5] if score >= min_similarity][:3]

                    if not top_chunks and scored:
                        top_chunks = [chunk for chunk, _ in scored[:3]]

                    summary = "\n\n".join(top_chunks)
                    method_used = "embedding"

            if analysis_mode == "llm":
                yield f"event: progress\ndata: {json.dumps({'percent': 40, 'stage': 'llm_analysis', 'model': analysis_model})}\n\n"

                full_text = "\n\n".join(chunks[:5])

                prompt = prompt_provider.build_text_analysis_prompt(
                    text=full_text[:4000],
                    detected_lang=detected_lang,
                )
                system = prompt_provider.text_analysis_system()
                options = {"num_predict": 1024, "temperature": 0.3}

                raw = ""
                try:
                    async for piece in ollama_generate_stream(analysis_model, prompt, system=system, options=options):
                        raw += piece
                except Exception as llm_error:
                    logger.warning("LLM analysis failed: %s", llm_error)
                    raw = "\n\n".join(chunks[:3])

                yield f"event: progress\ndata: {json.dumps({'percent': 80, 'stage': 'llm_complete'})}\n\n"

                summary = raw.strip() if raw.strip() else "\n\n".join(chunks[:3])
                method_used = "llm"

            result = {"content": [{"type": "text", "text": summary}], "method": method_used}

            analysis_id = save_analysis(
                src,
                summary,
                {"chunks": len(chunks), "method": method_used, "model": analysis_model},
            )
            result["analysis_id"] = analysis_id

            yield f"event: progress\ndata: {json.dumps({'percent': 100, 'stage': 'done', 'analysis_id': analysis_id, 'method': method_used})}\n\n"
            yield f"event: result\ndata: {json.dumps(result)}\n\n"

        except Exception as e:
            logger.exception("Error in analyze_text_stream")
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/generate-cards-stream")
async def generate_cards_stream(
    request: CardsRequest,
    prompt_provider: PromptProvider = Depends(get_prompt_provider),
):
    async def generate():
        try:
            model = request.model or OLLAMA_MODEL
            logger.info("Generation model: %s", model)

            use_openai = request.openaiApiKey and ("gpt" in model.lower() or model.startswith("o1-"))
            use_perplexity = request.perplexityApiKey and "sonar" in model.lower()
            use_ollama = not use_openai and not use_perplexity

            provider = "ollama" if use_ollama else ("openai" if use_openai else "perplexity")
            logger.info("Using provider: %s", provider)

            yield f"event: stage\ndata: {json.dumps({'stage': 'generation_started'})}\n\n"

            src = truncate_source(request.text or "")
            ctx = (request.textContext or "").strip()

            card_type = (request.cardType or "both").strip().lower()
            if card_type not in ("basic", "cloze", "both"):
                card_type = "both"

            word_count = len(src.split())
            if word_count < 140:
                target_min, target_max = 3, 8
            elif word_count < 320:
                target_min, target_max = 5, 12
            elif word_count < 700:
                target_min, target_max = 8, 18
            else:
                target_min, target_max = 10, 30

            request_id = save_generation_request(
                source_text=src,
                context_text=ctx,
                card_type=card_type,
                model=model,
                provider=provider,
                source_type="highlight" if len(src) < len(ctx) else "full_text",
                word_count=word_count,
                target_min=target_min,
                target_max=target_max,
                analysis_id=request.analysisId,
            )

            checklist_block = _format_checklist_block()

            prompt = prompt_provider.build_flashcards_generation_prompt(
                src=src,
                ctx=ctx,
                checklist_block=checklist_block,
                target_min=target_min,
                target_max=target_max,
                card_type=card_type,  # type: ignore[arg-type]
            )

            options = {"num_predict": 4096, "temperature": 0.0}
            system_prompt = prompt_provider.flashcards_system(card_type)  # type: ignore[arg-type]

            raw = ""
            if use_openai:
                async for piece in openai_generate_stream(request.openaiApiKey, model, prompt, system=system_prompt, options=options):
                    raw += piece
            elif use_perplexity:
                async for piece in perplexity_generate_stream(request.perplexityApiKey, model, prompt, system=system_prompt, options=options):
                    raw += piece
            else:
                async for piece in ollama_generate_stream(model, prompt, system=system_prompt, options=options):
                    raw += piece

            save_llm_response(
                provider=provider,
                model=model,
                prompt=prompt,
                response=raw,
                analysis_id=request.analysisId,
                system_prompt=system_prompt,
                card_type=card_type,
                source_text_length=len(src),
                options=options,
            )

            save_pipeline_stage(
                request_id=request_id,
                stage="llm_generation",
                cards_in=0,
                cards_out=0,
                details={"response_length": len(raw), "model": model, "provider": provider},
                analysis_id=request.analysisId,
            )

            cards_raw = normalize_cards(parse_flashcards_qa(raw))
            parse_mode = "qa"
            if not cards_raw:
                cards_raw = normalize_cards(parse_flashcards_json(raw))
                parse_mode = "json"

            save_pipeline_stage(
                request_id=request_id,
                stage="parsing",
                cards_in=0,
                cards_out=len(cards_raw),
                details={"parse_mode": parse_mode},
                analysis_id=request.analysisId,
            )

            cards_before_type_filter = len(cards_raw)
            cloze_count = sum(1 for c in cards_raw if "{{c1::" in (c.get("front") or ""))
            logger.info("Parsed %d cards (%d with cloze syntax), card_type=%s", cards_before_type_filter, cloze_count, card_type)

            cards_raw = _filter_by_card_type(cards_raw, card_type, analysis_id=request.analysisId)

            save_pipeline_stage(
                request_id=request_id,
                stage="type_filter",
                cards_in=cards_before_type_filter,
                cards_out=len(cards_raw),
                details={"card_type": card_type, "cloze_syntax_count": cloze_count},
                analysis_id=request.analysisId,
            )

            yield f"event: stage\ndata: {json.dumps({'stage': 'parsed', 'mode': parse_mode, 'count': len(cards_raw), 'before_type_filter': cards_before_type_filter})}\n\n"

            validation_model = request.validationModel or model
            logger.info("Validation model: %s", validation_model)

            cards_before_src = len(cards_raw)
            cards = await _validate_src_with_llm(
                cards_raw,
                src,
                prompt_provider=prompt_provider,
                provider=provider,
                model=validation_model,
                openai_key=request.openaiApiKey,
                perplexity_key=request.perplexityApiKey,
                analysis_id=request.analysisId,
            )

            save_pipeline_stage(
                request_id=request_id,
                stage="src_filter_llm",
                cards_in=cards_before_src,
                cards_out=len(cards),
                details={"method": "llm_validation", "validation_model": validation_model},
                analysis_id=request.analysisId,
            )

            yield f"event: stage\ndata: {json.dumps({'stage': 'src_filtered', 'kept': len(cards), 'dropped': max(0, len(cards_raw) - len(cards)), 'method': 'llm'})}\n\n"

            cards_before_relevance = len(cards)
            cards = await _filter_cards_by_content_relevance_llm(
                cards,
                src,
                prompt_provider=prompt_provider,
                provider=provider,
                model=validation_model,
                openai_key=request.openaiApiKey,
                perplexity_key=request.perplexityApiKey,
                analysis_id=request.analysisId,
            )
            if len(cards) < cards_before_relevance:
                yield f"event: stage\ndata: {json.dumps({'stage': 'llm_relevance_filtered', 'kept': len(cards), 'dropped': cards_before_relevance - len(cards)})}\n\n"

            if not cards and cards_raw:
                for c in cards_raw:
                    c.pop("src", None)
                cards = cards_raw
                yield f"event: stage\ndata: {json.dumps({'stage': 'src_bypassed', 'count': len(cards)})}\n\n"

            cards_relaxed = _relax_src_if_needed(cards, cards_raw, target_min=target_min, target_max=target_max)
            if len(cards_relaxed) != len(cards):
                yield (
                    "event: stage\ndata: "
                    + json.dumps(
                        {
                            "stage": "src_relaxed",
                            "kept_with_src": len(cards),
                            "total_after_relax": len(cards_relaxed),
                            "target_min": target_min,
                        }
                    )
                    + "\n\n"
                )
                cards = cards_relaxed

            out_lang = _cards_lang_from_cards(cards)
            yield f"event: stage\ndata: {json.dumps({'stage': 'lang_check', 'lang': out_lang, 'cards': len(cards), 'min': target_min})}\n\n"

            if not cards or out_lang != "pt-br" or len(cards) < target_min:
                yield (
                    "event: stage\ndata: "
                    + json.dumps(
                        {"stage": "repair_pass", "reason": f"lang={out_lang}, cards={len(cards)}, min={target_min}"}
                    )
                    + "\n\n"
                )

                repair_prompt = prompt_provider.build_flashcards_repair_prompt(
                    src=src,
                    ctx=ctx,
                    checklist_block=checklist_block,
                    target_min=target_min,
                    target_max=target_max,
                    card_type=card_type,  # type: ignore[arg-type]
                )

                raw2 = ""
                repair_system = prompt_provider.flashcards_system("basic")  # força system PTBR

                if use_openai:
                    async for piece in openai_generate_stream(
                        request.openaiApiKey,
                        model,
                        repair_prompt,
                        system=repair_system,
                        options={"num_predict": 4096, "temperature": 0.0},
                    ):
                        raw2 += piece
                elif use_perplexity:
                    async for piece in perplexity_generate_stream(
                        request.perplexityApiKey,
                        model,
                        repair_prompt,
                        system=repair_system,
                        options={"num_predict": 4096, "temperature": 0.0},
                    ):
                        raw2 += piece
                else:
                    async for piece in ollama_generate_stream(
                        model,
                        repair_prompt,
                        system=repair_system,
                        options={"num_predict": 4096, "temperature": 0.0},
                    ):
                        raw2 += piece

                cards2_raw = normalize_cards(parse_flashcards_qa(raw2))
                repair_mode = "qa"
                if not cards2_raw:
                    cards2_raw = normalize_cards(parse_flashcards_json(raw2))
                    repair_mode = "json"

                cards2_raw = _filter_by_card_type(cards2_raw, card_type, analysis_id=request.analysisId)

                yield f"event: stage\ndata: {json.dumps({'stage': 'repair_parsed', 'mode': repair_mode, 'count': len(cards2_raw)})}\n\n"

                cards2 = await _validate_src_with_llm(
                    cards2_raw,
                    src,
                    prompt_provider=prompt_provider,
                    provider=provider,
                    model=validation_model,
                    openai_key=request.openaiApiKey,
                    perplexity_key=request.perplexityApiKey,
                    analysis_id=request.analysisId,
                )
                yield f"event: stage\ndata: {json.dumps({'stage': 'repair_src_filtered', 'kept': len(cards2), 'dropped': max(0, len(cards2_raw) - len(cards2)), 'method': 'llm'})}\n\n"

                cards2_before_relevance = len(cards2)
                cards2 = await _filter_cards_by_content_relevance_llm(
                    cards2,
                    src,
                    prompt_provider=prompt_provider,
                    provider=provider,
                    model=validation_model,
                    openai_key=request.openaiApiKey,
                    perplexity_key=request.perplexityApiKey,
                    analysis_id=request.analysisId,
                )
                if len(cards2) < cards2_before_relevance:
                    yield f"event: stage\ndata: {json.dumps({'stage': 'repair_llm_relevance_filtered', 'kept': len(cards2), 'dropped': cards2_before_relevance - len(cards2)})}\n\n"

                if not cards2 and cards2_raw:
                    for c in cards2_raw:
                        c.pop("src", None)
                    cards2 = cards2_raw
                    yield f"event: stage\ndata: {json.dumps({'stage': 'repair_src_bypassed', 'count': len(cards2)})}\n\n"

                cards2_relaxed = _relax_src_if_needed(cards2, cards2_raw, target_min=target_min, target_max=target_max)
                if len(cards2_relaxed) != len(cards2):
                    yield (
                        "event: stage\ndata: "
                        + json.dumps(
                            {
                                "stage": "repair_src_relaxed",
                                "kept_with_src": len(cards2),
                                "total_after_relax": len(cards2_relaxed),
                                "target_min": target_min,
                            }
                        )
                        + "\n\n"
                    )
                    cards2 = cards2_relaxed

                if cards2:
                    cards = cards2

                out_lang2 = _cards_lang_from_cards(cards)
                yield f"event: stage\ndata: {json.dumps({'stage': 'lang_check_after_repair', 'lang': out_lang2, 'cards': len(cards)})}\n\n"

            deck = pick_default_deck(request.deckOptions or "General")

            result_cards = []
            for c in cards:
                item = {"front": c["front"], "back": c["back"], "deck": deck}
                if c.get("src"):
                    item["src"] = c["src"]
                result_cards.append(item)

            cards_id = save_cards(result_cards, analysis_id=request.analysisId, source_text=src)

            conn = _get_connection()
            conn.execute(
                "UPDATE llm_responses SET cards_id = ? WHERE analysis_id = ? AND cards_id = ''",
                [cards_id, request.analysisId or ""],
            )
            conn.close()

            yield f"event: stage\ndata: {json.dumps({'stage': 'done', 'total_cards': len(result_cards), 'cards_id': cards_id})}\n\n"
            yield f"event: result\ndata: {json.dumps({'success': True, 'cards': result_cards})}\n\n"

        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
