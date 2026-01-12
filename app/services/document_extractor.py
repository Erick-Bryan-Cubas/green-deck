"""
Document Text Extraction Service using Docling.

Este modulo fornece extracao de texto de documentos usando a biblioteca Docling,
com suporte para multiplos formatos: PDF, DOCX, PPTX, XLSX, HTML, Markdown, AsciiDoc, e imagens.
"""

import logging
import tempfile
import os
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
        self._pypdf_available = False
        self._converter = None
        self._check_docling()
        self._check_pypdf()

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

    def _check_pypdf(self):
        """Verifica se pypdf esta disponivel para manipulacao de PDFs."""
        try:
            from pypdf import PdfReader, PdfWriter  # noqa: F401
            self._pypdf_available = True
            logger.info("pypdf disponivel para manipulacao de PDFs")
        except ImportError:
            self._pypdf_available = False
            logger.warning(
                "pypdf nao instalado. Instale com: pip install pypdf"
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
        from pypdf import PdfReader, PdfWriter
        from io import BytesIO

        reader = PdfReader(BytesIO(pdf_bytes))
        writer = PdfWriter()

        total_pages = len(reader.pages)

        for page_num in sorted(page_numbers):
            if 1 <= page_num <= total_pages:
                writer.add_page(reader.pages[page_num - 1])

        output = BytesIO()
        writer.write(output)
        output.seek(0)

        return output.read()

    def _get_pdf_page_count(self, pdf_bytes: bytes) -> int:
        """Obtem o numero total de paginas do PDF."""
        from pypdf import PdfReader
        from io import BytesIO

        reader = PdfReader(BytesIO(pdf_bytes))
        return len(reader.pages)

    def is_available(self) -> bool:
        """Retorna True se Docling esta disponivel."""
        return self._docling_available

    async def extract_from_bytes(
        self,
        file_bytes: bytes,
        filename: str = "document",
        quality: ExtractionQuality = ExtractionQuality.CLEANED,
        chunk_size: Optional[int] = None,
    ) -> ExtractionResult:
        """
        Extrai texto de bytes de um documento.

        Args:
            file_bytes: Conteudo binario do documento
            filename: Nome do arquivo (para determinar formato)
            quality: Nivel de qualidade da extracao
            chunk_size: Se especificado, divide o texto em chunks de N palavras

        Returns:
            ExtractionResult com o texto extraido
        """
        if not self._docling_available:
            return ExtractionResult(
                text="",
                error="Docling nao esta instalado. Execute: pip install docling"
            )

        ext = Path(filename).suffix.lower()
        if not ext:
            ext = ".pdf"  # Default para PDF

        if ext not in SUPPORTED_FORMATS:
            return ExtractionResult(
                text="",
                error=f"Formato nao suportado: {ext}. Formatos validos: {', '.join(SUPPORTED_FORMATS.keys())}"
            )

        # Salva bytes em arquivo temporario (Docling precisa de path)
        with tempfile.NamedTemporaryFile(
            suffix=ext,
            delete=False,
            prefix="spaced_rep_"
        ) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        try:
            result = await self.extract_from_path(
                tmp_path,
                quality=quality,
                chunk_size=chunk_size
            )
            result.metadata["original_filename"] = filename
            result.metadata["format_type"] = SUPPORTED_FORMATS.get(ext, "Unknown")
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
    ) -> ExtractionResult:
        """
        Extrai texto de um arquivo no disco.

        Args:
            file_path: Caminho para o arquivo
            quality: Nivel de qualidade da extracao
            chunk_size: Se especificado, divide o texto em chunks de N palavras

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

            # Extrai texto em formato Markdown (preserva estrutura)
            raw_text = result.document.export_to_markdown()

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

    def _clean_text(self, text: str) -> str:
        """
        Limpa o texto extraido aplicando heuristicas.

        - Remove cabecalhos/rodapes repetitivos
        - Normaliza espacos e quebras de linha
        - Remove artefatos de OCR comuns
        """
        import re

        if not text:
            return ""

        # Normaliza quebras de linha excessivas
        text = re.sub(r'\n{4,}', '\n\n\n', text)

        # Remove linhas que sao apenas numeros (numeros de pagina)
        lines = text.split('\n')
        cleaned_lines = []
        for line in lines:
            stripped = line.strip()
            # Pula linhas que sao apenas numeros (paginas)
            if stripped.isdigit() and len(stripped) <= 4:
                continue
            # Pula linhas muito curtas que parecem artefatos
            if len(stripped) <= 2 and not stripped.isalpha():
                continue
            cleaned_lines.append(line)

        text = '\n'.join(cleaned_lines)

        # Normaliza espacos multiplos em linha
        text = re.sub(r'[ \t]{3,}', '  ', text)

        # Remove caracteres de controle exceto newline e tab
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)

        # Normaliza aspas tipograficas
        text = text.replace('"', '"').replace('"', '"')
        text = text.replace(''', "'").replace(''', "'")

        return text.strip()

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

        # Para PDFs, tenta usar pypdf para preview rapido
        if ext == ".pdf" and self._pypdf_available:
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

    async def _get_pdf_preview(
        self,
        pdf_bytes: bytes,
        filename: str,
        preview_chars: int,
    ) -> DocumentPreviewResult:
        """Preview especifico para PDFs usando pypdf."""
        try:
            from pypdf import PdfReader
            from io import BytesIO

            reader = PdfReader(BytesIO(pdf_bytes))
            total_pages = len(reader.pages)

            pages_info = []
            for i, page in enumerate(reader.pages):
                page_text = page.extract_text() or ""

                word_count = len(page_text.split()) if page_text else 0
                preview = page_text[:preview_chars].strip() if page_text else ""
                if len(page_text) > preview_chars:
                    preview += "..."

                pages_info.append(PageInfo(
                    page_number=i + 1,
                    word_count=word_count,
                    preview=preview,
                ))

            return DocumentPreviewResult(
                total_pages=total_pages,
                pages=pages_info,
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

        Returns:
            ExtractionResult com o texto extraido
        """
        ext = Path(filename).suffix.lower()

        # Para PDFs, usa extracao por pagina
        if ext == ".pdf":
            return await self._extract_pdf_pages(file_bytes, page_numbers, filename, quality)

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
    ) -> ExtractionResult:
        """Extrai paginas especificas de um PDF."""
        if not self._docling_available:
            return ExtractionResult(
                text="",
                error="Docling nao esta instalado. Execute: pip install docling"
            )

        if not self._pypdf_available:
            return ExtractionResult(
                text="",
                error="pypdf nao esta instalado. Execute: pip install pypdf"
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
                    prefix=f"spaced_rep_page_{page_num}_"
                ) as tmp:
                    tmp.write(single_page_pdf)
                    tmp_path = tmp.name

                try:
                    result = converter.convert(tmp_path)
                    page_markdown = result.document.export_to_markdown()

                    if quality in (ExtractionQuality.CLEANED, ExtractionQuality.LLM):
                        page_text = self._clean_text(page_markdown)
                    else:
                        page_text = page_markdown

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
) -> Dict[str, Any]:
    """
    Funcao de conveniencia para extracao de documentos.

    Args:
        file_bytes: Conteudo binario do documento
        filename: Nome do arquivo
        quality: "raw", "cleaned", ou "llm"
        chunk_size: Se especificado, divide em chunks

    Returns:
        Dicionario com resultado da extracao
    """
    quality_enum = ExtractionQuality(quality)
    result = await document_extractor.extract_from_bytes(
        file_bytes,
        filename,
        quality_enum,
        chunk_size
    )
    return result.to_dict()


# Alias para compatibilidade
async def extract_pdf_text(
    pdf_bytes: bytes,
    filename: str = "document.pdf",
    quality: str = "cleaned",
    chunk_size: Optional[int] = None,
) -> Dict[str, Any]:
    """Alias para compatibilidade com codigo existente."""
    return await extract_document_text(pdf_bytes, filename, quality, chunk_size)
