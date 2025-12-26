# app/api/flashcards.py
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
import json
import re
import logging
from pathlib import Path

from app.config import OLLAMA_MODEL, OLLAMA_ANALYSIS_MODEL, MAX_CTX_CHARS
from app.services.ollama import ollama_generate_stream
from app.services.parser import (
    parse_flashcards_qa,
    parse_flashcards_json,
    normalize_cards,
    pick_default_deck,
)
from app.utils.text import (
    truncate_source,
    strip_src_lines,
    detect_language_pt_en_es,
)
from app.services.storage import save_analysis, save_cards

router = APIRouter(prefix="/api", tags=["flashcards"])
logger = logging.getLogger(__name__)

SYSTEM_PTBR = (
    "Você é um gerador de flashcards.\n"
    "Fora do campo SRC, escreva SEMPRE em Português do Brasil (pt-BR).\n"
    "No campo SRC, COPIE literalmente do texto-fonte (pode estar em inglês).\n"
    "NUNCA responda em espanhol.\n"
)


class TextRequest(BaseModel):
    text: str


class CardsRequest(BaseModel):
    text: str
    textContext: Optional[str] = ""
    deckOptions: Optional[str] = "General"
    useRAG: Optional[bool] = False
    topK: Optional[int] = 0

    # "basic" | "cloze" | "both"
    cardType: Optional[str] = "both"


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
# Card SRC validation
# =============================================================================

def _is_src_valid(ref: str, src_text: str) -> bool:
    """
    Heurísticas simples:
    - src deve existir
    - src (normalizado) precisa aparecer no texto-fonte (normalizado)
    - src deve ter 5–25 palavras (para evitar SRC enorme ou trivial)
    """
    ref = (ref or "").strip().strip('"').strip()
    if not ref:
        return False

    wc = len(ref.split())
    if wc < 5 or wc > 25:
        return False

    return _norm_ws(ref) in _norm_ws(src_text)


def _filter_cards_with_valid_src(cards, src_text: str):
    """
    Mantém apenas cards cujo campo `src` aparece (quase-verbatim) dentro do texto-fonte.
    Isso ajuda a garantir que o modelo está ancorando no trecho selecionado.
    """
    kept = []
    for c in cards or []:
        ref = (c.get("src") or "").strip().strip('"').strip()
        if not _is_src_valid(ref, src_text):
            continue
        c["src"] = ref
        kept.append(c)
    return kept


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
            logger.info("Ollama analysis model (embeddings): %s", OLLAMA_ANALYSIS_MODEL)

            from app.services.ollama import ollama_embed, chunk_text, cosine_similarity

            yield f"event: progress\ndata: {json.dumps({'percent': 10, 'stage': 'preparing'})}\n\n"

            src = truncate_source(request.text or "")
            chunks = chunk_text(src, chunk_size=400)

            yield f"event: progress\ndata: {json.dumps({'percent': 30, 'stage': 'embedding'})}\n\n"

            chunk_embeddings = []
            for chunk in chunks:
                emb = await ollama_embed(OLLAMA_ANALYSIS_MODEL, chunk)
                chunk_embeddings.append((chunk, emb))

            query = "conceitos importantes, definições técnicas, contrastes e distinções"
            query_emb = await ollama_embed(OLLAMA_ANALYSIS_MODEL, query)

            yield f"event: progress\ndata: {json.dumps({'percent': 60, 'stage': 'ranking'})}\n\n"

            scored = [(chunk, cosine_similarity(emb, query_emb)) for chunk, emb in chunk_embeddings]
            scored.sort(key=lambda x: x[1], reverse=True)

            top_chunks = [chunk for chunk, _ in scored[:3]]
            summary = "\n\n".join(top_chunks)

            result = {"content": [{"type": "text", "text": summary}]}

            analysis_id = save_analysis(src, summary, {"chunks": len(chunks), "top_chunks": len(top_chunks)})
            result["analysis_id"] = analysis_id

            yield f"event: progress\ndata: {json.dumps({'percent': 100, 'stage': 'done'})}\n\n"
            yield f"event: result\ndata: {json.dumps(result)}\n\n"

        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/generate-cards-stream")
async def generate_cards_stream(request: CardsRequest):
    async def generate():
        try:
            logger.info("Ollama generation model (cards): %s", OLLAMA_MODEL)

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

            type_instruction = {
                "basic": "Gere APENAS cards [BASIC].",
                "cloze": "Gere APENAS cards [CLOZE].",
                "both": "Para cada conceito importante, gere 1 [BASIC] + 1 [CLOZE].",
            }[card_type]

            checklist_block = _format_checklist_block()

            prompt = f"""
CONTEÚDO-FONTE (use SOMENTE isso como base):
{src}

{("CONTEXTO (opcional):\n" + ctx) if ctx else ""}

{checklist_block if checklist_block else ""}

TAREFA:
- Crie flashcards em PT-BR BASEADOS APENAS no CONTEÚDO-FONTE.
- Se algo não estiver no texto, NÃO invente.
- Se o texto estiver em inglês, traduza os conceitos para PT-BR (sem adicionar fatos).
- IMPORTANTE: O campo SRC é uma CITAÇÃO LITERAL do texto-fonte; se o texto-fonte estiver em inglês, o SRC ficará em inglês (isso é permitido).
- Fora do campo SRC, NUNCA use inglês.

QUANTIDADE:
- Gere entre {target_min} e {target_max} cards.

TIPOS:
{type_instruction}

FORMATO OBRIGATÓRIO (use exatamente estas chaves):
Q: [BASIC] <pergunta específica em PT-BR>
A: <resposta curta em PT-BR (1-2 frases)>
SRC: "<trecho COPIADO do CONTEÚDO-FONTE (5-25 palavras), sem alterar>"

Q: [CLOZE] <frase em PT-BR com UMA lacuna {{c1::termo}}>
A: Extra: <1 frase de contexto adicional em PT-BR>
SRC: "<trecho COPIADO do CONTEÚDO-FONTE (5-25 palavras), sem alterar>"

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
            async for piece in ollama_generate_stream(OLLAMA_MODEL, prompt, system=SYSTEM_PTBR, options=options):
                raw += piece

            # Parse/normalize (QA -> JSON fallback)
            cards_raw = normalize_cards(parse_flashcards_qa(raw))
            parse_mode = "qa"
            if not cards_raw:
                cards_raw = normalize_cards(parse_flashcards_json(raw))
                parse_mode = "json"

            yield f"event: stage\ndata: {json.dumps({'stage': 'parsed', 'mode': parse_mode, 'count': len(cards_raw)})}\n\n"

            # SRC filter
            cards = _filter_cards_with_valid_src(cards_raw, src)
            yield f"event: stage\ndata: {json.dumps({'stage': 'src_filtered', 'kept': len(cards), 'dropped': max(0, len(cards_raw) - len(cards))})}\n\n"

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
CONTEÚDO-FONTE (use SOMENTE isso como base):
{src}

{("CONTEXTO (opcional):\n" + ctx) if ctx else ""}

{checklist_block if checklist_block else ""}

Reescreva em PT-BR seguindo RIGOROSAMENTE o formato e garantindo que CADA card tenha SRC literal (5–25 palavras) do texto-fonte.
Se o texto-fonte estiver em inglês, o SRC ficará em inglês (isso é permitido). Fora do campo SRC, escreva em PT-BR.
Gere entre {target_min} e {target_max} cards.

FORMATO:
Q: [BASIC] ...
A: ...
SRC: "..."

Q: [CLOZE] ... {{c1::...}} ...
A: Extra: ...
SRC: "..."

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
                async for piece in ollama_generate_stream(
                    OLLAMA_MODEL,
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

                yield f"event: stage\ndata: {json.dumps({'stage': 'repair_parsed', 'mode': repair_mode, 'count': len(cards2_raw)})}\n\n"

                cards2 = _filter_cards_with_valid_src(cards2_raw, src)
                yield f"event: stage\ndata: {json.dumps({'stage': 'repair_src_filtered', 'kept': len(cards2), 'dropped': max(0, len(cards2_raw) - len(cards2))})}\n\n"

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

            cards_id = save_cards(result_cards, source_text=src)

            yield f"event: stage\ndata: {json.dumps({'stage': 'done', 'total_cards': len(result_cards), 'cards_id': cards_id})}\n\n"
            yield f"event: result\ndata: {json.dumps({'success': True, 'cards': result_cards})}\n\n"

        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
