"""
Document extractors following Open/Closed Principle.
New extractors can be added by registering them with ExtractorRegistry.
"""

import io
import logging
from abc import ABC, abstractmethod
from typing import Dict, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ExtractionResult:
    """Result from document extraction."""
    text: str
    metadata: Dict


class DocumentExtractor(ABC):
    """Base class for document extractors."""

    @abstractmethod
    def extract(self, content: bytes) -> ExtractionResult:
        """Extract text from document content."""
        pass


class PDFExtractor(DocumentExtractor):
    """Extract text from PDF documents."""

    def extract(self, content: bytes) -> ExtractionResult:
        import pypdf
        try:
            reader = pypdf.PdfReader(io.BytesIO(content))
            pages = [page.extract_text() or '' for page in reader.pages]
            return ExtractionResult(
                text='\n\n'.join(pages),
                metadata={'page_count': len(reader.pages)}
            )
        except Exception as e:
            logger.warning(f"pypdf failed, trying unstructured: {e}")
            try:
                from unstructured.partition.pdf import partition_pdf
                elements = partition_pdf(file=io.BytesIO(content))
                return ExtractionResult(
                    text='\n\n'.join(str(el) for el in elements),
                    metadata={}
                )
            except ImportError:
                # If unstructured not available, re-raise original error
                raise e


class DocxExtractor(DocumentExtractor):
    """Extract text from Word documents."""

    def extract(self, content: bytes) -> ExtractionResult:
        from docx import Document
        doc = Document(io.BytesIO(content))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return ExtractionResult(text='\n\n'.join(paragraphs), metadata={})


class PlainTextExtractor(DocumentExtractor):
    """Extract text from plain text files."""

    def extract(self, content: bytes) -> ExtractionResult:
        return ExtractionResult(
            text=content.decode('utf-8', errors='ignore'),
            metadata={}
        )


class HTMLExtractor(DocumentExtractor):
    """Extract text from HTML documents."""

    def extract(self, content: bytes) -> ExtractionResult:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(content, 'html.parser')
        # Remove script and style elements
        for script in soup(['script', 'style']):
            script.decompose()
        lines = [
            line.strip()
            for line in soup.get_text(separator='\n').splitlines()
            if line.strip()
        ]
        return ExtractionResult(text='\n'.join(lines), metadata={})


class CSVExtractor(DocumentExtractor):
    """Extract text from CSV files."""

    def extract(self, content: bytes) -> ExtractionResult:
        import csv
        text_stream = io.StringIO(content.decode('utf-8', errors='ignore'))
        rows = list(csv.reader(text_stream))
        return ExtractionResult(
            text='\n'.join(', '.join(row) for row in rows),
            metadata={'row_count': len(rows)}
        )


class JSONExtractor(DocumentExtractor):
    """Extract text from JSON files."""

    def extract(self, content: bytes) -> ExtractionResult:
        import json
        data = json.loads(content.decode('utf-8'))
        return ExtractionResult(
            text=json.dumps(data, indent=2, ensure_ascii=False),
            metadata={}
        )


class ExtractorRegistry:
    """
    Registry for document extractors (Open/Closed Principle).

    New document types can be supported by registering new extractors
    without modifying existing code.
    """

    _extractors: Dict[str, DocumentExtractor] = {}

    @classmethod
    def register(cls, doc_type: str, extractor: DocumentExtractor):
        """Register an extractor for a document type."""
        cls._extractors[doc_type] = extractor

    @classmethod
    def get(cls, doc_type: str) -> DocumentExtractor:
        """Get extractor for a document type."""
        extractor = cls._extractors.get(doc_type)
        if not extractor:
            raise ValueError(f"No extractor registered for: {doc_type}")
        return extractor

    @classmethod
    def supported_types(cls) -> List[str]:
        """Return list of supported document types."""
        return list(cls._extractors.keys())

    @classmethod
    def is_supported(cls, doc_type: str) -> bool:
        """Check if document type is supported."""
        return doc_type in cls._extractors


# Register default extractors
ExtractorRegistry.register('pdf', PDFExtractor())
ExtractorRegistry.register('docx', DocxExtractor())
ExtractorRegistry.register('txt', PlainTextExtractor())
ExtractorRegistry.register('md', PlainTextExtractor())
ExtractorRegistry.register('html', HTMLExtractor())
ExtractorRegistry.register('csv', CSVExtractor())
ExtractorRegistry.register('json', JSONExtractor())
