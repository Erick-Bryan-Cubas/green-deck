"""
Document Text Extraction Service using Docling.

Este modulo fornece extracao de texto de documentos usando a biblioteca Docling,
com suporte para multiplos formatos: PDF, DOCX, PPTX, XLSX, HTML, Markdown, AsciiDoc, e imagens.
"""

import logging
import tempfile
import os
import asyncio
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class ExtractionQuality(str, Enum):
    """Qualidade da extracao de texto."""
    RAW = "raw"           # Texto bruto sem processamento
    CLEANED = "cleaned"   # Texto limpo com heuristicas
    LLM = "llm"          # Texto refinado via LLM


class PdfExtractor(str, Enum):
    """Extrator a ser usado para PDFs."""
    DOCLING = "docling"       # Docling: melhor estrutura, converte para Markdown
    PDFPLUMBER = "pdfplumber" # pdfplumber: mais rapido, melhor para tabelas


# Formatos suportados pelo Docling
# Referencia: https://ds4sd.github.io/docling/
SUPPORTED_FORMATS = {
    # Documentos
    ".pdf": "PDF Document",
    ".docx": "Microsoft Word",
    ".doc": "Microsoft Word (Legacy)",
    ".pptx": "Microsoft PowerPoint",
    ".ppt": "Microsoft PowerPoint (Legacy)",
    ".xlsx": "Microsoft Excel",
    ".xls": "Microsoft Excel (Legacy)",
    # Markup
    ".html": "HTML Document",
    ".htm": "HTML Document",
    ".md": "Markdown",
    ".markdown": "Markdown",
    ".adoc": "AsciiDoc",
    ".asciidoc": "AsciiDoc",
    # Imagens (OCR)
    ".png": "PNG Image",
    ".jpg": "JPEG Image",
    ".jpeg": "JPEG Image",
    ".tiff": "TIFF Image",
    ".tif": "TIFF Image",
    ".bmp": "Bitmap Image",
}

# Formatos que suportam paginacao
PAGINATED_FORMATS = {".pdf", ".pptx", ".ppt"}

# Formatos de imagem (requerem OCR)
IMAGE_FORMATS = {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"}


@dataclass
class ExtractionResult:
    """Resultado da extracao de texto de um documento."""
    text: str
    pages: int = 0
    word_count: int = 0
    quality: ExtractionQuality = ExtractionQuality.RAW
    metadata: Dict[str, Any] = field(default_factory=dict)
    chunks: List[str] = field(default_factory=list)
    pages_content: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "pages": self.pages,
            "word_count": self.word_count,
            "quality": self.quality.value,
            "metadata": self.metadata,
            "chunks": self.chunks,
            "pages_content": self.pages_content,
            "error": self.error,
        }


@dataclass
class PageInfo:
    """Informacoes de uma pagina do documento."""
    page_number: int
    word_count: int
    preview: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "page_number": self.page_number,
            "word_count": self.word_count,
            "preview": self.preview,
        }


@dataclass
class DocumentPreviewResult:
    """Resultado do preview de um documento."""
    total_pages: int
    pages: List[PageInfo]
    filename: str
    file_size: int
    format_type: str = ""
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_pages": self.total_pages,
            "pages": [p.to_dict() for p in self.pages],
            "filename": self.filename,
            "file_size": self.file_size,
            "format_type": self.format_type,
            "error": self.error,
        }


@dataclass
class PDFMetadataResult:
    """Resultado dos metadados do PDF (carregamento rápido)."""
    num_pages: int
    file_size: int
    filename: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "num_pages": self.num_pages,
            "file_size": self.file_size,
            "filename": self.filename,
            "metadata": self.metadata,
            "error": self.error,
        }


class DocumentExtractor:
    """
    Extrator de texto de documentos usando Docling.

    Docling e uma biblioteca da IBM que converte documentos em formatos
    estruturados como Markdown, preservando layout e estrutura.

    Formatos suportados:
    - PDF
    - DOCX, DOC (Microsoft Word)
    - PPTX, PPT (Microsoft PowerPoint)
    - XLSX, XLS (Microsoft Excel)
    - HTML
    - Markdown
    - AsciiDoc
    - Imagens (PNG, JPG, TIFF, BMP) via OCR
    """

    def __init__(self):
        self._docling_available = False
        self._pdfplumber_available = False
        self._pikepdf_available = False
        self._converter = None
        self._check_docling()
        self._check_pdfplumber()
        self._check_pikepdf()

    def _check_docling(self):
        """Verifica se Docling esta disponivel."""
        try:
            from docling.document_converter import DocumentConverter  # noqa: F401
            self._docling_available = True
            logger.info("Docling disponivel para extracao de documentos")
        except ImportError:
            self._docling_available = False
            logger.warning(
                "Docling nao instalado. Instale com: pip install docling"
            )

    def _check_pdfplumber(self):
        """Verifica se pdfplumber esta disponivel para extracao de texto de PDFs."""
        try:
            import pdfplumber  # noqa: F401
            self._pdfplumber_available = True
            logger.info("pdfplumber disponivel para extracao de texto de PDFs")
        except ImportError:
            self._pdfplumber_available = False
            logger.warning(
                "pdfplumber nao instalado. Instale com: pip install pdfplumber"
            )

    def _check_pikepdf(self):
        """Verifica se pikepdf esta disponivel para manipulacao de PDFs."""
        try:
            import pikepdf  # noqa: F401
            self._pikepdf_available = True
            logger.info("pikepdf disponivel para manipulacao de PDFs")
        except ImportError:
            self._pikepdf_available = False
            logger.warning(
                "pikepdf nao instalado. Instale com: pip install pikepdf"
            )

    def _get_converter(self):
        """Lazy initialization do converter Docling."""
        if self._converter is None and self._docling_available:
            from docling.document_converter import DocumentConverter  # noqa: F811
            self._converter = DocumentConverter()
        return self._converter

    def get_supported_formats(self) -> Dict[str, str]:
        """Retorna dicionario de formatos suportados."""
        return SUPPORTED_FORMATS.copy()

    def get_supported_extensions(self) -> List[str]:
        """Retorna lista de extensoes suportadas."""
        return list(SUPPORTED_FORMATS.keys())

    def is_supported_format(self, filename: str) -> bool:
        """Verifica se o formato do arquivo e suportado."""
        ext = Path(filename).suffix.lower()
        return ext in SUPPORTED_FORMATS

    def is_paginated_format(self, filename: str) -> bool:
        """Verifica se o formato suporta paginacao."""
        ext = Path(filename).suffix.lower()
        return ext in PAGINATED_FORMATS

    def is_image_format(self, filename: str) -> bool:
        """Verifica se o formato e uma imagem (requer OCR)."""
        ext = Path(filename).suffix.lower()
        return ext in IMAGE_FORMATS

    def _extract_pages_from_pdf(
        self,
        pdf_bytes: bytes,
        page_numbers: List[int]
    ) -> bytes:
        """
        Cria um novo PDF contendo apenas as paginas selecionadas.

        Args:
            pdf_bytes: Bytes do PDF original
            page_numbers: Lista de numeros de paginas (1-indexed)

        Returns:
            Bytes do novo PDF com apenas as paginas selecionadas
        """
        import pikepdf
        from io import BytesIO

        with pikepdf.open(BytesIO(pdf_bytes)) as pdf:
            new_pdf = pikepdf.Pdf.new()
            total_pages = len(pdf.pages)

            for page_num in sorted(page_numbers):
                if 1 <= page_num <= total_pages:
                    new_pdf.pages.append(pdf.pages[page_num - 1])

            output = BytesIO()
            new_pdf.save(output)
            output.seek(0)

            return output.read()

    def _get_pdf_page_count(self, pdf_bytes: bytes) -> int:
        """Obtem o numero total de paginas do PDF."""
        import pdfplumber
        from io import BytesIO

        with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
            return len(pdf.pages)

    def get_pdf_metadata(self, pdf_bytes: bytes, filename: str) -> PDFMetadataResult:
        """
        Obtem APENAS metadados do PDF de forma ultra-rapida (< 100ms).

        Nao processa conteudo das paginas, apenas le headers do PDF.
        Ideal para validar arquivo antes de processamento pesado.

        Args:
            pdf_bytes: Conteudo binario do PDF
            filename: Nome do arquivo

        Returns:
            PDFMetadataResult com numero de paginas e metadados basicos
        """
        import pdfplumber
        from io import BytesIO

        try:
            with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
                num_pages = len(pdf.pages)
                raw_metadata = pdf.metadata or {}

                # Extrair metadados relevantes
                metadata = {
                    "title": raw_metadata.get("Title", ""),
                    "author": raw_metadata.get("Author", ""),
                    "creator": raw_metadata.get("Creator", ""),
                    "producer": raw_metadata.get("Producer", ""),
                    "creation_date": str(raw_metadata.get("CreationDate", "")),
                    "modification_date": str(raw_metadata.get("ModDate", "")),
                }

                logger.info(f"PDF metadata extraido: {filename} - {num_pages} paginas")

                return PDFMetadataResult(
                    num_pages=num_pages,
                    file_size=len(pdf_bytes),
                    filename=filename,
                    metadata=metadata,
                )

        except Exception as e:
            logger.exception(f"Erro ao obter metadados do PDF {filename}: {e}")
            return PDFMetadataResult(
                num_pages=0,
                file_size=len(pdf_bytes),
                filename=filename,
                error=f"Erro ao ler PDF: {str(e)}",
            )

    def generate_pdf_thumbnails(
        self,
        pdf_bytes: bytes,
        pages_str: str = "1-12",
        width: int = 150,
    ) -> List[Dict[str, Any]]:
        """
        Gera thumbnails de paginas especificas do PDF usando pymupdf.

        Muito mais rapido que renderizar no frontend com pdfjs.
        Retorna imagens em base64 para renderizacao imediata.

        Args:
            pdf_bytes: Conteudo binario do PDF
            pages_str: Range de paginas ("1-12") ou lista ("1,5,10")
            width: Largura do thumbnail em pixels

        Returns:
            Lista de dicts com {page, data (base64), width, height}
        """
        try:
            import fitz  # pymupdf
            import base64

            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            total_pages = len(doc)
            thumbnails = []

            # Parse pages string
            page_numbers = self._parse_page_range(pages_str, total_pages)

            for page_num in page_numbers:
                if page_num < 1 or page_num > total_pages:
                    continue

                try:
                    page = doc[page_num - 1]

                    # Calcular escala para largura desejada
                    zoom = width / page.rect.width
                    mat = fitz.Matrix(zoom, zoom)

                    # Renderizar pagina como imagem
                    pix = page.get_pixmap(matrix=mat)

                    # Converter para base64
                    img_bytes = pix.tobytes("png")
                    b64 = base64.b64encode(img_bytes).decode()

                    thumbnails.append({
                        "page": page_num,
                        "data": f"data:image/png;base64,{b64}",
                        "width": pix.width,
                        "height": pix.height,
                    })

                except Exception as e:
                    logger.warning(f"Erro ao gerar thumbnail da pagina {page_num}: {e}")
                    thumbnails.append({
                        "page": page_num,
                        "data": None,
                        "error": str(e),
                    })

            doc.close()
            logger.info(f"Gerados {len(thumbnails)} thumbnails")
            return thumbnails

        except ImportError:
            logger.error("pymupdf nao esta instalado. Execute: pip install pymupdf")
            return []
        except Exception as e:
            logger.exception(f"Erro ao gerar thumbnails: {e}")
            return []

    def _parse_page_range(self, pages_str: str, total_pages: int) -> List[int]:
        """
        Parse string de paginas para lista de numeros.

        Suporta:
        - Range: "1-12" -> [1, 2, 3, ..., 12]
        - Lista: "1,5,10" -> [1, 5, 10]
        - Misto: "1-5,10,15-20" -> [1, 2, 3, 4, 5, 10, 15, 16, 17, 18, 19, 20]
        """
        page_numbers = []

        for part in pages_str.split(","):
            part = part.strip()
            if "-" in part:
                try:
                    start, end = part.split("-", 1)
                    start = max(1, int(start.strip()))
                    end = min(total_pages, int(end.strip()))
                    page_numbers.extend(range(start, end + 1))
                except ValueError:
                    continue
            else:
                try:
                    page_numbers.append(int(part))
                except ValueError:
                    continue

        return sorted(set(page_numbers))

    async def _extract_pdf_with_pdfplumber(
        self,
        pdf_bytes: bytes,
        filename: str,
        quality: ExtractionQuality,
        chunk_size: Optional[int] = None,
    ) -> ExtractionResult:
        """
        Extrai texto de um PDF usando pdfplumber.

        Mais rapido que Docling, melhor para tabelas e layouts simples.
        Nao preserva estrutura Markdown como Docling.

        Args:
            pdf_bytes: Conteudo binario do PDF
            filename: Nome do arquivo
            quality: Nivel de qualidade da extracao
            chunk_size: Se especificado, divide o texto em chunks

        Returns:
            ExtractionResult com o texto extraido
        """
        if not self._pdfplumber_available:
            return ExtractionResult(
                text="",
                error="pdfplumber nao esta instalado. Execute: pip install pdfplumber"
            )

        try:
            import pdfplumber
            from io import BytesIO

            all_texts: List[str] = []
            pages_content: List[Dict[str, Any]] = []
            total_words = 0

            with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
                total_pages = len(pdf.pages)

                for i, page in enumerate(pdf.pages):
                    page_text = page.extract_text() or ""

                    if quality in (ExtractionQuality.CLEANED, ExtractionQuality.LLM):
                        page_text = self._clean_text(page_text)

                    page_word_count = len(page_text.split())
                    total_words += page_word_count

                    pages_content.append({
                        "page_number": i + 1,
                        "text": page_text,
                        "word_count": page_word_count,
                    })

                    all_texts.append(page_text)

            PAGE_BREAK_MARKER = "\n\n<!-- PAGE_BREAK -->\n\n"
            combined_text = PAGE_BREAK_MARKER.join(all_texts)

            # Divide em chunks se solicitado
            chunks = []
            if chunk_size and chunk_size > 0:
                chunks = self._chunk_text(combined_text, chunk_size)

            logger.info(
                "Extracao pdfplumber concluida: %d paginas, %d palavras",
                total_pages,
                total_words
            )

            return ExtractionResult(
                text=combined_text,
                pages=total_pages,
                word_count=total_words,
                quality=quality,
                metadata={
                    "filename": filename,
                    "file_size": len(pdf_bytes),
                    "format_type": "PDF Document",
                    "extractor": "pdfplumber",
                    "page_break_marker": "<!-- PAGE_BREAK -->",
                },
                chunks=chunks,
                pages_content=pages_content,
            )

        except Exception as e:
            logger.exception("Erro na extracao com pdfplumber: %s", e)
            return ExtractionResult(
                text="",
                error=f"Erro na extracao: {str(e)}"
            )

    async def _extract_pdf_pages_with_pdfplumber(
        self,
        pdf_bytes: bytes,
        page_numbers: List[int],
        filename: str,
        quality: ExtractionQuality,
    ) -> ExtractionResult:
        """
        Extrai paginas especificas de um PDF usando pdfplumber.

        Args:
            pdf_bytes: Conteudo binario do PDF
            page_numbers: Lista de numeros de paginas (1-indexed)
            filename: Nome do arquivo
            quality: Nivel de qualidade da extracao

        Returns:
            ExtractionResult com o texto extraido
        """
        if not self._pdfplumber_available:
            return ExtractionResult(
                text="",
                error="pdfplumber nao esta instalado. Execute: pip install pdfplumber"
            )

        if not page_numbers:
            return ExtractionResult(
                text="",
                error="Nenhuma pagina selecionada"
            )

        try:
            import pdfplumber
            from io import BytesIO

            all_texts: List[str] = []
            pages_content: List[Dict[str, Any]] = []
            total_words = 0

            with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
                total_pages = len(pdf.pages)
                valid_pages = sorted([p for p in page_numbers if 1 <= p <= total_pages])

                if not valid_pages:
                    return ExtractionResult(
                        text="",
                        error=f"Paginas invalidas. O documento tem {total_pages} paginas."
                    )

                for page_num in valid_pages:
                    page = pdf.pages[page_num - 1]
                    page_text = page.extract_text() or ""

                    if quality in (ExtractionQuality.CLEANED, ExtractionQuality.LLM):
                        page_text = self._clean_text(page_text)

                    page_word_count = len(page_text.split())
                    total_words += page_word_count

                    pages_content.append({
                        "page_number": page_num,
                        "text": page_text,
                        "word_count": page_word_count,
                    })

                    all_texts.append(page_text)

            PAGE_BREAK_MARKER = "\n\n<!-- PAGE_BREAK -->\n\n"
            combined_text = PAGE_BREAK_MARKER.join(all_texts)

            logger.info(
                "Extracao pdfplumber (paginas selecionadas) concluida: %d paginas, %d palavras",
                len(valid_pages),
                total_words
            )

            return ExtractionResult(
                text=combined_text,
                pages=len(valid_pages),
                word_count=total_words,
                quality=quality,
                metadata={
                    "filename": filename,
                    "file_size": len(pdf_bytes),
                    "selected_pages": valid_pages,
                    "total_pages": total_pages,
                    "format_type": "PDF Document",
                    "extractor": "pdfplumber",
                    "page_break_marker": "<!-- PAGE_BREAK -->",
                },
                pages_content=pages_content,
            )

        except Exception as e:
            logger.exception("Erro na extracao de paginas com pdfplumber: %s", e)
            return ExtractionResult(
                text="",
                error=f"Erro na extracao: {str(e)}"
            )

    def is_available(self) -> bool:
        """Retorna True se Docling esta disponivel."""
        return self._docling_available

    async def extract_from_bytes(
        self,
        file_bytes: bytes,
        filename: str = "document",
        quality: ExtractionQuality = ExtractionQuality.CLEANED,
        chunk_size: Optional[int] = None,
        pdf_extractor: PdfExtractor = PdfExtractor.DOCLING,
    ) -> ExtractionResult:
        """
        Extrai texto de bytes de um documento.

        Args:
            file_bytes: Conteudo binario do documento
            filename: Nome do arquivo (para determinar formato)
            quality: Nivel de qualidade da extracao
            chunk_size: Se especificado, divide o texto em chunks de N palavras
            pdf_extractor: Extrator a usar para PDFs (docling ou pdfplumber)

        Returns:
            ExtractionResult com o texto extraido
        """
        ext = Path(filename).suffix.lower()
        if not ext:
            ext = ".pdf"  # Default para PDF

        if ext not in SUPPORTED_FORMATS:
            return ExtractionResult(
                text="",
                error=f"Formato nao suportado: {ext}. Formatos validos: {', '.join(SUPPORTED_FORMATS.keys())}"
            )

        # Para PDFs, permite escolher o extrator
        if ext == ".pdf" and pdf_extractor == PdfExtractor.PDFPLUMBER:
            return await self._extract_pdf_with_pdfplumber(
                file_bytes, filename, quality, chunk_size
            )

        # Para outros formatos ou PDFs com Docling
        if not self._docling_available:
            return ExtractionResult(
                text="",
                error="Docling nao esta instalado. Execute: pip install docling"
            )

        # Salva bytes em arquivo temporario (Docling precisa de path)
        with tempfile.NamedTemporaryFile(
            suffix=ext,
            delete=False,
            prefix="gd_"
        ) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        try:
            result = await self.extract_from_path(
                tmp_path,
                quality=quality,
                chunk_size=chunk_size,
                document_name=Path(filename).stem,
            )
            result.metadata["original_filename"] = filename
            result.metadata["format_type"] = SUPPORTED_FORMATS.get(ext, "Unknown")
            result.metadata["extractor"] = "docling"
            return result
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    async def extract_from_path(
        self,
        file_path: str,
        quality: ExtractionQuality = ExtractionQuality.CLEANED,
        chunk_size: Optional[int] = None,
        document_name: Optional[str] = None,
    ) -> ExtractionResult:
        """
        Extrai texto de um arquivo no disco.

        Args:
            file_path: Caminho para o arquivo
            quality: Nivel de qualidade da extracao
            chunk_size: Se especificado, divide o texto em chunks de N palavras
            document_name: Nome do documento original (usado no HTML exportado)

        Returns:
            ExtractionResult com o texto extraido
        """
        if not self._docling_available:
            return ExtractionResult(
                text="",
                error="Docling nao esta instalado. Execute: pip install docling"
            )

        path = Path(file_path)
        if not path.exists():
            return ExtractionResult(
                text="",
                error=f"Arquivo nao encontrado: {file_path}"
            )

        ext = path.suffix.lower()
        if ext not in SUPPORTED_FORMATS:
            return ExtractionResult(
                text="",
                error=f"Formato nao suportado: {ext}. Formatos validos: {', '.join(SUPPORTED_FORMATS.keys())}"
            )

        try:
            converter = self._get_converter()

            logger.info(f"Iniciando extracao de: {path.name} ({SUPPORTED_FORMATS.get(ext, 'Unknown')})")
            result = converter.convert(str(path))

            # Usa o nome original do documento no HTML exportado (evita artefatos de temp file)
            if document_name:
                result.document.name = document_name

            # Extrai texto em formato HTML (preserva estrutura com tags semanticas)
            raw_text = result.document.export_to_html()

            # Metadados do documento
            metadata = {
                "filename": path.name,
                "file_size": path.stat().st_size,
                "format": ext,
                "format_type": SUPPORTED_FORMATS.get(ext, "Unknown"),
            }

            # Tenta extrair numero de paginas
            pages = 0
            if hasattr(result.document, 'pages'):
                pages = len(result.document.pages)
            elif hasattr(result, 'pages'):
                pages = len(result.pages)

            # Para documentos sem paginacao, considera como 1 pagina
            if pages == 0 and raw_text:
                pages = 1

            # Aplica limpeza se solicitado
            if quality in (ExtractionQuality.CLEANED, ExtractionQuality.LLM):
                text = self._clean_text(raw_text)
            else:
                text = raw_text

            word_count = len(text.split())

            # Divide em chunks se solicitado
            chunks = []
            if chunk_size and chunk_size > 0:
                chunks = self._chunk_text(text, chunk_size)

            logger.info(
                f"Extracao concluida: {pages} paginas, {word_count} palavras"
            )

            return ExtractionResult(
                text=text,
                pages=pages,
                word_count=word_count,
                quality=quality,
                metadata=metadata,
                chunks=chunks,
            )

        except Exception as e:
            logger.exception(f"Erro na extracao do documento: {e}")
            return ExtractionResult(
                text="",
                error=f"Erro na extracao: {str(e)}"
            )

    def _fix_url_headings(self, html: str) -> str:
        """
        Corrige URLs que o Docling classificou incorretamente como headings.

        O Docling usa heuristicas visuais (tamanho de fonte, peso) para
        determinar headings. URLs standalone em linhas isoladas sao
        frequentemente classificadas como h1-h6 por engano.

        Trata casos como:
        - <h2>https://example.com</h2>
        - <h2><a href="url">url</a></h2>
        - <h2>&lt; https://example.com/path &gt;</h2>
        - URLs com espacos/quebras de linha inseridos pela extracao do PDF
        """
        import re

        if not html:
            return html

        def _replace_url_heading(match):
            full_match = match.group(0)
            content = match.group(3).strip()

            # Remove tags HTML internas para obter texto puro
            plain = re.sub(r'<[^>]+>', '', content).strip()

            # Decodifica entidades HTML comuns
            plain = (
                plain
                .replace('&lt;', '<')
                .replace('&gt;', '>')
                .replace('&amp;', '&')
                .replace('&nbsp;', ' ')
            )

            # Remove angle brackets, pontos e espacos das bordas
            core = plain.strip('<> .\n\r\t')

            # Verifica se o conteudo e primariamente uma URL
            if re.match(r'https?://', core):
                # Remove espacos/quebras inseridos pela extracao do PDF
                clean_url = re.sub(r'\s+', '', core)
                return f'<p><a href="{clean_url}">{clean_url}</a></p>'

            return full_match

        html = re.sub(
            r'<(h[1-6])([^>]*)>(.*?)</\1>',
            _replace_url_heading,
            html,
            flags=re.IGNORECASE | re.DOTALL,
        )

        return html

    def _clean_text(self, text: str) -> str:
        """
        Limpa o texto extraido aplicando heuristicas.

        - Remove artefatos de OCR comuns
        - Normaliza espacos e caracteres de controle
        """
        import re

        if not text:
            return ""

        # Escapa '<' soltos que nao fazem parte de tags HTML reais.
        # Ex: "acesse: < https://example.com" → "acesse: &lt; https://..."
        # Sem isso, o parser HTML interpreta "< https://..." como tag invalida
        # e engole o conteudo (incluindo a URL).
        # O pattern preserva tags validas: <p>, </div>, <!-- -->, <!DOCTYPE>
        text = re.sub(r'<(?![/a-zA-Z!])', '&lt;', text)

        # Corrige URLs classificadas como headings pelo Docling
        text = self._fix_url_headings(text)

        # Normaliza espacos multiplos em linha
        text = re.sub(r'[ \t]{3,}', '  ', text)

        # Remove caracteres de controle exceto newline e tab
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)

        # Normaliza aspas tipograficas
        text = text.replace('\u201c', '"').replace('\u201d', '"')
        text = text.replace('\u2018', "'").replace('\u2019', "'")

        # Auto-linkifica URLs em texto plano (fora de tags <a>)
        text = self._autolink_urls(text)

        return text.strip()

    def _autolink_urls(self, html: str) -> str:
        """
        Converte URLs em texto plano para links clicaveis.

        Detecta URLs (https?://...) que nao estao dentro de atributos
        href ou tags <a>, e envolve em <a href="url">url</a>.
        Tambem trata URLs com angle brackets: < https://... >.
        """
        import re

        if not html:
            return html

        # Trata URLs com angle brackets: &lt; URL &gt; ou &lt; URL (sem fechar)
        # Ex: "&lt; https://example.com &gt;" ou "&lt; https://example.com"
        def _fix_angle_bracket_url(match):
            url_text = match.group(1).strip()
            clean_url = re.sub(r'\s+', '', url_text)
            return f'<a href="{clean_url}">{clean_url}</a>'

        html = re.sub(
            r'&lt;\s*(https?://[^\s<>&]+(?:[^\s<>&])*?)'
            r'\s*(?:&gt;|(?=[\s.<]))',
            _fix_angle_bracket_url,
            html,
        )

        # Depois, linkifica URLs soltas que nao estao dentro de <a> ou href
        # Usa negative lookbehind para nao capturar URLs ja em href="" ou >
        def _linkify_plain_url(match):
            url = match.group(0).rstrip('.,;:!?)"\'>')
            trailing = match.group(0)[len(url):]
            return f'<a href="{url}">{url}</a>{trailing}'

        html = re.sub(
            r'(?<!["\'>=/])https?://[^\s<>"\']+',
            _linkify_plain_url,
            html,
        )

        return html

    def _chunk_text(
        self,
        text: str,
        max_words: int = 400,
        overlap_words: int = 50
    ) -> List[str]:
        """
        Divide texto em chunks com overlap.

        Args:
            text: Texto a ser dividido
            max_words: Maximo de palavras por chunk
            overlap_words: Palavras de overlap entre chunks

        Returns:
            Lista de chunks
        """
        words = text.split()
        if len(words) <= max_words:
            return [text]

        chunks = []
        start = 0

        while start < len(words):
            end = start + max_words
            chunk_words = words[start:end]
            chunks.append(' '.join(chunk_words))

            start = end - overlap_words
            if start >= len(words):
                break

        return chunks

    async def get_document_preview(
        self,
        file_bytes: bytes,
        filename: str = "document",
        preview_chars: int = 300,
    ) -> DocumentPreviewResult:
        """
        Obtem preview do documento mostrando informacoes de cada pagina.

        Para PDFs, usa pypdf para preview rapido.
        Para outros formatos, extrai com Docling e divide em secoes.

        Args:
            file_bytes: Conteudo binario do documento
            filename: Nome do arquivo
            preview_chars: Numero de caracteres de preview por pagina

        Returns:
            DocumentPreviewResult com informacoes de cada pagina
        """
        ext = Path(filename).suffix.lower()
        format_type = SUPPORTED_FORMATS.get(ext, "Unknown")

        # Para PDFs, tenta usar pdfplumber para preview rapido
        if ext == ".pdf" and self._pdfplumber_available:
            return await self._get_pdf_preview(file_bytes, filename, preview_chars)

        # Para outros formatos, extrai com Docling
        if not self._docling_available:
            return DocumentPreviewResult(
                total_pages=0,
                pages=[],
                filename=filename,
                file_size=len(file_bytes),
                format_type=format_type,
                error="Docling nao esta instalado. Execute: pip install docling"
            )

        try:
            # Extrai o documento completo
            result = await self.extract_from_bytes(file_bytes, filename)

            if result.error:
                return DocumentPreviewResult(
                    total_pages=0,
                    pages=[],
                    filename=filename,
                    file_size=len(file_bytes),
                    format_type=format_type,
                    error=result.error
                )

            # Para formatos nao paginados, divide o texto em secoes
            text = result.text

            # Se e paginado (PPTX), tenta identificar slides
            if ext in PAGINATED_FORMATS:
                pages_info = self._split_into_pages(text, preview_chars)
            else:
                # Para outros formatos, apresenta como documento unico
                word_count = len(text.split()) if text else 0
                preview = text[:preview_chars].strip() if text else ""
                if len(text) > preview_chars:
                    preview += "..."

                pages_info = [PageInfo(
                    page_number=1,
                    word_count=word_count,
                    preview=preview,
                )]

            return DocumentPreviewResult(
                total_pages=len(pages_info),
                pages=pages_info,
                filename=filename,
                file_size=len(file_bytes),
                format_type=format_type,
            )

        except Exception as e:
            logger.exception("Erro ao obter preview do documento: %s", e)
            return DocumentPreviewResult(
                total_pages=0,
                pages=[],
                filename=filename,
                file_size=len(file_bytes),
                format_type=format_type,
                error=f"Erro ao obter preview: {str(e)}"
            )

    async def _get_single_page_preview(
        self,
        pdf_bytes: bytes,
        page_num: int,
        preview_chars: int,
        semaphore: asyncio.Semaphore,
    ) -> PageInfo:
        """
        Obtém preview de uma única página do PDF de forma thread-safe.

        Args:
            pdf_bytes: Bytes do PDF
            page_num: Número da página (0-indexed internamente, retorna 1-indexed)
            preview_chars: Máximo de caracteres no preview
            semaphore: Semáforo para controle de concorrência

        Returns:
            PageInfo com informações da página
        """
        async with semaphore:
            def _extract_preview():
                import pdfplumber
                from io import BytesIO

                try:
                    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
                        if page_num >= len(pdf.pages):
                            return PageInfo(
                                page_number=page_num + 1,
                                word_count=0,
                                preview=""
                            )

                        page = pdf.pages[page_num]
                        page_text = page.extract_text() or ""

                        word_count = len(page_text.split()) if page_text else 0
                        preview = page_text[:preview_chars].strip() if page_text else ""
                        if len(page_text) > preview_chars:
                            preview += "..."

                        return PageInfo(
                            page_number=page_num + 1,
                            word_count=word_count,
                            preview=preview,
                        )
                except Exception as e:
                    logger.warning(f"Erro ao obter preview da página {page_num + 1}: {e}")
                    return PageInfo(
                        page_number=page_num + 1,
                        word_count=0,
                        preview=f"[Erro: {str(e)[:50]}]"
                    )

            return await asyncio.to_thread(_extract_preview)

    async def _get_pdf_preview(
        self,
        pdf_bytes: bytes,
        filename: str,
        preview_chars: int,
        max_concurrent: int = 10,
        batch_size: int = 50,
    ) -> DocumentPreviewResult:
        """
        Preview de PDF com processamento PARALELO em lotes.

        Args:
            pdf_bytes: Bytes do PDF
            filename: Nome do arquivo
            preview_chars: Caracteres máximos por preview
            max_concurrent: Máximo de páginas processadas simultaneamente
            batch_size: Tamanho de cada lote para processamento

        Returns:
            DocumentPreviewResult com preview de todas as páginas
        """
        try:
            import pdfplumber
            from io import BytesIO

            # Obter total de páginas (operação rápida)
            with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
                total_pages = len(pdf.pages)

            logger.info(
                "Iniciando preview paralelo de %d páginas (lotes de %d, max %d concurrent)",
                total_pages, batch_size, max_concurrent
            )

            # Semáforo para controlar concorrência
            semaphore = asyncio.Semaphore(max_concurrent)

            # Processar em lotes para PDFs muito grandes
            all_pages_info = []

            for batch_start in range(0, total_pages, batch_size):
                batch_end = min(batch_start + batch_size, total_pages)
                batch_pages = range(batch_start, batch_end)

                logger.debug("Processando lote: páginas %d a %d", batch_start + 1, batch_end)

                # Criar tasks para o lote atual
                tasks = [
                    self._get_single_page_preview(
                        pdf_bytes, page_num, preview_chars, semaphore
                    )
                    for page_num in batch_pages
                ]

                # Executar lote em paralelo
                batch_results = await asyncio.gather(*tasks, return_exceptions=True)

                # Processar resultados do lote
                for result in batch_results:
                    if isinstance(result, Exception):
                        logger.warning("Erro em página do lote: %s", result)
                        continue
                    all_pages_info.append(result)

            # Ordenar por número da página (garantir ordem correta)
            all_pages_info.sort(key=lambda x: x.page_number)

            logger.info(
                "Preview paralelo concluído: %d de %d páginas",
                len(all_pages_info), total_pages
            )

            return DocumentPreviewResult(
                total_pages=total_pages,
                pages=all_pages_info,
                filename=filename,
                file_size=len(pdf_bytes),
                format_type="PDF Document",
            )

        except Exception as e:
            logger.exception("Erro ao obter preview do PDF: %s", e)
            return DocumentPreviewResult(
                total_pages=0,
                pages=[],
                filename=filename,
                file_size=len(pdf_bytes),
                format_type="PDF Document",
                error=f"Erro ao obter preview: {str(e)}"
            )

    def _split_into_pages(self, text: str, preview_chars: int) -> List[PageInfo]:
        """Divide texto em paginas baseado em marcadores ou tamanho."""
        # Tenta encontrar marcadores de slide/pagina
        import re

        # Padroes comuns de separadores
        patterns = [
            r'\n---+\n',           # Markdown horizontal rule
            r'\n#{1,2}\s+',        # Headers Markdown
            r'\n\*{3,}\n',         # Asteriscos
            r'\nSlide\s+\d+',      # Slides numerados
        ]

        # Tenta dividir por padroes
        sections = [text]
        for pattern in patterns:
            if len(sections) == 1:
                parts = re.split(pattern, text)
                if len(parts) > 1:
                    sections = [p.strip() for p in parts if p.strip()]
                    break

        # Se nao conseguiu dividir, usa um tamanho fixo
        if len(sections) == 1 and len(text) > 2000:
            words = text.split()
            words_per_page = 300
            sections = []
            for i in range(0, len(words), words_per_page):
                section = ' '.join(words[i:i+words_per_page])
                sections.append(section)

        pages_info = []
        for i, section in enumerate(sections):
            word_count = len(section.split()) if section else 0
            preview = section[:preview_chars].strip() if section else ""
            if len(section) > preview_chars:
                preview += "..."

            pages_info.append(PageInfo(
                page_number=i + 1,
                word_count=word_count,
                preview=preview,
            ))

        return pages_info

    async def extract_pages(
        self,
        file_bytes: bytes,
        page_numbers: List[int],
        filename: str = "document",
        quality: ExtractionQuality = ExtractionQuality.CLEANED,
        pdf_extractor: PdfExtractor = PdfExtractor.DOCLING,
    ) -> ExtractionResult:
        """
        Extrai texto de paginas selecionadas.

        Para PDFs, extrai cada pagina individualmente.
        Para outros formatos, extrai o documento completo.

        Args:
            file_bytes: Conteudo binario do documento
            page_numbers: Lista de numeros de paginas (1-indexed)
            filename: Nome do arquivo
            quality: Nivel de qualidade da extracao
            pdf_extractor: Extrator a usar para PDFs (docling ou pdfplumber)

        Returns:
            ExtractionResult com o texto extraido
        """
        ext = Path(filename).suffix.lower()

        # Para PDFs, usa extracao por pagina
        if ext == ".pdf":
            return await self._extract_pdf_pages(
                file_bytes, page_numbers, filename, quality, pdf_extractor
            )

        # Para outros formatos, extrai o documento completo
        result = await self.extract_from_bytes(file_bytes, filename, quality)

        if result.error:
            return result

        # Adiciona metadados de paginacao
        result.metadata["selected_pages"] = page_numbers
        result.metadata["extraction_method"] = "docling"

        return result

    async def _extract_pdf_pages(
        self,
        pdf_bytes: bytes,
        page_numbers: List[int],
        filename: str,
        quality: ExtractionQuality,
        pdf_extractor: PdfExtractor = PdfExtractor.DOCLING,
    ) -> ExtractionResult:
        """Extrai paginas especificas de um PDF."""
        # Se usar pdfplumber, extrai diretamente as paginas selecionadas
        if pdf_extractor == PdfExtractor.PDFPLUMBER:
            return await self._extract_pdf_pages_with_pdfplumber(
                pdf_bytes, page_numbers, filename, quality
            )

        # Docling: precisa criar PDF temporario com paginas selecionadas
        if not self._docling_available:
            return ExtractionResult(
                text="",
                error="Docling nao esta instalado. Execute: pip install docling"
            )

        if not self._pikepdf_available:
            return ExtractionResult(
                text="",
                error="pikepdf nao esta instalado. Execute: pip install pikepdf"
            )

        if not page_numbers:
            return ExtractionResult(
                text="",
                error="Nenhuma pagina selecionada"
            )

        try:
            total_pages = self._get_pdf_page_count(pdf_bytes)
            valid_pages = sorted([p for p in page_numbers if 1 <= p <= total_pages])

            if not valid_pages:
                return ExtractionResult(
                    text="",
                    error=f"Paginas invalidas. O documento tem {total_pages} paginas."
                )

            logger.info("Extraindo %d paginas individualmente", len(valid_pages))

            pages_content: List[Dict[str, Any]] = []
            all_texts: List[str] = []
            total_words = 0

            converter = self._get_converter()

            for page_num in valid_pages:
                single_page_pdf = self._extract_pages_from_pdf(pdf_bytes, [page_num])

                with tempfile.NamedTemporaryFile(
                    suffix=".pdf",
                    delete=False,
                    prefix=f"gd_p{page_num}_"
                ) as tmp:
                    tmp.write(single_page_pdf)
                    tmp_path = tmp.name

                try:
                    result = converter.convert(tmp_path)
                    result.document.name = Path(filename).stem
                    page_html = result.document.export_to_html()

                    if quality in (ExtractionQuality.CLEANED, ExtractionQuality.LLM):
                        page_text = self._clean_text(page_html)
                    else:
                        page_text = page_html

                    page_word_count = len(page_text.split())
                    total_words += page_word_count

                    pages_content.append({
                        "page_number": page_num,
                        "text": page_text,
                        "word_count": page_word_count,
                    })

                    all_texts.append(page_text)
                    logger.debug("Pagina %d extraida: %d palavras", page_num, page_word_count)

                finally:
                    try:
                        os.unlink(tmp_path)
                    except Exception:
                        pass

            PAGE_BREAK_MARKER = "\n\n<!-- PAGE_BREAK -->\n\n"
            combined_text = PAGE_BREAK_MARKER.join(all_texts)

            logger.info(
                "Extracao Docling concluida: %d paginas, %d palavras",
                len(valid_pages),
                total_words
            )

            return ExtractionResult(
                text=combined_text,
                pages=len(valid_pages),
                word_count=total_words,
                quality=quality,
                metadata={
                    "filename": filename,
                    "file_size": len(pdf_bytes),
                    "selected_pages": valid_pages,
                    "total_pages": total_pages,
                    "extraction_method": "docling",
                    "page_break_marker": "<!-- PAGE_BREAK -->",
                    "format_type": "PDF Document",
                },
                pages_content=pages_content,
            )

        except Exception as e:
            logger.exception("Erro na extracao de paginas: %s", e)
            return ExtractionResult(
                text="",
                error=f"Erro na extracao: {str(e)}"
            )


# Instancia singleton para uso em toda a aplicacao
document_extractor = DocumentExtractor()

# Alias para compatibilidade com codigo existente
pdf_extractor = document_extractor


async def extract_document_text(
    file_bytes: bytes,
    filename: str = "document",
    quality: str = "cleaned",
    chunk_size: Optional[int] = None,
    pdf_extractor: str = "docling",
) -> Dict[str, Any]:
    """
    Funcao de conveniencia para extracao de documentos.

    Args:
        file_bytes: Conteudo binario do documento
        filename: Nome do arquivo
        quality: "raw", "cleaned", ou "llm"
        chunk_size: Se especificado, divide em chunks
        pdf_extractor: "docling" ou "pdfplumber"

    Returns:
        Dicionario com resultado da extracao
    """
    quality_enum = ExtractionQuality(quality)
    pdf_extractor_enum = PdfExtractor(pdf_extractor)
    result = await document_extractor.extract_from_bytes(
        file_bytes,
        filename,
        quality_enum,
        chunk_size,
        pdf_extractor_enum,
    )
    return result.to_dict()


# Alias para compatibilidade
async def extract_pdf_text(
    pdf_bytes: bytes,
    filename: str = "document.pdf",
    quality: str = "cleaned",
    chunk_size: Optional[int] = None,
    pdf_extractor: str = "docling",
) -> Dict[str, Any]:
    """Alias para compatibilidade com codigo existente."""
    return await extract_document_text(pdf_bytes, filename, quality, chunk_size, pdf_extractor)
