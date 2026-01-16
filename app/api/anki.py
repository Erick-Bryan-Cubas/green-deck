from fastapi import APIRouter, Query, Body
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Tuple, Literal
import httpx
import os
import json
import re
import unicodedata
import time
import uuid
import html as _html
from pathlib import Path
from datetime import datetime, timezone
from difflib import SequenceMatcher
import logging

from app.config import ANKI_CONNECT_URL

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
                order = safe_int(fv.get("order"), default=9999) or 9999
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
    results = []
    tags = [t.strip() for t in request.tags.split(",") if t.strip()] if request.tags else []

    async with httpx.AsyncClient(timeout=30.0) as client:
        for card in request.cards:
            try:
                note = {
                    "deckName": request.deckName or card.deck or "Default",
                    "modelName": request.modelName,
                    "fields": {request.frontField: card.front, request.backField: card.back},
                    "options": {"allowDuplicate": False},
                    "tags": tags,
                }
                rr = await client.post(
                    ANKI_CONNECT_URL,
                    json={"action": "addNote", "version": 6, "params": {"note": note}},
                )
                data = rr.json()
                if data.get("error"):
                    raise Exception(data["error"])
                results.append({"success": True, "id": data["result"]})
            except Exception as e:
                results.append({"success": False, "error": str(e)})

    return {
        "success": True,
        "results": results,
        "totalSuccess": sum(1 for r in results if r["success"]),
        "totalCards": len(request.cards),
    }

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

@router.post("/anki-note-update")
async def anki_note_update(req: AnkiNoteUpdateRequest):
    """
    Atualiza fields da nota via updateNoteFields.
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            note_id = int(req.noteId)
            fields = {str(k): str(v) for k, v in (req.fields or {}).items()}

            if not fields:
                return JSONResponse(status_code=400, content={"success": False, "error": "fields vazio."})

            payload = {"note": {"id": note_id, "fields": fields}}
            await ankiconnect(client, "updateNoteFields", payload)
            return {"success": True, "noteId": note_id, "updatedFields": len(fields)}
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
        "translated_fields": {
            "type": "object",
            "additionalProperties": {"type": "string"}
        }
    },
    "required": ["translated_fields"]
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
8) Se um campo estiver vazio ou contiver apenas mídia/HTML, retorne-o inalterado.

EXEMPLOS DE TRADUÇÃO:

Original: "The {{c1::heart}} pumps {{c2::blood}} through the body."
Traduzido: "O {{c1::coração}} bombeia {{c2::sangue}} pelo corpo."

Original: "<b>API</b> stands for Application Programming Interface"
Traduzido: "<b>API</b> significa Application Programming Interface (Interface de Programação de Aplicações)"

Original: "[sound:audio.mp3]<br>What is the capital of France?"
Traduzido: "[sound:audio.mp3]<br>Qual é a capital da França?"

SAÍDA:
{ "translated_fields": { "campo1": "valor traduzido", "campo2": "valor traduzido" } }
"""


class AnkiTranslateRequest(BaseModel):
    cardIds: List[int] = Field(default_factory=list)
    deckName: Optional[str] = None  # Se omitido, usa cardIds; se definido, traduz todo deck
    targetLanguage: str = "pt-br"
    model: Optional[str] = None  # Modelo para tradução (ex: gpt-4o, sonar, qwen-flashcard)
    # API Keys para providers externos
    openaiApiKey: Optional[str] = None
    perplexityApiKey: Optional[str] = None
    anthropicApiKey: Optional[str] = None


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


async def _translate_with_provider(
    *,
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
                api_key=openai_key,
                model=model,
                system=system_prompt,
                user=user_prompt,
                temperature=temperature,
            )
        elif provider == "anthropic" and anthropic_key:
            content = await _call_anthropic_translate(
                api_key=anthropic_key,
                model=model,
                system=system_prompt,
                user=user_prompt,
                temperature=temperature,
            )
        elif provider == "perplexity" and perplexity_key:
            content = await _call_perplexity_translate(
                api_key=perplexity_key,
                model=model,
                system=system_prompt,
                user=user_prompt,
                temperature=temperature,
            )
        else:
            # Fallback: Ollama
            content = await _call_ollama_translate(
                model=model,
                system=system_prompt,
                user=user_prompt,
                temperature=temperature,
            )

        dbg["elapsedMs"] = int((time.monotonic() - t0) * 1000)
        dbg["contentPreview"] = (content or "")[:500]
        path = _write_toon_file(f"translate_{provider}_ok_nid{source_note_id}", request_id, dbg)
        return content, path

    except Exception as e:
        dbg["error"] = str(e)
        dbg["elapsedMs"] = int((time.monotonic() - t0) * 1000)
        path = _write_toon_file(f"translate_{provider}_error_nid{source_note_id}", request_id, dbg)
        raise Exception(f"[{provider}] {e}. (Veja: {path})")


async def _call_openai_translate(
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

    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=payload
        )
        if r.status_code != 200:
            raise Exception(f"OpenAI HTTP {r.status_code}: {r.text[:300]}")

        data = r.json()
        return data.get("choices", [{}])[0].get("message", {}).get("content", "")


async def _call_anthropic_translate(
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

    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=payload
        )
        if r.status_code != 200:
            raise Exception(f"Anthropic HTTP {r.status_code}: {r.text[:300]}")

        data = r.json()
        content_blocks = data.get("content", [])
        if content_blocks and isinstance(content_blocks, list):
            return content_blocks[0].get("text", "")
        return ""


async def _call_perplexity_translate(
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

    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(
            "https://api.perplexity.ai/chat/completions",
            headers=headers,
            json=payload
        )
        if r.status_code != 200:
            raise Exception(f"Perplexity HTTP {r.status_code}: {r.text[:300]}")

        data = r.json()
        return data.get("choices", [{}])[0].get("message", {}).get("content", "")


async def _call_ollama_translate(
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

    async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT_S) as client:
        r = await client.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=OLLAMA_TIMEOUT_S)
        r.raise_for_status()
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

    user = {
        "task": "translate_anki_note_fields",
        "source_fields": source_fields,
        "target_language": target_lang_name,
        "target_field_names": list(source_fields.keys()),
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

    if not parsed or "translated_fields" not in parsed:
        dbg["error"] = "SLM/Ollama retornou conteúdo não-JSON ou fora do schema esperado."
        dbg["elapsedMs"] = int((time.monotonic() - t0) * 1000)
        path = _write_toon_file(f"translate_badjson_nid{source_note_id}", request_id, dbg)
        raise Exception(f"SLM/Ollama retornou JSON inválido/fora do schema. (Veja: {path})")

    translated = parsed.get("translated_fields") or {}
    if not isinstance(translated, dict):
        dbg["error"] = "translated_fields não é um dict."
        dbg["elapsedMs"] = int((time.monotonic() - t0) * 1000)
        path = _write_toon_file(f"translate_badfields_nid{source_note_id}", request_id, dbg)
        raise Exception(f"SLM/Ollama retornou translated_fields inválido. (Veja: {path})")

    out = {str(k): str(v) for k, v in translated.items()}
    dbg["elapsedMs"] = int((time.monotonic() - t0) * 1000)
    dbg["translatedPreview"] = {k: (out.get(k, "")[:200]) for k in list(out.keys())[:4]}
    path = _write_toon_file(f"translate_ok_nid{source_note_id}", request_id, dbg)
    return out, path


@router.post("/anki-translate")
async def translate_cards(req: AnkiTranslateRequest):
    """
    Traduz cards do Anki in-place usando LLM (Ollama, OpenAI, Anthropic ou Perplexity).
    Preserva tags, mídia e marcações cloze.
    Retorna SSE stream com eventos de progresso.
    
    Parâmetros:
    - cardIds: Lista de card IDs (se vazio e deckName fornecido, busca todo o deck)
    - deckName: Nome do deck (alternativa a cardIds)
    - targetLanguage: Idioma alvo (padrão: pt-br)
    - model: Modelo LLM para tradução
    """
    request_id = uuid.uuid4().hex[:12]
    
    # Resolver cardIds: se vazio e deckName fornecido, buscar todo deck
    card_ids = list(req.cardIds or [])
    if not card_ids and req.deckName:
        try:
            async with httpx.AsyncClient(timeout=30.0) as temp_client:
                deck_cards = await ankiconnect(
                    temp_client, "findCards", {"query": f'deck:"{req.deckName}"'}
                )
                card_ids = list(deck_cards or [])
        except Exception as e:
            async def error_gen():
                yield f"event: error\ndata: {json.dumps({'success': False, 'requestId': request_id, 'error': f'Erro ao buscar deck: {str(e)}'})}\n\n"
            return StreamingResponse(error_gen(), media_type="text/event-stream")

    target_language = (req.targetLanguage or "pt-br").strip().lower()

    # Detectar modelo e provider
    model = req.model or OLLAMA_MODEL_NEUTRAL
    provider = _detect_provider(
        model,
        openai_key=req.openaiApiKey,
        perplexity_key=req.perplexityApiKey,
        anthropic_key=req.anthropicApiKey,
    )

    # Preparar nomes de idiomas para o prompt
    language_names = {
        "pt-br": "português brasileiro",
        "pt": "português",
        "es": "espanhol",
        "en": "inglês",
        "fr": "francês",
        "de": "alemão",
        "it": "italiano",
    }
    target_lang_name = language_names.get(target_language, target_language)

    async def generate():
        t_all = time.monotonic()

        # Caso sem cards
        if not card_ids:
            yield f"event: result\ndata: {json.dumps({'success': True, 'requestId': request_id, 'totalCards': 0, 'totalNotes': 0, 'translated': 0, 'failed': 0, 'results': []})}\n\n"
            return

        try:
            async with httpx.AsyncClient(timeout=90.0) as anki_client:
                # 1) cardsInfo (para cardId/noteId)
                t0 = time.monotonic()
                infos = await ankiconnect(anki_client, "cardsInfo", {"cards": card_ids})
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

                # 2) notesInfo (tags + fields brutos)
                t0 = time.monotonic()
                notes_info = await ankiconnect(anki_client, "notesInfo", {"notes": note_ids})
                notes_info = list(notes_info or [])
                t_notesinfo_ms = int((time.monotonic() - t0) * 1000)

                note_info_by_id: Dict[int, Dict[str, Any]] = {}
                for ni in notes_info:
                    nid = safe_int(ni.get("noteId"), default=None)
                    if nid is not None:
                        note_info_by_id[nid] = ni

                # Emitir evento de início
                total_notes = len(note_ids)
                yield f"event: start\ndata: {json.dumps({'requestId': request_id, 'totalCards': len(card_ids), 'totalNotes': total_notes, 'provider': provider, 'model': model})}\n\n"

                # 3) traduzir e atualizar cada nota
                results: List[Dict[str, Any]] = []
                translated_count = 0
                failed_count = 0
                current_note = 0

                for inv in invalid:
                    results.append(inv)
                    failed_count += 1

                for nid, c in by_note.items():
                    current_note += 1
                    card_id = safe_int(c.get("cardId"), default=None)
                    ni = note_info_by_id.get(nid) or {}

                    src_fields_map, src_ordered = _extract_notesinfo_fields(ni)

                    # Filtrar campos vazios ou que são apenas mídia
                    fields_to_translate = {}
                    for fname, fvalue in src_fields_map.items():
                        # Pular campos vazios
                        if not fvalue or not fvalue.strip():
                            continue
                        # Pular campos que são apenas referências de mídia
                        text_only = re.sub(r'\[sound:[^\]]+\]', '', fvalue)
                        text_only = re.sub(r'<img[^>]+>', '', text_only)
                        text_only = TAG_PAT.sub('', text_only).strip()
                        if text_only:
                            fields_to_translate[fname] = fvalue

                    if not fields_to_translate:
                        # Nada para traduzir nesta nota
                        results.append({
                            "success": True,
                            "stage": "skip_empty",
                            "noteId": nid,
                            "cardId": card_id,
                            "message": "Nenhum campo com texto para traduzir"
                        })
                        # Emitir progresso (skip)
                        percent = int((current_note / total_notes) * 100)
                        yield f"event: progress\ndata: {json.dumps({'current': current_note, 'total': total_notes, 'percent': percent, 'noteId': nid, 'status': 'skipped', 'message': 'Sem texto para traduzir'})}\n\n"
                        continue

                    # Tentar traduzir com retry
                    max_attempts = 2
                    attempt = 0
                    last_error = None
                    last_toon = None

                    while attempt < max_attempts:
                        attempt += 1
                        temp = 0.3 if attempt == 1 else 0.5

                        # Montar prompts
                        system_prompt = (
                            "Você é um tradutor profissional. SEMPRE responda somente com JSON válido, "
                            "seguindo exatamente o schema solicitado. Não escreva nada fora do JSON."
                        )

                        user_content = {
                            "task": "translate_anki_note_fields",
                            "source_fields": fields_to_translate,
                            "target_language": target_lang_name,
                            "target_field_names": list(fields_to_translate.keys()),
                            "retry_hint": "Tente novamente." if attempt > 1 else "",
                            "instructions": PROMPT_TRANSLATE,
                        }
                        user_prompt = json.dumps(user_content, ensure_ascii=False)

                        try:
                            # Usar provider apropriado
                            content, toon_path = await _translate_with_provider(
                                provider=provider,
                                model=model,
                                system_prompt=system_prompt,
                                user_prompt=user_prompt,
                                temperature=temp,
                                request_id=request_id,
                                source_note_id=nid,
                                openai_key=req.openaiApiKey,
                                perplexity_key=req.perplexityApiKey,
                                anthropic_key=req.anthropicApiKey,
                            )
                            last_toon = toon_path

                            # Parse JSON da resposta
                            parsed = _try_extract_json(content)
                            if not parsed or "translated_fields" not in parsed:
                                raise Exception("Resposta não contém translated_fields válido")

                            translated_fields = parsed.get("translated_fields") or {}
                            if not isinstance(translated_fields, dict):
                                raise Exception("translated_fields não é um dict")

                            # Mesclar campos traduzidos com campos originais
                            final_fields = dict(src_fields_map)
                            for fname, tvalue in translated_fields.items():
                                if fname in final_fields and tvalue and str(tvalue).strip():
                                    final_fields[fname] = str(tvalue)

                            # Atualizar nota no Anki
                            update_payload = {"note": {"id": nid, "fields": final_fields}}
                            await ankiconnect(anki_client, "updateNoteFields", update_payload)

                            translated_count += 1
                            results.append({
                                "success": True,
                                "stage": "anki_updateNoteFields",
                                "requestId": request_id,
                                "noteId": nid,
                                "cardId": card_id,
                                "fieldsTranslated": len(translated_fields),
                                "targetLanguage": target_language,
                                "provider": provider,
                                "model": model,
                                "toonPath": last_toon,
                            })
                            last_error = None
                            break

                        except Exception as e:
                            last_error = str(e)
                            continue

                    # Emitir progresso após cada nota
                    percent = int((current_note / total_notes) * 100)
                    if last_error is not None:
                        failed_count += 1
                        results.append({
                            "success": False,
                            "stage": "translate_retry_exhausted",
                            "requestId": request_id,
                            "noteId": nid,
                            "cardId": card_id,
                            "targetLanguage": target_language,
                            "provider": provider,
                            "model": model,
                            "toonPath": last_toon,
                            "error": last_error,
                        })
                        yield f"event: progress\ndata: {json.dumps({'current': current_note, 'total': total_notes, 'percent': percent, 'noteId': nid, 'status': 'failed', 'error': last_error[:100]})}\n\n"
                    else:
                        yield f"event: progress\ndata: {json.dumps({'current': current_note, 'total': total_notes, 'percent': percent, 'noteId': nid, 'status': 'success'})}\n\n"

                timings = {
                    "cardsInfoMs": t_cardsinfo_ms,
                    "notesInfoMs": t_notesinfo_ms,
                    "totalMs": int((time.monotonic() - t_all) * 1000),
                    "avgPerNoteMs": int((time.monotonic() - t_all) * 1000 / max(1, len(note_ids))),
                }

                payload = {
                    "requestId": request_id,
                    "success": (translated_count > 0 and failed_count == 0),
                    "targetLanguage": target_language,
                    "provider": provider,
                    "model": model,
                    "totalCards": len(req.cardIds),
                    "totalNotes": len(note_ids),
                    "translated": translated_count,
                    "failed": failed_count,
                    "timings": timings,
                    "results": results,
                }

                if translated_count == 0 and failed_count > 0:
                    payload["success"] = False
                    payload["error"] = "Falha ao traduzir: nenhuma nota foi traduzida. Veja results para detalhes."

                if translated_count > 0 and failed_count > 0:
                    payload["success"] = True
                    payload["warning"] = "Sucesso parcial: algumas notas falharam. Veja results."

                yield f"event: result\ndata: {json.dumps(payload)}\n\n"

        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'success': False, 'requestId': request_id, 'error': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# =============================================================================
# Detect Language in Cards (usando langid)
# =============================================================================
class DetectLanguageRequest(BaseModel):
    cardIds: List[int] = Field(default_factory=list)
    deckName: Optional[str] = None  # Se omitido, usa cardIds; se definido, busca todo deck


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

            for ni in notes_info:
                # Concatenar campos para análise
                fields = ni.get("fields", {})
                text_content = " ".join(
                    str(v).strip() for v in fields.values() if v
                ).strip()

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
                    "totalNotes": len(notes_info),
                    "languages": language_counts,
                    "alreadyPortuguese": pt_count,
                    "needsTranslation": needs_translation,
                    "summary": {
                        "pt_percentage": int((pt_count / len(notes_info) * 100)) if notes_info else 0,
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
