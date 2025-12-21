from fastapi import APIRouter, Query
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import httpx
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
# --- NEW: browse cards --------------------------------------

@router.get("/anki-cards")
async def get_anki_cards(
    query: str = Query("is:review", description="Anki search query. Ex: deck:\"My Deck\" is:review"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    """
    Retorna cardsInfo paginado.
    Obs: AnkiConnect findCards retorna TODOS ids; aqui a gente pagina no servidor.
    """
    limit = clamp_int(limit, 1, 200)
    offset = max(0, offset)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            ids = await ankiconnect(client, "findCards", {"query": query})
            total = len(ids)

            page_ids = ids[offset : offset + limit]
            if not page_ids:
                return {"success": True, "query": query, "total": total, "items": []}

            items = await ankiconnect(client, "cardsInfo", {"cards": page_ids})
            return {"success": True, "query": query, "total": total, "items": items}

    except Exception as e:
        return {"success": False, "error": str(e), "query": query, "total": 0, "items": []}

# --- NEW: recreate learned cards ----------------------------

class AnkiRecreateRequest(BaseModel):
    cardIds: List[int]
    targetDeckName: Optional[str] = None  # se vazio, usa o deck original
    addTag: Optional[str] = "greendeck_recreated"  # tag extra
    allowDuplicate: bool = True

@router.post("/anki-recreate")
async def recreate_cards(req: AnkiRecreateRequest):
    """
    Recria cards duplicando a NOTA (note), criando cards NOVOS.
    Importante: se a nota gera múltiplos cards (ex: Basic + Reverse), recriar UM card recria a nota inteira.
    Por isso a gente deduplica por noteId.
    """
    if not req.cardIds:
        return {"success": True, "totalRequested": 0, "totalCreated": 0, "results": []}

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            # 1) cardsInfo
            infos = await ankiconnect(client, "cardsInfo", {"cards": req.cardIds})

            # dedup por noteId (recriar nota uma vez)
            by_note: Dict[int, Dict[str, Any]] = {}
            for c in infos:
                nid = int(c.get("noteId"))
                if nid not in by_note:
                    by_note[nid] = c

            note_ids = list(by_note.keys())

            # 2) notesInfo (pra tags)
            notes_info = await ankiconnect(client, "notesInfo", {"notes": note_ids})
            tags_by_note: Dict[int, List[str]] = {}
            fields_by_note: Dict[int, Dict[str, str]] = {}

            for n in notes_info:
                nid = int(n.get("noteId"))
                tags_by_note[nid] = list(n.get("tags") or [])
                fields_by_note[nid] = dict(n.get("fields") or {})

            results = []
            created = 0

            for nid, card in by_note.items():
                try:
                    deck_name = req.targetDeckName or card.get("deckName") or "Default"
                    model_name = card.get("modelName")

                    # prefere fields vindos do notesInfo (mais confiável p/ tags e campos completos)
                    fields = fields_by_note.get(nid) or card.get("fields") or {}

                    tags = tags_by_note.get(nid, [])
                    if req.addTag:
                        tags = [*tags, req.addTag, f"fromNote:{nid}"]

                    note_payload = {
                        "deckName": deck_name,
                        "modelName": model_name,
                        "fields": fields,
                        "options": {"allowDuplicate": bool(req.allowDuplicate)},
                        "tags": tags,
                    }

                    new_note_id = await ankiconnect(client, "addNote", {"note": note_payload})
                    created += 1
                    results.append({"success": True, "oldNoteId": nid, "newNoteId": new_note_id, "deckName": deck_name})
                except Exception as e:
                    results.append({"success": False, "oldNoteId": nid, "error": str(e)})

            return {
                "success": True,
                "totalRequestedCards": len(req.cardIds),
                "totalDedupNotes": len(by_note),
                "totalCreated": created,
                "results": results,
            }

    except Exception as e:
        return {"success": False, "error": str(e)}