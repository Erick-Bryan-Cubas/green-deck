from fastapi import APIRouter, Query, Body
from fastapi.responses import JSONResponse
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

from app.config import ANKI_CONNECT_URL

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

    difficulty: Optional[DifficultyInput] = "hard_neutral"

    # Mantém compatibilidade com frontend antigo, mas NÃO vamos mais enfiar tags "lixo"
    # Se quiser, pode usar como tag extra (opcional). Default = None.
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

    difficulty = normalize_difficulty(str(req.difficulty) if req.difficulty else "hard_neutral")

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
                                ollama_model = pick_ollama_model(difficulty)

                                # aumenta temperatura em retries
                                temp = OLLAMA_TEMPERATURE if attempt == 1 else min(0.85, OLLAMA_TEMPERATURE + 0.25 * attempt)

                                retry_hint = ""
                                if attempt > 1:
                                    retry_hint = (
                                        "A resposta anterior ficou muito parecida com o original ou fora do nível. "
                                        "Reescreva com MAIS diferença, mudando estrutura e vocabulário."
                                    )

                                try:
                                    gen_fields, toon_path = await ollama_generate_notes(
                                        slm_client,
                                        request_id=request_id,
                                        ollama_model=ollama_model,
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

                                        # valida quantidade por dificuldade
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
