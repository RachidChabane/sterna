"""
Document processor for text extraction and chunking.
"""

import logging
from typing import Dict, List, Tuple

from ..config import config
from .extractors import ExtractorRegistry
from .storage import StorageProvider, R2StorageProvider

logger = logging.getLogger(__name__)


class DocumentProcessor:
    """Handles document parsing and chunking."""

    def __init__(self, storage_provider: StorageProvider = None):
        self.storage = storage_provider or R2StorageProvider()

    def extract_text(self, document) -> Tuple[str, Dict]:
        """
        Extract text from document using registered extractor.

        Args:
            document: KnowledgeDocument instance

        Returns:
            Tuple of (extracted_text, metadata)
        """
        content = self._get_content(document)
        extractor = ExtractorRegistry.get(document.document_type)
        result = extractor.extract(content)
        return result.text.strip(), result.metadata

    def _get_content(self, document) -> bytes:
        """Load content from appropriate storage."""
        from ..models import StorageType

        if document.storage_type == StorageType.INLINE:
            return bytes(document.content)
        return self.storage.download(document.r2_bucket, document.r2_key)

    def chunk_text(self, text: str) -> List[Dict]:
        """
        Split text into overlapping chunks using config settings.

        Args:
            text: Text to chunk

        Returns:
            List of chunk dictionaries with text, position, and token count
        """
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        # Try to use tiktoken for accurate token counting
        try:
            import tiktoken
            enc = tiktoken.get_encoding("cl100k_base")
        except Exception:
            enc = None

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=config.chunk_size,
            chunk_overlap=config.chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

        chunks = splitter.split_text(text)
        result = []
        char_offset = 0

        for chunk in chunks:
            # Find position in original text
            start_char = text.find(chunk, char_offset)
            if start_char == -1:
                start_char = char_offset
            end_char = start_char + len(chunk)
            char_offset = start_char + 1

            # Count tokens
            if enc:
                token_count = len(enc.encode(chunk))
            else:
                token_count = int(len(chunk.split()) * config.tokens_per_word_estimate)

            result.append({
                'text': chunk,
                'start_char': start_char,
                'end_char': end_char,
                'token_count': token_count,
            })

        return result

    def estimate_page_number(self, document, char_position: int) -> int | None:
        """
        Estimate page number based on character position.
        Only works for documents with page_count metadata.
        """
        if not document.page_count or document.page_count <= 1:
            return 1

        total_chars = len(document.extracted_text)
        if total_chars == 0:
            return 1

        chars_per_page = total_chars / document.page_count
        return min(int(char_position / chars_per_page) + 1, document.page_count)
