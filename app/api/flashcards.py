# app/api/flashcards.py

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, Tuple, List
import json
import re
import logging
from pathlib import Path
import httpx

from app.config import OLLAMA_MODEL, OLLAMA_ANALYSIS_MODEL, OLLAMA_VALIDATION_MODEL, RATE_LIMIT_GENERATE
from app.middleware.rate_limit import limiter


# =============================================================================
# API Keys from Headers (Security Enhancement)
# =============================================================================
class ApiKeys:
    """Container for API keys extracted from headers or request body."""

    def __init__(
        self,
        anthropic_key: Optional[str] = None,
        openai_key: Optional[str] = None,
        perplexity_key: Optional[str] = None,
    ):
        self.anthropic = anthropic_key
        self.openai = openai_key
        self.perplexity = perplexity_key


def get_api_keys_from_headers(
    x_anthropic_key: Optional[str] = Header(None, alias="X-Anthropic-Key"),
    x_openai_key: Optional[str] = Header(None, alias="X-OpenAI-Key"),
    x_perplexity_key: Optional[str] = Header(None, alias="X-Perplexity-Key"),
) -> ApiKeys:
    """
    Extract API keys from request headers.
    This is more secure than passing keys in the request body as headers
    are typically not logged by default in server access logs.
    """
    return ApiKeys(
        anthropic_key=x_anthropic_key,
        openai_key=x_openai_key,
        perplexity_key=x_perplexity_key,
    )


def merge_api_keys(header_keys: ApiKeys, body_request) -> ApiKeys:
    """
    Merge API keys from headers and request body.
    Headers take priority over body for security reasons.
    Body values are used as fallback for backward compatibility.
    """
    return ApiKeys(
        anthropic_key=header_keys.anthropic or getattr(body_request, "anthropicApiKey", None),
        openai_key=header_keys.openai or getattr(body_request, "openaiApiKey", None),
        perplexity_key=header_keys.perplexity or getattr(body_request, "perplexityApiKey", None),
    )
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
from app.utils.validation import validate_content_sufficiency
from app.utils.prompt_validation import validate_custom_prompt, log_injection_attempt
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
from app.api.prompts import get_default_prompts_for_ui
from app.api.models import get_provider_for_model, get_first_available_ollama_llm
from app.api.topic_segmentation import (
    segment_with_langextract,
    is_langextract_available,
    TOPIC_CATEGORIES,
)

router = APIRouter(prefix="/api", tags=["flashcards"])
logger = logging.getLogger(__name__)


class TextRequest(BaseModel):
    text: str
    analysisModel: Optional[str] = None  # Modelo para embeddings/análise
    analysisMode: Optional[str] = "auto"  # "embedding", "llm", ou "auto"
    openaiApiKey: Optional[str] = None
    perplexityApiKey: Optional[str] = None


class CardsRequest(BaseModel):
    text: str
    textContext: Optional[str] = ""
    deckOptions: Optional[str] = "General"
    useRAG: Optional[bool] = False
    topK: Optional[int] = 0
    cardType: Optional[str] = "both"
    model: Optional[str] = None  # Modelo de geracao
    validationModel: Optional[str] = None  # Modelo de validacao de qualidade
    analysisModel: Optional[str] = None  # Modelo de analise de texto
    analysisId: Optional[str] = None
    anthropicApiKey: Optional[str] = None
    openaiApiKey: Optional[str] = None
    perplexityApiKey: Optional[str] = None
    # Prompts personalizados (opcional - se vazio, usa o padrao)
    customSystemPrompt: Optional[str] = None
    customGenerationPrompt: Optional[str] = None
    customGuidelines: Optional[str] = None
    # Quantidade de cards desejada (opcional - se vazio, calcula automaticamente)
    numCards: Optional[int] = None
    # Modo simulado/prova (textos com questões de múltipla escolha)
    isExamMode: Optional[bool] = False


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
        if not model:
            model = await get_first_available_ollama_llm()
        if not model:
            logger.warning("No model available for SRC validation, skipping")
            return cards_input  # Retorna cards sem validar

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

    removed_with_reasons = []  # Armazena cards removidos com motivos
    for i, c in enumerate(cards_input):
        if i in approved_indices:
            c["_src_validated_by"] = "llm"
            kept.append(c)
        else:
            reason = rejection_reasons.get(i, "SRC não encontrado no texto selecionado")
            logger.info(
                "SRC rejected by LLM [card %d]: %s | Motivo: %s",
                i + 1,
                (c.get("front") or c.get("src") or "")[:50],
                reason,
            )
            # Adiciona o motivo ao card removido para rastreabilidade
            removed_card = c.copy()
            removed_card["rejection_reason"] = reason
            removed_card["rejection_filter"] = "src_validation_llm"
            removed_with_reasons.append(removed_card)

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
            removed_cards_with_reasons=removed_with_reasons,
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
        model = OLLAMA_MODEL
        if not model:
            model = await get_first_available_ollama_llm()
        if not model:
            logger.warning("No model available for LLM relevance filter, skipping")
            return cards_input  # Retorna cards sem filtrar

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
    rejection_reasons = {}  # Captura motivos de rejeição

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
            else:
                # Tenta capturar motivo após o veredicto
                reason_match = re.search(r"\|\s*(.+)$", line)
                if reason_match:
                    rejection_reasons[idx] = reason_match.group(1).strip()

    if not approved_indices and cards_input:
        logger.warning("LLM relevance filter returned no parseable results. Keeping all cards.")
        return cards_input

    removed_with_reasons = []  # Cards removidos com motivos
    for i, c in enumerate(cards_input):
        if i in approved_indices:
            c["_llm_relevance"] = True
            kept.append(c)
        else:
            reason = rejection_reasons.get(i, "Informação não presente no texto-fonte")
            logger.debug("Card rejected by LLM relevance [%d]: %s | Motivo: %s", i+1, (c.get("front") or "")[:50], reason)
            # Adiciona o motivo ao card removido para rastreabilidade
            removed_card = c.copy()
            removed_card["rejection_reason"] = reason
            removed_card["rejection_filter"] = "llm_relevance"
            removed_with_reasons.append(removed_card)

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
                "rejection_reasons": rejection_reasons,
            },
            removed_cards_with_reasons=removed_with_reasons,
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
@limiter.limit("20/minute")
async def analyze_text_stream(
    http_request: Request,
    request: TextRequest,
    prompt_provider: PromptProvider = Depends(get_prompt_provider),
    header_keys: ApiKeys = Depends(get_api_keys_from_headers),
):
    # Merge API keys from headers (priority) and body (fallback for backward compatibility)
    api_keys = merge_api_keys(header_keys, request)

    async def generate():
        try:
            analysis_model = request.analysisModel or OLLAMA_ANALYSIS_MODEL

            # Fallback: buscar primeiro modelo Ollama disponível
            if not analysis_model:
                analysis_model = await get_first_available_ollama_llm()
                if not analysis_model:
                    yield f"event: error\ndata: {json.dumps({'error': 'Nenhum modelo disponível para análise.'})}\n\n"
                    return

            analysis_mode = request.analysisMode or "auto"

            # Detecta provider baseado no modelo e chaves API
            use_openai = api_keys.openai and ("gpt" in analysis_model.lower() or analysis_model.startswith("o1-"))
            use_perplexity = api_keys.perplexity and "sonar" in analysis_model.lower()
            use_ollama = not use_openai and not use_perplexity
            
            provider = "ollama" if use_ollama else ("openai" if use_openai else "perplexity")

            if analysis_mode == "auto":
                # APIs externas sempre usam modo LLM
                if use_openai or use_perplexity:
                    analysis_mode = "llm"
                else:
                    analysis_mode = "embedding" if _is_embedding_model(analysis_model) else "llm"

            logger.info("Analysis model: %s, mode: %s, provider: %s", analysis_model, analysis_mode, provider)

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
                    if use_openai:
                        async for piece in openai_generate_stream(api_keys.openai, analysis_model, prompt, system=system, options=options):
                            raw += piece
                    elif use_perplexity:
                        async for piece in perplexity_generate_stream(api_keys.perplexity, analysis_model, prompt, system=system, options=options):
                            raw += piece
                    else:
                        async for piece in ollama_generate_stream(analysis_model, prompt, system=system, options=options):
                            raw += piece
                except Exception as llm_error:
                    logger.warning("LLM analysis failed: %s", llm_error)
                    yield f"event: error\ndata: {json.dumps({'error': f'LLM analysis failed: {str(llm_error)}'})}\n\n"
                    return

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


# =============================================================================
# Topic Segmentation - Marcação automática por tópico
# =============================================================================

class SegmentTopicsRequest(BaseModel):
    text: str
    analysisModel: Optional[str] = None
    openaiApiKey: Optional[str] = None
    perplexityApiKey: Optional[str] = None


# Schemas Pydantic para Ollama JSON Mode
class TopicSegment(BaseModel):
    """Segmento de texto com categoria de tópico."""
    excerpt: str = Field(..., description="Trecho literal do texto (50-200 caracteres)")
    category: str = Field(..., description="DEFINICAO|EXEMPLO|CONCEITO|FORMULA|PROCEDIMENTO|COMPARACAO")
    custom_name: Optional[str] = Field(None, description="Nome customizado para categoria ESPECIFICO")


class SegmentationResponse(BaseModel):
    """Resposta de segmentação de tópicos."""
    segments: List[TopicSegment] = Field(..., description="Lista de segmentos identificados")


# Cores para categorias base de tópicos
TOPIC_COLORS = {
    "DEFINICAO": {"color": "#fef08a", "name": "Definições"},
    "EXEMPLO": {"color": "#bbf7d0", "name": "Exemplos"},
    "CONCEITO": {"color": "#bfdbfe", "name": "Conceitos"},
    "FORMULA": {"color": "#ddd6fe", "name": "Fórmulas"},
    "PROCEDIMENTO": {"color": "#fed7aa", "name": "Procedimentos"},
    "COMPARACAO": {"color": "#fbcfe8", "name": "Comparações"},
    "ESPECIFICO": {"color": "#e5e7eb", "name": "Específico"},
}

# Cores extras para tópicos customizados identificados pelo LLM
CUSTOM_TOPIC_COLORS = ["#fcd34d", "#4ade80", "#60a5fa", "#a78bfa", "#f87171", "#22d3d8"]


def _clean_llm_json(raw: str) -> str:
    """
    Limpa e corrige erros comuns de JSON gerado por LLMs.
    """
    cleaned = raw

    # Corrige todas as variações de "custom_name" (case insensitive)
    # Cobre: custom-Name, custom-name, customName, custom_Name, custom-than, etc.
    cleaned = re.sub(r'"custom[-_]?[nN]ame"', '"custom_name"', cleaned)
    cleaned = re.sub(r'"custom[-_]?than"', '"custom_name"', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'"customName"', '"custom_name"', cleaned, flags=re.IGNORECASE)

    # Remove fragmentos soltos como "custom", que não são pares chave-valor válidos
    # Padrão: "palavra", seguida de vírgula, sem : após
    cleaned = re.sub(r'"[a-zA-Z_-]+"\s*,\s*(?="[a-zA-Z_-]+":\s*)', '', cleaned)

    # Remove vírgulas antes de } ou ]
    cleaned = re.sub(r',\s*([}\]])', r'\1', cleaned)

    # Remove vírgulas duplicadas
    cleaned = re.sub(r',\s*,', ',', cleaned)

    # Remove caracteres de controle que podem quebrar JSON (exceto whitespace válido)
    cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', cleaned)

    return cleaned


async def _call_ollama_structured(prompt: str, schema: type, model: str) -> dict:
    """
    Chama Ollama com JSON Mode estruturado usando Pydantic schema.
    Garante JSON 100% válido conforme o schema fornecido.
    """
    payload = {
        "model": model,
        "prompt": prompt,
        "format": schema.model_json_schema(),
        "stream": False,
        "options": {"temperature": 0.0}
    }

    logger.info("[Ollama JSON Mode] Calling model: %s with schema: %s", model, schema.__name__)

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "http://localhost:11434/api/generate",
                json=payload,
                timeout=120.0
            )
            response.raise_for_status()
            result = response.json()

            raw_response = result.get("response", "{}")
            logger.debug("[Ollama JSON Mode] Raw response: %s", raw_response[:500])

            parsed = json.loads(raw_response)
            logger.info("[Ollama JSON Mode] Successfully parsed JSON with %d segments",
                       len(parsed.get("segments", [])))
            return parsed

    except httpx.HTTPStatusError as e:
        logger.error("[Ollama JSON Mode] HTTP error: %s", e)
        raise
    except json.JSONDecodeError as e:
        logger.error("[Ollama JSON Mode] JSON parse error: %s", e)
        raise
    except Exception as e:
        logger.error("[Ollama JSON Mode] Unexpected error: %s", e)
        raise


def _normalize_whitespace(text: str) -> tuple[str, list[int]]:
    """
    Normaliza whitespace (múltiplos espaços/quebras de linha -> espaço único).
    Retorna (texto_normalizado, mapeamento_posicoes).
    O mapeamento permite converter índices do texto normalizado para o original.
    """
    normalized = []
    position_map = []  # position_map[i] = índice no texto original
    i = 0
    prev_was_space = False

    while i < len(text):
        char = text[i]
        if char in ' \t\n\r':
            if not prev_was_space:
                normalized.append(' ')
                position_map.append(i)
                prev_was_space = True
        else:
            normalized.append(char)
            position_map.append(i)
            prev_was_space = False
        i += 1

    return ''.join(normalized), position_map


def _find_in_normalized(text: str, excerpt: str, text_norm: str, pos_map: list[int]) -> tuple[int, int]:
    """
    Busca excerpt no texto usando normalização de whitespace.
    Retorna (start_original, end_original) ou (-1, -1) se não encontrado.
    """
    # Normaliza o excerpt também
    excerpt_norm = ' '.join(excerpt.split())

    # Busca no texto normalizado
    norm_start = text_norm.find(excerpt_norm)
    if norm_start == -1:
        # Tenta case-insensitive
        norm_start = text_norm.lower().find(excerpt_norm.lower())

    if norm_start == -1:
        return -1, -1

    norm_end = norm_start + len(excerpt_norm)

    # Mapeia de volta para posições originais
    if norm_start >= len(pos_map) or norm_end > len(pos_map):
        return -1, -1

    orig_start = pos_map[norm_start]

    # Para o end, precisamos encontrar o fim do último caractere no original
    if norm_end >= len(pos_map):
        orig_end = len(text)
    else:
        orig_end = pos_map[norm_end - 1] + 1
        # Expande para incluir whitespace trailing no original
        while orig_end < len(text) and text[orig_end] in ' \t\n\r':
            orig_end += 1
            # Para no próximo caractere não-whitespace
            if orig_end < len(text) and text[orig_end] not in ' \t\n\r':
                break

    return orig_start, orig_end


def _calculate_positions(text: str, segments_raw: List[dict]) -> List[dict]:
    """
    Calcula posições start/end a partir dos trechos extraídos pelo LLM.
    Usa busca com normalização de whitespace para maior tolerância.
    """
    results = []
    used_positions = set()  # Evita duplicatas de posição

    logger.info("[CalculatePositions] Processing %d raw segments", len(segments_raw))

    # Pré-calcula texto normalizado para buscas flexíveis
    text_norm, pos_map = _normalize_whitespace(text)

    for i, seg in enumerate(segments_raw):
        excerpt = seg.get("excerpt", "")
        if not excerpt or len(excerpt) < 20:
            logger.debug("[CalculatePositions] Segment %d skipped: excerpt too short (%d chars)", i, len(excerpt))
            continue

        start = -1
        end = -1

        # 1. Busca exata primeiro
        exact_start = text.find(excerpt)
        if exact_start != -1:
            start = exact_start
            end = start + len(excerpt)
            logger.debug("[CalculatePositions] Segment %d: found via exact match", i)

        # 2. Se não encontrou, tenta case-insensitive
        if start == -1:
            lower_start = text.lower().find(excerpt.lower())
            if lower_start != -1:
                start = lower_start
                end = start + len(excerpt)
                logger.debug("[CalculatePositions] Segment %d: found via case-insensitive search", i)

        # 3. Se ainda não encontrou, tenta com normalização de whitespace
        if start == -1:
            start, end = _find_in_normalized(text, excerpt, text_norm, pos_map)
            if start != -1:
                logger.debug("[CalculatePositions] Segment %d: found via whitespace-normalized search", i)

        # 4. Fallback: busca primeiros 50 caracteres
        if start == -1 and len(excerpt) > 50:
            short = excerpt[:50]
            short_start = text.find(short)
            if short_start == -1:
                short_start = text.lower().find(short.lower())
            if short_start == -1:
                # Tenta com normalização
                short_start, _ = _find_in_normalized(text, short, text_norm, pos_map)
            if short_start != -1:
                start = short_start
                end = min(start + len(excerpt), len(text))
                logger.debug("[CalculatePositions] Segment %d: found via partial match (first 50 chars)", i)

        if start == -1:
            logger.warning("[CalculatePositions] Segment %d NOT FOUND in text: '%s...'", i, excerpt[:60])
            continue

        if start in used_positions:
            logger.debug("[CalculatePositions] Segment %d skipped: duplicate position %d", i, start)
            continue

        # Limita ao tamanho do texto
        end = min(end, len(text))

        used_positions.add(start)

        results.append({
            "start": start,
            "end": end,
            "category": seg.get("category", "CONCEITO").upper(),
            "custom_name": seg.get("custom_name"),
            "text": text[start:end],
        })

        logger.debug("[CalculatePositions] Segment %d: start=%d, end=%d, category=%s",
                    i, start, end, seg.get("category"))

    logger.info("[CalculatePositions] Found %d valid segments out of %d", len(results), len(segments_raw))
    return results


def _parse_topic_segments(raw_response: str, original_text: str) -> list:
    """
    Parseia a resposta JSON do LLM e valida os segmentos.
    """
    logger.info("Parsing topic segments from LLM response (length: %d)", len(raw_response))
    logger.debug("Raw response preview: %s", raw_response[:500] if raw_response else "empty")

    # Tenta extrair JSON da resposta
    try:
        # Remove possíveis markdown code blocks
        cleaned = re.sub(r"```json\s*", "", raw_response)
        cleaned = re.sub(r"```\s*", "", cleaned)
        cleaned = cleaned.strip()

        # Limpa erros comuns de JSON do LLM
        cleaned = _clean_llm_json(cleaned)

        # Encontra o JSON
        json_match = re.search(r'\{[\s\S]*\}', cleaned)
        if json_match:
            json_str = json_match.group()
            logger.debug("Cleaned JSON (first 500 chars): %s", json_str[:500] if json_str else "empty")
            try:
                data = json.loads(json_str)
            except json.JSONDecodeError as e:
                logger.warning("First JSON parse failed at pos %d: %s", e.pos, e.msg)
                # Log do contexto ao redor do erro
                error_context = json_str[max(0, e.pos-30):min(len(json_str), e.pos+30)]
                logger.warning("Error context: ...%s...", repr(error_context))
                # Tenta limpeza mais agressiva
                json_str = re.sub(r'[^\x20-\x7E\n\r\t]', '', json_str)
                try:
                    data = json.loads(json_str)
                except json.JSONDecodeError as e2:
                    logger.error("Second JSON parse also failed: %s", e2)
                    raise e2
            logger.info("Found JSON with %d segments", len(data.get("segments", [])))
        else:
            logger.warning("No JSON found in response")
            return []

        segments = data.get("segments", [])
        validated = []
        text_len = len(original_text)
        logger.info("Original text length: %d, segments to validate: %d", text_len, len(segments))

        for i, seg in enumerate(segments):
            start = seg.get("start", 0)
            end = seg.get("end", 0)
            category = seg.get("category", "ESPECIFICO")
            custom_name = seg.get("custom_name")

            # Valida posições
            if start < 0 or end <= start or end > text_len:
                logger.debug("Segment %d rejected: invalid positions (start=%d, end=%d, text_len=%d)", i, start, end, text_len)
                continue
            if end - start < 20 or end - start > 600:
                logger.debug("Segment %d rejected: invalid length (%d)", i, end - start)
                continue

            # Extrai texto do segmento
            segment_text = original_text[start:end]

            validated.append({
                "start": start,
                "end": end,
                "category": category.upper() if category else "ESPECIFICO",
                "custom_name": custom_name,
                "text": segment_text,
            })

        logger.info("Validated %d segments out of %d", len(validated), len(segments))
        return validated
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.warning("Failed to parse topic segments: %s", e)
        logger.debug("Raw response that failed: %s", raw_response[:1000] if raw_response else "empty")
        return []


def _build_topic_definitions(segments: list) -> list:
    """
    Constrói a lista de definições de tópicos com cores atribuídas.
    """
    topics = {}
    custom_color_idx = 0

    for seg in segments:
        category = seg["category"]
        custom_name = seg.get("custom_name")

        # Gera ID único para o tópico
        if category == "ESPECIFICO" and custom_name:
            topic_id = f"custom_{custom_name.lower().replace(' ', '_')}"
            topic_name = custom_name
        else:
            topic_id = category.lower()
            topic_name = TOPIC_COLORS.get(category, {}).get("name", category.title())

        if topic_id not in topics:
            # Atribui cor
            if category in TOPIC_COLORS:
                color = TOPIC_COLORS[category]["color"]
            else:
                color = CUSTOM_TOPIC_COLORS[custom_color_idx % len(CUSTOM_TOPIC_COLORS)]
                custom_color_idx += 1

            topics[topic_id] = {
                "id": topic_id,
                "name": topic_name,
                "color": color,
                "category": "base" if category in TOPIC_COLORS and category != "ESPECIFICO" else "custom",
                "count": 0,
            }

        topics[topic_id]["count"] += 1
        seg["topic_id"] = topic_id

    return list(topics.values())


@router.post("/segment-topics")
@limiter.limit("20/minute")
async def segment_topics(
    http_request: Request,
    request: SegmentTopicsRequest,
    prompt_provider: PromptProvider = Depends(get_prompt_provider),
    header_keys: ApiKeys = Depends(get_api_keys_from_headers),
):
    """
    Segmenta texto por tópicos para highlighting automático.
    Usa LangExtract (se disponível) para posições exatas,
    com fallback para Ollama JSON Mode + str.find().
    """
    # Merge API keys from headers (priority) and body (fallback for backward compatibility)
    api_keys = merge_api_keys(header_keys, request)

    async def generate():
        try:
            analysis_model = request.analysisModel or OLLAMA_ANALYSIS_MODEL

            # Fallback: buscar primeiro modelo Ollama disponível
            if not analysis_model:
                analysis_model = await get_first_available_ollama_llm()
                if not analysis_model:
                    yield f"event: error\ndata: {json.dumps({'error': 'Nenhum modelo disponível para segmentação.'})}\n\n"
                    return

            # Detecta provider
            use_openai = api_keys.openai and ("gpt" in analysis_model.lower() or analysis_model.startswith("o1-"))
            use_perplexity = api_keys.perplexity and "sonar" in analysis_model.lower()
            use_ollama = not use_openai and not use_perplexity

            provider = "ollama" if use_ollama else ("openai" if use_openai else "perplexity")
            logger.info("Topic segmentation - model: %s, provider: %s", analysis_model, provider)

            yield f"event: progress\ndata: {json.dumps({'percent': 10, 'stage': 'preparing'})}\n\n"

            # Trunca texto se muito longo
            src = request.text[:15000] if len(request.text) > 15000 else request.text

            segments = []
            method_used = "legacy"

            # Tenta usar LangExtract primeiro (posições exatas)
            if is_langextract_available():
                yield f"event: progress\ndata: {json.dumps({'percent': 30, 'stage': 'calling_langextract', 'model': analysis_model})}\n\n"

                try:
                    segments = await segment_with_langextract(
                        text=src,
                        model=analysis_model,
                        ollama_url="http://localhost:11434",
                        openai_key=api_keys.openai if use_openai else None,
                        gemini_key=None,  # TODO: adicionar suporte a Gemini
                    )
                    method_used = "langextract"
                    logger.info("[TopicSegmentation] LangExtract returned %d segments with exact positions", len(segments))

                except Exception as langextract_error:
                    logger.warning("[TopicSegmentation] LangExtract failed, falling back to legacy: %s", langextract_error)
                    segments = []

            # Fallback para método legado (Ollama JSON Mode + str.find)
            if not segments:
                yield f"event: progress\ndata: {json.dumps({'percent': 20, 'stage': 'building_prompt'})}\n\n"

                from app.api.prompts import PROMPTS
                prompt = PROMPTS["TOPIC_SEGMENTATION_PROMPT"].replace("${text}", src)

                yield f"event: progress\ndata: {json.dumps({'percent': 30, 'stage': 'calling_llm', 'model': analysis_model})}\n\n"

                segments_raw = []

                try:
                    if use_ollama:
                        llm_result = await _call_ollama_structured(
                            prompt=prompt,
                            schema=SegmentationResponse,
                            model=analysis_model,
                        )
                        segments_raw = llm_result.get("segments", [])
                        logger.info("[TopicSegmentation] Ollama JSON Mode returned %d segments", len(segments_raw))

                    else:
                        system = PROMPTS["TOPIC_SEGMENTATION_SYSTEM"]
                        options = {"num_predict": 2048, "temperature": 0.2}

                        raw = ""
                        if use_openai:
                            async for piece in openai_generate_stream(api_keys.openai, analysis_model, prompt, system=system, options=options):
                                raw += piece
                        elif use_perplexity:
                            async for piece in perplexity_generate_stream(api_keys.perplexity, analysis_model, prompt, system=system, options=options):
                                raw += piece

                        try:
                            cleaned = _clean_llm_json(raw)
                            json_match = re.search(r'\{[\s\S]*\}', cleaned)
                            if json_match:
                                data = json.loads(json_match.group())
                                segments_raw = data.get("segments", [])
                        except Exception as parse_error:
                            logger.warning("[TopicSegmentation] Failed to parse external provider response: %s", parse_error)

                except Exception as llm_error:
                    logger.warning("Topic segmentation LLM failed: %s", llm_error)
                    yield f"event: error\ndata: {json.dumps({'error': f'LLM failed: {str(llm_error)}'})}\n\n"
                    return

                yield f"event: progress\ndata: {json.dumps({'percent': 60, 'stage': 'calculating_positions', 'raw_segments': len(segments_raw)})}\n\n"

                segments = _calculate_positions(src, segments_raw)
                method_used = "legacy_ollama" if use_ollama else "legacy_api"

            if not segments:
                logger.warning("No valid segments found after position calculation")
                yield f"event: progress\ndata: {json.dumps({'percent': 100, 'stage': 'done', 'segments': 0})}\n\n"
                yield f"event: result\ndata: {json.dumps({'success': True, 'segments': [], 'topics': [], 'text_length': len(src), 'analysis_id': None})}\n\n"
                return

            yield f"event: progress\ndata: {json.dumps({'percent': 85, 'stage': 'building_topics', 'segments': len(segments)})}\n\n"

            # Constrói definições de tópicos com cores
            topics = _build_topic_definitions(segments)

            # Salva no banco
            analysis_id = save_analysis(
                src[:1000],  # Salva apenas amostra do texto
                f"Topic segmentation: {len(segments)} segments, {len(topics)} topics",
                {
                    "type": "topic_segmentation",
                    "segments_count": len(segments),
                    "topics_count": len(topics),
                    "model": analysis_model,
                    "provider": provider,
                    "method": method_used,
                },
            )

            result = {
                "success": True,
                "segments": segments,
                "topics": topics,
                "text_length": len(src),
                "analysis_id": analysis_id,
            }

            yield f"event: progress\ndata: {json.dumps({'percent': 100, 'stage': 'done', 'segments': len(segments), 'topics': len(topics)})}\n\n"
            yield f"event: result\ndata: {json.dumps(result)}\n\n"

        except Exception as e:
            logger.exception("Error in segment_topics")
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.get("/prompts/defaults")
async def get_default_prompts():
    """
    Retorna os prompts padrão para o frontend.
    
    O usuário pode visualizar e editar esses prompts antes de gerar cards.
    Se não enviar prompts customizados, o sistema usa esses padrões.
    
    Returns:
        Dict com prompts organizados por categoria (system, guidelines, generation, format)
    """
    return get_default_prompts_for_ui()


@router.post("/generate-cards-stream")
@limiter.limit(RATE_LIMIT_GENERATE)
async def generate_cards_stream(
    http_request: Request,
    request: CardsRequest,
    header_keys: ApiKeys = Depends(get_api_keys_from_headers),
):
    # Merge API keys from headers (priority) and body (fallback for backward compatibility)
    api_keys = merge_api_keys(header_keys, request)

    async def generate():
        try:
            model = request.model or OLLAMA_MODEL

            # Fallback: buscar primeiro modelo Ollama disponível se nenhum especificado
            if not model:
                model = await get_first_available_ollama_llm()
                if not model:
                    yield f"event: error\ndata: {json.dumps({'error': 'Nenhum modelo disponível. Configure uma API key ou instale um modelo no Ollama.'})}\n\n"
                    return
                logger.info("Using fallback Ollama model: %s", model)

            logger.info("Generation model: %s", model)

            use_openai = api_keys.openai and ("gpt" in model.lower() or model.startswith("o1-"))
            use_perplexity = api_keys.perplexity and "sonar" in model.lower()
            use_ollama = not use_openai and not use_perplexity

            provider = "ollama" if use_ollama else ("openai" if use_openai else "perplexity")
            logger.info("Using provider: %s", provider)

            # Validate custom prompts for injection attempts
            custom_prompts_to_validate = [
                ("customSystemPrompt", request.customSystemPrompt),
                ("customGenerationPrompt", request.customGenerationPrompt),
                ("customGuidelines", request.customGuidelines),
            ]
            for prompt_name, prompt_value in custom_prompts_to_validate:
                if prompt_value:
                    is_valid, error_msg, pattern_type = validate_custom_prompt(prompt_value)
                    if not is_valid:
                        log_injection_attempt(prompt_value, pattern_type, source="generate-cards-stream")
                        yield f"event: error\ndata: {json.dumps({'error': f'Invalid {prompt_name}: {error_msg}', 'type': 'prompt_validation'})}\n\n"
                        return

            # Cria PromptProvider com prompts customizados (se fornecidos)
            prompt_provider = get_prompt_provider(
                custom_system=request.customSystemPrompt,
                custom_generation=request.customGenerationPrompt,
                custom_guidelines=request.customGuidelines,
                is_exam_mode=request.isExamMode or False,
            )

            using_custom = any([
                request.customSystemPrompt,
                request.customGenerationPrompt,
                request.customGuidelines,
            ])
            if using_custom:
                logger.info("Using custom prompts from request")

            yield f"event: stage\ndata: {json.dumps({'stage': 'generation_started'})}\n\n"

            src = truncate_source(request.text or "")
            ctx = (request.textContext or "").strip()

            card_type = (request.cardType or "both").strip().lower()
            if card_type not in ("basic", "cloze", "both"):
                card_type = "both"

            word_count = len(src.split())

            # Se o usuario especificou numCards, usa com range de +-20%
            if request.numCards and request.numCards > 0:
                # Validacao de escassez de conteudo
                validation = validate_content_sufficiency(src, request.numCards)
                if not validation.is_valid:
                    yield f"event: error\ndata: {json.dumps({'error': validation.message, 'type': 'content_scarcity', 'recommended_max': validation.recommended_max_cards, 'token_count': validation.token_count})}\n\n"
                    return
                elif validation.message:
                    # Aviso (permite continuar)
                    yield f"event: warning\ndata: {json.dumps({'message': validation.message, 'recommended_max': validation.recommended_max_cards})}\n\n"

                target_min = max(1, int(request.numCards * 0.8))
                target_max = int(request.numCards * 1.2)
            else:
                # Calculo automatico baseado em word count
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
                async for piece in openai_generate_stream(api_keys.openai, model, prompt, system=system_prompt, options=options):
                    raw += piece
            elif use_perplexity:
                async for piece in perplexity_generate_stream(api_keys.perplexity, model, prompt, system=system_prompt, options=options):
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
            # Detecta o provider correto para o modelo de validação (usa cache)
            validation_provider = get_provider_for_model(
                validation_model,
                openai_key=api_keys.openai,
                perplexity_key=api_keys.perplexity,
            )
            logger.info("Validation model: %s (provider: %s)", validation_model, validation_provider)

            cards_before_src = len(cards_raw)
            cards = await _validate_src_with_llm(
                cards_raw,
                src,
                prompt_provider=prompt_provider,
                provider=validation_provider,
                model=validation_model,
                openai_key=api_keys.openai,
                perplexity_key=api_keys.perplexity,
                analysis_id=request.analysisId,
            )

            save_pipeline_stage(
                request_id=request_id,
                stage="src_filter_llm",
                cards_in=cards_before_src,
                cards_out=len(cards),
                details={"method": "llm_validation", "validation_model": validation_model, "validation_provider": validation_provider},
                analysis_id=request.analysisId,
            )

            yield f"event: stage\ndata: {json.dumps({'stage': 'src_filtered', 'kept': len(cards), 'dropped': max(0, len(cards_raw) - len(cards)), 'method': 'llm'})}\n\n"

            cards_before_relevance = len(cards)
            cards = await _filter_cards_by_content_relevance_llm(
                cards,
                src,
                prompt_provider=prompt_provider,
                provider=validation_provider,
                model=validation_model,
                openai_key=api_keys.openai,
                perplexity_key=api_keys.perplexity,
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
                        api_keys.openai,
                        model,
                        repair_prompt,
                        system=repair_system,
                        options={"num_predict": 4096, "temperature": 0.0},
                    ):
                        raw2 += piece
                elif use_perplexity:
                    async for piece in perplexity_generate_stream(
                        api_keys.perplexity,
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
                    provider=validation_provider,
                    model=validation_model,
                    openai_key=api_keys.openai,
                    perplexity_key=api_keys.perplexity,
                    analysis_id=request.analysisId,
                )
                yield f"event: stage\ndata: {json.dumps({'stage': 'repair_src_filtered', 'kept': len(cards2), 'dropped': max(0, len(cards2_raw) - len(cards2)), 'method': 'llm'})}\n\n"

                cards2_before_relevance = len(cards2)
                cards2 = await _filter_cards_by_content_relevance_llm(
                    cards2,
                    src,
                    prompt_provider=prompt_provider,
                    provider=validation_provider,
                    model=validation_model,
                    openai_key=api_keys.openai,
                    perplexity_key=api_keys.perplexity,
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


# =============================================================================
# Card Rewrite Endpoint
# =============================================================================

class CardRewriteRequest(BaseModel):
    """Request para reescrever um card usando LLM."""
    front: str
    back: str
    action: str  # "densify" | "split_cloze" | "simplify"
    model: Optional[str] = None
    openaiApiKey: Optional[str] = None
    perplexityApiKey: Optional[str] = None


def _parse_rewrite_response(raw: str) -> dict:
    """
    Parseia a resposta do LLM de reescrita.
    Espera formato:
        Front: ...
        Back: ...
    """
    lines = raw.strip().split("\n")
    front = ""
    back = ""
    mode = None

    for line in lines:
        line = line.strip()
        if line.lower().startswith("front:"):
            mode = "front"
            front = line[6:].strip()
        elif line.lower().startswith("back:"):
            mode = "back"
            back = line[5:].strip()
        elif mode == "front" and line:
            front += " " + line
        elif mode == "back" and line:
            back += " " + line

    return {"front": front.strip(), "back": back.strip()}


@router.post("/rewrite-card")
@limiter.limit("30/minute")
async def rewrite_card(
    http_request: Request,
    request: CardRewriteRequest,
    header_keys: ApiKeys = Depends(get_api_keys_from_headers),
):
    """
    Reescreve um card usando LLM.

    Actions:
    - densify: Adiciona mais cloze deletions
    - split_cloze: Divide em multiplos cloze
    - simplify: Simplifica o card
    """
    # Merge API keys from headers (priority) and body (fallback for backward compatibility)
    api_keys = merge_api_keys(header_keys, request)

    try:
        model = request.model or OLLAMA_MODEL
        # Fallback: buscar primeiro modelo Ollama disponível
        if not model:
            model = await get_first_available_ollama_llm()
            if not model:
                return {"success": False, "error": "Nenhum modelo disponível"}

        # Detecta provider
        use_openai = api_keys.openai and ("gpt" in model.lower() or model.startswith("o1-"))
        use_perplexity = api_keys.perplexity and "sonar" in model.lower()

        prompt_provider = PromptProvider()
        prompt = prompt_provider.build_card_rewrite_prompt(
            front=request.front,
            back=request.back,
            action=request.action,
        )
        system_prompt = prompt_provider.card_rewrite_system()

        options = {"num_predict": 1024, "temperature": 0.0}

        raw = ""
        if use_openai:
            async for piece in openai_generate_stream(
                api_keys.openai, model, prompt, system=system_prompt, options=options
            ):
                raw += piece
        elif use_perplexity:
            async for piece in perplexity_generate_stream(
                api_keys.perplexity, model, prompt, system=system_prompt, options=options
            ):
                raw += piece
        else:
            async for piece in ollama_generate_stream(
                model, prompt, system=system_prompt, options=options
            ):
                raw += piece

        result = _parse_rewrite_response(raw)

        if not result["front"]:
            return {"success": False, "error": "Falha ao parsear resposta do LLM", "raw": raw}

        return {
            "success": True,
            "front": result["front"],
            "back": result["back"],
            "action": request.action,
        }

    except Exception as e:
        logger.exception("Error rewriting card")
        return {"success": False, "error": str(e)}
