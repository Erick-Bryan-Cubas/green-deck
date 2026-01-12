"""
API endpoints para extracao de texto de documentos.

Este modulo fornece endpoints para upload e extracao de texto de documentos,
que podem entao ser usados para gerar flashcards.

Formatos suportados (via Docling):
- PDF
- DOCX, DOC (Microsoft Word)
- PPTX, PPT (Microsoft PowerPoint)
- XLSX, XLS (Microsoft Excel)
- HTML
- Markdown
- AsciiDoc
- Imagens (PNG, JPG, TIFF, BMP) via OCR
"""

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import logging

from app.services.document_extractor import (
    document_extractor,
    ExtractionQuality,
    SUPPORTED_FORMATS,
)

router = APIRouter(prefix="/api/documents", tags=["documents"])
logger = logging.getLogger(__name__)

# Limites de upload
MAX_FILE_SIZE_MB = 50
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

# Extensoes permitidas (todas suportadas pelo Docling)
ALLOWED_EXTENSIONS = set(SUPPORTED_FORMATS.keys())


class PageContent(BaseModel):
    """Conteudo de uma pagina extraida."""
    page_number: int
    text: str
    word_count: int


class ExtractionResponse(BaseModel):
    """Resposta da extracao de documento."""
    success: bool
    text: str = ""
    pages: int = 0
    word_count: int = 0
    quality: str = "raw"
    chunks: List[str] = []
    filename: str = ""
    pages_content: List[PageContent] = []
    metadata: Dict[str, Any] = {}
    error: Optional[str] = None


class ExtractionStatusResponse(BaseModel):
    """Status do servico de extracao."""
    available: bool
    supported_formats: List[str]
    format_descriptions: Dict[str, str]
    max_file_size_mb: int


class PageInfoResponse(BaseModel):
    """Informacoes de uma pagina."""
    page_number: int
    word_count: int
    preview: str


class DocumentPreviewResponse(BaseModel):
    """Resposta do preview de paginas do documento."""
    success: bool
    total_pages: int = 0
    pages: List[PageInfoResponse] = []
    filename: str = ""
    file_size: int = 0
    format_type: str = ""
    error: Optional[str] = None


def get_file_extension(filename: str) -> str:
    """Extrai a extensao do arquivo de forma segura."""
    if not filename or "." not in filename:
        return ""
    return "." + filename.rsplit(".", 1)[-1].lower()


def validate_file_extension(filename: str) -> tuple[bool, str]:
    """Valida a extensao do arquivo e retorna (valido, extensao)."""
    ext = get_file_extension(filename)
    if ext not in ALLOWED_EXTENSIONS:
        return False, ext
    return True, ext


@router.get("/status", response_model=ExtractionStatusResponse)
async def get_extraction_status():
    """
    Verifica se o servico de extracao esta disponivel.

    Returns:
        Status do servico incluindo formatos suportados
    """
    return ExtractionStatusResponse(
        available=document_extractor.is_available(),
        supported_formats=list(SUPPORTED_FORMATS.keys()),
        format_descriptions=SUPPORTED_FORMATS,
        max_file_size_mb=MAX_FILE_SIZE_MB,
    )


@router.post("/extract", response_model=ExtractionResponse)
async def extract_document(
    file: UploadFile = File(..., description="Arquivo para extracao"),
    quality: str = Form(
        default="cleaned",
        description="Qualidade da extracao: 'raw', 'cleaned', ou 'llm'"
    ),
    chunk_size: Optional[int] = Form(
        default=None,
        description="Tamanho do chunk em palavras (opcional)"
    ),
):
    """
    Extrai texto de um documento.

    Formatos suportados:
    - PDF
    - DOCX, DOC (Microsoft Word)
    - PPTX, PPT (Microsoft PowerPoint)
    - XLSX, XLS (Microsoft Excel)
    - HTML, HTM
    - Markdown (.md)
    - AsciiDoc (.adoc)
    - Imagens (PNG, JPG, JPEG, TIFF, BMP) via OCR

    Args:
        file: Arquivo para upload
        quality: Nivel de limpeza do texto
            - "raw": Texto bruto sem processamento
            - "cleaned": Texto limpo com heuristicas (padrao)
            - "llm": Refinamento via LLM (nao implementado ainda)
        chunk_size: Se especificado, divide o texto em chunks de N palavras

    Returns:
        ExtractionResponse com o texto extraido
    """
    filename = file.filename or "document"
    valid, ext = validate_file_extension(filename)

    if not valid:
        raise HTTPException(
            status_code=400,
            detail=f"Formato nao suportado: {ext}. Formatos validos: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    if not document_extractor.is_available():
        raise HTTPException(
            status_code=503,
            detail="Servico de extracao nao disponivel. Instale docling: pip install docling"
        )

    try:
        quality_enum = ExtractionQuality(quality)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Qualidade invalida: {quality}. Use: raw, cleaned, ou llm"
        )

    try:
        content = await file.read()
    except Exception as e:
        logger.exception("Erro ao ler arquivo")
        raise HTTPException(status_code=400, detail=f"Erro ao ler arquivo: {str(e)}")

    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Arquivo muito grande. Maximo: {MAX_FILE_SIZE_MB}MB"
        )

    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Arquivo vazio")

    logger.info(f"Extraindo texto de: {filename} ({len(content)} bytes)")

    try:
        result = await document_extractor.extract_from_bytes(
            file_bytes=content,
            filename=filename,
            quality=quality_enum,
            chunk_size=chunk_size,
        )
    except Exception as e:
        logger.exception("Erro na extracao")
        raise HTTPException(status_code=500, detail=f"Erro na extracao: {str(e)}")

    if result.error:
        return ExtractionResponse(
            success=False,
            error=result.error,
            filename=filename,
        )

    return ExtractionResponse(
        success=True,
        text=result.text,
        pages=result.pages,
        word_count=result.word_count,
        quality=result.quality.value,
        chunks=result.chunks,
        filename=filename,
        metadata=result.metadata,
    )


@router.post("/extract-and-preview")
async def extract_and_preview(
    file: UploadFile = File(...),
    max_preview_chars: int = Form(default=2000),
):
    """
    Extrai texto e retorna um preview para confirmacao do usuario.

    Util para verificar a qualidade da extracao antes de gerar cards.

    Args:
        file: Arquivo do documento
        max_preview_chars: Maximo de caracteres no preview

    Returns:
        Preview do texto extraido com estatisticas
    """
    response = await extract_document(file=file, quality="cleaned")

    if not response.success:
        return response

    full_text = response.text
    preview = full_text[:max_preview_chars]
    if len(full_text) > max_preview_chars:
        preview += "\n\n[...texto truncado para preview...]"

    return {
        "success": True,
        "preview": preview,
        "full_text": full_text,
        "pages": response.pages,
        "word_count": response.word_count,
        "quality": response.quality,
        "filename": response.filename,
        "is_truncated": len(full_text) > max_preview_chars,
        "metadata": response.metadata,
    }


@router.post("/preview-pages", response_model=DocumentPreviewResponse)
async def preview_document_pages(
    file: UploadFile = File(..., description="Arquivo para preview"),
):
    """
    Obtem preview de cada pagina do documento antes da extracao.

    Retorna informacoes sobre cada pagina incluindo:
    - Numero da pagina
    - Contagem de palavras
    - Preview do texto (primeiros 300 caracteres)

    Para documentos nao paginados (Word, HTML, etc), retorna o documento
    como uma unica pagina.

    Args:
        file: Arquivo para upload

    Returns:
        DocumentPreviewResponse com informacoes de cada pagina
    """
    filename = file.filename or "document"
    valid, ext = validate_file_extension(filename)

    if not valid:
        raise HTTPException(
            status_code=400,
            detail=f"Formato nao suportado: {ext}. Formatos validos: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    if not document_extractor.is_available():
        raise HTTPException(
            status_code=503,
            detail="Servico de extracao nao disponivel. Instale docling: pip install docling"
        )

    try:
        content = await file.read()
    except Exception as e:
        logger.exception("Erro ao ler arquivo")
        raise HTTPException(status_code=400, detail=f"Erro ao ler arquivo: {str(e)}")

    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Arquivo muito grande. Maximo: {MAX_FILE_SIZE_MB}MB"
        )

    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Arquivo vazio")

    try:
        result = await document_extractor.get_document_preview(
            file_bytes=content,
            filename=filename,
            preview_chars=300,
        )
    except Exception as e:
        logger.exception("Erro ao obter preview")
        raise HTTPException(status_code=500, detail=f"Erro ao obter preview: {str(e)}")

    if result.error:
        return DocumentPreviewResponse(
            success=False,
            error=result.error,
            filename=filename,
        )

    return DocumentPreviewResponse(
        success=True,
        total_pages=result.total_pages,
        pages=[
            PageInfoResponse(
                page_number=p.page_number,
                word_count=p.word_count,
                preview=p.preview,
            )
            for p in result.pages
        ],
        filename=result.filename,
        file_size=result.file_size,
        format_type=result.format_type,
    )


@router.post("/extract-pages", response_model=ExtractionResponse)
async def extract_selected_pages(
    file: UploadFile = File(..., description="Arquivo do documento"),
    page_numbers: str = Form(..., description="Numeros das paginas separados por virgula (ex: 1,2,5)"),
    quality: str = Form(default="cleaned"),
):
    """
    Extrai texto apenas das paginas selecionadas.

    Para PDFs, extrai cada pagina individualmente.
    Para outros formatos, extrai o documento completo (page_numbers e ignorado).

    Args:
        file: Arquivo para upload
        page_numbers: Numeros das paginas a extrair (1-indexed), separados por virgula
        quality: Nivel de limpeza do texto

    Returns:
        ExtractionResponse com o texto das paginas selecionadas
    """
    filename = file.filename or "document"
    valid, ext = validate_file_extension(filename)

    if not valid:
        raise HTTPException(
            status_code=400,
            detail=f"Formato nao suportado: {ext}. Formatos validos: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    if not document_extractor.is_available():
        raise HTTPException(
            status_code=503,
            detail="Servico de extracao nao disponivel. Instale docling: pip install docling"
        )

    try:
        pages_list = [int(p.strip()) for p in page_numbers.split(",") if p.strip()]
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Formato invalido para page_numbers. Use numeros separados por virgula."
        )

    if not pages_list:
        raise HTTPException(status_code=400, detail="Nenhuma pagina especificada")

    try:
        quality_enum = ExtractionQuality(quality)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Qualidade invalida: {quality}. Use: raw, cleaned, ou llm"
        )

    try:
        content = await file.read()
    except Exception as e:
        logger.exception("Erro ao ler arquivo")
        raise HTTPException(status_code=400, detail=f"Erro ao ler arquivo: {str(e)}")

    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Arquivo muito grande. Maximo: {MAX_FILE_SIZE_MB}MB"
        )

    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Arquivo vazio")

    logger.info("Extraindo paginas %s de: %s", pages_list, filename)

    try:
        result = await document_extractor.extract_pages(
            file_bytes=content,
            page_numbers=pages_list,
            filename=filename,
            quality=quality_enum,
        )
    except Exception as e:
        logger.exception("Erro na extracao de paginas")
        raise HTTPException(status_code=500, detail=f"Erro na extracao: {str(e)}")

    if result.error:
        return ExtractionResponse(
            success=False,
            error=result.error,
            filename=filename,
        )

    pages_content_list = [
        PageContent(
            page_number=p["page_number"],
            text=p["text"],
            word_count=p["word_count"]
        )
        for p in result.pages_content
    ] if result.pages_content else []

    return ExtractionResponse(
        success=True,
        text=result.text,
        pages=result.pages,
        word_count=result.word_count,
        quality=result.quality.value,
        chunks=result.chunks,
        filename=filename,
        pages_content=pages_content_list,
        metadata=result.metadata,
    )
