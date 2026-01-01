from fastapi import APIRouter
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
from app.services.storage import save_analysis, save_cards, save_llm_response, save_filter_result, save_generation_request, save_pipeline_stage, _get_connection

router = APIRouter(prefix="/api", tags=["flashcards"])
logger = logging.getLogger(__name__)

SYSTEM_PTBR = (
    "Você é um gerador de flashcards Anki.\n"
    "Fora do campo SRC, escreva SEMPRE em Português do Brasil (pt-BR).\n"
    "No campo SRC, COPIE literalmente do texto-fonte (pode estar em inglês).\n"
    "NUNCA responda em espanhol.\n"
)

# System prompt dedicado para cloze - mais assertivo sobre a sintaxe obrigatória
SYSTEM_CLOZE = (
    "Você é um especialista em criar flashcards cloze para Anki.\n"
    "REGRA OBRIGATÓRIA: Todo card cloze DEVE conter exatamente {{c1::termo}} na frase.\n"
    "A sintaxe {{c1::termo}} é INEGOCIÁVEL - cards sem ela serão REJEITADOS.\n"
    "Fora do campo SRC, escreva SEMPRE em Português do Brasil (pt-BR).\n"
    "No campo SRC, COPIE literalmente do texto-fonte.\n"
    "NUNCA use Q: ou A: para cloze. Use apenas CLOZE: e EXTRA:.\n"
)


class TextRequest(BaseModel):
    text: str
    analysisModel: Optional[str] = None  # Modelo para embeddings/análise


class CardsRequest(BaseModel):
    text: str
    textContext: Optional[str] = ""
    deckOptions: Optional[str] = "General"
    useRAG: Optional[bool] = False
    topK: Optional[int] = 0
    cardType: Optional[str] = "both"
    model: Optional[str] = None                    # Modelo de geração
    validationModel: Optional[str] = None          # Modelo de validação de qualidade
    analysisModel: Optional[str] = None            # Modelo de análise de texto
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
    provider: str = "ollama",
    model: str = None,
    openai_key: Optional[str] = None,
    perplexity_key: Optional[str] = None,
    analysis_id: Optional[str] = None,
) -> list:
    """
    Valida rigorosamente se o campo SRC de cada card está presente no texto selecionado.
    
    Critérios de validação:
    1. O SRC deve ser uma citação LITERAL do texto selecionado
    2. Variações mínimas são permitidas (pontuação, espaços)
    3. O conteúdo do card (front/back) deve ser derivável do SRC
    4. Cards sem SRC são automaticamente rejeitados
    
    Args:
        cards: Lista de cards a serem validados
        src_text: Texto fonte original (trecho selecionado pelo usuário)
        provider: Provider do LLM ('ollama', 'openai', 'perplexity')
        model: Nome do modelo de validação
        openai_key: API key para OpenAI
        perplexity_key: API key para Perplexity
        analysis_id: ID da análise para persistência
    
    Returns:
        Lista filtrada de cards com SRC válido
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
    
    prompt = f"""# TAREFA: VALIDAÇÃO RIGOROSA DE FLASHCARDS

Você é um validador técnico de flashcards para sistemas de repetição espaçada.

## TEXTO SELECIONADO PELO USUÁRIO (FONTE ÚNICA VÁLIDA):
---BEGIN_SELECTED_TEXT---
{src_text[:4000]}
---END_SELECTED_TEXT---

## FLASHCARDS A VALIDAR:
{cards_text}

## REGRAS DE VALIDAÇÃO (APLIQUE RIGOROSAMENTE):

### REGRA 1: SRC OBRIGATÓRIO
- O campo SRC é OBRIGATÓRIO em cada card
- Cards sem SRC ou com SRC vazio = NÃO

### REGRA 2: SRC DEVE SER CITAÇÃO LITERAL
- O SRC deve aparecer LITERALMENTE no TEXTO SELECIONADO
- Permitido: variações mínimas de pontuação, espaços, capitalização
- PROIBIDO: SRC que é paráfrase, resumo ou texto de outra seção

### REGRA 3: CONTEÚDO DERIVÁVEL DO SRC
- O conteúdo do FRONT e BACK deve ser derivável do SRC
- Se o card fala sobre conceitos NÃO mencionados no TEXTO SELECIONADO = NÃO

### REGRA 4: CONTEXTO EXTERNO É INVÁLIDO
- Se o SRC parece vir de outra parte do documento (contexto geral) = NÃO
- Apenas o TEXTO SELECIONADO é válido como fonte

## FORMATO DE RESPOSTA:
Para cada card, responda EXATAMENTE neste formato (uma linha por card):
CARD_N: VEREDICTO | MOTIVO

Onde:
- N = número do card (1, 2, 3...)
- VEREDICTO = SIM ou NÃO
- MOTIVO = breve explicação (máx 10 palavras)

## EXEMPLOS:
CARD_1: SIM | SRC encontrado literalmente no texto
CARD_2: NÃO | SRC não aparece no texto selecionado
CARD_3: NÃO | card sobre conceito ausente no texto selecionado
CARD_4: NÃO | SRC vazio

## INICIE A VALIDAÇÃO:"""

    system = """Você é um validador técnico rigoroso. 
Analise cada card criteriosamente.
Responda APENAS no formato especificado.
Seja conservador: na dúvida, rejeite o card."""

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
    
    # Parse da resposta - formato: CARD_N: SIM|NÃO | motivo
    kept = []
    approved_indices = set()
    rejection_reasons = {}
    
    for line in raw.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        
        # Formato novo: CARD_N: SIM|NÃO | motivo
        match_new = re.match(r"CARD[_\s]*(\d+)\s*:\s*(SIM|NÃO|NAO|YES|NO)", line, re.IGNORECASE)
        # Formato antigo fallback: N: SIM|NÃO
        match_old = re.match(r"(\d+)\s*:\s*(SIM|NÃO|NAO|YES|NO)", line, re.IGNORECASE)
        
        match = match_new or match_old
        if match:
            idx = int(match.group(1)) - 1
            verdict = match.group(2).upper()
            if verdict in ("SIM", "YES"):
                approved_indices.add(idx)
            else:
                # Extrai motivo se disponível
                reason_match = re.search(r"\|\s*(.+)$", line)
                if reason_match:
                    rejection_reasons[idx] = reason_match.group(1).strip()
    
    # Se LLM não conseguiu parsear, retorna todos os cards
    if not approved_indices and cards_input:
        logger.warning("LLM SRC validation returned no parseable results. Returning all cards without SRC filter.")
        return cards_input
    
    # Filtra cards aprovados
    for i, c in enumerate(cards_input):
        if i in approved_indices:
            c["_src_validated_by"] = "llm"
            kept.append(c)
        else:
            reason = rejection_reasons.get(i, "não passou na validação")
            logger.info("SRC rejected by LLM [card %d]: %s | Motivo: %s", i+1, (c.get("src") or "")[:50], reason)
    
    logger.info("SRC validation complete: %d/%d cards approved", len(kept), len(cards_input))
    
    # Salva resultado do filtro
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
                "method": "llm_validation"
            }
        )
    except Exception as e:
        logger.warning("Failed to save LLM SRC filter result: %s", e)
    
    return kept


async def _filter_cards_by_content_relevance_llm(
    cards,
    src_text: str,
    *,
    provider: str = "ollama",
    model: str = None,
    openai_key: Optional[str] = None,
    perplexity_key: Optional[str] = None,
    analysis_id: Optional[str] = None,
) -> list:
    """
    Usa o LLM para filtrar cards cujo conteúdo não está diretamente relacionado ao texto fonte.
    Isso evita que o modelo gere cards baseados no contexto geral em vez do trecho selecionado.
    Salva resultados do filtro no DuckDB para análise posterior.
    
    Args:
        cards: Lista de cards a serem avaliados
        src_text: Texto fonte original (trecho selecionado/destacado)
        provider: Provider do LLM ('ollama', 'openai', 'perplexity')
        model: Nome do modelo a usar (deve ser o mesmo usado para geração, NÃO embedding)
        openai_key: API key para OpenAI
        perplexity_key: API key para Perplexity
        analysis_id: ID da análise para persistência
    
    Returns:
        Lista filtrada de cards que são relevantes ao texto fonte
    """
    cards_input = list(cards or [])
    
    if not cards_input:
        return []
    
    if len(cards_input) == 0:
        return cards_input
    
    # O modelo DEVE ser passado explicitamente pelo chamador
    # Se não for passado, usa o modelo de geração padrão (NÃO o de embedding!)
    if not model:
        logger.warning("No model specified for LLM relevance filter, using default OLLAMA_MODEL")
        model = OLLAMA_MODEL
    
    # Formata os cards para o prompt
    cards_text = ""
    for i, c in enumerate(cards):
        front = (c.get("front") or "").strip()
        back = (c.get("back") or "").strip()
        cards_text += f"[CARD {i+1}]\nQ: {front}\nA: {back}\n\n"
    
    prompt = f"""Analise se cada flashcard abaixo foi criado com base EXCLUSIVAMENTE no TEXTO-FONTE fornecido.

TEXTO-FONTE:
{src_text[:2000]}

FLASHCARDS PARA AVALIAR:
{cards_text}

TAREFA:
Para cada card, responda APENAS com o número do card e "SIM" ou "NÃO":
- SIM = O card trata de informação que está EXPLICITAMENTE presente no TEXTO-FONTE
- NÃO = O card trata de informação que NÃO está no TEXTO-FONTE (pode ser conhecimento geral, contexto externo, ou inferência não justificada)

IMPORTANTE:
- Se o card menciona um conceito que aparece no texto-fonte, responda SIM
- Se o card traz informação adicional que NÃO está no texto-fonte, responda NÃO
- Seja RIGOROSO: apenas cards ancorados no texto-fonte devem passar

FORMATO DA RESPOSTA (uma linha por card):
1: SIM
2: NÃO
3: SIM
...

RESPONDA AGORA:"""

    system = "Você é um avaliador rigoroso de flashcards. Responda apenas no formato solicitado."
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
        return cards  # Em caso de erro, mantém todos os cards
    
    # Parse da resposta
    kept = []
    approved_indices = set()
    
    for line in raw.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        
        # Tenta extrair "N: SIM" ou "N: NÃO"
        match = re.match(r"(\d+)\s*:\s*(SIM|NÃO|NAO|YES|NO)", line, re.IGNORECASE)
        if match:
            idx = int(match.group(1)) - 1  # Converte para 0-based
            verdict = match.group(2).upper()
            if verdict in ("SIM", "YES"):
                approved_indices.add(idx)
    
    # Se o LLM não conseguiu parsear nada, mantém todos
    if not approved_indices and cards_input:
        logger.warning("LLM relevance filter returned no parseable results. Keeping all cards.")
        return cards_input
    
    # Filtra cards aprovados
    for i, c in enumerate(cards_input):
        if i in approved_indices:
            c["_llm_relevance"] = True
            kept.append(c)
        else:
            logger.debug("Card rejected by LLM relevance: %s", (c.get("front") or "")[:50])
    
    # Se filtrou demais (>80% dos cards), mantém todos como fallback
    if len(kept) < len(cards_input) * 0.2 and len(cards_input) >= 3:
        logger.warning("LLM relevance filter too aggressive (kept %d/%d). Keeping all.", len(kept), len(cards_input))
        return cards_input
    
    # Salva resultado do filtro no DuckDB
    try:
        save_filter_result(
            filter_type="llm_relevance",
            cards_before=cards_input,
            cards_after=kept,
            analysis_id=analysis_id,
            metadata={
                "provider": provider,
                "model": model,
                "llm_raw_response": raw[:1000],  # Trunca para não estourar
                "approved_indices": list(approved_indices)
            }
        )
    except Exception as e:
        logger.warning("Failed to save llm relevance filter result: %s", e)
    
    return kept


def _filter_cards_by_content_relevance(cards, src_text: str, min_keyword_overlap: float = 0.3):
    """
    Filtra cards cujo conteúdo (front/back) não tem relação com o texto fonte.
    Versão síncrona usando heurísticas de palavras-chave (fallback).
    
    Para filtragem mais precisa, use _filter_cards_by_content_relevance_llm (async).
    
    Args:
        cards: Lista de cards
        src_text: Texto fonte original (trecho selecionado/destacado)
        min_keyword_overlap: Proporção mínima de palavras-chave do card que devem aparecer no src
    
    Returns:
        Lista filtrada de cards
    """
    if not cards:
        return []
    
    # Extrai palavras significativas do texto fonte (ignora stopwords comuns)
    stopwords_pt = {
        'o', 'e', 'de', 'da', 'em', 'um', 'uma', 'para', 'com', 'não', 'que',
        'os', 'dos', 'das', 'no', 'na', 'por', 'mais', 'se', 'ou', 'seu', 'sua',
        'como', 'mas', 'ao', 'ele', 'ela', 'entre', 'quando', 'muito', 'nos', 'já',
        'também', 'só', 'pelo', 'pela', 'até', 'isso', 'esse', 'essa', 'este', 'esta',
        'são', 'tem', 'ser', 'ter', 'foi', 'eram', 'está', 'pode', 'podem',
        'the', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have',
        'has', 'had', 'does', 'did', 'will', 'would', 'could', 'should', 'may',
        'of', 'to', 'in', 'for', 'on', 'with', 'at', 'by', 'from', 'into', 'and', 'or'
    }
    
    src_norm = _normalize_text_for_matching(src_text)
    src_words = set(src_norm.split()) - stopwords_pt
    
    kept = []
    for c in cards:
        front = _normalize_text_for_matching(c.get("front") or "")
        back = _normalize_text_for_matching(c.get("back") or "")
        
        # Extrai palavras do card (exceto stopwords)
        card_words = (set(front.split()) | set(back.split())) - stopwords_pt
        
        # Remove palavras muito curtas (< 3 chars)
        card_words = {w for w in card_words if len(w) >= 3}
        
        if not card_words:
            kept.append(c)  # Se não há palavras significativas, mantém o card
            continue
        
        # Calcula overlap
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
    
    Critérios:
    - Tamanho da resposta (ideal: 10-30 palavras)
    - Tipo de pergunta (penaliza sim/não)
    - Presença e qualidade do SRC
    - Atomicidade (uma ideia por card)
    - Clareza (evita termos vagos)
    """
    score = 1.0
    front = (card.get("front") or "").strip()
    back = (card.get("back") or "").strip()
    src = (card.get("src") or "").strip()
    
    front_lower = front.lower()
    back_lower = back.lower()
    
    # --- Penalizações ---
    
    # Respostas muito longas (>40 palavras)
    back_words = len(back.split())
    if back_words > 40:
        score -= 0.25
    elif back_words > 30:
        score -= 0.1
    
    # Respostas muito curtas (<5 palavras, exceto cloze)
    if back_words < 5 and "{{c1::" not in front:
        score -= 0.15
    
    # Perguntas sim/não ou muito genéricas
    yes_no_patterns = [
        r'^(é verdade|é correto|existe|há|houve|foi|será|pode ser|é possível)',
        r'\?$.*\b(sim|não|verdadeiro|falso)\b',
        r'^(verdadeiro ou falso|v ou f)',
    ]
    for pattern in yes_no_patterns:
        if re.search(pattern, front_lower):
            score -= 0.3
            break
    
    # Termos vagos na resposta
    vague_terms = ['coisa', 'algo', 'isso', 'aquilo', 'etc', 'entre outros', 'e assim por diante']
    for term in vague_terms:
        if term in back_lower:
            score -= 0.1
            break
    
    # Resposta igual à pergunta (pode indicar problema)
    if _normalize_text_for_matching(front) == _normalize_text_for_matching(back):
        score -= 0.4
    
    # --- Bonificações ---
    
    # SRC presente e válido
    if src:
        score += 0.1
        src_score = card.get("_src_score", 0)
        if src_score >= 95:
            score += 0.05  # SRC quase exato
    
    # Pergunta específica (começa com interrogativo)
    interrogatives = ['o que', 'qual', 'quais', 'como', 'por que', 'quando', 'onde', 'quem']
    for interr in interrogatives:
        if front_lower.startswith(interr):
            score += 0.05
            break
    
    # Cloze bem formado
    if "{{c1::" in front:
        cloze_content = re.findall(r'\{\{c1::([^}]+)\}\}', front)
        if cloze_content:
            cloze_words = len(cloze_content[0].split())
            if 1 <= cloze_words <= 3:  # Lacuna ideal: 1-3 palavras
                score += 0.1
            elif cloze_words > 5:  # Lacuna muito longa
                score -= 0.15
    
    # Garante range 0.0 - 1.0
    return max(0.0, min(1.0, score))


def filter_and_rank_by_quality(
    cards: list,
    min_score: float = 0.4,
    max_cards: Optional[int] = None,
    analysis_id: Optional[str] = None
) -> list:
    """
    Filtra cards por score mínimo e retorna ordenados por qualidade.
    Salva resultados do filtro no DuckDB para análise posterior.
    
    Args:
        cards: Lista de cards
        min_score: Score mínimo para manter o card
        max_cards: Máximo de cards a retornar (None = todos)
        analysis_id: ID da análise para persistência
    
    Returns:
        Lista de cards ordenados por qualidade (melhor primeiro)
    """
    cards_input = list(cards or [])
    scored_cards = []
    
    for card in cards_input:
        quality = score_card_quality(card)
        card["_quality_score"] = quality
        if quality >= min_score:
            scored_cards.append(card)
        else:
            logger.debug(
                "Card rejected (quality=%.2f): %s",
                quality,
                (card.get("front") or "")[:50]
            )
    
    # Ordena por qualidade (maior primeiro)
    scored_cards.sort(key=lambda c: c.get("_quality_score", 0), reverse=True)
    
    if max_cards and len(scored_cards) > max_cards:
        scored_cards = scored_cards[:max_cards]
    
    # Salva resultado do filtro no DuckDB
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
                    "scores": {
                        (c.get("front") or "")[:50]: c.get("_quality_score", 0) 
                        for c in cards_input
                    }
                }
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
    
    Args:
        provider: 'ollama', 'openai', ou 'perplexity'
        model: Nome do modelo
        prompt: Prompt de geração
        system: System prompt
        options: Opções de geração (temperature, num_predict, etc.)
        openai_key: API key para OpenAI (se provider='openai')
        perplexity_key: API key para Perplexity (se provider='perplexity')
    
    Returns:
        Resposta completa do modelo
    """
    raw = ""
    
    if provider == "openai" and openai_key:
        async for piece in openai_generate_stream(openai_key, model, prompt, system=system, options=options):
            raw += piece
    elif provider == "perplexity" and perplexity_key:
        async for piece in perplexity_generate_stream(perplexity_key, model, prompt, system=system, options=options):
            raw += piece
    else:  # ollama
        async for piece in ollama_generate_stream(model, prompt, system=system, options=options):
            raw += piece
    
    return raw


def _parse_and_normalize_cards(raw: str, card_type: str, analysis_id: Optional[str] = None) -> Tuple[list, str]:
    """
    Parseia resposta do LLM e normaliza os cards.
    
    Args:
        raw: Resposta bruta do LLM
        card_type: Tipo de card ('basic', 'cloze', 'both')
        analysis_id: ID da análise para persistência
    
    Returns:
        Tuple[cards_normalizados, modo_parse ('qa' ou 'json')]
    """
    cards_raw = normalize_cards(parse_flashcards_qa(raw))
    parse_mode = "qa"
    
    if not cards_raw:
        cards_raw = normalize_cards(parse_flashcards_json(raw))
        parse_mode = "json"
    
    # Aplica filtro por tipo de card
    cards_raw = _filter_by_card_type(cards_raw, card_type, analysis_id=analysis_id)
    
    return cards_raw, parse_mode



async def _apply_src_and_quality_filters_llm(
    cards_raw: list,
    src_text: str,
    target_min: int,
    target_max: int,
    *,
    provider: str = "ollama",
    validation_model: str = None,
    openai_key: Optional[str] = None,
    perplexity_key: Optional[str] = None,
    apply_quality_filter: bool = True,
    analysis_id: Optional[str] = None
) -> list:
    """
    Aplica filtros de SRC (via LLM) e qualidade aos cards.
    
    Args:
        cards_raw: Cards parseados
        src_text: Texto fonte para validação
        target_min: Quantidade mínima desejada
        target_max: Quantidade máxima desejada
        provider: Provider do LLM
        validation_model: Modelo para validação
        openai_key: API key OpenAI
        perplexity_key: API key Perplexity
        apply_quality_filter: Se deve aplicar filtro de qualidade
        analysis_id: ID da análise para persistência
    
    Returns:
        Lista de cards filtrados
    """
    # Filtro de SRC com LLM
    cards = await _validate_src_with_llm(
        cards_raw, 
        src_text, 
        provider=provider,
        model=validation_model,
        openai_key=openai_key,
        perplexity_key=perplexity_key,
        analysis_id=analysis_id
    )
    
    # Fallback: se filtro derrubar 100% mas há cards parseados
    if not cards and cards_raw:
        for c in cards_raw:
            c.pop("src", None)
        cards = cards_raw
    
    # Relaxa SRC se necessário
    cards = _relax_src_if_needed(cards, cards_raw, target_min=target_min, target_max=target_max)
    
    # Aplica filtro de qualidade
    if apply_quality_filter and cards:
        cards = filter_and_rank_by_quality(
            cards,
            min_score=0.35,
            max_cards=target_max,
            analysis_id=analysis_id
        )
    
    return cards


# =============================================================================
# BÔNUS: relaxamento do SRC quando derruba demais
# =============================================================================

def _dedupe_key(card: dict) -> str:
    return (card.get("front") or "").strip() + "||" + (card.get("back") or "").strip()


def _relax_src_if_needed(cards_with_src, cards_raw, *, target_min: int, target_max: int):
    """
    Se o filtro SRC for restritivo demais (ex.: gerou 20, mas só 3 passaram),
    mantém os cards com SRC válido e completa até target_min com cards sem SRC.

    Regra prática:
    - só relaxa se cards_raw >= target_min e cards_with_src < target_min
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
        c2.pop("src", None)  # os extras entram sem SRC
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
    Garante que só passem cards do tipo solicitado:
    - cloze  -> front contém "{{c1::"
    - basic  -> front NÃO contém "{{c1::"
    - both   -> não filtra
    
    Salva resultados do filtro no DuckDB para análise posterior.
    """
    cards_input = list(cards or [])
    
    if card_type == "cloze":
        result = [c for c in cards_input if "{{c1::" in (c.get("front") or "")]
    elif card_type == "basic":
        result = [c for c in cards_input if "{{c1::" not in (c.get("front") or "")]
    else:
        result = cards_input
    
    # Salva resultado do filtro no DuckDB (apenas se houve filtragem)
    if card_type != "both" and cards_input:
        try:
            save_filter_result(
                filter_type="card_type",
                cards_before=cards_input,
                cards_after=result,
                analysis_id=analysis_id,
                metadata={
                    "card_type_requested": card_type
                }
            )
        except Exception as e:
            logger.warning("Failed to save card type filter result: %s", e)
    
    return result


def _cards_lang_from_cards(cards) -> str:
    """
    Detecta o idioma a partir do conteúdo REAL que importa (front/back),
    ao invés do `raw` inteiro (que tem Q:/A:/SRC: e pode confundir em textos curtos).

    Usa apenas langid por baixo (detect_language_pt_en_es).
    """
    blob = "\n".join(
        ((c.get("front") or "") + " " + (c.get("back") or "")).strip()
        for c in (cards or [])
    ).strip()

    if not blob:
        return "unknown"

    return detect_language_pt_en_es(blob)


@router.post("/analyze-text-stream")
async def analyze_text_stream(request: TextRequest):
    async def generate():
        try:
            # Usa modelo do request ou fallback para config
            analysis_model = request.analysisModel or OLLAMA_ANALYSIS_MODEL
            logger.info("Ollama analysis model (embeddings): %s", analysis_model)

            from app.services.ollama import (
                ollama_embed,
                chunk_text_semantic,
                chunk_text,
                cosine_similarity
            )

            yield f"event: progress\ndata: {json.dumps({'percent': 10, 'stage': 'preparing'})}\n\n"

            src = truncate_source(request.text or "")
            
            # Usa chunking semântico com overlap para melhor contexto
            # Detecta idioma para escolher tokenizer correto
            detected_lang = detect_language_pt_en_es(src[:500])
            language = "portuguese" if detected_lang == "pt-br" else "english"
            
            chunks = chunk_text_semantic(
                src,
                max_words=400,
                overlap_sentences=2,
                language=language
            )
            
            # Fallback para chunking simples se semântico falhar
            if not chunks:
                chunks = chunk_text(src, chunk_size=400)

            yield f"event: progress\ndata: {json.dumps({'percent': 20, 'stage': 'chunking', 'chunks': len(chunks), 'method': 'semantic' if len(chunks) > 0 else 'simple'})}\n\n"

            yield f"event: progress\ndata: {json.dumps({'percent': 30, 'stage': 'embedding', 'model': analysis_model})}\n\n"

            chunk_embeddings = []
            for i, chunk in enumerate(chunks):
                emb = await ollama_embed(analysis_model, chunk)
                chunk_embeddings.append((chunk, emb))
                # Progresso incremental durante embedding
                if len(chunks) > 3:
                    progress = 30 + int((i + 1) / len(chunks) * 25)
                    yield f"event: progress\ndata: {json.dumps({'percent': progress, 'stage': 'embedding', 'chunk': i + 1, 'total': len(chunks)})}\n\n"

            # Query semântica adaptada ao idioma detectado
            if detected_lang == "pt-br":
                query = "conceitos importantes, definições técnicas, contrastes e distinções"
            else:
                query = "important concepts, technical definitions, contrasts and distinctions"
            
            query_emb = await ollama_embed(analysis_model, query)

            yield f"event: progress\ndata: {json.dumps({'percent': 60, 'stage': 'ranking'})}\n\n"

            scored = [(chunk, cosine_similarity(emb, query_emb)) for chunk, emb in chunk_embeddings]
            scored.sort(key=lambda x: x[1], reverse=True)

            # Seleciona top chunks com score mínimo
            min_similarity = 0.3
            top_chunks = [
                chunk for chunk, score in scored[:5]
                if score >= min_similarity
            ][:3]  # Máximo 3 chunks
            
            if not top_chunks and scored:
                # Fallback: pega os 3 melhores mesmo com score baixo
                top_chunks = [chunk for chunk, _ in scored[:3]]
            
            summary = "\n\n".join(top_chunks)

            result = {"content": [{"type": "text", "text": summary}]}

            analysis_id = save_analysis(src, summary, {"chunks": len(chunks), "top_chunks": len(top_chunks)})
            result["analysis_id"] = analysis_id

            yield f"event: progress\ndata: {json.dumps({'percent': 100, 'stage': 'done', 'analysis_id': analysis_id})}\n\n"
            yield f"event: result\ndata: {json.dumps(result)}\n\n"

        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/generate-cards-stream")
async def generate_cards_stream(request: CardsRequest):
    async def generate():
        try:
            model = request.model or OLLAMA_MODEL
            logger.info("Generation model: %s", model)

            # Determina qual provedor usar baseado no nome do modelo
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

            # Quantidade alvo: ajusta por tamanho do trecho selecionado
            word_count = len(src.split())
            if word_count < 140:
                target_min, target_max = 3, 8
            elif word_count < 320:
                target_min, target_max = 5, 12
            elif word_count < 700:
                target_min, target_max = 8, 18
            else:
                target_min, target_max = 10, 30

            # Salva request de geração para rastreamento
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
                analysis_id=request.analysisId
            )

            type_instruction = {
                "basic": "Gere APENAS cards básicos (perguntas e respostas). NÃO gere cards cloze.",
                "cloze": "Gere APENAS cards cloze. Cada card cloze é uma FRASE AFIRMATIVA (não pergunta) com uma lacuna {{c1::termo}}. Use o prefixo CLOZE: (não Q:).",
                "both": "Para cada conceito importante, gere 1 card básico (Q:/A:) + 1 card cloze (CLOZE:/EXTRA:).",
            }[card_type]

            # Bloco de formato dependente do tipo
            if card_type == "basic":
                format_block = """
FORMATO OBRIGATÓRIO (use exatamente estas chaves):

Q: <pergunta específica em PT-BR>
A: <resposta curta em PT-BR (1-2 frases)>
SRC: "<trecho COPIADO do CONTEÚDO-FONTE (5-25 palavras), sem alterar>"

RESTRIÇÕES:
- NUNCA use {{c1::...}}.
- Não gere nenhum card que seja cloze.
""".strip()
            elif card_type == "cloze":
                format_block = """
=== EXEMPLOS DE CLOZE CORRETO (SIGA ESTE FORMATO EXATO) ===

CLOZE: Um banco de dados é uma {{c1::coleção organizada}} de dados relacionados.
EXTRA: Permite armazenamento e recuperação eficiente de informações.
SRC: "banco de dados é uma coleção organizada de dados"

CLOZE: O {{c1::SGBD}} é o software responsável por gerenciar o banco de dados.
EXTRA: Exemplos incluem MySQL, PostgreSQL e Oracle.
SRC: "Sistema Gerenciador de Banco de Dados (SGBD) é o software"

CLOZE: No modelo hierárquico, os dados são organizados em estrutura de {{c1::árvore}}.
EXTRA: Cada nó pode ter múltiplos filhos, mas apenas um pai.
SRC: "modelo hierárquico, os dados são organizados em uma estrutura de árvore"

CLOZE: A {{c1::informação}} surge quando dados são organizados e interpretados em contexto.
EXTRA: Diferente do dado bruto, possui significado e utilidade.
SRC: "Informação surge quando dados são organizados e interpretados"

=== FIM DOS EXEMPLOS ===

FORMATO OBRIGATÓRIO:
CLOZE: <frase AFIRMATIVA com UMA lacuna {{c1::termo}}>  ← OBRIGATÓRIO ter {{c1::}}
EXTRA: <1 frase de contexto adicional>
SRC: "<citação literal do texto-fonte>"

REGRAS CRÍTICAS:
- A sintaxe {{c1::termo}} é OBRIGATÓRIA em TODA linha CLOZE:
- NUNCA escreva "CLOZE: Texto sem lacuna" - isso será REJEITADO
- NUNCA use Q: ou A: - use apenas CLOZE: e EXTRA:
- Cada card DEVE ter exatamente UMA ocorrência de {{c1::}}
""".strip()
            else:  # both
                format_block = """
FORMATO OBRIGATÓRIO:

Para cards BÁSICOS (pergunta/resposta):
Q: <pergunta específica em PT-BR>
A: <resposta curta em PT-BR (1-2 frases)>
SRC: "<trecho COPIADO do CONTEÚDO-FONTE (5-25 palavras), sem alterar>"

Para cards CLOZE (frase com lacuna):
CLOZE: <frase AFIRMATIVA em PT-BR com UMA lacuna {{c1::termo}}>
EXTRA: <1 frase de contexto adicional em PT-BR>
SRC: "<trecho COPIADO do CONTEÚDO-FONTE (5-25 palavras), sem alterar>"
""".strip()

            checklist_block = _format_checklist_block()

            prompt = f"""
CONTEÚDO-FONTE (crie cards EXCLUSIVAMENTE sobre este trecho):
{src}

{("CONTEXTO GERAL (apenas para entender o assunto - NÃO crie cards sobre informações que estão APENAS aqui):\n" + ctx) if ctx else ""}

{checklist_block if checklist_block else ""}

TAREFA:
- Crie flashcards em PT-BR BASEADOS EXCLUSIVAMENTE no CONTEÚDO-FONTE acima.
- PROIBIDO criar cards sobre informações que aparecem apenas no CONTEXTO GERAL.
- Se um conceito não estiver no CONTEÚDO-FONTE, NÃO crie card sobre ele.
- Se o texto estiver em inglês, traduza os conceitos para PT-BR (sem adicionar fatos).
- IMPORTANTE: O campo SRC é uma CITAÇÃO LITERAL do CONTEÚDO-FONTE; se o texto-fonte estiver em inglês, o SRC ficará em inglês (isso é permitido).
- Fora do campo SRC, NUNCA use inglês.

QUANTIDADE:
- Gere entre {target_min} e {target_max} cards.

TIPOS:
{type_instruction}

{format_block}

EXEMPLO DE CLOZE CORRETO:
CLOZE: A capital do Brasil é {{c1::Brasília}}.
EXTRA: Brasília foi inaugurada em 1960.
SRC: "A capital do Brasil é Brasília"

ATENÇÃO: Use EXATAMENTE {{c1::palavra}} (dois dois-pontos, NÃO três)
REGRAS CRÍTICAS:
- SEM markdown, SEM listas, SEM numeração.
- Uma linha em branco entre cards.
- O campo SRC PRECISA ser um trecho literal do texto-fonte (5–25 palavras).
- Evite repetir o mesmo SRC em cards diferentes (quando possível).
- NÃO crie cards sobre as “Diretrizes de Qualidade”.

COMECE:
""".strip()

            raw = ""
            # temperature 0.0 tende a reduzir “desobediência” de idioma
            options = {"num_predict": 4096, "temperature": 0.0}
            
            # Seleciona system prompt: dedicado para cloze, genérico para outros
            system_prompt = SYSTEM_CLOZE if card_type == "cloze" else SYSTEM_PTBR
            
            if use_openai:
                async for piece in openai_generate_stream(request.openaiApiKey, model, prompt, system=system_prompt, options=options):
                    raw += piece
            elif use_perplexity:
                async for piece in perplexity_generate_stream(request.perplexityApiKey, model, prompt, system=system_prompt, options=options):
                    raw += piece
            else:
                async for piece in ollama_generate_stream(model, prompt, system=system_prompt, options=options):
                    raw += piece

            # Salva resposta do LLM com campos expandidos para debug
            save_llm_response(
                provider=provider, 
                model=model, 
                prompt=prompt, 
                response=raw, 
                analysis_id=request.analysisId,
                system_prompt=system_prompt,
                card_type=card_type,
                source_text_length=len(src),
                options=options
            )
            
            # Registra etapa de geração no pipeline
            save_pipeline_stage(
                request_id=request_id,
                stage="llm_generation",
                cards_in=0,
                cards_out=0,
                details={"response_length": len(raw), "model": model, "provider": provider},
                analysis_id=request.analysisId
            )

            # Parse/normalize (QA -> JSON fallback)
            cards_raw = normalize_cards(parse_flashcards_qa(raw))
            parse_mode = "qa"
            if not cards_raw:
                cards_raw = normalize_cards(parse_flashcards_json(raw))
                parse_mode = "json"

            # Registra etapa de parsing no pipeline
            save_pipeline_stage(
                request_id=request_id,
                stage="parsing",
                cards_in=0,
                cards_out=len(cards_raw),
                details={"parse_mode": parse_mode},
                analysis_id=request.analysisId
            )

            # Log resumido do diagnóstico
            cards_before_type_filter = len(cards_raw)
            cloze_count = sum(1 for c in cards_raw if "{{c1::" in (c.get("front") or ""))
            logger.info("Parsed %d cards (%d with cloze syntax), card_type=%s", cards_before_type_filter, cloze_count, card_type)

            # Aplica filtro por tipo de card (basic / cloze / both)
            cards_raw = _filter_by_card_type(cards_raw, card_type, analysis_id=request.analysisId)
            
            # Registra etapa de filtro por tipo no pipeline
            save_pipeline_stage(
                request_id=request_id,
                stage="type_filter",
                cards_in=cards_before_type_filter,
                cards_out=len(cards_raw),
                details={"card_type": card_type, "cloze_syntax_count": cloze_count},
                analysis_id=request.analysisId
            )

            yield f"event: stage\ndata: {json.dumps({'stage': 'parsed', 'mode': parse_mode, 'count': len(cards_raw), 'before_type_filter': cards_before_type_filter})}\n\n"

            # Determina modelo de validação
            validation_model = request.validationModel or model
            logger.info("Validation model: %s", validation_model)

            # SRC filter usando LLM
            cards_before_src = len(cards_raw)
            cards = await _validate_src_with_llm(
                cards_raw, 
                src, 
                provider=provider,
                model=validation_model,
                openai_key=request.openaiApiKey,
                perplexity_key=request.perplexityApiKey,
                analysis_id=request.analysisId
            )
            
            # Registra etapa de filtro SRC no pipeline
            save_pipeline_stage(
                request_id=request_id,
                stage="src_filter_llm",
                cards_in=cards_before_src,
                cards_out=len(cards),
                details={"method": "llm_validation", "validation_model": validation_model},
                analysis_id=request.analysisId
            )
            
            yield f"event: stage\ndata: {json.dumps({'stage': 'src_filtered', 'kept': len(cards), 'dropped': max(0, len(cards_raw) - len(cards)), 'method': 'llm'})}\n\n"

            # Content relevance filter usando LLM - garante que cards são sobre o trecho selecionado
            cards_before_relevance = len(cards)
            cards = await _filter_cards_by_content_relevance_llm(
                cards, 
                src,
                provider=provider,
                model=validation_model,  # Usa modelo de validação
                openai_key=request.openaiApiKey,
                perplexity_key=request.perplexityApiKey,
                analysis_id=request.analysisId,
            )
            if len(cards) < cards_before_relevance:
                yield f"event: stage\ndata: {json.dumps({'stage': 'llm_relevance_filtered', 'kept': len(cards), 'dropped': cards_before_relevance - len(cards)})}\n\n"

            # Fallback: se o filtro derrubar 100% mas há cards parseados, não zera tudo
            if not cards and cards_raw:
                for c in cards_raw:
                    c.pop("src", None)
                cards = cards_raw
                yield f"event: stage\ndata: {json.dumps({'stage': 'src_bypassed', 'count': len(cards)})}\n\n"

            # BÔNUS: relaxa SRC se ele derrubar demais e impedir o mínimo
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

            # Idioma detectado a partir do conteúdo (front/back), não do raw
            out_lang = _cards_lang_from_cards(cards)
            yield f"event: stage\ndata: {json.dumps({'stage': 'lang_check', 'lang': out_lang, 'cards': len(cards), 'min': target_min})}\n\n"

            # Repair pass se:
            # - não gerou nada útil
            # - output NÃO veio em pt-br
            # - ou ficou abaixo do mínimo esperado
            if not cards or out_lang != "pt-br" or len(cards) < target_min:
                yield (
                    "event: stage\ndata: "
                    + json.dumps(
                        {
                            "stage": "repair_pass",
                            "reason": f"lang={out_lang}, cards={len(cards)}, min={target_min}",
                        }
                    )
                    + "\n\n"
                )

                # IMPORTANTE: NÃO incluir "SAÍDA RUIM: {raw}" aqui,
                # isso estava puxando o modelo pro inglês.
                repair_prompt = f"""
CONTEÚDO-FONTE (crie cards EXCLUSIVAMENTE sobre este trecho):
{src}

{("CONTEXTO GERAL (apenas para entender o assunto - NÃO crie cards sobre informações que estão APENAS aqui):\n" + ctx) if ctx else ""}

{checklist_block if checklist_block else ""}

Reescreva em PT-BR seguindo RIGOROSAMENTE o formato e garantindo que CADA card:
1. Seja sobre um conceito presente no CONTEÚDO-FONTE (não no contexto geral)
2. Tenha SRC literal (5–25 palavras) copiado do CONTEÚDO-FONTE
Se o texto-fonte estiver em inglês, o SRC ficará em inglês (isso é permitido). Fora do campo SRC, escreva em PT-BR.
Gere entre {target_min} e {target_max} cards.

{format_block}

EXEMPLO DE CLOZE CORRETO:
CLOZE: A capital do Brasil é {{c1::Brasília}}.
EXTRA: Brasília foi inaugurada em 1960.
SRC: "A capital do Brasil é Brasília"

PROIBIDO:
- Qualquer idioma que NÃO seja Português do Brasil (pt-BR) fora do campo SRC
- Espanhol fora do campo SRC
- Inglês fora do campo SRC
- Listas (bullets, números)
- Markdown
- "Question:" / "Answer:"
- Múltiplas lacunas cloze
- Cards sobre as “Diretrizes de Qualidade”

COMECE DIRETO (sem explicar nada):
""".strip()

                raw2 = ""
                
                if use_openai:
                    async for piece in openai_generate_stream(
                        request.openaiApiKey,
                        model,
                        repair_prompt,
                        system=SYSTEM_PTBR,
                        options={"num_predict": 4096, "temperature": 0.0},
                    ):
                        raw2 += piece
                elif use_perplexity:
                    async for piece in perplexity_generate_stream(
                        request.perplexityApiKey,
                        model,
                        repair_prompt,
                        system=SYSTEM_PTBR,
                        options={"num_predict": 4096, "temperature": 0.0},
                    ):
                        raw2 += piece
                else:
                    async for piece in ollama_generate_stream(
                        model,
                        repair_prompt,
                        system=SYSTEM_PTBR,
                        options={"num_predict": 4096, "temperature": 0.0},
                    ):
                        raw2 += piece

                # Repair parse (QA -> JSON fallback)
                cards2_raw = normalize_cards(parse_flashcards_qa(raw2))
                repair_mode = "qa"
                if not cards2_raw:
                    cards2_raw = normalize_cards(parse_flashcards_json(raw2))
                    repair_mode = "json"

                # Aplica filtro por tipo também no repair
                cards2_raw = _filter_by_card_type(cards2_raw, card_type, analysis_id=request.analysisId)

                yield f"event: stage\ndata: {json.dumps({'stage': 'repair_parsed', 'mode': repair_mode, 'count': len(cards2_raw)})}\n\n"

                # SRC filter usando LLM no repair também
                cards2 = await _validate_src_with_llm(
                    cards2_raw, 
                    src, 
                    provider=provider,
                    model=validation_model,
                    openai_key=request.openaiApiKey,
                    perplexity_key=request.perplexityApiKey,
                    analysis_id=request.analysisId
                )
                yield f"event: stage\ndata: {json.dumps({'stage': 'repair_src_filtered', 'kept': len(cards2), 'dropped': max(0, len(cards2_raw) - len(cards2)), 'method': 'llm'})}\n\n"

                # Content relevance filter usando LLM no repair também
                cards2_before_relevance = len(cards2)
                cards2 = await _filter_cards_by_content_relevance_llm(
                    cards2, 
                    src,
                    provider=provider,
                    model=validation_model,  # Usa modelo de validação
                    openai_key=request.openaiApiKey,
                    perplexity_key=request.perplexityApiKey,
                    analysis_id=request.analysisId,
                )
                if len(cards2) < cards2_before_relevance:
                    yield f"event: stage\ndata: {json.dumps({'stage': 'repair_llm_relevance_filtered', 'kept': len(cards2), 'dropped': cards2_before_relevance - len(cards2)})}\n\n"

                # Fallback no repair também
                if not cards2 and cards2_raw:
                    for c in cards2_raw:
                        c.pop("src", None)
                    cards2 = cards2_raw
                    yield f"event: stage\ndata: {json.dumps({'stage': 'repair_src_bypassed', 'count': len(cards2)})}\n\n"

                # BÔNUS também no repair
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

                # aceita a versão reparada se existir
                if cards2:
                    cards = cards2

                out_lang2 = _cards_lang_from_cards(cards)
                yield f"event: stage\ndata: {json.dumps({'stage': 'lang_check_after_repair', 'lang': out_lang2, 'cards': len(cards)})}\n\n"

            deck = pick_default_deck(request.deckOptions or "General")

            # Propaga SRC para o frontend + persistência
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
