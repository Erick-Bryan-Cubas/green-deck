"""
API das sessões de estudo por PDF.

Guarda o PDF original, as marcações feitas sobre ele, a posição de leitura e o
snapshot das sessões do gerador — tudo no DuckDB local (ver
``app/services/study_store``). É o que permite fechar o app e reabrir o estudo
exatamente onde parou, sem depender do localStorage do navegador.
"""
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.services import study_store
from app.services.study_store import StudyStoreError

router = APIRouter(prefix="/api/study", tags=["study"])
logger = logging.getLogger(__name__)

MAX_FILE_SIZE_MB = 50
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024


# ============================================================
# Modelos
# ============================================================
class HighlightItem(BaseModel):
    id: str = ""
    page: int = 1
    color: str = "yellow"
    text: str = ""
    rects: List[Dict[str, float]] = Field(default_factory=list)


class HighlightsRequest(BaseModel):
    highlights: List[HighlightItem] = Field(default_factory=list)


class ReadingRequest(BaseModel):
    page: int = 1
    scale: float = 1.0
    fitWidth: bool = True
    pageDark: bool = False


class SessionRequest(BaseModel):
    """Snapshot livre da sessão do gerador (o formato evolui no front)."""
    session: Dict[str, Any] = Field(default_factory=dict)


def _count_pdf_pages(content: bytes) -> int:
    """Número de páginas do PDF; 0 quando não dá para ler (não é fatal)."""
    try:
        from io import BytesIO

        from pypdf import PdfReader

        return len(PdfReader(BytesIO(content)).pages)
    except Exception:
        logger.debug("Não foi possível contar as páginas do PDF enviado")
        return 0


def _bad_request(exc: StudyStoreError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


# ============================================================
# Documentos
# ============================================================
@router.post("/documents")
async def upload_study_document(
    file: UploadFile = File(..., description="PDF aberto no modo de estudo"),
):
    """
    Registra (ou reencontra) um PDF de estudo.

    A identidade é o sha256 do conteúdo: subir o mesmo arquivo de novo devolve
    o mesmo id, junto com as marcações e a posição de leitura já salvas.
    """
    filename = file.filename or "documento.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Apenas arquivos PDF são aceitos aqui")

    try:
        content = await file.read()
    except Exception as e:
        logger.exception("Erro ao ler o PDF enviado")
        raise HTTPException(status_code=400, detail=f"Erro ao ler arquivo: {e}")

    if not content:
        raise HTTPException(status_code=400, detail="Arquivo vazio")
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=413, detail=f"Arquivo muito grande. Máximo: {MAX_FILE_SIZE_MB}MB"
        )

    document = study_store.save_document(content, filename, pages=_count_pdf_pages(content))
    highlights = study_store.get_highlights(document["id"])

    return {"success": True, "document": document, "highlights": highlights}


@router.get("/documents")
async def list_study_documents(limit: int = 50):
    """Lista os PDFs já estudados (mais recentes primeiro)."""
    return {"success": True, "documents": study_store.list_documents(max(1, min(limit, 200)))}


@router.get("/documents/{doc_id}")
async def get_study_document(doc_id: str):
    """Metadados + marcações + posição de leitura de um documento."""
    try:
        document = study_store.get_document(doc_id)
    except StudyStoreError as e:
        raise _bad_request(e)

    if not document:
        raise HTTPException(status_code=404, detail="Documento não encontrado")

    return {
        "success": True,
        "document": document,
        "highlights": study_store.get_highlights(doc_id),
    }


@router.get("/documents/{doc_id}/file")
async def get_study_document_file(doc_id: str):
    """Devolve o PDF original para reabrir o leitor."""
    try:
        path = study_store.document_file_path(doc_id)
    except StudyStoreError as e:
        raise _bad_request(e)

    if not path:
        raise HTTPException(status_code=404, detail="Arquivo do documento não encontrado")

    return FileResponse(
        str(path),
        media_type="application/pdf",
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.delete("/documents/{doc_id}")
async def delete_study_document(doc_id: str):
    """Remove o PDF do disco e todas as marcações dele."""
    try:
        study_store.delete_document(doc_id)
    except StudyStoreError as e:
        raise _bad_request(e)
    return {"success": True}


@router.put("/documents/{doc_id}/highlights")
async def put_study_highlights(doc_id: str, payload: HighlightsRequest):
    """Substitui todas as marcações do documento."""
    try:
        highlights = study_store.save_highlights(
            doc_id, [h.model_dump() for h in payload.highlights]
        )
    except StudyStoreError as e:
        raise _bad_request(e)
    return {"success": True, "highlights": highlights}


@router.put("/documents/{doc_id}/reading")
async def put_study_reading(doc_id: str, payload: ReadingRequest):
    """Guarda a posição de leitura (página, zoom, tema da página)."""
    try:
        reading = study_store.save_reading(doc_id, payload.model_dump())
    except StudyStoreError as e:
        raise _bad_request(e)
    return {"success": True, "reading": reading}


# ============================================================
# Sessões
# ============================================================
@router.get("/sessions")
async def list_study_sessions(limit: Optional[int] = None):
    """Sessões do gerador guardadas no banco (mais recentes primeiro)."""
    capped = study_store.MAX_SESSIONS if limit is None else max(1, min(limit, study_store.MAX_SESSIONS))
    return {"success": True, "sessions": study_store.list_sessions(capped)}


@router.put("/sessions/{session_id}")
async def put_study_session(session_id: str, payload: SessionRequest):
    """Insere ou atualiza o snapshot de uma sessão."""
    session = dict(payload.session or {})
    session["id"] = session_id
    try:
        saved = study_store.save_session(session)
    except StudyStoreError as e:
        raise _bad_request(e)
    return {"success": True, "session": saved}


@router.delete("/sessions/{session_id}")
async def delete_study_session(session_id: str):
    try:
        study_store.delete_session(session_id)
    except StudyStoreError as e:
        raise _bad_request(e)
    return {"success": True}


@router.delete("/sessions")
async def clear_study_sessions():
    return {"success": True, "removed": study_store.clear_sessions()}


@router.get("/stats")
async def study_stats():
    return {"success": True, **study_store.get_stats()}
