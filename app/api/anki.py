from fastapi import APIRouter, Query
from pydantic import BaseModel
from typing import List, Optional, Dict, Any, Literal
import httpx
import re
import unicodedata
import html

from app.config import ANKI_CONNECT_URL

router = APIRouter(prefix="/api", tags=["anki"])

# --- helpers -------------------------------------------------
async def ankiconnect(client: httpx.AsyncClient, action: str, params: Optional[dict] = None):
    payload: Dict[str, Any] = {"action": action, "version": 6}
    if params is not None:
        payload["params"] = params

    r = await client.post(ANKI_CONNECT_URL, json=payload)
    data = r.json()
    if data.get("error"):
        raise Exception(data["error"])
    return data.get("result")


def clamp_int(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


def safe_int(v: Any, default: Optional[int] = None) -> Optional[int]:
    try:
        if v is None:
            return default
        return int(v)
    except Exception:
        return default


def strip_html(s: str) -> str:
    if not s:
        return ""
    # remove tags
    s = re.sub(r"<[^>]*>", " ", s)
    s = html.unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def normalize_name(s: str) -> str:
    s = (s or "").strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"\s+", " ", s).strip()
    return s


SUPPORTED_BASIC = {"basic", "basico"}  # "Básico" normaliza para "basico"
SUPPORTED_CLOZE = {"cloze", "omissao de palavras"}


def is_supported_basic(model_name: str) -> bool:
    return normalize_name(model_name) in SUPPORTED_BASIC


def is_supported_cloze(model_name: str) -> bool:
    return normalize_name(model_name) in SUPPORTED_CLOZE


def normalize_anki_fields(raw_fields: Any) -> Dict[str, str]:
    """
    AnkiConnect pode retornar fields assim:
      - {"Front":{"value":"...","order":0}, "Back":{"value":"...","order":1}}
      - ou flat: {"Front":"...", "Back":"..."}
    addNote exige dict[str,str] (flat).
    """
    out: Dict[str, str] = {}
    if not isinstance(raw_fields, dict):
        return out

    for k, v in raw_fields.items():
        if isinstance(v, dict) and "value" in v:
            out[str(k)] = str(v.get("value") or "")
        else:
            out[str(k)] = str(v or "")
    return out


# --- upload to Anki (já existia) -----------------------------
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
                r = await client.post(
                    ANKI_CONNECT_URL,
                    json={"action": "addNote", "version": 6, "params": {"note": note}},
                )
                data = r.json()
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
    """
    Mantido como estava (pode ser útil em outras telas).
    """
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


# --- NEW: list note types (modelNames) -----------------------
@router.get("/anki-note-types")
async def get_anki_note_types():
    """
    Retorna os Note Types disponíveis no Anki (modelNames),
    para o usuário "consultar" no modal.
    """
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            names = await ankiconnect(client, "modelNames", None)
            names = list(names or [])
            names.sort(key=lambda x: normalize_name(str(x)))
            return {"success": True, "items": names}
    except Exception as e:
        return {"success": False, "error": str(e), "items": []}


# --- NEW: browse cards --------------------------------------
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


# --- NEW: recreate (v2 strategy: convert to basic/cloze/both)-
class AnkiRecreateRequest(BaseModel):
    cardIds: List[int]
    targetDeckName: Optional[str] = None
    addTag: Optional[str] = "greendeck_recreated"
    allowDuplicate: bool = True

    suspendOriginal: bool = True  # suspend selected NOTES (all cards of those noteIds)
    mode: Literal["basic", "cloze", "both"] = "basic"

    basicModelName: Optional[str] = None
    clozeModelName: Optional[str] = None

    countPerNote: int = 1  # how many new notes per selected note (per type)


@router.post("/anki-recreate")
async def recreate_cards(req: AnkiRecreateRequest):
    """
    Nova estratégia:
      - NÃO clona o Note Type original.
      - Cria novas notas usando Basic / Cloze (ou ambas), baseado no question/answer do card.
      - Pode suspender as notas originais (todos os cards do noteId).
      - Bloqueia qualquer modelName que não seja Basic/Básico ou Cloze/Omissão de Palavras.
    """
    if not req.cardIds:
        return {
            "success": True,
            "totalRequestedCards": 0,
            "totalSelectedNotes": 0,
            "totalCreated": 0,
            "totalFailed": 0,
            "totalSuspendedCards": 0,
            "results": [],
        }

    req.countPerNote = clamp_int(int(req.countPerNote or 1), 1, 50)

    # validação de modelos (UI já bloqueia, mas backend também)
    if req.mode in ("basic", "both"):
        if not req.basicModelName:
            return {"success": False, "error": "basicModelName é obrigatório para mode=basic/both."}
        if not is_supported_basic(req.basicModelName):
            return {"success": False, "error": f"Note Type não suportado: '{req.basicModelName}'. Suportados: Basic/Básico."}

    if req.mode in ("cloze", "both"):
        if not req.clozeModelName:
            return {"success": False, "error": "clozeModelName é obrigatório para mode=cloze/both."}
        if not is_supported_cloze(req.clozeModelName):
            return {"success": False, "error": f"Note Type não suportado: '{req.clozeModelName}'. Suportados: Cloze/Omissão de Palavras."}

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            infos = await ankiconnect(client, "cardsInfo", {"cards": req.cardIds})
            infos = list(infos or [])

            # cardsInfo normalmente traz noteId em "note" (não "noteId")
            # Vamos deduplicar por noteId e manter o primeiro card selecionado como base de conteúdo.
            by_note: Dict[int, Dict[str, Any]] = {}
            invalid: List[Dict[str, Any]] = []

            for c in infos:
                nid = safe_int(c.get("noteId") or c.get("note"), default=None)
                cid = safe_int(c.get("cardId"), default=None)

                if nid is None:
                    invalid.append(
                        {
                            "success": False,
                            "cardId": cid,
                            "error": "cardsInfo retornou noteId/note=None (payload inesperado).",
                        }
                    )
                    continue

                if nid not in by_note:
                    by_note[nid] = c

            note_ids = list(by_note.keys())

            # pega fieldNames dos modelos escolhidos
            basic_fields: List[str] = []
            cloze_fields: List[str] = []

            if req.mode in ("basic", "both"):
                basic_fields = await ankiconnect(client, "modelFieldNames", {"modelName": req.basicModelName})
                basic_fields = list(basic_fields or [])
                if len(basic_fields) < 2:
                    # ainda dá pra criar, mas vai ficar meio ruim; preferimos falhar com mensagem clara
                    return {"success": False, "error": f"O Note Type '{req.basicModelName}' deveria ter >=2 campos (front/back). Encontrado: {basic_fields}"}

            if req.mode in ("cloze", "both"):
                cloze_fields = await ankiconnect(client, "modelFieldNames", {"modelName": req.clozeModelName})
                cloze_fields = list(cloze_fields or [])
                if len(cloze_fields) < 1:
                    return {"success": False, "error": f"O Note Type '{req.clozeModelName}' não tem campos."}

            results: List[Dict[str, Any]] = []
            created = 0
            failed = 0

            for inv in invalid:
                results.append(inv)
                failed += 1

            # cria novas notas por noteId selecionado
            for nid, c in by_note.items():
                question_html = str(c.get("question") or "")
                answer_html = str(c.get("answer") or "")

                # para Cloze, usamos texto “limpo” no c1::
                answer_plain = strip_html(answer_html) or "..."

                deck_name = req.targetDeckName or c.get("deckName") or "Default"

                base_tags: List[str] = []
                if req.addTag:
                    base_tags.append(req.addTag)
                base_tags.append(f"fromNote:{nid}")
                if c.get("cardId"):
                    base_tags.append(f"fromCard:{c.get('cardId')}")

                # repete countPerNote vezes
                for k in range(req.countPerNote):
                    # BASIC
                    if req.mode in ("basic", "both"):
                        try:
                            front_field = basic_fields[0]
                            back_field = basic_fields[1]

                            note_payload = {
                                "deckName": deck_name,
                                "modelName": req.basicModelName,
                                "fields": {
                                    front_field: question_html,
                                    back_field: answer_html,
                                },
                                "options": {"allowDuplicate": bool(req.allowDuplicate)},
                                "tags": [*base_tags, "recreate:basic", f"recreateIndex:{k+1}"],
                            }
                            new_note_id = await ankiconnect(client, "addNote", {"note": note_payload})
                            created += 1
                            results.append(
                                {
                                    "success": True,
                                    "kind": "basic",
                                    "oldNoteId": nid,
                                    "newNoteId": new_note_id,
                                    "deckName": deck_name,
                                    "modelName": req.basicModelName,
                                }
                            )
                        except Exception as e:
                            failed += 1
                            results.append({"success": False, "kind": "basic", "oldNoteId": nid, "error": str(e)})

                    # CLOZE
                    if req.mode in ("cloze", "both"):
                        try:
                            text_field = cloze_fields[0]
                            extra_field = cloze_fields[1] if len(cloze_fields) >= 2 else None

                            cloze_body = (
                                question_html
                                + "<hr>"
                                + "<div>"
                                + "{{c1::"
                                + html.escape(answer_plain)
                                + "}}"
                                + "</div>"
                            )

                            fields = {text_field: cloze_body}
                            if extra_field:
                                fields[extra_field] = answer_html

                            note_payload = {
                                "deckName": deck_name,
                                "modelName": req.clozeModelName,
                                "fields": fields,
                                "options": {"allowDuplicate": bool(req.allowDuplicate)},
                                "tags": [*base_tags, "recreate:cloze", f"recreateIndex:{k+1}"],
                            }
                            new_note_id = await ankiconnect(client, "addNote", {"note": note_payload})
                            created += 1
                            results.append(
                                {
                                    "success": True,
                                    "kind": "cloze",
                                    "oldNoteId": nid,
                                    "newNoteId": new_note_id,
                                    "deckName": deck_name,
                                    "modelName": req.clozeModelName,
                                }
                            )
                        except Exception as e:
                            failed += 1
                            results.append({"success": False, "kind": "cloze", "oldNoteId": nid, "error": str(e)})

            # suspender originais (todas as cards do noteId)
            suspended_cards = 0
            if req.suspendOriginal and note_ids:
                try:
                    all_cards: List[int] = []
                    for nid in note_ids:
                        ids = await ankiconnect(client, "findCards", {"query": f"nid:{nid}"})
                        for x in (ids or []):
                            cid = safe_int(x, default=None)
                            if cid is not None:
                                all_cards.append(cid)

                    # unique
                    all_cards = sorted(set(all_cards))
                    if all_cards:
                        await ankiconnect(client, "suspend", {"cards": all_cards})
                        suspended_cards = len(all_cards)
                except Exception as e:
                    # não falha tudo, mas reporta
                    results.append({"success": False, "kind": "suspend", "error": str(e)})
                    failed += 1

            return {
                "success": True,
                "totalRequestedCards": len(req.cardIds),
                "totalSelectedNotes": len(note_ids),
                "countPerNote": req.countPerNote,
                "mode": req.mode,
                "basicModelName": req.basicModelName,
                "clozeModelName": req.clozeModelName,
                "totalCreated": created,
                "totalFailed": failed,
                "totalSuspendedCards": suspended_cards,
                "results": results,
            }

    except Exception as e:
        return {"success": False, "error": str(e)}
