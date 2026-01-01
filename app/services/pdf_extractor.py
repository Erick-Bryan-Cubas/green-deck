"""
PDF Text Extraction Service using Docling.

Este módulo fornece extração de texto de documentos PDF usando a biblioteca Docling,
com suporte opcional para pós-processamento via LLM para melhorar a qualidade do texto.
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
    """Qualidade da extração de texto."""
    RAW = "raw"           # Texto bruto sem processamento
    CLEANED = "cleaned"   # Texto limpo com heurísticas
    LLM = "llm"          # Texto refinado via LLM


@dataclass
class ExtractionResult:
    """Resultado da extração de texto de um documento."""
    text: str
    pages: int = 0
    word_count: int = 0
    quality: ExtractionQuality = ExtractionQuality.RAW
    metadata: Dict[str, Any] = field(default_factory=dict)
    chunks: List[str] = field(default_factory=list)
    pages_content: List[Dict[str, Any]] = field(default_factory=list)  # Conteúdo por página
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
    """Informações de uma página do PDF."""
    page_number: int
    word_count: int
    preview: str  # Primeiros N caracteres
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "page_number": self.page_number,
            "word_count": self.word_count,
            "preview": self.preview,
        }


@dataclass 
class PdfPreviewResult:
    """Resultado do preview de um PDF."""
    total_pages: int
    pages: List[PageInfo]
    filename: str
    file_size: int
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_pages": self.total_pages,
            "pages": [p.to_dict() for p in self.pages],
            "filename": self.filename,
            "file_size": self.file_size,
            "error": self.error,
        }


class PDFExtractor:
    """
    Extrator de texto de PDFs usando Docling.
    
    Docling é uma biblioteca da IBM que converte documentos em formatos
    estruturados como Markdown, preservando layout e estrutura.
    """
    
    def __init__(self):
        self._docling_available = False
        self._converter = None
        self._check_docling()
    
    def _check_docling(self):
        """Verifica se Docling está disponível."""
        try:
            from docling.document_converter import DocumentConverter  # noqa: F401
            self._docling_available = True
            logger.info("Docling disponível para extração de PDF")
        except ImportError:
            self._docling_available = False
            logger.warning(
                "Docling não instalado. Instale com: pip install docling"
            )
    
    def _get_converter(self):
        """Lazy initialization do converter Docling."""
        if self._converter is None and self._docling_available:
            from docling.document_converter import DocumentConverter  # noqa: F811
            self._converter = DocumentConverter()
        return self._converter
    
    def is_available(self) -> bool:
        """Retorna True se Docling está disponível."""
        return self._docling_available
    
    async def extract_from_bytes(
        self,
        pdf_bytes: bytes,
        filename: str = "document.pdf",
        quality: ExtractionQuality = ExtractionQuality.CLEANED,
        chunk_size: Optional[int] = None,
    ) -> ExtractionResult:
        """
        Extrai texto de bytes de um PDF.
        
        Args:
            pdf_bytes: Conteúdo binário do PDF
            filename: Nome do arquivo (para metadados)
            quality: Nível de qualidade da extração
            chunk_size: Se especificado, divide o texto em chunks de N palavras
        
        Returns:
            ExtractionResult com o texto extraído
        """
        if not self._docling_available:
            return ExtractionResult(
                text="",
                error="Docling não está instalado. Execute: pip install docling"
            )
        
        # Salva bytes em arquivo temporário (Docling precisa de path)
        with tempfile.NamedTemporaryFile(
            suffix=".pdf", 
            delete=False,
            prefix="spaced_rep_"
        ) as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name
        
        try:
            result = await self.extract_from_path(
                tmp_path, 
                quality=quality,
                chunk_size=chunk_size
            )
            result.metadata["original_filename"] = filename
            return result
        finally:
            # Limpa arquivo temporário
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
    
    async def extract_from_path(
        self,
        pdf_path: str,
        quality: ExtractionQuality = ExtractionQuality.CLEANED,
        chunk_size: Optional[int] = None,
    ) -> ExtractionResult:
        """
        Extrai texto de um arquivo PDF no disco.
        
        Args:
            pdf_path: Caminho para o arquivo PDF
            quality: Nível de qualidade da extração
            chunk_size: Se especificado, divide o texto em chunks de N palavras
        
        Returns:
            ExtractionResult com o texto extraído
        """
        if not self._docling_available:
            return ExtractionResult(
                text="",
                error="Docling não está instalado. Execute: pip install docling"
            )
        
        path = Path(pdf_path)
        if not path.exists():
            return ExtractionResult(
                text="",
                error=f"Arquivo não encontrado: {pdf_path}"
            )
        
        if not path.suffix.lower() == ".pdf":
            return ExtractionResult(
                text="",
                error=f"Formato não suportado: {path.suffix}. Apenas PDF é suportado."
            )
        
        try:
            converter = self._get_converter()
            
            # Docling converte o documento
            logger.info(f"Iniciando extração de: {path.name}")
            result = converter.convert(str(path))
            
            # Extrai texto em formato Markdown (preserva estrutura)
            raw_text = result.document.export_to_markdown()
            
            # Metadados do documento
            metadata = {
                "filename": path.name,
                "file_size": path.stat().st_size,
            }
            
            # Tenta extrair número de páginas
            pages = 0
            if hasattr(result.document, 'pages'):
                pages = len(result.document.pages)
            elif hasattr(result, 'pages'):
                pages = len(result.pages)
            
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
                f"Extração concluída: {pages} páginas, {word_count} palavras"
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
            logger.exception(f"Erro na extração do PDF: {e}")
            return ExtractionResult(
                text="",
                error=f"Erro na extração: {str(e)}"
            )
    
    def _clean_text(self, text: str) -> str:
        """
        Limpa o texto extraído aplicando heurísticas.
        
        - Remove cabeçalhos/rodapés repetitivos
        - Normaliza espaços e quebras de linha
        - Remove artefatos de OCR comuns
        """
        import re
        
        if not text:
            return ""
        
        # Normaliza quebras de linha excessivas
        text = re.sub(r'\n{4,}', '\n\n\n', text)
        
        # Remove linhas que são apenas números (números de página)
        lines = text.split('\n')
        cleaned_lines = []
        for line in lines:
            stripped = line.strip()
            # Pula linhas que são apenas números (páginas)
            if stripped.isdigit() and len(stripped) <= 4:
                continue
            # Pula linhas muito curtas que parecem artefatos
            if len(stripped) <= 2 and not stripped.isalpha():
                continue
            cleaned_lines.append(line)
        
        text = '\n'.join(cleaned_lines)
        
        # Normaliza espaços múltiplos em linha
        text = re.sub(r'[ \t]{3,}', '  ', text)
        
        # Remove caracteres de controle exceto newline e tab
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
        
        # Normaliza aspas tipográficas
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
            max_words: Máximo de palavras por chunk
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
            
            # Próximo chunk começa com overlap
            start = end - overlap_words
            if start >= len(words):
                break
        
        return chunks
    
    async def get_pdf_preview(
        self,
        pdf_bytes: bytes,
        filename: str = "document.pdf",
        preview_chars: int = 300,
    ) -> PdfPreviewResult:
        """
        Obtém preview do PDF mostrando informações de cada página.
        
        Args:
            pdf_bytes: Conteúdo binário do PDF
            filename: Nome do arquivo
            preview_chars: Número de caracteres de preview por página
        
        Returns:
            PdfPreviewResult com informações de cada página
        """
        if not self._docling_available:
            return PdfPreviewResult(
                total_pages=0,
                pages=[],
                filename=filename,
                file_size=len(pdf_bytes),
                error="Docling não está instalado. Execute: pip install docling"
            )
        
        # Salva bytes em arquivo temporário
        with tempfile.NamedTemporaryFile(
            suffix=".pdf", 
            delete=False,
            prefix="spaced_rep_preview_"
        ) as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name
        
        try:
            # Usa pypdfium2 para obter preview rápido por página
            try:
                import pypdfium2 as pdfium
                
                pdf = pdfium.PdfDocument(tmp_path)
                total_pages = len(pdf)
                
                pages_info = []
                for i in range(total_pages):
                    page = pdf[i]
                    text_page = page.get_textpage()
                    page_text = text_page.get_text_range()
                    
                    word_count = len(page_text.split()) if page_text else 0
                    preview = page_text[:preview_chars].strip() if page_text else ""
                    if len(page_text) > preview_chars:
                        preview += "..."
                    
                    pages_info.append(PageInfo(
                        page_number=i + 1,
                        word_count=word_count,
                        preview=preview,
                    ))
                
                pdf.close()
                
                return PdfPreviewResult(
                    total_pages=total_pages,
                    pages=pages_info,
                    filename=filename,
                    file_size=len(pdf_bytes),
                )
                
            except ImportError:
                # Fallback: usar Docling para contagem de páginas
                converter = self._get_converter()
                result = converter.convert(tmp_path)
                
                total_pages = 0
                if hasattr(result.document, 'pages'):
                    total_pages = len(result.document.pages)
                
                # Sem pypdfium2, retorna apenas contagem sem preview detalhado
                return PdfPreviewResult(
                    total_pages=total_pages,
                    pages=[PageInfo(page_number=i+1, word_count=0, preview="") for i in range(total_pages)],
                    filename=filename,
                    file_size=len(pdf_bytes),
                )
                
        except Exception as e:
            logger.exception("Erro ao obter preview do PDF: %s", e)
            return PdfPreviewResult(
                total_pages=0,
                pages=[],
                filename=filename,
                file_size=len(pdf_bytes),
                error=f"Erro ao obter preview: {str(e)}"
            )
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
    
    async def extract_pages(
        self,
        pdf_bytes: bytes,
        page_numbers: List[int],
        filename: str = "document.pdf",
        quality: ExtractionQuality = ExtractionQuality.CLEANED,
    ) -> ExtractionResult:
        """
        Extrai texto apenas das páginas selecionadas.
        
        Args:
            pdf_bytes: Conteúdo binário do PDF
            page_numbers: Lista de números de páginas (1-indexed)
            filename: Nome do arquivo
            quality: Nível de qualidade da extração
        
        Returns:
            ExtractionResult com o texto das páginas selecionadas
        """
        if not self._docling_available:
            return ExtractionResult(
                text="",
                error="Docling não está instalado. Execute: pip install docling"
            )
        
        if not page_numbers:
            return ExtractionResult(
                text="",
                error="Nenhuma página selecionada"
            )
        
        # Salva bytes em arquivo temporário
        with tempfile.NamedTemporaryFile(
            suffix=".pdf", 
            delete=False,
            prefix="spaced_rep_pages_"
        ) as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name
        
        try:
            # Usa pypdfium2 para extração rápida por página
            try:
                import pypdfium2 as pdfium
                
                pdf = pdfium.PdfDocument(tmp_path)
                total_pages = len(pdf)
                
                # Valida números de páginas
                valid_pages = [p for p in page_numbers if 1 <= p <= total_pages]
                if not valid_pages:
                    pdf.close()
                    return ExtractionResult(
                        text="",
                        error=f"Páginas inválidas. O documento tem {total_pages} páginas."
                    )
                
                pages_content = []
                all_text_parts = []
                
                for page_num in sorted(valid_pages):
                    page = pdf[page_num - 1]  # pypdfium2 é 0-indexed
                    text_page = page.get_textpage()
                    page_text = text_page.get_text_range()
                    
                    if quality in (ExtractionQuality.CLEANED, ExtractionQuality.LLM):
                        page_text = self._clean_text(page_text)
                    
                    pages_content.append({
                        "page_number": page_num,
                        "text": page_text,
                        "word_count": len(page_text.split()) if page_text else 0,
                    })
                    
                    if page_text:
                        all_text_parts.append(f"## Página {page_num}\n\n{page_text}")
                
                pdf.close()
                
                combined_text = "\n\n".join(all_text_parts)
                
                return ExtractionResult(
                    text=combined_text,
                    pages=len(valid_pages),
                    word_count=len(combined_text.split()),
                    quality=quality,
                    metadata={
                        "filename": filename,
                        "file_size": len(pdf_bytes),
                        "selected_pages": valid_pages,
                        "total_pages": total_pages,
                    },
                    pages_content=pages_content,
                )
                
            except ImportError:
                # Fallback: extrai tudo e não filtra por página
                logger.warning("pypdfium2 não disponível, extraindo documento completo")
                return await self.extract_from_bytes(pdf_bytes, filename, quality)
                
        except Exception as e:
            logger.exception("Erro na extração de páginas: %s", e)
            return ExtractionResult(
                text="",
                error=f"Erro na extração: {str(e)}"
            )
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


# Instância singleton para uso em toda a aplicação
pdf_extractor = PDFExtractor()


async def extract_pdf_text(
    pdf_bytes: bytes,
    filename: str = "document.pdf",
    quality: str = "cleaned",
    chunk_size: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Função de conveniência para extração de PDF.
    
    Args:
        pdf_bytes: Conteúdo binário do PDF
        filename: Nome do arquivo
        quality: "raw", "cleaned", ou "llm"
        chunk_size: Se especificado, divide em chunks
    
    Returns:
        Dicionário com resultado da extração
    """
    quality_enum = ExtractionQuality(quality)
    result = await pdf_extractor.extract_from_bytes(
        pdf_bytes, 
        filename, 
        quality_enum,
        chunk_size
    )
    return result.to_dict()
