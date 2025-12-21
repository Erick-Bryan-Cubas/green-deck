from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional
import httpx
from app.config import ANKI_CONNECT_URL

router = APIRouter(prefix="/api", tags=["anki"])

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
