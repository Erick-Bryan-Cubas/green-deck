"""
API endpoints para extração de texto de documentos (PDF, etc).

Este módulo fornece endpoints para upload e extração de texto de documentos,
que podem então ser usados para gerar flashcards.
"""

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import logging

from app.services.pdf_extractor import pdf_extractor, ExtractionQuality

router = APIRouter(prefix="/api/documents", tags=["documents"])
logger = logging.getLogger(__name__)

# Limites de upload
MAX_FILE_SIZE_MB = 50
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
ALLOWED_EXTENSIONS = {".pdf"}


class ExtractionResponse(BaseModel):
    """Resposta da extração de documento."""
    success: bool
    text: str = ""
    pages: int = 0
    word_count: int = 0
    quality: str = "raw"
    chunks: List[str] = []
    filename: str = ""
    error: Optional[str] = None


class ExtractionStatusResponse(BaseModel):
    """Status do serviço de extração."""
    available: bool
    supported_formats: List[str]
    max_file_size_mb: int


@router.get("/status", response_model=ExtractionStatusResponse)
async def get_extraction_status():
    """
    Verifica se o serviço de extração está disponível.
    
    Returns:
        Status do serviço incluindo formatos suportados
    """
    return ExtractionStatusResponse(
        available=pdf_extractor.is_available(),
        supported_formats=["pdf"],
        max_file_size_mb=MAX_FILE_SIZE_MB,
    )


@router.post("/extract", response_model=ExtractionResponse)
async def extract_document(
    file: UploadFile = File(..., description="Arquivo PDF para extração"),
    quality: str = Form(
        default="cleaned",
        description="Qualidade da extração: 'raw', 'cleaned', ou 'llm'"
    ),
    chunk_size: Optional[int] = Form(
        default=None,
        description="Tamanho do chunk em palavras (opcional)"
    ),
):
    """
    Extrai texto de um documento PDF.
    
    O texto extraído pode ser usado diretamente no endpoint de geração
    de flashcards (/api/generate-cards).
    
    Args:
        file: Arquivo PDF para upload
        quality: Nível de limpeza do texto
            - "raw": Texto bruto sem processamento
            - "cleaned": Texto limpo com heurísticas (padrão)
            - "llm": Refinamento via LLM (não implementado ainda)
        chunk_size: Se especificado, divide o texto em chunks de N palavras
    
    Returns:
        ExtractionResponse com o texto extraído
    """
    # Valida extensão do arquivo
    filename = file.filename or "document.pdf"
    extension = "." + filename.split(".")[-1].lower() if "." in filename else ""
    
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Formato não suportado: {extension}. Use: {', '.join(ALLOWED_EXTENSIONS)}"
        )
    
    # Verifica se Docling está disponível
    if not pdf_extractor.is_available():
        raise HTTPException(
            status_code=503,
            detail="Serviço de extração não disponível. Instale docling: pip install docling"
        )
    
    # Valida qualidade
    try:
        quality_enum = ExtractionQuality(quality)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Qualidade inválida: {quality}. Use: raw, cleaned, ou llm"
        )
    
    # Lê o arquivo
    try:
        content = await file.read()
    except Exception as e:
        logger.exception("Erro ao ler arquivo")
        raise HTTPException(status_code=400, detail=f"Erro ao ler arquivo: {str(e)}")
    
    # Valida tamanho
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Arquivo muito grande. Máximo: {MAX_FILE_SIZE_MB}MB"
        )
    
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Arquivo vazio")
    
    # Extrai texto
    logger.info(f"Extraindo texto de: {filename} ({len(content)} bytes)")
    
    try:
        result = await pdf_extractor.extract_from_bytes(
            pdf_bytes=content,
            filename=filename,
            quality=quality_enum,
            chunk_size=chunk_size,
        )
    except Exception as e:
        logger.exception("Erro na extração")
        raise HTTPException(status_code=500, detail=f"Erro na extração: {str(e)}")
    
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
    )


@router.post("/extract-and-preview")
async def extract_and_preview(
    file: UploadFile = File(...),
    max_preview_chars: int = Form(default=2000),
):
    """
    Extrai texto e retorna um preview para confirmação do usuário.
    
    Útil para verificar a qualidade da extração antes de gerar cards.
    
    Args:
        file: Arquivo PDF
        max_preview_chars: Máximo de caracteres no preview
    
    Returns:
        Preview do texto extraído com estatísticas
    """
    # Usa a função principal de extração
    response = await extract_document(file=file, quality="cleaned")
    
    if not response.success:
        return response
    
    # Cria preview truncado
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
    }


class PageInfoResponse(BaseModel):
    """Informações de uma página."""
    page_number: int
    word_count: int
    preview: str


class PdfPreviewResponse(BaseModel):
    """Resposta do preview de páginas do PDF."""
    success: bool
    total_pages: int = 0
    pages: List[PageInfoResponse] = []
    filename: str = ""
    file_size: int = 0
    error: Optional[str] = None


class PagesExtractionRequest(BaseModel):
    """Request para extração de páginas específicas."""
    page_numbers: List[int]
    quality: str = "cleaned"


@router.post("/preview-pages", response_model=PdfPreviewResponse)
async def preview_pdf_pages(
    file: UploadFile = File(..., description="Arquivo PDF para preview"),
):
    """
    Obtém preview de cada página do PDF antes da extração.
    
    Retorna informações sobre cada página incluindo:
    - Número da página
    - Contagem de palavras
    - Preview do texto (primeiros 300 caracteres)
    
    Args:
        file: Arquivo PDF para upload
    
    Returns:
        PdfPreviewResponse com informações de cada página
    """
    filename = file.filename or "document.pdf"
    extension = "." + filename.split(".")[-1].lower() if "." in filename else ""
    
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Formato não suportado: {extension}. Use: {', '.join(ALLOWED_EXTENSIONS)}"
        )
    
    if not pdf_extractor.is_available():
        raise HTTPException(
            status_code=503,
            detail="Serviço de extração não disponível. Instale docling: pip install docling"
        )
    
    try:
        content = await file.read()
    except Exception as e:
        logger.exception("Erro ao ler arquivo")
        raise HTTPException(status_code=400, detail=f"Erro ao ler arquivo: {str(e)}")
    
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Arquivo muito grande. Máximo: {MAX_FILE_SIZE_MB}MB"
        )
    
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Arquivo vazio")
    
    try:
        result = await pdf_extractor.get_pdf_preview(
            pdf_bytes=content,
            filename=filename,
            preview_chars=300,
        )
    except Exception as e:
        logger.exception("Erro ao obter preview")
        raise HTTPException(status_code=500, detail=f"Erro ao obter preview: {str(e)}")
    
    if result.error:
        return PdfPreviewResponse(
            success=False,
            error=result.error,
            filename=filename,
        )
    
    return PdfPreviewResponse(
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
    )


@router.post("/extract-pages", response_model=ExtractionResponse)
async def extract_selected_pages(
    file: UploadFile = File(..., description="Arquivo PDF"),
    page_numbers: str = Form(..., description="Números das páginas separados por vírgula (ex: 1,2,5)"),
    quality: str = Form(default="cleaned"),
):
    """
    Extrai texto apenas das páginas selecionadas.
    
    Args:
        file: Arquivo PDF para upload
        page_numbers: Números das páginas a extrair (1-indexed), separados por vírgula
        quality: Nível de limpeza do texto
    
    Returns:
        ExtractionResponse com o texto das páginas selecionadas
    """
    filename = file.filename or "document.pdf"
    extension = "." + filename.split(".")[-1].lower() if "." in filename else ""
    
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Formato não suportado: {extension}. Use: {', '.join(ALLOWED_EXTENSIONS)}"
        )
    
    if not pdf_extractor.is_available():
        raise HTTPException(
            status_code=503,
            detail="Serviço de extração não disponível. Instale docling: pip install docling"
        )
    
    # Parse page numbers
    try:
        pages_list = [int(p.strip()) for p in page_numbers.split(",") if p.strip()]
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Formato inválido para page_numbers. Use números separados por vírgula."
        )
    
    if not pages_list:
        raise HTTPException(status_code=400, detail="Nenhuma página especificada")
    
    try:
        quality_enum = ExtractionQuality(quality)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Qualidade inválida: {quality}. Use: raw, cleaned, ou llm"
        )
    
    try:
        content = await file.read()
    except Exception as e:
        logger.exception("Erro ao ler arquivo")
        raise HTTPException(status_code=400, detail=f"Erro ao ler arquivo: {str(e)}")
    
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Arquivo muito grande. Máximo: {MAX_FILE_SIZE_MB}MB"
        )
    
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Arquivo vazio")
    
    logger.info("Extraindo páginas %s de: %s", pages_list, filename)
    
    try:
        result = await pdf_extractor.extract_pages(
            pdf_bytes=content,
            page_numbers=pages_list,
            filename=filename,
            quality=quality_enum,
        )
    except Exception as e:
        logger.exception("Erro na extração de páginas")
        raise HTTPException(status_code=500, detail=f"Erro na extração: {str(e)}")
    
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
    )
