from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Tuple, Literal
import asyncio
import httpx
import os
import json
import random
import re
import unicodedata
import time
import uuid
import html as _html
from pathlib import Path
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from difflib import SequenceMatcher
import logging

from app.config import (
    ANKI_CONNECT_URL,
    TRANSLATION_DEFAULT_CONCURRENCY,
    TRANSLATION_MAX_CONCURRENCY,
    TRANSLATION_OLLAMA_MAX_CONCURRENCY,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["anki"])

# =============================================================================
# Helpers env / time / filesystem
# =============================================================================

def _env_float(name: str, default: float) -> Optional[float]:
    raw = os.getenv(name, None)
    if raw is None:
        v = float(default)
    else:
        try:
            v = float(raw)
        except Exception:
            v = float(default)
    if v <= 0:
        return None
    return v

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _slug(s: str, max_len: int = 80) -> str:
    s = (s or "").strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return (s[:max_len] or "x")

DATA_BROWSER_DIR = Path(os.getenv("BROWSER_DATA_DIR", str(Path("data") / "browser")))
DATA_BROWSER_DIR.mkdir(parents=True, exist_ok=True)

def _write_toon_file(kind: str, request_id: str, payload: dict) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{ts}_{kind}_{request_id}.toon"
    path = DATA_BROWSER_DIR / filename
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)

def clamp_int(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))

def safe_int(v: Any, default: Optional[int] = None) -> Optional[int]:
    try:
        if v is None:
            return default
        return int(v)
    except Exception:
        return default

# =============================================================================
# Dificuldade + escolha de modelo Ollama
# =============================================================================

DifficultyInput = Literal[
    "easy", "hard_neutral", "hard_technical",
    "facil", "dificil_neutra", "dificil_tecnica"
]

def normalize_difficulty(s: Optional[str]) -> str:
    v = (s or "hard_neutral").strip().lower()
    m = {
        "easy": "easy",
        "facil": "easy",
        "hard_neutral": "hard_neutral",
        "dificil_neutra": "hard_neutral",
        "hard_technical": "hard_technical",
        "dificil_tecnica": "hard_technical",
    }
    return m.get(v, "hard_neutral")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL_EASY = os.getenv("OLLAMA_MODEL_EASY", "qwen-flashcard")               # easy + hard_neutral
OLLAMA_MODEL_NEUTRAL = os.getenv("OLLAMA_MODEL_NEUTRAL", "qwen-flashcard")         # idem
OLLAMA_MODEL_TECH = os.getenv("OLLAMA_MODEL_TECH", "qwen3:4b-instruct")            # hard_technical

OLLAMA_TIMEOUT_S: Optional[float] = _env_float("OLLAMA_TIMEOUT_S", 120.0)
OLLAMA_TEMPERATURE = float(os.getenv("OLLAMA_TEMPERATURE", "0.4"))

def pick_ollama_model(difficulty: str) -> str:
    if difficulty == "hard_technical":
        return OLLAMA_MODEL_TECH
    if difficulty == "easy":
        return OLLAMA_MODEL_EASY
    return OLLAMA_MODEL_NEUTRAL

# =============================================================================
# Prompts (agora com DIFICULDADE + regra de NÃO COPIAR)
# =============================================================================

CLOZE_EXAMPLES = """\
EXEMPLOS (apenas para guiar o estilo):

Versão fácil:
A criação de usuários, grupos e o gerenciamento de políticas de acesso são feitos no serviço {{c1::IAM}} (Identity and Access Management).

Versão difícil neutra:
A criação de {{c1::usuários}} e {{c2::grupos}} e o gerenciamento de {{c3::políticas (permissions)}} de acesso na AWS são feitos no serviço {{c4::IAM (Identity and Access Management)}}.

Versão difícil técnica:
No serviço {{c1::IAM (Identity and Access Management)}}, você define {{c2::identidades (principals)}}, como {{c3::users}}, {{c4::groups}} e {{c5::roles}}, e controla permissões anexando {{c6::políticas baseadas em identidade (identity-based policies, JSON)}} às identidades (ou políticas em recursos quando aplicável), sempre avaliadas por lógica de {{c7::explicit deny > allow}}.
"""

PROMPT_STRUCT_CLOZE = f"""\
Você é um gerador de notas do Anki do tipo CLOZE.

OBJETIVO:
Recriar uma nova nota (não copiar), mantendo o mesmo conceito do texto original.

ENTRADA:
- source_text: texto original (curto, sem HTML pesado)
- difficulty: "easy" | "hard_neutral" | "hard_technical"
- target_fields: lista exata de campos do note type

REGRAS GERAIS:
1) Responda APENAS com JSON válido no schema solicitado.
2) NÃO devolva HTML. Saída deve ser texto puro.
3) NÃO copie o texto original. Reescreva com outras palavras e/ou reestruture a frase.
   - Evite reutilizar trechos longos idênticos do source_text.
4) O campo principal (primeiro campo em target_fields) DEVE conter clozes no formato {{cN::...}}.
   - Numere em ordem (c1, c2, c3...).

REGRAS POR DIFICULDADE:
- easy:
  - Use exatamente 1 cloze.
  - Frase curta e direta.
- hard_neutral:
  - Use 3 a 5 clozes.
  - Pode usar dicas em parênteses (ex.: termo em inglês).
- hard_technical:
  - Use 5 a 8 clozes.
  - Linguagem mais técnica (termos e taxonomia quando fizer sentido).
  - Pode incluir termos em inglês e detalhes (sem inventar fatos fora do tema).

{CLOZE_EXAMPLES}

SAÍDA:
{{ "notes": [ {{ "fields": {{ ... }} }} ] }}
"""

PROMPT_STRUCT_BASIC = """\
Você é um gerador de notas do Anki do tipo BASIC.

OBJETIVO:
Recriar (não copiar) uma nova pergunta/resposta mantendo o mesmo conceito.

ENTRADA:
- source_front / source_back (texto original, sem HTML pesado)
- difficulty: "easy" | "hard_neutral" | "hard_technical"
- target_fields: lista exata de campos do note type

REGRAS:
1) Responda APENAS com JSON válido no schema solicitado.
2) NÃO copie a pergunta/resposta original; reescreva.
3) difficulty:
   - easy: pergunta direta e resposta curta.
   - hard_neutral: pergunta um pouco mais contextualizada (cenário), resposta ainda objetiva.
   - hard_technical: pergunta técnica (termos/precisão), resposta técnica (sem inventar).
4) Use o 1º campo como Front e 2º como Back. Campos extras: deixe "".

SAÍDA:
{ "notes": [ { "fields": { ... } } ] }
"""

PROMPT_STRUCT_ALLINONE = """\
Você é um gerador de notas do Anki para Note Type AllInOne (kprim, mc, sc).

OBJETIVO:
Recriar (não copiar) uma questão equivalente ao conteúdo original.

ENTRADA:
- source_text
- difficulty: "easy" | "hard_neutral" | "hard_technical"
- target_fields

REGRAS:
1) JSON válido apenas.
2) Não copie o texto; reescreva.
3) Dificuldade:
   - easy: alternativas mais óbvias.
   - hard_neutral: distratores plausíveis.
   - hard_technical: termos técnicos e distratores mais próximos.
4) Preencha campos QType/Q_1..Q_5/Answers se existirem.

SAÍDA:
{ "notes": [ { "fields": { ... } } ] }
"""

def normalize_name(s: str) -> str:
    s = (s or "").strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"\s+", " ", s).strip()
    return s

PROMPTS_BY_NORMALIZED_NOTE_TYPE: Dict[str, str] = {
    "allinone (kprim, mc, sc)": PROMPT_STRUCT_ALLINONE,
    "basic": PROMPT_STRUCT_BASIC,
    "basico": PROMPT_STRUCT_BASIC,
    "basico (cartao invertido opcional)": PROMPT_STRUCT_BASIC,
    "basic (optional reversed card)": PROMPT_STRUCT_BASIC,
    "basico (digite a resposta)": PROMPT_STRUCT_BASIC,
    "basic (type in the answer)": PROMPT_STRUCT_BASIC,
    "basico (e cartao invertido)": PROMPT_STRUCT_BASIC,
    "basic (and reversed card)": PROMPT_STRUCT_BASIC,
    "cloze": PROMPT_STRUCT_CLOZE,
    "omissao de palavras": PROMPT_STRUCT_CLOZE,
}

def prompt_family_for_model(model_name: str) -> Optional[str]:
    n = normalize_name(model_name)
    if n in PROMPTS_BY_NORMALIZED_NOTE_TYPE:
        p = PROMPTS_BY_NORMALIZED_NOTE_TYPE[n]
        if p == PROMPT_STRUCT_BASIC:
            return "basic"
        if p == PROMPT_STRUCT_CLOZE:
            return "cloze"
        if p == PROMPT_STRUCT_ALLINONE:
            return "allinone"
    if n.startswith("basic") or n.startswith("basico"):
        return "basic"
    if "cloze" in n or "omissao de palavras" in n:
        return "cloze"
    if n.startswith("allinone"):
        return "allinone"
    return None

def prompt_for_model(model_name: str) -> Optional[str]:
    n = normalize_name(model_name)
    if n in PROMPTS_BY_NORMALIZED_NOTE_TYPE:
        return PROMPTS_BY_NORMALIZED_NOTE_TYPE[n]
    fam = prompt_family_for_model(model_name)
    if fam == "basic":
        return PROMPT_STRUCT_BASIC
    if fam == "cloze":
        return PROMPT_STRUCT_CLOZE
    if fam == "allinone":
        return PROMPT_STRUCT_ALLINONE
    return None

# =============================================================================
# HTML -> texto (pra não mandar “lixo” pro SLM e não aceitar HTML na volta)
# =============================================================================

STYLE_BLOCK_PAT = re.compile(r"<style[^>]*>.*?</style>", flags=re.IGNORECASE | re.DOTALL)
SCRIPT_BLOCK_PAT = re.compile(r"<script[^>]*>.*?</script>", flags=re.IGNORECASE | re.DOTALL)
TAG_PAT = re.compile(r"<[^>]+>", flags=re.DOTALL)

CLOZE_PAT = re.compile(r"\{\{c\d+::.+?\}\}", flags=re.DOTALL)

SPAN_CLOZE_PAT = re.compile(
    r"<span(?P<attrs>[^>]*)>(?P<inner>.*?)</span>",
    flags=re.IGNORECASE | re.DOTALL,
)

def _span_cloze_to_mustaches(html: str) -> str:
    if not html:
        return html or ""

    def repl(m: re.Match) -> str:
        attrs = m.group("attrs") or ""
        inner = (m.group("inner") or "").strip()

        class_m = re.search(r"class=['\"]([^'\"]+)['\"]", attrs, flags=re.IGNORECASE)
        cls = (class_m.group(1) if class_m else "") or ""
        if "cloze" not in cls.lower():
            return m.group(0)

        ord_m = re.search(r"data-ordinal=['\"](\d+)['\"]", attrs, flags=re.IGNORECASE)
        n = int(ord_m.group(1)) if ord_m else 1

        dc_m = re.search(r"data-cloze=['\"]([^'\"]+)['\"]", attrs, flags=re.IGNORECASE)
        dc = _html.unescape(dc_m.group(1)) if dc_m else ""

        inner_txt = TAG_PAT.sub("", inner).strip()
        chosen = inner_txt
        if (not chosen) or chosen in {"[...]", "..."}:
            if dc:
                chosen = dc
        if not chosen:
            chosen = inner_txt or dc or "..."
        
        chosen = chosen.replace("}", "").replace("{", "")

        return f"{{{{c{n}::{chosen}}}}}"

    return SPAN_CLOZE_PAT.sub(repl, html)

def _html_to_text_preserve_cloze(s: str) -> str:
    if not s:
        return ""
    s = _span_cloze_to_mustaches(s)
    s = STYLE_BLOCK_PAT.sub(" ", s)
    s = SCRIPT_BLOCK_PAT.sub(" ", s)
    s = re.sub(r"(?i)<br\s*/?>", "\n", s)
    s = re.sub(r"(?i)</(div|p|li|tr|h\d)>", "\n", s)
    s = TAG_PAT.sub(" ", s)
    s = _html.unescape(s)
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n", s)
    return s.strip()

def _contains_cloze(s: str) -> bool:
    return bool(CLOZE_PAT.search(s or ""))

def _count_cloze_occurrences(s: str) -> int:
    return len(re.findall(r"\{\{c\d+::", s or ""))

def _renumber_clozes_sequential(s: str) -> str:
    if not s:
        return s or ""

    pat = re.compile(r"\{\{c(\d+)::(.*?)\}\}", flags=re.DOTALL)

    idx = 0
    def repl(m: re.Match) -> str:
        nonlocal idx
        idx += 1
        body = m.group(2)
        return f"{{c{idx}::{body}}}"

    return pat.sub(repl, s)

def _normalize_for_similarity(s: str) -> str:
    s = _html_to_text_preserve_cloze(s)
    s = re.sub(r"\{\{c\d+::(.*?)\}\}", r"\1", s, flags=re.DOTALL)
    s = s.lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _too_similar(a: str, b: str, threshold: float = 0.90) -> bool:
    aa = _normalize_for_similarity(a)
    bb = _normalize_for_similarity(b)
    if not aa or not bb:
        return False
    if aa == bb:
        return True
    ratio = SequenceMatcher(None, aa, bb).ratio()
    return ratio >= threshold

# =============================================================================
# AnkiConnect helpers
# =============================================================================

async def ankiconnect(client: httpx.AsyncClient, action: str, params: Optional[dict] = None):
    payload: Dict[str, Any] = {"action": action, "version": 6}
    if params is not None:
        payload["params"] = params

    r = await client.post(ANKI_CONNECT_URL, json=payload)
    r.raise_for_status()

    data = r.json()
    if data.get("error"):
        raise Exception(f"AnkiConnect error (action={action}): {data['error']}")
    return data.get("result")

async def anki_can_add_note_detail(client: httpx.AsyncClient, note_payload: dict) -> Tuple[bool, Optional[str]]:
    try:
        res = await ankiconnect(client, "canAddNotesWithErrorDetail", {"notes": [note_payload]})
        if isinstance(res, list) and res:
            item = res[0]
            if isinstance(item, dict):
                return bool(item.get("canAdd", True)), (item.get("error") or None)
    except Exception:
        pass
    return True, None

def _extract_notesinfo_fields(note_info: Dict[str, Any]) -> Tuple[Dict[str, str], List[Tuple[int, str, str]]]:
    """
    Retorna:
      - dict fieldName->value
      - lista ordenada por "order": [(order, fieldName, value), ...]
    """
    out: Dict[str, str] = {}
    ordered: List[Tuple[int, str, str]] = []
    fields = note_info.get("fields") or {}
    if isinstance(fields, dict):
        for fname, fv in fields.items():
            if isinstance(fv, dict):
                val = str(fv.get("value") or "")
                parsed_order = safe_int(fv.get("order"), default=9999)
                order = parsed_order if parsed_order is not None else 9999
            else:
                val = str(fv or "")
                order = 9999
            out[str(fname)] = val
            ordered.append((order, str(fname), val))
    ordered.sort(key=lambda x: x[0])
    return out, ordered

# =============================================================================
# Health checks
# =============================================================================

@router.get("/health/anki")
async def health_anki():
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            v = await ankiconnect(client, "version", None)
            return {"ok": True, "service": "anki", "ankiConnectUrl": ANKI_CONNECT_URL, "ankiConnectVersion": v}
    except Exception as e:
        return JSONResponse(status_code=503, content={"ok": False, "service": "anki", "error": str(e)})

@router.get("/health/ollama")
async def health_ollama():
    """
    Agora checa se os dois modelos exigidos existem:
      - qwen-flashcard (easy/hard_neutral)
      - qwen3:4b-instruct (hard_technical)
    """
    try:
        async with httpx.AsyncClient(timeout=2.5) as client:
            r = await client.get(f"{OLLAMA_URL}/api/tags")
            r.raise_for_status()
            data = r.json() if r.content else {}
            models = [str(m.get("name")) for m in (data.get("models") or []) if isinstance(m, dict) and m.get("name")]

            def has(name: str) -> bool:
                return any(x == name or x.startswith(name + ":") or name.startswith(x + ":") for x in models)

            return {
                "ok": True,
                "service": "ollama",
                "ollamaUrl": OLLAMA_URL,
                "timeoutS": OLLAMA_TIMEOUT_S,
                "modelsCount": len(models),
                "required": {
                    "easy_or_neutral": {"model": OLLAMA_MODEL_NEUTRAL, "available": has(OLLAMA_MODEL_NEUTRAL)},
                    "hard_technical": {"model": OLLAMA_MODEL_TECH, "available": has(OLLAMA_MODEL_TECH)},
                },
            }
    except Exception as e:
        return JSONResponse(status_code=503, content={"ok": False, "service": "ollama", "ollamaUrl": OLLAMA_URL, "error": str(e)})

# =============================================================================
# Ollama helper (JSON output via /api/chat + schema)
# =============================================================================

OLLAMA_NOTES_SCHEMA = {
    "type": "object",
    "properties": {
        "notes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "fields": {
                        "type": "object",
                        "additionalProperties": {"type": "string"}
                    }
                },
                "required": ["fields"]
            }
        }
    },
    "required": ["notes"]
}

def _try_extract_json(text: str) -> Optional[dict]:
    if not text:
        return None
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"(\{.*\})", text, flags=re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except Exception:
        return None

async def ollama_generate_notes(
    client: httpx.AsyncClient,
    *,
    request_id: str,
    ollama_model: str,
    temperature: float,
    source_note_id: int,
    source_card_id: Optional[int],
    target_model_name: str,
    target_fields: List[str],
    family: str,
    difficulty: str,
    source_payload: Dict[str, Any],
    prompt_struct: str,
    retry_hint: Optional[str] = None,
) -> Tuple[Dict[str, str], str]:
    system = (
        "Você gera conteúdo para notas do Anki e SEMPRE responde somente com JSON válido, "
        "seguindo exatamente o schema solicitado. Não escreva nada fora do JSON."
    )

    user = {
        "task": "recreate_notes_from_selected_card",
        "target_model_name": target_model_name,
        "target_fields": target_fields,
        "family": family,
        "difficulty": difficulty,
        "source": source_payload,
        "retry_hint": retry_hint or "",
        "instructions": prompt_struct,
    }

    payload = {
        "model": ollama_model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
        ],
        "stream": False,
        "format": OLLAMA_NOTES_SCHEMA,
        "options": {"temperature": float(temperature)},
    }

    t0 = time.monotonic()
    dbg: dict = {
        "kind": "ollama_generation",
        "ts": _now_iso(),
        "requestId": request_id,
        "ollamaUrl": OLLAMA_URL,
        "ollamaModel": ollama_model,
        "temperature": temperature,
        "timeoutS": OLLAMA_TIMEOUT_S,
        "sourceNoteId": source_note_id,
        "sourceCardId": source_card_id,
        "targetModelName": target_model_name,
        "targetFields": target_fields,
        "family": family,
        "difficulty": difficulty,
        "retryHint": retry_hint or "",
        "requestPayload": payload,
    }

    try:
        r = await client.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=OLLAMA_TIMEOUT_S)
        r.raise_for_status()
        data = r.json()
        dbg["httpStatus"] = r.status_code
        dbg["rawResponse"] = data
    except httpx.TimeoutException as e:
        dbg["error"] = f"Ollama timeout após {OLLAMA_TIMEOUT_S}s: {e}"
        dbg["elapsedMs"] = int((time.monotonic() - t0) * 1000)
        path = _write_toon_file(f"ollama_timeout_nid{source_note_id}_{_slug(target_model_name)}", request_id, dbg)
        raise Exception(f"Ollama timeout após {OLLAMA_TIMEOUT_S}s. (Veja: {path})")
    except Exception as e:
        dbg["error"] = f"Ollama HTTP/parse falhou: {e}"
        dbg["elapsedMs"] = int((time.monotonic() - t0) * 1000)
        path = _write_toon_file(f"ollama_error_nid{source_note_id}_{_slug(target_model_name)}", request_id, dbg)
        raise Exception(f"Ollama indisponível ou erro HTTP. (Veja: {path})")

    content = ""
    if isinstance(data, dict):
        msg = data.get("message") or {}
        content = msg.get("content") or ""

    dbg["messageContentHead"] = (content or "")[:5000]
    parsed = _try_extract_json(content)
    dbg["parsed"] = parsed

    if not parsed or "notes" not in parsed:
        dbg["error"] = "SLM/Ollama retornou conteúdo não-JSON ou fora do schema esperado."
        dbg["elapsedMs"] = int((time.monotonic() - t0) * 1000)
        path = _write_toon_file(f"ollama_badjson_nid{source_note_id}_{_slug(target_model_name)}", request_id, dbg)
        raise Exception(f"SLM/Ollama retornou JSON inválido/fora do schema. (Veja: {path})")

    notes = parsed.get("notes") or []
    if not notes or not isinstance(notes, list) or not isinstance(notes[0], dict):
        dbg["error"] = "SLM/Ollama não retornou notes válidas."
        dbg["elapsedMs"] = int((time.monotonic() - t0) * 1000)
        path = _write_toon_file(f"ollama_empty_nid{source_note_id}_{_slug(target_model_name)}", request_id, dbg)
        raise Exception(f"SLM/Ollama não retornou notes válidas. (Veja: {path})")

    fields = (notes[0] or {}).get("fields") or {}
    if not isinstance(fields, dict):
        dbg["error"] = "fields inválido."
        dbg["elapsedMs"] = int((time.monotonic() - t0) * 1000)
        path = _write_toon_file(f"ollama_badfields_nid{source_note_id}_{_slug(target_model_name)}", request_id, dbg)
        raise Exception(f"SLM/Ollama retornou fields inválido. (Veja: {path})")

    out = {str(k): str(v) for k, v in fields.items()}
    dbg["elapsedMs"] = int((time.monotonic() - t0) * 1000)
    dbg["fieldsPreview"] = {k: (out.get(k, "")[:250]) for k in list(out.keys())[:4]}
    path = _write_toon_file(f"ollama_ok_nid{source_note_id}_{_slug(target_model_name)}", request_id, dbg)
    return out, path


# =============================================================================
# Multi-provider generation (OpenAI, Perplexity, Anthropic)
# =============================================================================

async def generate_notes_multi_provider(
    *,
    request_id: str,
    provider: str,
    model: str,
    temperature: float,
    source_note_id: int,
    source_card_id: Optional[int],
    target_model_name: str,
    target_fields: List[str],
    family: str,
    difficulty: Optional[str],
    source_payload: Dict[str, Any],
    prompt_struct: str,
    retry_hint: Optional[str] = None,
    custom_system: Optional[str] = None,
    custom_guidelines: Optional[str] = None,
    openai_api_key: Optional[str] = None,
    perplexity_api_key: Optional[str] = None,
    anthropic_api_key: Optional[str] = None,
) -> Tuple[Dict[str, str], str]:
    """
    Gera notas usando múltiplos providers (OpenAI, Perplexity, Anthropic).
    Retorna tupla (fields_dict, debug_file_path).
    """

    # Build system prompt
    system = custom_system or (
        "Você gera conteúdo para notas do Anki e SEMPRE responde somente com JSON válido, "
        "seguindo exatamente o schema solicitado. Não escreva nada fora do JSON."
    )

    # Build user prompt with optional difficulty
    user_content = {
        "task": "recreate_notes_from_selected_card",
        "target_model_name": target_model_name,
        "target_fields": target_fields,
        "family": family,
        "source": source_payload,
        "retry_hint": retry_hint or "",
        "instructions": prompt_struct,
    }

    if difficulty:
        user_content["difficulty"] = difficulty

    if custom_guidelines:
        user_content["guidelines"] = custom_guidelines

    t0 = time.monotonic()
    dbg: dict = {
        "kind": f"{provider}_generation",
        "ts": _now_iso(),
        "requestId": request_id,
        "provider": provider,
        "model": model,
        "temperature": temperature,
        "sourceNoteId": source_note_id,
        "sourceCardId": source_card_id,
        "targetModelName": target_model_name,
        "targetFields": target_fields,
        "family": family,
        "difficulty": difficulty,
        "retryHint": retry_hint or "",
    }

    try:
        content = ""

        if provider == "openai":
            if not openai_api_key:
                raise Exception("OpenAI API key não fornecida")

            async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, read=180.0)) as client:
                # Reasoning models (o1, o3, gpt-5) não suportam temperature
                if model.startswith(("o1-", "o1", "o3-", "o3", "gpt-5")):
                    payload = {
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": json.dumps(user_content, ensure_ascii=False)},
                        ],
                        "max_completion_tokens": 4096,
                        "response_format": {"type": "json_object"},
                    }
                else:
                    payload = {
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": json.dumps(user_content, ensure_ascii=False)},
                        ],
                        "temperature": temperature,
                        "max_completion_tokens": 4096,
                        "response_format": {"type": "json_object"},
                    }

                r = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {openai_api_key}",
                        "Content-Type": "application/json"
                    },
                    json=payload
                )
                r.raise_for_status()
                data = r.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

        elif provider == "perplexity":
            if not perplexity_api_key:
                raise Exception("Perplexity API key não fornecida")

            async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, read=180.0)) as client:
                payload = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": json.dumps(user_content, ensure_ascii=False)},
                    ],
                    "temperature": temperature,
                    "max_tokens": 4096,
                }

                r = await client.post(
                    "https://api.perplexity.ai/chat/completions",
                    headers={
                        "Authorization": f"Bearer {perplexity_api_key}",
                        "Content-Type": "application/json"
                    },
                    json=payload
                )
                r.raise_for_status()
                data = r.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

        elif provider == "anthropic":
            if not anthropic_api_key:
                raise Exception("Anthropic API key não fornecida")

            async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, read=180.0)) as client:
                payload = {
                    "model": model,
                    "max_tokens": 4096,
                    "system": system,
                    "messages": [
                        {"role": "user", "content": json.dumps(user_content, ensure_ascii=False)},
                    ],
                }

                r = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": anthropic_api_key,
                        "anthropic-version": "2023-06-01",
                        "Content-Type": "application/json"
                    },
                    json=payload
                )
                r.raise_for_status()
                data = r.json()
                # Anthropic returns content as array of blocks
                content_blocks = data.get("content", [])
                content = "".join(b.get("text", "") for b in content_blocks if b.get("type") == "text")
        else:
            raise Exception(f"Provider não suportado: {provider}")

        dbg["messageContentHead"] = (content or "")[:5000]
        parsed = _try_extract_json(content)
        dbg["parsed"] = parsed

        if not parsed or "notes" not in parsed:
            dbg["error"] = f"{provider} retornou conteúdo não-JSON ou fora do schema esperado."
            dbg["elapsedMs"] = int((time.monotonic() - t0) * 1000)
            path = _write_toon_file(f"{provider}_badjson_nid{source_note_id}_{_slug(target_model_name)}", request_id, dbg)
            raise Exception(f"{provider} retornou JSON inválido/fora do schema. (Veja: {path})")

        notes = parsed.get("notes") or []
        if not notes or not isinstance(notes, list) or not isinstance(notes[0], dict):
            dbg["error"] = f"{provider} não retornou notes válidas."
            dbg["elapsedMs"] = int((time.monotonic() - t0) * 1000)
            path = _write_toon_file(f"{provider}_empty_nid{source_note_id}_{_slug(target_model_name)}", request_id, dbg)
            raise Exception(f"{provider} não retornou notes válidas. (Veja: {path})")

        fields = (notes[0] or {}).get("fields") or {}
        if not isinstance(fields, dict):
            dbg["error"] = "fields inválido."
            dbg["elapsedMs"] = int((time.monotonic() - t0) * 1000)
            path = _write_toon_file(f"{provider}_badfields_nid{source_note_id}_{_slug(target_model_name)}", request_id, dbg)
            raise Exception(f"{provider} retornou fields inválido. (Veja: {path})")

        out = {str(k): str(v) for k, v in fields.items()}
        dbg["elapsedMs"] = int((time.monotonic() - t0) * 1000)
        dbg["fieldsPreview"] = {k: (out.get(k, "")[:250]) for k in list(out.keys())[:4]}
        path = _write_toon_file(f"{provider}_ok_nid{source_note_id}_{_slug(target_model_name)}", request_id, dbg)
        return out, path

    except httpx.TimeoutException as e:
        dbg["error"] = f"{provider} timeout: {e}"
        dbg["elapsedMs"] = int((time.monotonic() - t0) * 1000)
        path = _write_toon_file(f"{provider}_timeout_nid{source_note_id}_{_slug(target_model_name)}", request_id, dbg)
        raise Exception(f"{provider} timeout. (Veja: {path})")
    except Exception as e:
        dbg["error"] = f"{provider} erro: {e}"
        dbg["elapsedMs"] = int((time.monotonic() - t0) * 1000)
        path = _write_toon_file(f"{provider}_error_nid{source_note_id}_{_slug(target_model_name)}", request_id, dbg)
        raise Exception(f"{provider} erro: {e}. (Veja: {path})")


# =============================================================================
# Upload / listagens (mantidos)
# =============================================================================

class AnkiCard(BaseModel):
    front: str
    back: str
    deck: Optional[str] = None

class AnkiUpload(BaseModel):
    cards: List[AnkiCard]
    modelName: str
    frontField: str
    backField: str
    deckName: Optional[str] = None
    tags: Optional[str] = ""

@router.post("/upload-to-anki")
async def upload_to_anki(request: AnkiUpload):
    from fastapi.responses import JSONResponse
    import logging
    logger = logging.getLogger(__name__)

    results = []
    tags = [t.strip() for t in request.tags.split(",") if t.strip()] if request.tags else []

    logger.info(f"[Anki Export] Starting export of {len(request.cards)} cards")
    logger.info(f"[Anki Export] Model: {request.modelName}, Front: {request.frontField}, Back: {request.backField}, Deck: {request.deckName}")

    async with httpx.AsyncClient(timeout=30.0) as client:
        for i, card in enumerate(request.cards):
            try:
                deck_name = request.deckName or card.deck or "Default"
                note = {
                    "deckName": deck_name,
                    "modelName": request.modelName,
                    "fields": {request.frontField: card.front, request.backField: card.back},
                    "options": {"allowDuplicate": False},
                    "tags": tags,
                }
                logger.info(f"[Anki Export] Card {i+1}: deck={deck_name}, fields={list(note['fields'].keys())}")

                rr = await client.post(
                    ANKI_CONNECT_URL,
                    json={"action": "addNote", "version": 6, "params": {"note": note}},
                )
                data = rr.json()
                logger.info(f"[Anki Export] Card {i+1} response: {data}")

                if data.get("error"):
                    raise Exception(data["error"])
                results.append({"success": True, "id": data["result"]})
            except Exception as e:
                logger.error(f"[Anki Export] Card {i+1} failed: {str(e)}")
                results.append({"success": False, "error": str(e)})

    total_success = sum(1 for r in results if r["success"])
    total_cards = len(request.cards)

    response_data = {
        "success": total_success > 0,
        "results": results,
        "totalSuccess": total_success,
        "totalCards": total_cards,
    }

    # Retorna código HTTP apropriado
    if total_success == 0:
        # Nenhum card foi exportado - erro
        return JSONResponse(status_code=422, content=response_data)
    elif total_success < total_cards:
        # Sucesso parcial - 207 Multi-Status
        return JSONResponse(status_code=207, content=response_data)
    else:
        # Todos exportados com sucesso
        return response_data

@router.get("/anki-decks")
async def get_anki_decks():
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(ANKI_CONNECT_URL, json={"action": "deckNames", "version": 6})
            data = r.json()
            if data.get("error"):
                raise Exception(data["error"])
            return {"success": True, "decks": data["result"]}
    except Exception as e:
        return {"success": False, "error": str(e), "fallbackDecks": {"Default": "Default"}}

@router.get("/anki-models")
async def get_anki_models():
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(ANKI_CONNECT_URL, json={"action": "modelNames", "version": 6})
            model_names = r.json()["result"]

            models = {}
            for name in model_names:
                rr = await client.post(
                    ANKI_CONNECT_URL,
                    json={"action": "modelFieldNames", "version": 6, "params": {"modelName": name}},
                )
                models[name] = rr.json()["result"]

            deck_resp = await client.post(ANKI_CONNECT_URL, json={"action": "deckNames", "version": 6})
            decks = deck_resp.json()["result"]
            return {"success": True, "models": models, "decks": decks}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/anki-tags")
async def get_anki_tags():
    """
    Fetch all tags from Anki using AnkiConnect's getTags action.
    Returns sorted list of tags.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            tags = await ankiconnect(client, "getTags", None)
            tags = list(tags or [])
            tags.sort(key=lambda x: str(x).lower())
            return {"success": True, "tags": tags}
    except Exception as e:
        return {"success": False, "error": str(e), "tags": []}


@router.get("/anki-note-types")
async def get_anki_note_types():
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            names = await ankiconnect(client, "modelNames", None)
            names = list(names or [])
            names.sort(key=lambda x: normalize_name(str(x)))

            items = []
            for name in names:
                fam = prompt_family_for_model(str(name))
                supported = fam is not None and prompt_for_model(str(name)) is not None
                items.append({
                    "name": str(name),
                    "supported": bool(supported),
                    "family": fam or "unsupported",
                    "supportLabel": "Suportado" if supported else "Sem suporte",
                })

            return {"success": True, "items": items}
    except Exception as e:
        return {"success": False, "error": str(e), "items": []}

@router.get("/anki-cards")
async def get_anki_cards(
    query: str = Query("is:review", description="Anki search query. Ex: deck:\"My Deck\" is:review"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    limit = clamp_int(limit, 1, 200)
    offset = max(0, offset)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            ids = await ankiconnect(client, "findCards", {"query": query})
            ids = list(ids or [])
            total = len(ids)

            page_ids = ids[offset : offset + limit]
            if not page_ids:
                return {"success": True, "query": query, "total": total, "items": []}

            items = await ankiconnect(client, "cardsInfo", {"cards": page_ids})
            return {"success": True, "query": query, "total": total, "items": items or []}

    except Exception as e:
        return {"success": False, "error": str(e), "query": query, "total": 0, "items": []}

# =============================================================================
# Recreate via SLM/Ollama (com dificuldade + tags originais + anti-cópia)
# =============================================================================

class AnkiRecreateRequest(BaseModel):
    cardIds: List[int] = Field(default_factory=list)

    targetDeckName: Optional[str] = None
    allowDuplicate: bool = False
    suspendOriginal: bool = True
    countPerNote: int = 1
    targetModelNames: List[str] = Field(default_factory=list)

    # Modelo e provider selecionados
    model: Optional[str] = None  # Nome do modelo (ex: "qwen-flashcard", "gpt-4o", "sonar-pro")
    provider: Optional[str] = None  # "ollama", "openai", "perplexity", "anthropic"

    # Dificuldade (opcional)
    useDifficulty: bool = False
    difficulty: Optional[DifficultyInput] = None

    # Prompts customizados (opcional)
    customSystemPrompt: Optional[str] = None
    customGenerationPrompt: Optional[str] = None
    customGuidelines: Optional[str] = None

    # API keys
    openaiApiKey: Optional[str] = None
    perplexityApiKey: Optional[str] = None
    anthropicApiKey: Optional[str] = None

    # Mantém compatibilidade com frontend antigo
    addTag: Optional[str] = None

@router.post("/anki-recreate")
async def recreate_cards(req: AnkiRecreateRequest):
    request_id = uuid.uuid4().hex[:12]

    if not req.cardIds:
        return {
            "success": True,
            "requestId": request_id,
            "totalRequestedCards": 0,
            "totalSelectedNotes": 0,
            "totalCreated": 0,
            "totalFailed": 0,
            "totalSuspendedCards": 0,
            "results": [],
        }

    req.countPerNote = clamp_int(int(req.countPerNote or 1), 1, 50)

    if not req.targetModelNames:
        return JSONResponse(
            status_code=400,
            content={"success": False, "requestId": request_id, "error": "Selecione 1+ Note Types (targetModelNames)."},
        )

    # Configurações do modelo/provider
    llm_model = req.model or OLLAMA_MODEL_NEUTRAL
    llm_provider = (req.provider or "ollama").lower()

    # Dificuldade (opcional)
    use_difficulty = req.useDifficulty
    difficulty = normalize_difficulty(str(req.difficulty)) if use_difficulty and req.difficulty else None

    # Prompts customizados
    custom_system = req.customSystemPrompt or None
    custom_guidelines = req.customGuidelines or None

    unsupported: List[str] = []
    model_prompts: Dict[str, str] = {}
    model_families: Dict[str, str] = {}

    for mn in req.targetModelNames:
        p = prompt_for_model(mn)
        fam = prompt_family_for_model(mn)
        if not p or not fam:
            unsupported.append(mn)
        else:
            model_prompts[mn] = p
            model_families[mn] = fam

    if unsupported:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "requestId": request_id,
                "error": f"Note Type(s) sem suporte: {unsupported}.",
            },
        )

    t_all = time.monotonic()

    try:
        async with httpx.AsyncClient(timeout=90.0) as anki_client:
            # 1) cardsInfo (para cardId/deckName/noteId)
            t0 = time.monotonic()
            infos = await ankiconnect(anki_client, "cardsInfo", {"cards": req.cardIds})
            infos = list(infos or [])
            t_cardsinfo_ms = int((time.monotonic() - t0) * 1000)

            by_note: Dict[int, Dict[str, Any]] = {}
            invalid: List[Dict[str, Any]] = []

            for c in infos:
                nid = safe_int(c.get("noteId") or c.get("note"), default=None)
                cid = safe_int(c.get("cardId"), default=None)
                if nid is None:
                    invalid.append({"success": False, "stage": "anki_cardsInfo", "cardId": cid, "error": "noteId=None"})
                    continue
                if nid not in by_note:
                    by_note[nid] = c

            note_ids = list(by_note.keys())

            # 2) notesInfo (tags originais + fields brutos)
            t0 = time.monotonic()
            notes_info = await ankiconnect(anki_client, "notesInfo", {"notes": note_ids})
            notes_info = list(notes_info or [])
            t_notesinfo_ms = int((time.monotonic() - t0) * 1000)

            note_info_by_id: Dict[int, Dict[str, Any]] = {}
            for ni in notes_info:
                nid = safe_int(ni.get("noteId"), default=None)
                if nid is not None:
                    note_info_by_id[nid] = ni

            # 3) modelFieldNames (target)
            t0 = time.monotonic()
            model_fields: Dict[str, List[str]] = {}
            for mn in req.targetModelNames:
                f = await ankiconnect(anki_client, "modelFieldNames", {"modelName": mn})
                f = list(f or [])
                if not f:
                    return JSONResponse(
                        status_code=500,
                        content={"success": False, "requestId": request_id, "stage": "anki_modelFieldNames", "error": f"Sem campos para '{mn}'."},
                    )
                model_fields[mn] = [str(x) for x in f]
            t_model_fields_ms = int((time.monotonic() - t0) * 1000)

            # 4) geração e addNote
            results: List[Dict[str, Any]] = []
            created = 0
            failed = 0
            successful_note_ids: set[int] = set()

            for inv in invalid:
                results.append(inv)
                failed += 1

            async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT_S) as slm_client:
                for nid, c in by_note.items():
                    card_id = safe_int(c.get("cardId"), default=None)
                    deck_name = req.targetDeckName or c.get("deckName") or "Default"

                    ni = note_info_by_id.get(nid) or {}
                    origin_tags = ni.get("tags") or []
                    if isinstance(origin_tags, str):
                        origin_tags = [origin_tags]
                    if not isinstance(origin_tags, list):
                        origin_tags = []
                    origin_tags = [str(t) for t in origin_tags if str(t).strip()]

                    # tag extra opcional (se quiser manter esse feature)
                    extra_tag = (req.addTag or "").strip()
                    tags_for_new_note = origin_tags[:] + ([extra_tag] if extra_tag else [])

                    src_fields_map, src_ordered = _extract_notesinfo_fields(ni)

                    # fontes curtas pro SLM (sem HTML pesado)
                    src_main = src_ordered[0][2] if len(src_ordered) >= 1 else ""
                    src_second = src_ordered[1][2] if len(src_ordered) >= 2 else ""

                    src_main_txt = _html_to_text_preserve_cloze(src_main)
                    src_second_txt = _html_to_text_preserve_cloze(src_second)

                    for mn in req.targetModelNames:
                        t_fields = model_fields[mn]
                        fam = model_families[mn]
                        prompt_struct = model_prompts[mn]

                        # heurística: source principal para o tipo
                        if fam == "cloze":
                            source_payload = {"source_text": src_main_txt}
                            source_for_similarity = src_main_txt
                        elif fam == "basic":
                            source_payload = {"source_front": src_main_txt, "source_back": src_second_txt}
                            source_for_similarity = src_main_txt + "\n" + src_second_txt
                        else:
                            source_payload = {"source_text": src_main_txt}

                        # gerar N notas, 1 por vez (permite retry anti-cópia)
                        for gen_idx in range(req.countPerNote):
                            max_attempts = 3
                            attempt = 0
                            last_toon = None
                            last_error = None

                            while attempt < max_attempts:
                                attempt += 1

                                # Determina modelo baseado no provider
                                if llm_provider == "ollama":
                                    # Para Ollama, pode usar dificuldade para escolher modelo
                                    if use_difficulty and difficulty:
                                        actual_model = pick_ollama_model(difficulty)
                                    else:
                                        actual_model = llm_model
                                else:
                                    actual_model = llm_model

                                # aumenta temperatura em retries
                                temp = OLLAMA_TEMPERATURE if attempt == 1 else min(0.85, OLLAMA_TEMPERATURE + 0.25 * attempt)

                                retry_hint = ""
                                if attempt > 1:
                                    retry_hint = (
                                        "A resposta anterior ficou muito parecida com o original ou fora do nível. "
                                        "Reescreva com MAIS diferença, mudando estrutura e vocabulário."
                                    )

                                try:
                                    # Escolhe função de geração baseado no provider
                                    if llm_provider == "ollama":
                                        gen_fields, toon_path = await ollama_generate_notes(
                                            slm_client,
                                            request_id=request_id,
                                            ollama_model=actual_model,
                                            temperature=temp,
                                            source_note_id=nid,
                                            source_card_id=card_id,
                                            target_model_name=mn,
                                            target_fields=t_fields,
                                            family=fam,
                                            difficulty=difficulty,
                                            source_payload=source_payload,
                                            prompt_struct=prompt_struct,
                                            retry_hint=retry_hint,
                                        )
                                    else:
                                        # Usa multi-provider (OpenAI, Perplexity, Anthropic)
                                        gen_fields, toon_path = await generate_notes_multi_provider(
                                            request_id=request_id,
                                            provider=llm_provider,
                                            model=actual_model,
                                            temperature=temp,
                                            source_note_id=nid,
                                            source_card_id=card_id,
                                            target_model_name=mn,
                                            target_fields=t_fields,
                                            family=fam,
                                            difficulty=difficulty,
                                            source_payload=source_payload,
                                            prompt_struct=prompt_struct,
                                            retry_hint=retry_hint,
                                            custom_system=custom_system,
                                            custom_guidelines=custom_guidelines,
                                            openai_api_key=req.openaiApiKey,
                                            perplexity_api_key=req.perplexityApiKey,
                                            anthropic_api_key=req.anthropicApiKey,
                                        )
                                    last_toon = toon_path

                                    # montar fields completos
                                    full_fields = {fn: "" for fn in t_fields}
                                    for k, v in gen_fields.items():
                                        if k in full_fields:
                                            full_fields[k] = str(v)

                                    # sanitização (anti-HTML)
                                    if fam == "cloze":
                                        main_field = t_fields[0]
                                        v = full_fields.get(main_field, "")

                                        v = _html_to_text_preserve_cloze(v)
                                        v = _renumber_clozes_sequential(v)
                                        full_fields[main_field] = v

                                        # valida cloze
                                        if not _contains_cloze(v):
                                            last_error = f"Cloze inválido: nenhum {{cN::...}} no campo '{main_field}'."
                                            continue

                                        # valida quantidade por dificuldade (apenas se habilitado)
                                        if use_difficulty and difficulty:
                                            nclz = _count_cloze_occurrences(v)
                                            if difficulty == "easy" and nclz != 1:
                                                last_error = f"easy exige 1 cloze; veio {nclz}."
                                                continue
                                            if difficulty == "hard_neutral" and nclz < 3:
                                                last_error = f"hard_neutral exige >=3 clozes; veio {nclz}."
                                                continue
                                            if difficulty == "hard_technical" and nclz < 5:
                                                last_error = f"hard_technical exige >=5 clozes; veio {nclz}."
                                                continue

                                        # anti-cópia
                                        if _too_similar(source_for_similarity, v, threshold=0.90):
                                            last_error = "Gerado ficou muito parecido com o original (similaridade alta)."
                                            continue

                                    elif fam == "basic":
                                        front_field = t_fields[0]
                                        back_field = t_fields[1] if len(t_fields) > 1 else None

                                        front = _html_to_text_preserve_cloze(full_fields.get(front_field, ""))
                                        back = _html_to_text_preserve_cloze(full_fields.get(back_field, "") if back_field else "")
                                        full_fields[front_field] = front
                                        if back_field:
                                            full_fields[back_field] = back

                                        if _too_similar(source_for_similarity, front + "\n" + back, threshold=0.90):
                                            last_error = "Basic ficou muito parecido com o original."
                                            continue

                                    else:
                                        # allinone/outros: sanitiza campos textuais superficiais
                                        for fn in list(full_fields.keys())[:3]:
                                            full_fields[fn] = _html_to_text_preserve_cloze(full_fields.get(fn, ""))

                                        if _too_similar(source_for_similarity, " ".join(full_fields.values())[:400], threshold=0.92):
                                            last_error = "Gerado ficou muito parecido com o original."
                                            continue

                                    # pronto: cria nota com tags originais
                                    note_payload = {
                                        "deckName": deck_name,
                                        "modelName": mn,
                                        "fields": full_fields,
                                        "options": {"allowDuplicate": bool(req.allowDuplicate)},
                                        "tags": tags_for_new_note,
                                    }

                                    can_add, reason = await anki_can_add_note_detail(anki_client, note_payload)
                                    if not can_add:
                                        last_error = f"Anki recusou antes do addNote: {reason or 'unknown'}"
                                        break

                                    new_note_id = await ankiconnect(anki_client, "addNote", {"note": note_payload})
                                    created += 1
                                    successful_note_ids.add(nid)
                                    results.append({
                                        "success": True,
                                        "stage": "anki_addNote",
                                        "requestId": request_id,
                                        "oldNoteId": nid,
                                        "cardId": card_id,
                                        "newNoteId": new_note_id,
                                        "deckName": deck_name,
                                        "modelName": mn,
                                        "difficulty": difficulty,
                                        "ollamaModel": pick_ollama_model(difficulty),
                                        "toonPath": last_toon,
                                    })
                                    last_error = None
                                    break

                                except Exception as e:
                                    last_error = str(e)
                                    # tenta novamente (até max_attempts)
                                    continue

                            if last_error is not None:
                                failed += 1
                                results.append({
                                    "success": False,
                                    "stage": "recreate_retry_exhausted",
                                    "requestId": request_id,
                                    "oldNoteId": nid,
                                    "cardId": card_id,
                                    "modelName": mn,
                                    "difficulty": difficulty,
                                    "toonPath": last_toon,
                                    "error": last_error,
                                })

            # 5) suspender originais (só as que tiveram sucesso)
            suspended_cards = 0
            if req.suspendOriginal and successful_note_ids:
                try:
                    all_cards: List[int] = []
                    for nid2 in sorted(successful_note_ids):
                        ids = await ankiconnect(anki_client, "findCards", {"query": f"nid:{nid2}"})
                        for x in (ids or []):
                            cid2 = safe_int(x, default=None)
                            if cid2 is not None:
                                all_cards.append(cid2)

                    all_cards = sorted(set(all_cards))
                    if all_cards:
                        await ankiconnect(anki_client, "suspend", {"cards": all_cards})
                        suspended_cards = len(all_cards)
                except Exception as e:
                    failed += 1
                    results.append({"success": False, "stage": "anki_suspend", "error": str(e)})

            timings = {
                "cardsInfoMs": t_cardsinfo_ms,
                "notesInfoMs": t_notesinfo_ms,
                "modelFieldNamesMs": t_model_fields_ms,
                "totalMs": int((time.monotonic() - t_all) * 1000),
            }

            payload = {
                "requestId": request_id,
                "success": (created > 0 and failed == 0),
                "difficulty": difficulty,
                "totalRequestedCards": len(req.cardIds),
                "totalSelectedNotes": len(note_ids),
                "countPerNote": req.countPerNote,
                "targetModelNames": req.targetModelNames,
                "totalCreated": created,
                "totalFailed": failed,
                "totalSuspendedCards": suspended_cards,
                "timings": timings,
                "results": results,
            }

            if created == 0 and failed > 0:
                payload["success"] = False
                payload["error"] = "Falha ao recriar: nenhuma nota foi criada. Veja results para detalhes."
                return JSONResponse(status_code=500, content=payload)

            if created > 0 and failed > 0:
                payload["success"] = True
                payload["warning"] = "Sucesso parcial: algumas notas falharam (ou ficaram semelhantes demais). Veja results."
                return JSONResponse(status_code=207, content=payload)

            return JSONResponse(status_code=200, content=payload)

    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "requestId": request_id, "error": str(e)})

class AnkiNoteSuspendRequest(BaseModel):
    noteId: int
    suspend: bool = True

@router.post("/anki-note-suspend")
async def anki_note_suspend(req: AnkiNoteSuspendRequest):
    """
    Suspende/desuspende TODOS os cards de uma nota (noteId).
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            note_id = int(req.noteId)
            card_ids = await ankiconnect(client, "findCards", {"query": f"nid:{note_id}"})
            card_ids = list(card_ids or [])
            if not card_ids:
                return {"success": True, "noteId": note_id, "totalCards": 0, "action": "noop"}

            action = "suspend" if req.suspend else "unsuspend"
            await ankiconnect(client, action, {"cards": card_ids})
            return {"success": True, "noteId": note_id, "totalCards": len(card_ids), "action": action}
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


@router.get("/anki-note-info")
async def anki_note_info(noteId: int = Query(..., ge=1)):
    """
    Retorna notesInfo (fields ordenados + tags) para edição.
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            note_id = int(noteId)
            info = await ankiconnect(client, "notesInfo", {"notes": [note_id]})
            info = list(info or [])
            if not info:
                return JSONResponse(status_code=404, content={"success": False, "error": f"noteId {note_id} não encontrado."})

            ni = info[0]
            fields_map, ordered = _extract_notesinfo_fields(ni)

            fields_ordered = [{"order": int(o), "name": str(n), "value": str(v)} for (o, n, v) in ordered]
            tags = ni.get("tags") or []
            if isinstance(tags, str):
                tags = [tags]
            if not isinstance(tags, list):
                tags = []
            tags = [str(t) for t in tags if str(t).strip()]

            out = {
                "noteId": note_id,
                "modelName": str(ni.get("modelName") or ""),
                "tags": tags,
                "fields": {str(k): str(v) for k, v in fields_map.items()},
                "fieldsOrdered": fields_ordered,
            }
            return {"success": True, "note": out}
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})

class AnkiNoteUpdateRequest(BaseModel):
    noteId: int
    fields: Dict[str, str] = Field(default_factory=dict)
    tags: Optional[List[str]] = None


@router.post("/anki-note-update")
async def anki_note_update(req: AnkiNoteUpdateRequest):
    """
    Atualiza fields e/ou tags da nota.
    - fields: via updateNoteFields
    - tags: via addTags/removeTags (calcula diff)
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            note_id = int(req.noteId)
            fields = {str(k): str(v) for k, v in (req.fields or {}).items()}
            updated_fields = 0
            updated_tags = False

            # Update fields if provided
            if fields:
                payload = {"note": {"id": note_id, "fields": fields}}
                await ankiconnect(client, "updateNoteFields", payload)
                updated_fields = len(fields)

            # Update tags if provided (not None)
            if req.tags is not None:
                # Get current tags from note
                info = await ankiconnect(client, "notesInfo", {"notes": [note_id]})
                current_tags = set(info[0].get("tags", []) if info else [])
                new_tags = set(str(t).strip() for t in req.tags if str(t).strip())

                # Calculate diff
                tags_to_add = list(new_tags - current_tags)
                tags_to_remove = list(current_tags - new_tags)

                # Add new tags
                if tags_to_add:
                    await ankiconnect(client, "addTags", {
                        "notes": [note_id],
                        "tags": " ".join(tags_to_add)
                    })

                # Remove old tags
                if tags_to_remove:
                    await ankiconnect(client, "removeTags", {
                        "notes": [note_id],
                        "tags": " ".join(tags_to_remove)
                    })

                updated_tags = True

            if not fields and req.tags is None:
                return JSONResponse(status_code=400, content={"success": False, "error": "Nenhum campo ou tag para atualizar."})

            return {"success": True, "noteId": note_id, "updatedFields": updated_fields, "updatedTags": updated_tags}
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


class AnkiMigrateFieldsRequest(BaseModel):
    cardIds: List[int] = Field(default_factory=list)
    sourceField: str
    targetField: str

@router.post("/anki-migrate-fields")
async def anki_migrate_fields(req: AnkiMigrateFieldsRequest):
    """
    Migra conteúdo de um campo para outro em múltiplas notas.
    Copia o valor do sourceField para o targetField em todas as notas dos cards selecionados.
    """
    request_id = str(uuid.uuid4())[:8]
    started = time.time()

    if not req.cardIds:
        return JSONResponse(status_code=400, content={
            "success": False,
            "requestId": request_id,
            "error": "Nenhum card selecionado."
        })

    if not req.sourceField or not req.targetField:
        return JSONResponse(status_code=400, content={
            "success": False,
            "requestId": request_id,
            "error": "Campos origem e destino são obrigatórios."
        })

    if req.sourceField == req.targetField:
        return JSONResponse(status_code=400, content={
            "success": False,
            "requestId": request_id,
            "error": "Campos origem e destino devem ser diferentes."
        })

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            # 1. Buscar info dos cards para obter noteIds únicos
            cards_info = await ankiconnect(client, "cardsInfo", {"cards": req.cardIds})
            cards_info = list(cards_info or [])

            if not cards_info:
                return JSONResponse(status_code=404, content={
                    "success": False,
                    "requestId": request_id,
                    "error": "Nenhum card encontrado."
                })

            # Extrair noteIds únicos
            note_ids = list(set(c.get("note") for c in cards_info if c.get("note")))

            if not note_ids:
                return JSONResponse(status_code=404, content={
                    "success": False,
                    "requestId": request_id,
                    "error": "Nenhum noteId encontrado nos cards."
                })

            # 2. Buscar info das notas
            notes_info = await ankiconnect(client, "notesInfo", {"notes": note_ids})
            notes_info = list(notes_info or [])

            # 3. Processar cada nota
            updated = 0
            skipped = 0
            failed = 0
            errors = []

            for ni in notes_info:
                note_id = ni.get("noteId")
                fields_raw = ni.get("fields") or {}

                # Verificar se os campos existem
                if req.sourceField not in fields_raw:
                    skipped += 1
                    continue

                if req.targetField not in fields_raw:
                    skipped += 1
                    continue

                # Extrair valor do campo origem
                source_val = fields_raw.get(req.sourceField)
                if isinstance(source_val, dict):
                    source_val = source_val.get("value", "")
                source_val = str(source_val or "")

                # Se origem está vazia, pular
                if not source_val.strip():
                    skipped += 1
                    continue

                # Extrair valor atual do campo destino
                target_val = fields_raw.get(req.targetField)
                if isinstance(target_val, dict):
                    target_val = target_val.get("value", "")
                target_val = str(target_val or "")

                # Concatenar: adicionar conteúdo origem abaixo do destino
                if target_val.strip():
                    # Se destino já tem conteúdo, adiciona quebra de linha e o conteúdo origem
                    new_value = f"{target_val}<br><br>{source_val}"
                else:
                    # Se destino está vazio, apenas usa o conteúdo origem
                    new_value = source_val

                # Atualizar nota
                try:
                    payload = {
                        "note": {
                            "id": note_id,
                            "fields": {req.targetField: new_value}
                        }
                    }
                    await ankiconnect(client, "updateNoteFields", payload)
                    updated += 1
                except Exception as e:
                    failed += 1
                    errors.append(f"noteId={note_id}: {str(e)[:100]}")

            elapsed = round((time.time() - started) * 1000)

            return {
                "success": True,
                "requestId": request_id,
                "totalCards": len(req.cardIds),
                "totalNotes": len(note_ids),
                "updated": updated,
                "skipped": skipped,
                "failed": failed,
                "errors": errors[:5] if errors else [],
                "sourceField": req.sourceField,
                "targetField": req.targetField,
                "elapsedMs": elapsed
            }

    except Exception as e:
        return JSONResponse(status_code=500, content={
            "success": False,
            "requestId": request_id,
            "error": str(e)
        })


# =============================================================================
# Translate via SLM/Ollama (traduz cards in-place preservando estrutura)
# =============================================================================

OLLAMA_TRANSLATE_SCHEMA = {
    "type": "object",
    "properties": {
        "translations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "field_id": {"type": "string"},
                    "translated_text": {"type": "string"},
                },
                "required": ["field_id", "translated_text"],
            },
        }
    },
    "required": ["translations"]
}

PROMPT_TRANSLATE = """\
Você é um tradutor profissional especializado em material educacional.

OBJETIVO:
Traduzir o conteúdo dos campos de flashcards do Anki para o idioma de destino.

REGRAS OBRIGATÓRIAS:
1) Responda APENAS com JSON válido no schema solicitado.
2) PRESERVE EXATAMENTE as marcações de cloze no formato {{c1::texto::hint}} ou {{c1::texto}}.
   - Traduza APENAS o texto dentro do cloze, mantendo a estrutura {{cN::...}}.
   - Exemplo: "{{c1::dog}}" → "{{c1::cachorro}}"
3) PRESERVE tags HTML como <b>, <i>, <br>, <div>, <span>, etc.
4) PRESERVE referências de mídia:
   - Áudio: [sound:arquivo.mp3]
   - Imagens: <img src="...">
5) Mantenha termos técnicos em inglês quando não houver tradução consagrada.
6) Mantenha siglas e acrônimos originais (ex: AWS, API, HTTP).
7) Use português brasileiro natural e fluente.
8) Cada item possui um field_id imutável. NUNCA troque conteúdo entre field_ids.
9) Retorne exatamente um item para cada field_id recebido, sem criar ou omitir itens.

EXEMPLOS DE TRADUÇÃO:

Original: "The {{c1::heart}} pumps {{c2::blood}} through the body."
Traduzido: "O {{c1::coração}} bombeia {{c2::sangue}} pelo corpo."

Original: "<b>API</b> stands for Application Programming Interface"
Traduzido: "<b>API</b> significa Application Programming Interface (Interface de Programação de Aplicações)"

Original: "[sound:audio.mp3]<br>What is the capital of France?"
Traduzido: "[sound:audio.mp3]<br>Qual é a capital da França?"

SAÍDA:
{ "translations": [
  { "field_id": "field_0", "translated_text": "valor traduzido" },
  { "field_id": "field_1", "translated_text": "outro valor traduzido" }
] }
"""


class AnkiTranslateRequest(BaseModel):
    cardIds: List[int] = Field(default_factory=list)
    deckName: Optional[str] = None  # Se omitido, usa cardIds; se definido, traduz todo deck
    targetLanguage: str = "pt-br"
    model: Optional[str] = None  # Modelo para tradução (ex: gpt-4o, sonar, qwen-flashcard)
    noteType: Optional[str] = None  # Se definido, traduz apenas notas deste tipo
    fieldNames: List[str] = Field(default_factory=list)  # Vazio = detecção automática
    maxConcurrency: int = Field(
        default=TRANSLATION_DEFAULT_CONCURRENCY,
        ge=1,
        le=10,
    )
    translationContext: Optional[str] = Field(default=None, max_length=6000)
    # API Keys para providers externos
    openaiApiKey: Optional[str] = None
    perplexityApiKey: Optional[str] = None
    anthropicApiKey: Optional[str] = None


class AnkiTranslationAnalysisRequest(BaseModel):
    cardIds: List[int] = Field(default_factory=list)
    deckName: Optional[str] = None


def _translation_text_only(value: Any) -> str:
    """Remove apenas estrutura não textual para classificar um campo."""
    text = str(value or "")
    text = re.sub(r'\[sound:[^\]]+\]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'<img\b[^>]*>', '', text, flags=re.IGNORECASE)
    text = TAG_PAT.sub('', text)
    text = _html.unescape(text).replace('\xa0', ' ')
    return re.sub(r'\s+', ' ', text).strip()


def _is_numeric_only_translation_field(value: Any) -> bool:
    """True para campos cujo conteúdo útil é composto somente por números/sinais."""
    text = _translation_text_only(value)
    if not text or not re.search(r'\d', text):
        return False
    return re.fullmatch(r'[\d\s.,;:+\-/%()]+', text) is not None


def _automatic_translation_field(value: Any) -> bool:
    text = _translation_text_only(value)
    return bool(text) and not _is_numeric_only_translation_field(value)


def _translation_items(fields: Dict[str, str]) -> Tuple[List[Dict[str, str]], Dict[str, str]]:
    """Cria IDs opacos para impedir que o LLM renomeie ou realoque campos."""
    items: List[Dict[str, str]] = []
    field_id_to_name: Dict[str, str] = {}
    for index, (field_name, content) in enumerate(fields.items()):
        field_id = f"field_{index}"
        field_id_to_name[field_id] = field_name
        items.append({"field_id": field_id, "content": content})
    return items, field_id_to_name


def _parse_translation_response(parsed: Any, field_id_to_name: Dict[str, str]) -> Dict[str, str]:
    if not isinstance(parsed, dict) or not isinstance(parsed.get("translations"), list):
        raise ValueError("Resposta não contém translations válido")

    expected_ids = set(field_id_to_name)
    seen_ids: set[str] = set()
    translated: Dict[str, str] = {}
    for item in parsed["translations"]:
        if not isinstance(item, dict):
            raise ValueError("Item de tradução inválido")
        field_id = str(item.get("field_id") or "")
        if field_id not in expected_ids:
            raise ValueError(f"field_id inesperado: {field_id or '(vazio)'}")
        if field_id in seen_ids:
            raise ValueError(f"field_id duplicado: {field_id}")
        if "translated_text" not in item:
            raise ValueError(f"Tradução ausente para {field_id}")
        seen_ids.add(field_id)
        translated[field_id_to_name[field_id]] = str(item["translated_text"])

    missing_ids = expected_ids - seen_ids
    if missing_ids:
        raise ValueError(f"Campos ausentes na tradução: {', '.join(sorted(missing_ids))}")
    return translated


async def _resolve_translation_card_ids(
    client: httpx.AsyncClient,
    card_ids: List[int],
    deck_name: Optional[str],
) -> List[int]:
    resolved = list(card_ids or [])
    if not resolved and deck_name:
        deck_cards = await ankiconnect(
            client, "findCards", {"query": f'deck:"{deck_name}"'}
        )
        resolved = list(deck_cards or [])
    return resolved


@router.post("/anki-translation-analysis")
async def analyze_translation_fields(req: AnkiTranslationAnalysisRequest):
    """Agrupa campos por tipo de nota e recomenda somente os que contêm texto."""
    request_id = uuid.uuid4().hex[:12]
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            card_ids = await _resolve_translation_card_ids(
                client, req.cardIds, req.deckName
            )
            if not card_ids:
                return {
                    "success": True,
                    "requestId": request_id,
                    "totalCards": 0,
                    "totalNotes": 0,
                    "noteTypes": [],
                }

            infos = list(await ankiconnect(client, "cardsInfo", {"cards": card_ids}) or [])
            note_cards: Dict[int, Dict[str, Any]] = {}
            for card in infos:
                note_id = safe_int(card.get("noteId") or card.get("note"), default=None)
                if note_id is not None and note_id not in note_cards:
                    note_cards[note_id] = card

            note_ids = list(note_cards)
            notes = list(await ankiconnect(client, "notesInfo", {"notes": note_ids}) or [])
            grouped: Dict[str, Dict[str, Any]] = {}

            for note in notes:
                note_id = safe_int(note.get("noteId"), default=None)
                card = note_cards.get(note_id or -1, {})
                model_name = str(note.get("modelName") or card.get("modelName") or "Desconhecido")
                group = grouped.setdefault(model_name, {"noteCount": 0, "fields": {}})
                group["noteCount"] += 1

                _, ordered = _extract_notesinfo_fields(note)
                for order, field_name, value in ordered:
                    stats = group["fields"].setdefault(field_name, {
                        "name": field_name,
                        "order": order,
                        "nonEmptyCount": 0,
                        "numericOnlyCount": 0,
                        "textCount": 0,
                    })
                    text_only = _translation_text_only(value)
                    if text_only:
                        stats["nonEmptyCount"] += 1
                        if _is_numeric_only_translation_field(value):
                            stats["numericOnlyCount"] += 1
                        else:
                            stats["textCount"] += 1

            note_types: List[Dict[str, Any]] = []
            for model_name, group in grouped.items():
                fields = []
                for stats in group["fields"].values():
                    numeric_only = (
                        stats["nonEmptyCount"] > 0
                        and stats["numericOnlyCount"] == stats["nonEmptyCount"]
                    )
                    fields.append({
                        **stats,
                        "numericOnly": numeric_only,
                        "recommended": stats["textCount"] > 0 and not numeric_only,
                    })
                fields.sort(key=lambda item: (item["order"], item["name"]))
                note_types.append({
                    "name": model_name,
                    "noteCount": group["noteCount"],
                    "fields": fields,
                })

            note_types.sort(key=lambda item: (-item["noteCount"], item["name"].lower()))
            return {
                "success": True,
                "requestId": request_id,
                "totalCards": len(card_ids),
                "totalNotes": len(notes),
                "noteTypes": note_types,
            }
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={"success": False, "requestId": request_id, "error": str(exc)},
        )


def _detect_provider(
    model: str,
    openai_key: Optional[str] = None,
    perplexity_key: Optional[str] = None,
    anthropic_key: Optional[str] = None,
) -> str:
    """Detecta o provider baseado no nome do modelo e chaves disponíveis."""
    if not model:
        return "ollama"

    name_lower = model.lower()

    # OpenAI: gpt-*, o1-*, chatgpt-*
    if openai_key and ("gpt" in name_lower or model.startswith("o1-") or "chatgpt" in name_lower):
        return "openai"

    # Anthropic: claude-*
    if anthropic_key and "claude" in name_lower:
        return "anthropic"

    # Perplexity: sonar*
    if perplexity_key and "sonar" in name_lower:
        return "perplexity"

    return "ollama"


class TranslateProviderError(Exception):
    """Erro HTTP de provedor com metadados necessários para retry seguro."""

    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        error_code: Optional[str] = None,
        retry_after: Optional[float] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.retry_after = retry_after
        self.debug_path: Optional[str] = None

    @property
    def retryable(self) -> bool:
        if self.error_code == "insufficient_quota":
            return False
        return self.status_code in {408, 429} or bool(
            self.status_code and self.status_code >= 500
        )


def _response_error_code(response: httpx.Response) -> Optional[str]:
    try:
        payload = response.json()
    except Exception:
        return None
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict):
        return str(error.get("code") or error.get("type") or "") or None
    return None


def _response_retry_after(response: httpx.Response) -> Optional[float]:
    raw = (response.headers.get("Retry-After") or "").strip()
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(raw)
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            return max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None


def _raise_translate_http_error(provider: str, response: httpx.Response) -> None:
    if 200 <= response.status_code < 300:
        return
    code = _response_error_code(response)
    raise TranslateProviderError(
        f"{provider} HTTP {response.status_code}: {response.text[:300]}",
        status_code=response.status_code,
        error_code=code,
        retry_after=_response_retry_after(response),
    )


async def _translate_with_provider(
    *,
    client: httpx.AsyncClient,
    provider: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    request_id: str,
    source_note_id: int,
    openai_key: Optional[str] = None,
    perplexity_key: Optional[str] = None,
    anthropic_key: Optional[str] = None,
) -> Tuple[str, str]:
    """
    Executa tradução usando o provider especificado.
    Retorna: (conteúdo_resposta, caminho_debug_file)
    """
    t0 = time.monotonic()
    dbg: dict = {
        "kind": "translate_provider",
        "ts": _now_iso(),
        "requestId": request_id,
        "provider": provider,
        "model": model,
        "temperature": temperature,
        "sourceNoteId": source_note_id,
    }

    try:
        if provider == "openai" and openai_key:
            content = await _call_openai_translate(
                client=client,
                api_key=openai_key,
                model=model,
                system=system_prompt,
                user=user_prompt,
                temperature=temperature,
            )
        elif provider == "anthropic" and anthropic_key:
            content = await _call_anthropic_translate(
                client=client,
                api_key=anthropic_key,
                model=model,
                system=system_prompt,
                user=user_prompt,
                temperature=temperature,
            )
        elif provider == "perplexity" and perplexity_key:
            content = await _call_perplexity_translate(
                client=client,
                api_key=perplexity_key,
                model=model,
                system=system_prompt,
                user=user_prompt,
                temperature=temperature,
            )
        else:
            # Fallback: Ollama
            content = await _call_ollama_translate(
                client=client,
                model=model,
                system=system_prompt,
                user=user_prompt,
                temperature=temperature,
            )

        dbg["elapsedMs"] = int((time.monotonic() - t0) * 1000)
        dbg["contentPreview"] = (content or "")[:500]
        path = _write_toon_file(f"translate_{provider}_ok_nid{source_note_id}", request_id, dbg)
        return content, path

    except TranslateProviderError as e:
        dbg["error"] = str(e)
        dbg["elapsedMs"] = int((time.monotonic() - t0) * 1000)
        path = _write_toon_file(f"translate_{provider}_error_nid{source_note_id}", request_id, dbg)
        e.debug_path = path
        raise
    except (httpx.TimeoutException, httpx.TransportError) as e:
        dbg["error"] = str(e)
        dbg["elapsedMs"] = int((time.monotonic() - t0) * 1000)
        path = _write_toon_file(f"translate_{provider}_error_nid{source_note_id}", request_id, dbg)
        setattr(e, "debug_path", path)
        raise
    except Exception as e:
        dbg["error"] = str(e)
        dbg["elapsedMs"] = int((time.monotonic() - t0) * 1000)
        path = _write_toon_file(f"translate_{provider}_error_nid{source_note_id}", request_id, dbg)
        raise Exception(f"[{provider}] {e}. (Veja: {path})")


async def _call_openai_translate(
    client: httpx.AsyncClient,
    api_key: str,
    model: str,
    system: str,
    user: str,
    temperature: float,
) -> str:
    """Chama OpenAI API para tradução (não-streaming)."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    # Reasoning models (o1, o3, gpt-5) não suportam temperature
    if model.startswith(("o1-", "o1", "o3-", "o3", "gpt-5")):
        payload = {
            "model": model,
            "messages": messages,
            "max_completion_tokens": 4096
        }
    else:
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_completion_tokens": 4096
        }

    r = await client.post(
        "https://api.openai.com/v1/chat/completions",
        headers=headers,
        json=payload,
        timeout=120.0,
    )
    _raise_translate_http_error("OpenAI", r)
    data = r.json()
    return data.get("choices", [{}])[0].get("message", {}).get("content", "")


async def _call_anthropic_translate(
    client: httpx.AsyncClient,
    api_key: str,
    model: str,
    system: str,
    user: str,
    temperature: float,
) -> str:
    """Chama Anthropic API para tradução (não-streaming)."""
    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01"
    }

    payload = {
        "model": model,
        "max_tokens": 4096,
        "temperature": temperature,
        "system": system,
        "messages": [
            {"role": "user", "content": user}
        ]
    }

    r = await client.post(
        "https://api.anthropic.com/v1/messages",
        headers=headers,
        json=payload,
        timeout=120.0,
    )
    _raise_translate_http_error("Anthropic", r)
    data = r.json()
    content_blocks = data.get("content", [])
    if content_blocks and isinstance(content_blocks, list):
        return content_blocks[0].get("text", "")
    return ""


async def _call_perplexity_translate(
    client: httpx.AsyncClient,
    api_key: str,
    model: str,
    system: str,
    user: str,
    temperature: float,
) -> str:
    """Chama Perplexity API para tradução (não-streaming)."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": 4096
    }

    r = await client.post(
        "https://api.perplexity.ai/chat/completions",
        headers=headers,
        json=payload,
        timeout=120.0,
    )
    _raise_translate_http_error("Perplexity", r)
    data = r.json()
    return data.get("choices", [{}])[0].get("message", {}).get("content", "")


async def _call_ollama_translate(
    client: httpx.AsyncClient,
    model: str,
    system: str,
    user: str,
    temperature: float,
) -> str:
    """Chama Ollama API para tradução (não-streaming)."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "format": OLLAMA_TRANSLATE_SCHEMA,
        "options": {"temperature": temperature},
    }

    r = await client.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=OLLAMA_TIMEOUT_S)
    _raise_translate_http_error("Ollama", r)
    data = r.json()
    msg = data.get("message") or {}
    return msg.get("content") or ""


async def ollama_translate_fields(
    client: httpx.AsyncClient,
    *,
    request_id: str,
    ollama_model: str,
    temperature: float,
    source_note_id: int,
    source_card_id: Optional[int],
    source_fields: Dict[str, str],
    target_language: str,
    retry_hint: Optional[str] = None,
) -> Tuple[Dict[str, str], str]:
    """
    Traduz os campos de uma nota usando Ollama.
    Retorna: (campos_traduzidos, caminho_do_arquivo_toon)
    """
    system = (
        "Você é um tradutor profissional. SEMPRE responda somente com JSON válido, "
        "seguindo exatamente o schema solicitado. Não escreva nada fora do JSON."
    )

    language_names = {
        "pt-br": "português brasileiro",
        "pt": "português",
        "es": "espanhol",
        "en": "inglês",
        "fr": "francês",
        "de": "alemão",
        "it": "italiano",
    }
    target_lang_name = language_names.get(target_language.lower(), target_language)

    source_items, field_id_to_name = _translation_items(source_fields)
    user = {
        "task": "translate_anki_note_fields",
        "source_fields": source_items,
        "target_language": target_lang_name,
        "retry_hint": retry_hint or "",
        "instructions": PROMPT_TRANSLATE,
    }

    payload = {
        "model": ollama_model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
        ],
        "stream": False,
        "format": OLLAMA_TRANSLATE_SCHEMA,
        "options": {"temperature": float(temperature)},
    }

    t0 = time.monotonic()
    dbg: dict = {
        "kind": "ollama_translation",
        "ts": _now_iso(),
        "requestId": request_id,
        "ollamaUrl": OLLAMA_URL,
        "ollamaModel": ollama_model,
        "temperature": temperature,
        "timeoutS": OLLAMA_TIMEOUT_S,
        "sourceNoteId": source_note_id,
        "sourceCardId": source_card_id,
        "targetLanguage": target_language,
        "sourceFieldsPreview": {k: v[:200] for k, v in list(source_fields.items())[:4]},
        "retryHint": retry_hint or "",
        "requestPayload": payload,
    }

    try:
        r = await client.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=OLLAMA_TIMEOUT_S)
        r.raise_for_status()
        data = r.json()
        dbg["httpStatus"] = r.status_code
        dbg["rawResponse"] = data
    except httpx.TimeoutException as e:
        dbg["error"] = f"Ollama timeout após {OLLAMA_TIMEOUT_S}s: {e}"
        dbg["elapsedMs"] = int((time.monotonic() - t0) * 1000)
        path = _write_toon_file(f"translate_timeout_nid{source_note_id}", request_id, dbg)
        raise Exception(f"Ollama timeout após {OLLAMA_TIMEOUT_S}s. (Veja: {path})")
    except Exception as e:
        dbg["error"] = f"Ollama HTTP/parse falhou: {e}"
        dbg["elapsedMs"] = int((time.monotonic() - t0) * 1000)
        path = _write_toon_file(f"translate_error_nid{source_note_id}", request_id, dbg)
        raise Exception(f"Ollama indisponível ou erro HTTP. (Veja: {path})")

    content = ""
    if isinstance(data, dict):
        msg = data.get("message") or {}
        content = msg.get("content") or ""

    dbg["messageContentHead"] = (content or "")[:5000]
    parsed = _try_extract_json(content)
    dbg["parsed"] = parsed

    if not parsed or "translations" not in parsed:
        dbg["error"] = "SLM/Ollama retornou conteúdo não-JSON ou fora do schema esperado."
        dbg["elapsedMs"] = int((time.monotonic() - t0) * 1000)
        path = _write_toon_file(f"translate_badjson_nid{source_note_id}", request_id, dbg)
        raise Exception(f"SLM/Ollama retornou JSON inválido/fora do schema. (Veja: {path})")

    try:
        out = _parse_translation_response(parsed, field_id_to_name)
    except ValueError as exc:
        dbg["error"] = str(exc)
        dbg["elapsedMs"] = int((time.monotonic() - t0) * 1000)
        path = _write_toon_file(f"translate_badfields_nid{source_note_id}", request_id, dbg)
        raise Exception(f"SLM/Ollama retornou campos inválidos. (Veja: {path})")

    dbg["elapsedMs"] = int((time.monotonic() - t0) * 1000)
    dbg["translatedPreview"] = {k: (out.get(k, "")[:200]) for k in list(out.keys())[:4]}
    path = _write_toon_file(f"translate_ok_nid{source_note_id}", request_id, dbg)
    return out, path


@router.post("/anki-translate")
async def translate_cards(req: AnkiTranslateRequest):
    """Traduz notas concorrentemente e serializa as gravações no Anki."""
    request_id = uuid.uuid4().hex[:12]
    card_ids = list(req.cardIds or [])
    if not card_ids and req.deckName:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                card_ids = list(await _resolve_translation_card_ids(client, [], req.deckName))
        except Exception as exc:
            async def deck_error():
                data = {"success": False, "requestId": request_id, "error": f"Erro ao buscar deck: {exc}"}
                yield f"event: error\ndata: {json.dumps(data)}\n\n"
            return StreamingResponse(deck_error(), media_type="text/event-stream")

    target_language = (req.targetLanguage or "pt-br").strip().lower()
    language_names = {
        "pt-br": "português brasileiro", "pt": "português", "es": "espanhol",
        "en": "inglês", "fr": "francês", "de": "alemão", "it": "italiano",
    }
    target_lang_name = language_names.get(target_language, target_language)
    model = req.model or OLLAMA_MODEL_NEUTRAL
    provider = _detect_provider(
        model,
        openai_key=req.openaiApiKey,
        perplexity_key=req.perplexityApiKey,
        anthropic_key=req.anthropicApiKey,
    )
    requested_concurrency = max(1, min(10, int(req.maxConcurrency)))
    effective_concurrency = min(
        requested_concurrency,
        max(1, min(10, int(TRANSLATION_MAX_CONCURRENCY))),
    )
    if provider == "ollama":
        effective_concurrency = min(
            effective_concurrency,
            max(1, int(TRANSLATION_OLLAMA_MAX_CONCURRENCY)),
        )

    async def generate():
        started_all = time.monotonic()
        tasks: List[asyncio.Task] = []
        if not card_ids:
            empty = {
                "success": True, "requestId": request_id, "totalCards": 0,
                "totalNotes": 0, "translated": 0, "failed": 0,
                "requestedConcurrency": requested_concurrency,
                "effectiveConcurrency": effective_concurrency, "results": [],
            }
            yield f"event: result\ndata: {json.dumps(empty)}\n\n"
            return

        try:
            limits = httpx.Limits(
                max_connections=effective_concurrency,
                max_keepalive_connections=effective_concurrency,
            )
            async with (
                httpx.AsyncClient(timeout=90.0) as anki_client,
                httpx.AsyncClient(timeout=120.0, limits=limits) as provider_client,
            ):
                t0 = time.monotonic()
                infos = list(await ankiconnect(anki_client, "cardsInfo", {"cards": card_ids}) or [])
                cards_info_ms = int((time.monotonic() - t0) * 1000)
                by_note: Dict[int, Dict[str, Any]] = {}
                invalid: List[Dict[str, Any]] = []
                for source_index, card in enumerate(infos):
                    note_id = safe_int(card.get("noteId") or card.get("note"), default=None)
                    card_id = safe_int(card.get("cardId"), default=None)
                    if note_id is None:
                        invalid.append({
                            "success": False, "stage": "anki_cardsInfo", "cardId": card_id,
                            "sourceIndex": source_index, "error": "noteId=None",
                        })
                    elif note_id not in by_note:
                        by_note[note_id] = {"card": card, "sourceIndex": source_index}

                t0 = time.monotonic()
                note_ids = list(by_note)
                notes_info = list(await ankiconnect(anki_client, "notesInfo", {"notes": note_ids}) or [])
                notes_info_ms = int((time.monotonic() - t0) * 1000)
                notes_by_id = {
                    note_id: note
                    for note in notes_info
                    if (note_id := safe_int(note.get("noteId"), default=None)) is not None
                }
                selected_note_type = (req.noteType or "").strip()
                if selected_note_type:
                    by_note = {
                        note_id: item for note_id, item in by_note.items()
                        if str(
                            (notes_by_id.get(note_id) or {}).get("modelName")
                            or item["card"].get("modelName") or ""
                        ) == selected_note_type
                    }

                total_notes = len(by_note)
                start_event = {
                    "requestId": request_id, "totalCards": len(card_ids),
                    "totalNotes": total_notes, "provider": provider, "model": model,
                    "noteType": selected_note_type or None,
                    "requestedConcurrency": requested_concurrency,
                    "effectiveConcurrency": effective_concurrency,
                    "completed": 0, "inFlight": 0,
                }
                yield f"event: start\ndata: {json.dumps(start_event)}\n\n"

                semaphore = asyncio.Semaphore(effective_concurrency)
                active = {"count": 0}

                async def translate_note(note_id: int, item: Dict[str, Any]) -> Dict[str, Any]:
                    note_started = time.monotonic()
                    card = item["card"]
                    source_index = item["sourceIndex"]
                    card_id = safe_int(card.get("cardId"), default=None)
                    note = notes_by_id.get(note_id) or {}
                    source_fields, ordered_fields = _extract_notesinfo_fields(note)
                    requested_fields = set(req.fieldNames or [])
                    selected_fields: Dict[str, str] = {}
                    for _, field_name, field_value in ordered_fields:
                        if requested_fields and field_name not in requested_fields:
                            continue
                        if not _translation_text_only(field_value):
                            continue
                        if not requested_fields and not _automatic_translation_field(field_value):
                            continue
                        selected_fields[field_name] = field_value

                    base_result = {
                        "requestId": request_id, "noteId": note_id, "cardId": card_id,
                        "sourceIndex": source_index, "targetLanguage": target_language,
                        "provider": provider, "model": model,
                    }
                    if not selected_fields:
                        return {
                            **base_result, "success": True, "stage": "skip_empty",
                            "retries": 0, "rateLimits": 0,
                            "durationMs": int((time.monotonic() - note_started) * 1000),
                            "message": "Nenhum campo com texto para traduzir",
                        }

                    source_items, field_id_map = _translation_items(selected_fields)
                    system_prompt = (
                        "Você é um tradutor profissional. SEMPRE responda somente com JSON válido, "
                        "seguindo exatamente o schema solicitado. Use o contexto de tradução para "
                        "resolver terminologia e ambiguidades, mas não o traduza nem o inclua na saída. "
                        "Não escreva nada fora do JSON."
                    )
                    retries = 0
                    rate_limits = 0
                    last_toon = None
                    async with semaphore:
                        active["count"] += 1
                        try:
                            for attempt in range(1, 4):
                                prompt = json.dumps({
                                    "task": "translate_anki_note_fields",
                                    "note_type": str(note.get("modelName") or card.get("modelName") or ""),
                                    "source_fields": source_items,
                                    "target_language": target_lang_name,
                                    "translation_context": (req.translationContext or "").strip(),
                                    "retry_hint": "Tente novamente após uma falha transitória." if attempt > 1 else "",
                                    "instructions": PROMPT_TRANSLATE,
                                }, ensure_ascii=False)
                                try:
                                    content, last_toon = await _translate_with_provider(
                                        client=provider_client, provider=provider, model=model,
                                        system_prompt=system_prompt, user_prompt=prompt,
                                        temperature=0.3, request_id=request_id,
                                        source_note_id=note_id, openai_key=req.openaiApiKey,
                                        perplexity_key=req.perplexityApiKey,
                                        anthropic_key=req.anthropicApiKey,
                                    )
                                    translations = _parse_translation_response(
                                        _try_extract_json(content), field_id_map
                                    )
                                    final_fields = dict(source_fields)
                                    for field_name, translated_value in translations.items():
                                        if field_name in selected_fields and str(translated_value).strip():
                                            final_fields[field_name] = str(translated_value)
                                    return {
                                        **base_result, "success": True, "stage": "translation_ready",
                                        "fieldsTranslated": len(translations),
                                        "fieldNames": list(translations),
                                        "noteType": str(note.get("modelName") or card.get("modelName") or ""),
                                        "toonPath": last_toon, "retries": retries,
                                        "rateLimits": rate_limits,
                                        "durationMs": int((time.monotonic() - note_started) * 1000),
                                        "_finalFields": final_fields,
                                    }
                                except asyncio.CancelledError:
                                    raise
                                except Exception as exc:
                                    last_toon = getattr(exc, "debug_path", last_toon)
                                    if isinstance(exc, TranslateProviderError) and exc.status_code == 429:
                                        rate_limits += 1
                                    retryable = isinstance(exc, (httpx.TimeoutException, httpx.TransportError)) or (
                                        isinstance(exc, TranslateProviderError) and exc.retryable
                                    )
                                    if not retryable or attempt >= 3:
                                        return {
                                            **base_result, "success": False,
                                            "stage": "translate_retry_exhausted" if retryable else "translate_permanent_error",
                                            "toonPath": last_toon, "retries": retries,
                                            "rateLimits": rate_limits,
                                            "durationMs": int((time.monotonic() - note_started) * 1000),
                                            "error": str(exc),
                                        }
                                    retries += 1
                                    retry_after = exc.retry_after if isinstance(exc, TranslateProviderError) else None
                                    delay = retry_after if retry_after is not None else (
                                        (2 ** (attempt - 1)) + random.uniform(0.0, 0.5)
                                    )
                                    await asyncio.sleep(delay)
                        finally:
                            active["count"] -= 1
                    raise RuntimeError("Tradução terminou sem resultado")

                tasks = [
                    asyncio.create_task(translate_note(note_id, item))
                    for note_id, item in by_note.items()
                ]
                results = list(invalid)
                translated = 0
                failed = len(invalid)
                skipped = 0
                completed = 0
                retries = 0
                rate_limits = 0
                try:
                    for finished in asyncio.as_completed(tasks):
                        item_result = await finished
                        completed += 1
                        retries += int(item_result.get("retries") or 0)
                        rate_limits += int(item_result.get("rateLimits") or 0)
                        status = "failed"
                        if item_result.get("stage") == "skip_empty":
                            skipped += 1
                            status = "skipped"
                        elif item_result.get("success"):
                            final_fields = item_result.pop("_finalFields")
                            try:
                                await ankiconnect(
                                    anki_client, "updateNoteFields",
                                    {"note": {"id": item_result["noteId"], "fields": final_fields}},
                                )
                                item_result["stage"] = "anki_updateNoteFields"
                                translated += 1
                                status = "success"
                            except asyncio.CancelledError:
                                raise
                            except Exception as exc:
                                item_result.update(success=False, stage="anki_updateNoteFields", error=str(exc))
                                failed += 1
                        else:
                            failed += 1
                        results.append(item_result)
                        progress = {
                            "current": completed, "completed": completed, "total": total_notes,
                            "percent": int(completed / max(1, total_notes) * 100),
                            "noteId": item_result.get("noteId"), "status": status,
                            "requestedConcurrency": requested_concurrency,
                            "effectiveConcurrency": effective_concurrency,
                            "inFlight": active["count"], "retries": retries,
                            "rateLimits": rate_limits,
                        }
                        if item_result.get("error"):
                            progress["error"] = str(item_result["error"])[:100]
                        yield f"event: progress\ndata: {json.dumps(progress)}\n\n"
                finally:
                    pending = [task for task in tasks if not task.done()]
                    for task in pending:
                        task.cancel()
                    if pending:
                        await asyncio.gather(*pending, return_exceptions=True)

                duration = max(0.001, time.monotonic() - started_all)
                duration_ms = int(duration * 1000)
                notes_per_second = round(total_notes / duration, 3)
                payload = {
                    "requestId": request_id, "success": failed == 0,
                    "targetLanguage": target_language, "provider": provider, "model": model,
                    "noteType": selected_note_type or None, "fieldNames": list(req.fieldNames or []),
                    "totalCards": len(card_ids), "totalNotes": total_notes,
                    "translated": translated, "skipped": skipped, "failed": failed,
                    "requestedConcurrency": requested_concurrency,
                    "effectiveConcurrency": effective_concurrency,
                    "retryCount": retries, "rateLimitCount": rate_limits,
                    "notesPerSecond": notes_per_second,
                    "timings": {
                        "cardsInfoMs": cards_info_ms, "notesInfoMs": notes_info_ms,
                        "totalMs": duration_ms,
                        "avgPerNoteMs": int(duration_ms / max(1, total_notes)),
                    },
                    "results": sorted(results, key=lambda value: int(value.get("sourceIndex", 10**12))),
                }
                if translated == 0 and failed > 0:
                    payload["error"] = "Falha ao traduzir: nenhuma nota foi traduzida. Veja results para detalhes."
                elif translated > 0 and failed > 0:
                    payload["success"] = True
                    payload["warning"] = "Sucesso parcial: algumas notas falharam. Veja results."
                logger.info("anki_translation_complete %s", json.dumps({
                    "requestId": request_id, "provider": provider,
                    "requestedConcurrency": requested_concurrency,
                    "effectiveConcurrency": effective_concurrency,
                    "durationMs": duration_ms, "notesPerSecond": notes_per_second,
                    "retries": retries, "rateLimits": rate_limits,
                }))
                yield f"event: result\ndata: {json.dumps(payload)}\n\n"
        except asyncio.CancelledError:
            pending = [task for task in tasks if not task.done()]
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            logger.info(
                "anki_translation_cancelled requestId=%s requestedConcurrency=%s effectiveConcurrency=%s",
                request_id, requested_concurrency, effective_concurrency,
            )
            raise
        except Exception as exc:
            data = {"success": False, "requestId": request_id, "error": str(exc)}
            yield f"event: error\ndata: {json.dumps(data)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# =============================================================================
# Detect Language in Cards (usando langid)
# =============================================================================
class DetectLanguageRequest(BaseModel):
    cardIds: List[int] = Field(default_factory=list)
    deckName: Optional[str] = None  # Se omitido, usa cardIds; se definido, busca todo deck
    noteType: Optional[str] = None
    fieldNames: List[str] = Field(default_factory=list)


@router.post("/detect-card-languages")
async def detect_card_languages(req: DetectLanguageRequest):
    """
    Detecta idiomas nos campos de cartões usando langid.
    Retorna quantos já estão em português e quantos não estão.
    """
    try:
        import langid
    except ImportError:
        return JSONResponse(
            {"error": "langid não instalado. Execute: pip install langid"},
            status_code=500,
        )

    request_id = uuid.uuid4().hex[:12]
    card_ids = list(req.cardIds or [])

    # Se deckName fornecido, buscar todo o deck
    if req.deckName and not card_ids:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                deck_cards = await ankiconnect(
                    client, "findCards", {"query": f'deck:"{req.deckName}"'}
                )
                card_ids = list(deck_cards or [])
        except Exception as e:
            return JSONResponse(
                {"error": f"Erro ao buscar deck: {str(e)}", "requestId": request_id},
                status_code=400,
            )

    if not card_ids:
        return JSONResponse(
            {
                "success": True,
                "requestId": request_id,
                "totalCards": 0,
                "languages": {},
                "alreadyPortuguese": 0,
                "needsTranslation": 0,
            }
        )

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            # Buscar info dos cartões
            infos = await ankiconnect(client, "cardsInfo", {"cards": card_ids})
            infos = list(infos or [])

            # Buscar notas info
            note_ids = []
            for c in infos:
                nid = safe_int(c.get("noteId") or c.get("note"), default=None)
                if nid and nid not in note_ids:
                    note_ids.append(nid)

            notes_info = await ankiconnect(client, "notesInfo", {"notes": note_ids})
            notes_info = list(notes_info or [])

            # Detectar idiomas
            language_counts = {}
            pt_count = 0
            needs_translation = 0

            analyzed_notes = 0
            selected_fields = set(req.fieldNames or [])
            for ni in notes_info:
                if req.noteType and str(ni.get("modelName") or "") != req.noteType:
                    continue

                # Concatenar somente os valores reais dos campos escolhidos.
                fields_map, _ = _extract_notesinfo_fields(ni)
                text_content = " ".join(
                    value.strip()
                    for name, value in fields_map.items()
                    if value and (not selected_fields or name in selected_fields)
                ).strip()
                analyzed_notes += 1

                if not text_content:
                    lang = "empty"
                else:
                    # Remover tags HTML e markdown simples
                    text_clean = re.sub(r"<[^>]+>", "", text_content)
                    text_clean = re.sub(r"\{\{c\d+::[^}]+\}\}", "", text_clean)

                    if text_clean.strip():
                        try:
                            lang, conf = langid.classify(text_clean)
                        except Exception:
                            lang = "unknown"
                    else:
                        lang = "empty"

                language_counts[lang] = language_counts.get(lang, 0) + 1

                if lang in ["pt", "pt-br", "pt_br"]:
                    pt_count += 1
                elif lang != "empty":
                    needs_translation += 1

            return JSONResponse(
                {
                    "success": True,
                    "requestId": request_id,
                    "totalCards": len(card_ids),
                    "totalNotes": analyzed_notes,
                    "languages": language_counts,
                    "alreadyPortuguese": pt_count,
                    "needsTranslation": needs_translation,
                    "summary": {
                        "pt_percentage": int((pt_count / analyzed_notes * 100)) if analyzed_notes else 0,
                        "message": f"{pt_count} em português, {needs_translation} precisam tradução",
                    },
                }
            )

    except Exception as e:
        import traceback

        return JSONResponse(
            {
                "success": False,
                "requestId": request_id,
                "error": str(e),
                "trace": traceback.format_exc(),
            },
            status_code=500,
        )


# =============================================================================
# Upload Questions to Anki (AllInOne kprim, mc, sc)
# =============================================================================

class QuestionOption(BaseModel):
    text: str
    isCorrect: bool


class AllInOneQuestion(BaseModel):
    question: str
    qtype: int  # 0=kprim, 1=mc, 2=sc
    options: List[QuestionOption]
    answers: str  # Gabarito codificado
    comment: str = ""
    sources: str = ""
    domain: str = ""
    deck: Optional[str] = None


class AllInOneUpload(BaseModel):
    questions: List[AllInOneQuestion]
    deckName: Optional[str] = None
    tags: Optional[str] = ""


@router.post("/upload-questions-to-anki")
async def upload_questions_to_anki(request: AllInOneUpload):
    """
    Upload questions to Anki using AllInOne (kprim, mc, sc) note type.
    Maps question fields to AllInOne model fields.
    """
    import logging
    logger = logging.getLogger(__name__)

    MODEL_NAME = "AllInOne (kprim, mc, sc)"

    # Field mapping from AllInOne note type
    # Based on screenshot: Question, QType (0=kprim,1=mc,2=sc), Q_1, Q_2, Q_3, Q_4, Q_5, Answers, Comment, Sources, Domain

    results = []
    tags = [t.strip() for t in request.tags.split(",") if t.strip()] if request.tags else []

    logger.info(f"[Anki Question Export] Starting export of {len(request.questions)} questions")

    async with httpx.AsyncClient(timeout=30.0) as client:
        # First, check if AllInOne model exists
        try:
            r = await client.post(ANKI_CONNECT_URL, json={"action": "modelNames", "version": 6})
            model_names = r.json().get("result", [])

            if MODEL_NAME not in model_names:
                return JSONResponse(
                    status_code=422,
                    content={
                        "success": False,
                        "error": f"Modelo '{MODEL_NAME}' não encontrado no Anki",
                        "message": "Instale a extensão Multiple Choice for Anki: https://ankiweb.net/shared/info/1566095810",
                        "availableModels": model_names,
                    }
                )
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={
                    "success": False,
                    "error": f"Erro ao conectar com Anki: {str(e)}",
                    "message": "Verifique se o Anki está aberto e o AnkiConnect está instalado",
                }
            )

        for i, q in enumerate(request.questions):
            try:
                deck_name = request.deckName or q.deck or "Default"

                # Build fields for AllInOne note type
                fields = {
                    "Question": q.question,
                    "QType (0=kprim,1=mc,2=sc)": str(q.qtype),
                    "Q_1": q.options[0].text if len(q.options) > 0 else "",
                    "Q_2": q.options[1].text if len(q.options) > 1 else "",
                    "Q_3": q.options[2].text if len(q.options) > 2 else "",
                    "Q_4": q.options[3].text if len(q.options) > 3 else "",
                    "Q_5": q.options[4].text if len(q.options) > 4 else "",
                    "Answers": q.answers,
                    "Comment": q.comment,
                    "Sources": q.sources,
                    "Domain": q.domain,
                }

                note = {
                    "deckName": deck_name,
                    "modelName": MODEL_NAME,
                    "fields": fields,
                    "options": {"allowDuplicate": False},
                    "tags": tags,
                }

                logger.info(f"[Anki Question Export] Question {i+1}: deck={deck_name}, qtype={q.qtype}")

                rr = await client.post(
                    ANKI_CONNECT_URL,
                    json={"action": "addNote", "version": 6, "params": {"note": note}},
                )
                data = rr.json()
                logger.info(f"[Anki Question Export] Question {i+1} response: {data}")

                if data.get("error"):
                    raise Exception(data["error"])
                results.append({"success": True, "id": data["result"], "index": i})
            except Exception as e:
                logger.error(f"[Anki Question Export] Question {i+1} failed: {str(e)}")
                results.append({"success": False, "error": str(e), "index": i})

    total_success = sum(1 for r in results if r["success"])
    total_questions = len(request.questions)

    # Count by type
    type_counts = {
        "kprim": sum(1 for q in request.questions if q.qtype == 0),
        "mc": sum(1 for q in request.questions if q.qtype == 1),
        "sc": sum(1 for q in request.questions if q.qtype == 2),
    }

    response_data = {
        "success": total_success > 0,
        "results": results,
        "totalSuccess": total_success,
        "totalQuestions": total_questions,
        "typeCounts": type_counts,
    }

    if total_success == 0:
        return JSONResponse(status_code=422, content=response_data)
    elif total_success < total_questions:
        return JSONResponse(status_code=207, content=response_data)
    else:
        return response_data


@router.get("/check-allinone-model")
async def check_allinone_model():
    """
    Check if AllInOne (kprim, mc, sc) model is available in Anki.
    """
    MODEL_NAME = "AllInOne (kprim, mc, sc)"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(ANKI_CONNECT_URL, json={"action": "modelNames", "version": 6})
            data = r.json()

            if data.get("error"):
                raise Exception(data["error"])

            model_names = data.get("result", [])
            has_model = MODEL_NAME in model_names

            # If model exists, get its fields
            fields = []
            if has_model:
                rf = await client.post(
                    ANKI_CONNECT_URL,
                    json={"action": "modelFieldNames", "version": 6, "params": {"modelName": MODEL_NAME}},
                )
                fields = rf.json().get("result", [])

            return {
                "success": True,
                "hasModel": has_model,
                "modelName": MODEL_NAME,
                "fields": fields,
                "installUrl": "https://ankiweb.net/shared/info/1566095810" if not has_model else None,
            }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "hasModel": False,
            "modelName": MODEL_NAME,
            "installUrl": "https://ankiweb.net/shared/info/1566095810",
        }
