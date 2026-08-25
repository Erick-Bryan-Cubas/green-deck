"""
Persistência das sessões de estudo (DuckDB + arquivos em disco).

O PDF original fica em ``data/study_pdfs/<sha256>.pdf`` e todo o resto —
metadados do documento, marcações, posição de leitura e o snapshot das sessões
do gerador — vai para o mesmo DuckDB usado pelo restante do app.

A identidade do documento é o sha256 do conteúdo: reabrir o mesmo arquivo, com
outro nome ou de outra pasta, recupera as marcações já feitas.
"""
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import duckdb

from app.services.storage import DB_PATH

PDF_DIR = Path("data/study_pdfs")

# Limites defensivos: o cliente manda a lista inteira a cada alteração
MAX_HIGHLIGHTS = 5000
MAX_SESSIONS = 200

_DOC_ID_RE = re.compile(r"^[0-9a-f]{64}$")
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,80}$")


class StudyStoreError(ValueError):
    """Erro de validação de entrada do store."""


def _now() -> datetime:
    """UTC ingênuo — o front manda ISO com Z, então as colunas precisam da
    mesma referência para que a ordenação e a comparação de versões batam."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def validate_document_id(doc_id: str) -> str:
    """Garante que o id é um sha256 — ele vira nome de arquivo em disco."""
    if not _DOC_ID_RE.match(doc_id or ""):
        raise StudyStoreError("Identificador de documento inválido")
    return doc_id


def validate_session_id(session_id: str) -> str:
    if not _SESSION_ID_RE.match(session_id or ""):
        raise StudyStoreError("Identificador de sessão inválido")
    return session_id


def _connect():
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(DB_PATH))

    # PDFs abertos no modo de estudo
    conn.execute("""
        CREATE TABLE IF NOT EXISTS study_documents (
            id VARCHAR PRIMARY KEY,
            name VARCHAR,
            size BIGINT,
            pages INTEGER,
            path VARCHAR,
            created_at TIMESTAMP,
            updated_at TIMESTAMP,
            reading TEXT
        )
    """)

    # Marcações feitas sobre as páginas do PDF
    conn.execute("""
        CREATE TABLE IF NOT EXISTS study_highlights (
            id VARCHAR PRIMARY KEY,
            document_id VARCHAR,
            page INTEGER,
            color VARCHAR,
            text TEXT,
            rects TEXT,
            created_at TIMESTAMP,
            updated_at TIMESTAMP
        )
    """)

    # Snapshot das sessões do gerador (texto, cartões, questões, vínculo com PDF)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS study_sessions (
            id VARCHAR PRIMARY KEY,
            title VARCHAR,
            document_id VARCHAR,
            created_at TIMESTAMP,
            updated_at TIMESTAMP,
            cards_count INTEGER,
            questions_count INTEGER,
            payload TEXT
        )
    """)

    return conn


def _loads(raw, fallback):
    try:
        value = json.loads(raw) if raw else fallback
    except (TypeError, ValueError):
        return fallback
    return value if isinstance(value, type(fallback)) else fallback


def _iso(value) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value or "")


# ============================================================
# Documentos
# ============================================================
def _document_from_row(row) -> Dict:
    return {
        "id": row[0],
        "name": row[1],
        "size": int(row[2] or 0),
        "pages": int(row[3] or 0),
        "created_at": _iso(row[5]),
        "updated_at": _iso(row[6]),
        "reading": _loads(row[7], {}),
    }


def save_document(content: bytes, name: str, pages: int = 0) -> Dict:
    """Grava o PDF em disco (dedup por sha256) e registra/atualiza o metadado."""
    digest = hashlib.sha256(content).hexdigest()
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    path = PDF_DIR / f"{digest}.pdf"
    if not path.exists():
        path.write_bytes(content)

    conn = _connect()
    try:
        existing = conn.execute(
            "SELECT created_at, reading, pages FROM study_documents WHERE id = ?", [digest]
        ).fetchone()
        created_at = existing[0] if existing else _now()
        reading = existing[1] if existing else "{}"
        # Reabrir o mesmo PDF não deve zerar a contagem de páginas já conhecida
        page_count = pages or (int(existing[2] or 0) if existing else 0)

        conn.execute("DELETE FROM study_documents WHERE id = ?", [digest])
        conn.execute(
            """
            INSERT INTO study_documents
                (id, name, size, pages, path, created_at, updated_at, reading)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [digest, name, len(content), page_count, str(path), created_at, _now(), reading],
        )
        row = conn.execute(
            "SELECT id, name, size, pages, path, created_at, updated_at, reading FROM study_documents WHERE id = ?",
            [digest],
        ).fetchone()
        return _document_from_row(row)
    finally:
        conn.close()


def get_document(doc_id: str) -> Optional[Dict]:
    validate_document_id(doc_id)
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT id, name, size, pages, path, created_at, updated_at, reading FROM study_documents WHERE id = ?",
            [doc_id],
        ).fetchone()
        return _document_from_row(row) if row else None
    finally:
        conn.close()


def list_documents(limit: int = 50) -> List[Dict]:
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT d.id, d.name, d.size, d.pages, d.path, d.created_at, d.updated_at, d.reading,
                   (SELECT COUNT(*) FROM study_highlights h WHERE h.document_id = d.id)
            FROM study_documents d
            ORDER BY d.updated_at DESC
            LIMIT ?
            """,
            [limit],
        ).fetchall()
        return [{**_document_from_row(r), "highlights_count": int(r[8] or 0)} for r in rows]
    finally:
        conn.close()


def document_file_path(doc_id: str) -> Optional[Path]:
    """Caminho do PDF em disco, ou None se o registro/arquivo não existir."""
    validate_document_id(doc_id)
    conn = _connect()
    try:
        row = conn.execute("SELECT path FROM study_documents WHERE id = ?", [doc_id]).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    path = Path(row[0])
    return path if path.exists() else None


def delete_document(doc_id: str) -> bool:
    validate_document_id(doc_id)
    path = document_file_path(doc_id)
    conn = _connect()
    try:
        conn.execute("DELETE FROM study_highlights WHERE document_id = ?", [doc_id])
        conn.execute("DELETE FROM study_documents WHERE id = ?", [doc_id])
    finally:
        conn.close()
    if path:
        try:
            path.unlink()
        except OSError:
            pass  # arquivo em uso/removido — o registro já saiu
    return True


def save_reading(doc_id: str, reading: Dict) -> Dict:
    """Guarda a posição de leitura (página, zoom, preferências) do documento."""
    validate_document_id(doc_id)
    payload = json.dumps(reading or {})
    conn = _connect()
    try:
        updated = conn.execute(
            "UPDATE study_documents SET reading = ?, updated_at = ? WHERE id = ?",
            [payload, _now(), doc_id],
        )
        # DuckDB não expõe rowcount de UPDATE de forma portátil: confere depois
        del updated
        row = conn.execute("SELECT id FROM study_documents WHERE id = ?", [doc_id]).fetchone()
        if not row:
            raise StudyStoreError("Documento não encontrado")
        return reading or {}
    finally:
        conn.close()


# ============================================================
# Marcações
# ============================================================
def _highlight_from_row(row) -> Dict:
    return {
        "id": row[0],
        "page": int(row[2] or 1),
        "color": row[3] or "yellow",
        "text": row[4] or "",
        "rects": _loads(row[5], []),
    }


def get_highlights(doc_id: str) -> List[Dict]:
    validate_document_id(doc_id)
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT id, document_id, page, color, text, rects, created_at, updated_at
            FROM study_highlights
            WHERE document_id = ?
            ORDER BY page, created_at
            """,
            [doc_id],
        ).fetchall()
        return [_highlight_from_row(r) for r in rows]
    finally:
        conn.close()


def save_highlights(doc_id: str, highlights: List[Dict]) -> List[Dict]:
    """Substitui todas as marcações do documento pela lista recebida."""
    validate_document_id(doc_id)
    items = list(highlights or [])[:MAX_HIGHLIGHTS]
    now = _now()

    rows = []
    for index, h in enumerate(items):
        if not isinstance(h, dict):
            continue
        hl_id = str(h.get("id") or "")[:80] or f"{doc_id[:8]}_{index}_{int(now.timestamp() * 1000)}"
        rects = h.get("rects")
        rows.append([
            hl_id,
            doc_id,
            int(h.get("page") or 1),
            str(h.get("color") or "yellow")[:24],
            str(h.get("text") or ""),
            json.dumps(rects if isinstance(rects, list) else []),
            now,
            now,
        ])

    conn = _connect()
    try:
        conn.execute("DELETE FROM study_highlights WHERE document_id = ?", [doc_id])
        for row in rows:
            conn.execute(
                """
                INSERT INTO study_highlights
                    (id, document_id, page, color, text, rects, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                row,
            )
        conn.execute(
            "UPDATE study_documents SET updated_at = ? WHERE id = ?", [now, doc_id]
        )
    finally:
        conn.close()

    return get_highlights(doc_id)


# ============================================================
# Sessões do gerador
# ============================================================
def _session_from_row(row) -> Dict:
    payload = _loads(row[7], {})
    # Os carimbos originais do front (ISO com fuso) mandam: as colunas servem
    # para ordenar, mas devolvê-las como naive faria o cliente ler local como UTC
    return {
        **payload,
        "id": row[0],
        "title": row[1] or payload.get("title") or "Sessão",
        "documentId": row[2] or payload.get("documentId") or "",
        "createdAt": payload.get("createdAt") or _iso(row[3]),
        "updatedAt": payload.get("updatedAt") or _iso(row[4]),
    }


def list_sessions(limit: int = MAX_SESSIONS) -> List[Dict]:
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT id, title, document_id, created_at, updated_at, cards_count, questions_count, payload
            FROM study_sessions
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            [limit],
        ).fetchall()
        return [_session_from_row(r) for r in rows]
    finally:
        conn.close()


def _parse_stamp(value, fallback: datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except (TypeError, ValueError):
        return fallback


def save_session(session: Dict) -> Dict:
    """Insere ou atualiza o snapshot de uma sessão."""
    session = session or {}
    session_id = validate_session_id(str(session.get("id") or ""))
    now = _now()

    created_at = _parse_stamp(session.get("createdAt"), now)
    updated_at = _parse_stamp(session.get("updatedAt"), now)
    cards = session.get("cards")
    questions = session.get("questionCards")

    conn = _connect()
    try:
        existing = conn.execute(
            "SELECT created_at FROM study_sessions WHERE id = ?", [session_id]
        ).fetchone()
        if existing:
            created_at = existing[0]

        conn.execute("DELETE FROM study_sessions WHERE id = ?", [session_id])
        conn.execute(
            """
            INSERT INTO study_sessions
                (id, title, document_id, created_at, updated_at, cards_count, questions_count, payload)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                session_id,
                str(session.get("title") or "Sessão")[:200],
                str((session.get("pdf") or {}).get("documentId") or "")[:64],
                created_at,
                updated_at,
                len(cards) if isinstance(cards, list) else 0,
                len(questions) if isinstance(questions, list) else 0,
                json.dumps(session, ensure_ascii=False),
            ],
        )

        # Mantém o histórico enxuto: só as N sessões mais recentes ficam
        conn.execute(
            """
            DELETE FROM study_sessions WHERE id IN (
                SELECT id FROM study_sessions ORDER BY updated_at DESC OFFSET ?
            )
            """,
            [MAX_SESSIONS],
        )

        row = conn.execute(
            """
            SELECT id, title, document_id, created_at, updated_at, cards_count, questions_count, payload
            FROM study_sessions WHERE id = ?
            """,
            [session_id],
        ).fetchone()
        return _session_from_row(row)
    finally:
        conn.close()


def delete_session(session_id: str) -> bool:
    validate_session_id(session_id)
    conn = _connect()
    try:
        conn.execute("DELETE FROM study_sessions WHERE id = ?", [session_id])
    finally:
        conn.close()
    return True


def clear_sessions() -> int:
    conn = _connect()
    try:
        total = conn.execute("SELECT COUNT(*) FROM study_sessions").fetchone()[0]
        conn.execute("DELETE FROM study_sessions")
        return int(total or 0)
    finally:
        conn.close()


def get_stats() -> Dict:
    conn = _connect()
    try:
        documents = conn.execute("SELECT COUNT(*) FROM study_documents").fetchone()[0]
        highlights = conn.execute("SELECT COUNT(*) FROM study_highlights").fetchone()[0]
        sessions = conn.execute("SELECT COUNT(*) FROM study_sessions").fetchone()[0]
    finally:
        conn.close()
    return {
        "documents": int(documents or 0),
        "highlights": int(highlights or 0),
        "sessions": int(sessions or 0),
        "pdf_dir": str(PDF_DIR.absolute()),
        "db_path": str(DB_PATH.absolute()),
    }
