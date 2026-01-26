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
from sse_starlette.sse import EventSourceResponse
from functools import partial

from app.services.document_extractor import (
    document_extractor,
    ExtractionQuality,
    PdfExtractor,
    SUPPORTED_FORMATS,
)
from app.config import DOCUMENT_EXTRACTION_TIMEOUT, DOCUMENT_PREVIEW_TIMEOUT

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
        # Wrap extraction in thread pool to avoid blocking event loop and add timeout
        result = await with_timeout(
            asyncio.to_thread(
                document_extractor.extract_from_bytes,
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
        # Wrap preview in thread pool and add timeout
        result = await with_timeout(
            asyncio.to_thread(
                document_extractor.get_document_preview,
                file_bytes=content,
                filename=filename,
                preview_chars=300,
            ),
            DOCUMENT_PREVIEW_TIMEOUT,
            "Pré-visualização de páginas"
        )
    except HTTPException:
        # Re-raise timeout errors
        raise
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
        # Wrap page extraction in thread pool and add timeout
        result = await with_timeout(
            asyncio.to_thread(
                document_extractor.extract_pages,
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

            # Create extraction task
            loop = asyncio.get_event_loop()
            extraction_task = asyncio.create_task(
                with_timeout(
                    loop.run_in_executor(
                        None,
                        partial(
                            document_extractor.extract_from_bytes,
                            file_bytes=content,
                            filename=filename,
                            quality=quality_enum,
                            pdf_extractor=pdf_extractor_enum
                        )
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
            yield {
                "event": "complete",
                "data": json.dumps({
                    "success": True,
                    "text": result.text,
                    "word_count": result.word_count,
                    "total_pages": result.total_pages,
                    "pages": result.pages,
                    "quality": result.quality.value,
                    "filename": filename,
                    "metadata": result.metadata or {},
                    "message": f"Extração concluída! {result.word_count} palavras extraídas."
                })
            }

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
