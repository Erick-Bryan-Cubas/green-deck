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
import asyncio
import json
import uuid
import multiprocessing as mp
import queue as std_queue
from sse_starlette.sse import EventSourceResponse

from app.services.document_extractor import (
    document_extractor,
    ExtractionQuality,
    PdfExtractor,
    SUPPORTED_FORMATS,
)
from app.config import DOCUMENT_EXTRACTION_TIMEOUT
from app.api.websocket import extraction_manager

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


class PDFMetadataResponse(BaseModel):
    """Resposta com metadados do PDF (carregamento rapido)."""
    success: bool
    num_pages: int = 0
    file_size: int = 0
    filename: str = ""
    metadata: Dict[str, Any] = {}
    error: Optional[str] = None


class ExtractPagesAsyncResponse(BaseModel):
    """Resposta do endpoint de extração assíncrona via WebSocket."""
    task_id: str
    total_pages: int
    filename: str
    message: str = "Extração iniciada. Conecte-se ao WebSocket para acompanhar o progresso."


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


async def with_timeout(coro, timeout_seconds: int, operation_name: str):
    """Execute coroutine with timeout and helpful error message."""
    try:
        return await asyncio.wait_for(coro, timeout=timeout_seconds)
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail=f"{operation_name} excedeu o tempo limite de {timeout_seconds}s. "
                   f"Tente um arquivo menor, selecione menos páginas, ou use o extrator 'pdfplumber' (mais rápido)."
        )


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


@router.post("/pdf-metadata", response_model=PDFMetadataResponse)
async def get_pdf_metadata(
    file: UploadFile = File(..., description="Arquivo PDF para extrair metadados"),
):
    """
    Obtem APENAS metadados do PDF de forma ULTRA-RAPIDA (< 2 segundos para 13MB).

    Nao processa conteudo, apenas:
    - Numero de paginas
    - Tamanho do arquivo
    - Metadados do documento (titulo, autor, datas)

    Ideal para validar arquivo antes de processamento pesado.

    Returns:
        PDFMetadataResponse com metadados basicos
    """
    filename = file.filename or "document.pdf"
    valid, ext = validate_file_extension(filename)

    if not valid or ext != ".pdf":
        raise HTTPException(
            status_code=400,
            detail="Este endpoint e especifico para PDFs. Use /preview-pages para outros formatos."
        )

    try:
        content = await file.read()
    except Exception as e:
        logger.exception("Erro ao ler arquivo PDF")
        raise HTTPException(status_code=400, detail=f"Erro ao ler arquivo: {str(e)}")

    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Arquivo muito grande. Maximo: {MAX_FILE_SIZE_MB}MB"
        )

    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Arquivo vazio")

    # Executa de forma sincrona em thread pool (ultra-rapido)
    result = await asyncio.to_thread(
        document_extractor.get_pdf_metadata,
        content,
        filename
    )

    if result.error:
        return PDFMetadataResponse(
            success=False,
            error=result.error,
            filename=filename,
            file_size=len(content),
        )

    return PDFMetadataResponse(
        success=True,
        num_pages=result.num_pages,
        file_size=result.file_size,
        filename=result.filename,
        metadata=result.metadata,
    )


class ThumbnailInfo(BaseModel):
    """Informacoes de um thumbnail."""
    page: int
    data: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    error: Optional[str] = None


class PDFThumbnailsResponse(BaseModel):
    """Resposta com thumbnails do PDF."""
    success: bool
    thumbnails: List[ThumbnailInfo] = []
    error: Optional[str] = None


@router.post("/pdf-thumbnails", response_model=PDFThumbnailsResponse)
async def get_pdf_thumbnails(
    file: UploadFile = File(..., description="Arquivo PDF"),
    pages: str = Form(default="1-12", description="Range de paginas: '1-12' ou '1,5,10'"),
    width: int = Form(default=150, description="Largura do thumbnail em pixels"),
):
    """
    Gera thumbnails de paginas especificas do PDF.

    Muito mais rapido que renderizar no frontend.
    Retorna imagens em base64 para renderizacao imediata.

    Args:
        file: Arquivo PDF
        pages: Range de paginas ("1-12") ou lista ("1,5,10")
        width: Largura do thumbnail em pixels (default: 150)

    Returns:
        PDFThumbnailsResponse com lista de thumbnails em base64
    """
    filename = file.filename or "document.pdf"
    valid, ext = validate_file_extension(filename)

    if not valid or ext != ".pdf":
        raise HTTPException(
            status_code=400,
            detail="Este endpoint e especifico para PDFs."
        )

    try:
        content = await file.read()
    except Exception as e:
        logger.exception("Erro ao ler arquivo PDF")
        raise HTTPException(status_code=400, detail=f"Erro ao ler arquivo: {str(e)}")

    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Arquivo muito grande. Maximo: {MAX_FILE_SIZE_MB}MB"
        )

    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Arquivo vazio")

    # Limitar largura para evitar uso excessivo de memoria
    width = min(max(50, width), 300)

    # Gerar thumbnails em thread pool
    thumbnails = await asyncio.to_thread(
        document_extractor.generate_pdf_thumbnails,
        content,
        pages,
        width
    )

    return PDFThumbnailsResponse(
        success=True,
        thumbnails=[ThumbnailInfo(**t) for t in thumbnails],
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
    pdf_extractor: str = Form(
        default="docling",
        description="Extrator para PDFs: 'docling' (melhor estrutura) ou 'pdfplumber' (mais rapido)"
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
        pdf_extractor: Extrator para PDFs
            - "docling": Melhor estrutura, converte para Markdown (padrao)
            - "pdfplumber": Mais rapido, melhor para tabelas

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
        pdf_extractor_enum = PdfExtractor(pdf_extractor)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Extrator invalido: {pdf_extractor}. Use: docling ou pdfplumber"
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

    logger.info(f"Extraindo texto de: {filename} ({len(content)} bytes) com extrator: {pdf_extractor}")

    try:
        # extract_from_bytes is async, call directly with timeout
        result = await with_timeout(
            document_extractor.extract_from_bytes(
                file_bytes=content,
                filename=filename,
                quality=quality_enum,
                chunk_size=chunk_size,
                pdf_extractor=pdf_extractor_enum,
            ),
            DOCUMENT_EXTRACTION_TIMEOUT,
            "Extração de documento"
        )
    except HTTPException:
        # Re-raise timeout errors
        raise
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
        # Preview sem timeout - processamento paralelo interno garante performance
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
    pdf_extractor: str = Form(
        default="docling",
        description="Extrator para PDFs: 'docling' (melhor estrutura) ou 'pdfplumber' (mais rapido)"
    ),
):
    """
    Extrai texto apenas das paginas selecionadas.

    Para PDFs, extrai cada pagina individualmente.
    Para outros formatos, extrai o documento completo (page_numbers e ignorado).

    Args:
        file: Arquivo para upload
        page_numbers: Numeros das paginas a extrair (1-indexed), separados por virgula
        quality: Nivel de limpeza do texto
        pdf_extractor: Extrator para PDFs (docling ou pdfplumber)

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
        pdf_extractor_enum = PdfExtractor(pdf_extractor)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Extrator invalido: {pdf_extractor}. Use: docling ou pdfplumber"
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

    logger.info("Extraindo paginas %s de: %s com extrator: %s", pages_list, filename, pdf_extractor)

    try:
        # extract_pages is async, call directly with timeout
        result = await with_timeout(
            document_extractor.extract_pages(
                file_bytes=content,
                page_numbers=pages_list,
                filename=filename,
                quality=quality_enum,
                pdf_extractor=pdf_extractor_enum,
            ),
            DOCUMENT_EXTRACTION_TIMEOUT,
            "Extração de páginas específicas"
        )
    except HTTPException:
        # Re-raise timeout errors
        raise
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


@router.post("/extract-stream")
async def extract_document_stream(
    file: UploadFile = File(..., description="Arquivo para extracao"),
    quality: str = Form(default="cleaned"),
    pdf_extractor: str = Form(default="docling"),
):
    """
    Stream document extraction with real-time progress updates via Server-Sent Events (SSE).

    This endpoint provides progress feedback during extraction for better UX with large files.
    Progress is simulated based on file size and expected extraction speed.
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
        pdf_extractor_enum = PdfExtractor(pdf_extractor)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Extrator invalido: {pdf_extractor}. Use: docling ou pdfplumber"
        )

    try:
        content = await file.read()
    except Exception as e:
        logger.exception("Erro ao ler arquivo")
        raise HTTPException(status_code=400, detail=f"Erro ao ler arquivo: {str(e)}")

    file_size = len(content)

    if file_size > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Arquivo muito grande. Maximo: {MAX_FILE_SIZE_MB}MB"
        )

    if file_size == 0:
        raise HTTPException(status_code=400, detail="Arquivo vazio")

    # Async generator for SSE events
    async def event_generator():
        try:
            # Send start event
            yield {
                "event": "start",
                "data": json.dumps({
                    "message": "Iniciando extração...",
                    "file_size_mb": round(file_size / (1024 * 1024), 2)
                })
            }

            # Get page count for PDFs to provide better progress estimates
            total_pages = None
            if ext == "pdf":
                try:
                    total_pages = document_extractor._get_pdf_page_count(content)
                    yield {
                        "event": "info",
                        "data": json.dumps({
                            "total_pages": total_pages,
                            "message": f"Documento PDF com {total_pages} páginas"
                        })
                    }
                except Exception:
                    logger.warning("Could not get PDF page count for progress estimation")

            # Create extraction task (extract_from_bytes is async)
            extraction_task = asyncio.create_task(
                with_timeout(
                    document_extractor.extract_from_bytes(
                        file_bytes=content,
                        filename=filename,
                        quality=quality_enum,
                        pdf_extractor=pdf_extractor_enum
                    ),
                    DOCUMENT_EXTRACTION_TIMEOUT,
                    "Extração de documento (streaming)"
                )
            )

            # Simulate progress while extraction runs
            # Estimate extraction speed: ~2 seconds per page for docling, ~0.5s for pdfplumber
            if total_pages:
                seconds_per_page = 0.5 if pdf_extractor_enum == PdfExtractor.PDFPLUMBER else 2.0
                estimated_total_time = total_pages * seconds_per_page
                progress_interval = min(2.0, max(0.5, estimated_total_time / 20))  # 20 updates max
            else:
                # For non-PDFs, estimate based on file size (rough estimate: 1MB per second)
                estimated_total_time = max(2, file_size / (1024 * 1024))
                progress_interval = min(2.0, max(0.5, estimated_total_time / 10))

            elapsed = 0
            while not extraction_task.done():
                await asyncio.sleep(progress_interval)
                elapsed += progress_interval

                # Calculate progress (cap at 95% until actually complete)
                if estimated_total_time > 0:
                    progress = min(95, (elapsed / estimated_total_time) * 100)
                else:
                    progress = 50

                if total_pages:
                    current_page = min(total_pages, max(1, int((progress / 100) * total_pages)))
                    message = f"Processando página {current_page} de {total_pages}..."
                else:
                    message = f"Processando documento... {int(progress)}%"

                yield {
                    "event": "progress",
                    "data": json.dumps({
                        "progress_percent": round(progress, 1),
                        "message": message
                    })
                }

            # Get result
            result = await extraction_task

            # Send completion
            logger.info(f"Enviando evento 'complete' para {filename}: {result.word_count} palavras")
            yield {
                "event": "complete",
                "data": json.dumps({
                    "success": True,
                    "text": result.text,
                    "word_count": result.word_count,
                    "total_pages": result.pages,
                    "pages": result.pages,
                    "quality": result.quality.value,
                    "filename": filename,
                    "metadata": result.metadata or {},
                    "message": f"Extração concluída! {result.word_count} palavras extraídas."
                })
            }
            logger.info(f"Evento 'complete' enviado com sucesso para {filename}")

        except HTTPException as e:
            # Timeout or other HTTP errors
            yield {
                "event": "error",
                "data": json.dumps({
                    "error": e.detail,
                    "status_code": e.status_code
                })
            }
        except Exception as e:
            logger.exception("Error in streaming extraction")
            yield {
                "event": "error",
                "data": json.dumps({
                    "error": str(e)
                })
            }

    return EventSourceResponse(event_generator())


@router.post("/extract-pages-stream")
async def extract_pages_stream(
    file: UploadFile = File(..., description="Arquivo para extracao"),
    page_numbers: str = Form(..., description="Numeros das paginas separados por virgula (ex: 1,2,5)"),
    quality: str = Form(default="cleaned"),
    pdf_extractor: str = Form(default="docling"),
):
    """
    Stream extraction of SELECTED PAGES with real-time progress via SSE.

    Processes pages in batches for better progress feedback.
    Each page is processed individually and progress is reported per page.
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
        pdf_extractor_enum = PdfExtractor(pdf_extractor)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Extrator invalido: {pdf_extractor}. Use: docling ou pdfplumber"
        )

    try:
        content = await file.read()
    except Exception as e:
        logger.exception("Erro ao ler arquivo")
        raise HTTPException(status_code=400, detail=f"Erro ao ler arquivo: {str(e)}")

    file_size = len(content)

    if file_size > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Arquivo muito grande. Maximo: {MAX_FILE_SIZE_MB}MB"
        )

    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Arquivo vazio")

    total_pages = len(pages_list)
    logger.info(f"Extraindo {total_pages} paginas selecionadas de: {filename}")

    async def event_generator():
        try:
            # Send start event
            yield {
                "event": "start",
                "data": json.dumps({
                    "message": f"Iniciando extração de {total_pages} páginas...",
                    "total_pages": total_pages,
                    "pages": pages_list
                })
            }

            # Process pages one by one for accurate progress
            all_text_parts = []
            total_words = 0
            pages_content = []
            processed_count = 0

            for page_num in pages_list:
                # Report progress BEFORE processing each page
                progress = (processed_count / total_pages) * 100
                yield {
                    "event": "progress",
                    "data": json.dumps({
                        "progress_percent": round(progress, 1),
                        "message": f"Processando página {page_num}... ({processed_count + 1}/{total_pages})",
                        "current_page": page_num,
                        "processed": processed_count,
                        "total": total_pages
                    })
                }

                # Extract this single page
                try:
                    page_result = await with_timeout(
                        document_extractor.extract_pages(
                            file_bytes=content,
                            page_numbers=[page_num],
                            filename=filename,
                            quality=quality_enum,
                            pdf_extractor=pdf_extractor_enum,
                        ),
                        DOCUMENT_EXTRACTION_TIMEOUT,
                        f"Extração da página {page_num}"
                    )

                    if page_result.text:
                        all_text_parts.append(page_result.text)
                        total_words += page_result.word_count

                    if page_result.pages_content:
                        pages_content.extend(page_result.pages_content)

                    processed_count += 1

                except Exception as page_error:
                    logger.warning(f"Erro na página {page_num}: {page_error}")
                    processed_count += 1  # Still count as processed
                    # Continue with other pages

            # Combine all text
            final_text = "\n\n".join(all_text_parts)

            # Send completion
            logger.info(f"Enviando evento 'complete' para {filename}: {total_words} palavras de {processed_count} paginas")
            yield {
                "event": "complete",
                "data": json.dumps({
                    "success": True,
                    "text": final_text,
                    "word_count": total_words,
                    "total_pages": processed_count,
                    "pages": processed_count,
                    "quality": quality_enum.value,
                    "filename": filename,
                    "pages_content": pages_content,
                    "metadata": {"selected_pages": pages_list},
                    "message": f"Extração concluída! {total_words} palavras de {processed_count} páginas."
                })
            }
            logger.info(f"Evento 'complete' enviado com sucesso para {filename}")

        except HTTPException as e:
            yield {
                "event": "error",
                "data": json.dumps({
                    "error": e.detail,
                    "status_code": e.status_code
                })
            }
        except Exception as e:
            logger.exception("Error in streaming page extraction")
            yield {
                "event": "error",
                "data": json.dumps({
                    "error": str(e)
                })
            }

    return EventSourceResponse(event_generator())


# ============================================================================
# WebSocket-based extraction (real-time progress)
# ============================================================================

@router.post("/extract-pages-async", response_model=ExtractPagesAsyncResponse)
async def extract_pages_async(
    file: UploadFile = File(...),
    page_numbers: str = Form(...),
    quality: str = Form(default="cleaned"),
    pdf_extractor: str = Form(default="docling"),
):
    """
    Inicia extração assíncrona de páginas e retorna task_id.

    O progresso pode ser acompanhado via WebSocket em /ws/extraction.

    Args:
        file: Arquivo PDF para extração
        page_numbers: Lista de páginas separadas por vírgula (ex: "1,2,3")
        quality: Qualidade da extração (raw, cleaned, formatted)
        pdf_extractor: Extrator a usar (docling, pymupdf)

    Returns:
        task_id: ID da tarefa para acompanhar via WebSocket
    """
    filename = file.filename or "document.pdf"
    ext = get_file_extension(filename)

    # Validações
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Formato não suportado: {ext}. Formatos aceitos: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    content = await file.read()
    file_size = len(content)

    if file_size > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"Arquivo muito grande ({file_size / 1024 / 1024:.1f}MB). Máximo: {MAX_FILE_SIZE_MB}MB"
        )

    # Parsear páginas
    try:
        pages_list = [int(p.strip()) for p in page_numbers.split(",") if p.strip()]
        if not pages_list:
            raise ValueError("Lista de páginas vazia")
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Formato de páginas inválido: {page_numbers}. Use números separados por vírgula."
        )

    # Validar enums
    try:
        quality_enum = ExtractionQuality(quality.lower())
    except ValueError:
        quality_enum = ExtractionQuality.CLEANED

    try:
        pdf_extractor_enum = PdfExtractor(pdf_extractor.lower())
    except ValueError:
        pdf_extractor_enum = PdfExtractor.DOCLING

    # Criar task_id e registrar no ExtractionManager
    task_id = str(uuid.uuid4())
    extraction_manager.create_task(task_id, len(pages_list), filename)

    logger.info(f"[Async Extraction] Task {task_id} created for {filename} ({len(pages_list)} pages)")

    # Disparar execução em background e manter referência para cancelamento
    task = asyncio.create_task(
        run_extraction_task(
            task_id,
            content,
            pages_list,
            filename,
            quality_enum,
            pdf_extractor_enum
        )
    )
    extraction_manager.attach_running_task(task_id, task)

    return ExtractPagesAsyncResponse(
        task_id=task_id,
        total_pages=len(pages_list),
        filename=filename
    )


async def run_extraction_task(
    task_id: str,
    content: bytes,
    pages_list: List[int],
    filename: str,
    quality_enum: ExtractionQuality,
    pdf_extractor_enum: PdfExtractor
):
    """
    Executa a extração de páginas em background e notifica via WebSocket.

    Esta função é executada assincronamente após o endpoint retornar.
    O progresso é enviado em tempo real para clientes WebSocket inscritos.
    """
    total_pages = len(pages_list)
    all_texts = []
    pages_content = []
    total_words = 0
    worker_process: Optional[mp.Process] = None
    worker_queue = None

    try:
        logger.info(f"[Async Extraction] Starting task {task_id}: {total_pages} pages")

        # Aguarda um momento para o frontend se inscrever no WebSocket
        # Isso evita race condition onde a extração inicia antes do subscribe
        await asyncio.sleep(0.5)

        if pdf_extractor_enum == PdfExtractor.DOCLING:
            ctx = mp.get_context("spawn")
            worker_queue = ctx.Queue()
            worker_process = ctx.Process(
                target=_docling_extract_worker,
                args=(content, pages_list, filename, quality_enum.value, worker_queue),
                daemon=True,
            )
            worker_process.start()

            finished = False
            while not finished:
                task_status = extraction_manager.get_task_status(task_id)
                if task_status and task_status.get("status") == "cancelled":
                    logger.info("[Async Extraction] Task %s interrupted (cancelled by user)", task_id)
                    return

                try:
                    msg = await asyncio.to_thread(worker_queue.get, True, 0.2)
                except std_queue.Empty:
                    if worker_process is not None and not worker_process.is_alive():
                        finished = True
                    continue

                msg_type = msg.get("type")
                if msg_type == "page_start":
                    index = int(msg.get("index", 1))
                    page_num = int(msg.get("page_num", 0))
                    progress = ((index - 1) / max(1, total_pages)) * 100
                    message = f"Extraindo página {page_num}... ({index}/{total_pages})"
                    await extraction_manager.update_progress(task_id, page_num, progress, message)
                    continue

                if msg_type == "page_done":
                    page_num = int(msg.get("page_num", 0))
                    if msg.get("success"):
                        page_text = msg.get("text") or ""
                        page_words = int(msg.get("word_count", 0))
                        all_texts.append(page_text)
                        total_words += page_words
                        pages_content.append({
                            "page_number": page_num,
                            "text": page_text,
                            "word_count": page_words,
                        })
                    else:
                        pages_content.append({
                            "page_number": page_num,
                            "text": "",
                            "word_count": 0,
                            "error": msg.get("error") or "Erro na extração",
                        })
                    continue

                if msg_type == "worker_error":
                    raise RuntimeError(msg.get("error") or "Erro no worker Docling")

                if msg_type == "done":
                    finished = True

        else:
            for i, page_num in enumerate(pages_list):
                task_status = extraction_manager.get_task_status(task_id)
                if task_status and task_status.get("status") == "cancelled":
                    logger.info(f"[Async Extraction] Task {task_id} interrupted before page loop")
                    return

                progress = ((i + 1) / total_pages) * 100
                message = f"Extraindo página {page_num}... ({i + 1}/{total_pages})"
                await extraction_manager.update_progress(task_id, page_num, progress, message)

                logger.debug(f"[Async Extraction] Task {task_id}: Processing page {page_num} ({progress:.1f}%)")

                try:
                    result = await asyncio.wait_for(
                        document_extractor.extract_pages(
                            file_bytes=content,
                            page_numbers=[page_num],
                            filename=filename,
                            quality=quality_enum,
                            pdf_extractor=pdf_extractor_enum
                        ),
                        timeout=DOCUMENT_EXTRACTION_TIMEOUT
                    )

                    if result.error is None:
                        page_text = result.text
                        page_words = len(page_text.split())

                        all_texts.append(page_text)
                        total_words += page_words

                        pages_content.append({
                            "page_number": page_num,
                            "text": page_text,
                            "word_count": page_words
                        })
                    else:
                        logger.warning(f"[Async Extraction] Page {page_num} failed: {result.error}")
                        pages_content.append({
                            "page_number": page_num,
                            "text": "",
                            "word_count": 0,
                            "error": result.error
                        })

                except asyncio.TimeoutError:
                    logger.error(f"[Async Extraction] Timeout on page {page_num}")
                    pages_content.append({
                        "page_number": page_num,
                        "text": "",
                        "word_count": 0,
                        "error": "Timeout na extração"
                    })
                except Exception as e:
                    logger.error(f"[Async Extraction] Error on page {page_num}: {e}")
                    pages_content.append({
                        "page_number": page_num,
                        "text": "",
                        "word_count": 0,
                        "error": str(e)
                    })

        # Combinar texto final com marcadores de page break
        PAGE_BREAK_MARKER = "\n\n<!-- PAGE_BREAK -->\n\n"
        final_text = PAGE_BREAK_MARKER.join(all_texts)

        # Notificar conclusão via WebSocket
        await extraction_manager.complete_task(task_id, {
            "success": True,
            "text": final_text,
            "word_count": total_words,
            "pages": total_pages,
            "quality": quality_enum.value,
            "filename": filename,
            "pages_content": pages_content,
            "metadata": {"selected_pages": pages_list}
        })

        logger.info(f"[Async Extraction] Task {task_id} completed: {total_words} words from {total_pages} pages")

    except asyncio.CancelledError:
        logger.info(f"[Async Extraction] Task {task_id} cancelled")
        return
    except Exception as e:
        logger.exception(f"[Async Extraction] Task {task_id} failed: {e}")
        await extraction_manager.fail_task(task_id, str(e))
    finally:
        if worker_process is not None and worker_process.is_alive():
            worker_process.terminate()
            worker_process.join(timeout=1.5)
            if worker_process.is_alive():
                worker_process.kill()
                worker_process.join(timeout=1.0)


def _docling_extract_worker(
    content: bytes,
    pages_list: List[int],
    filename: str,
    quality_value: str,
    output_queue,
) -> None:
    """Worker isolado para permitir kill forçado do Docling (GPU/torch)."""

    async def _run() -> None:
        quality = ExtractionQuality(quality_value)

        for index, page_num in enumerate(pages_list, start=1):
            output_queue.put({
                "type": "page_start",
                "index": index,
                "page_num": page_num,
            })

            try:
                result = await asyncio.wait_for(
                    document_extractor.extract_pages(
                        file_bytes=content,
                        page_numbers=[page_num],
                        filename=filename,
                        quality=quality,
                        pdf_extractor=PdfExtractor.DOCLING,
                    ),
                    timeout=DOCUMENT_EXTRACTION_TIMEOUT,
                )

                if result.error is None:
                    page_text = result.text or ""
                    output_queue.put({
                        "type": "page_done",
                        "page_num": page_num,
                        "success": True,
                        "text": page_text,
                        "word_count": len(page_text.split()),
                    })
                else:
                    output_queue.put({
                        "type": "page_done",
                        "page_num": page_num,
                        "success": False,
                        "error": result.error,
                    })

            except asyncio.TimeoutError:
                output_queue.put({
                    "type": "page_done",
                    "page_num": page_num,
                    "success": False,
                    "error": "Timeout na extração",
                })
            except Exception as exc:
                output_queue.put({
                    "type": "page_done",
                    "page_num": page_num,
                    "success": False,
                    "error": str(exc),
                })

    try:
        asyncio.run(_run())
        output_queue.put({"type": "done"})
    except Exception as exc:
        output_queue.put({"type": "worker_error", "error": str(exc)})


@router.post("/extract-cancel/{task_id}")
async def extract_cancel(task_id: str):
    """Cancela uma extração assíncrona em andamento."""
    status = extraction_manager.get_task_status(task_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    cancelled = await extraction_manager.cancel_task(task_id)
    return {
        "success": True,
        "task_id": task_id,
        "cancelled": cancelled,
        "status": extraction_manager.get_task_status(task_id).get("status") if extraction_manager.get_task_status(task_id) else None,
    }
