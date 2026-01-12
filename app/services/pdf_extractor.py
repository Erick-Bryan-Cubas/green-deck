"""
DEPRECATED: This module is kept for backward compatibility.
Use document_extractor.py instead, which supports all Docling formats.
"""

# Re-export everything from document_extractor for backward compatibility
from .document_extractor import (
    DocumentExtractor as PDFExtractor,
    document_extractor as pdf_extractor,
    ExtractionQuality,
    ExtractionResult,
    PageInfo,
    DocumentPreviewResult as PdfPreviewResult,
    extract_document_text as extract_pdf_text,
    SUPPORTED_FORMATS,
)

__all__ = [
    'PDFExtractor',
    'pdf_extractor',
    'ExtractionQuality',
    'ExtractionResult',
    'PageInfo',
    'PdfPreviewResult',
    'extract_pdf_text',
    'SUPPORTED_FORMATS',
]
