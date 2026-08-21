"""
Document upload service (Single Responsibility Principle).
Handles all upload logic extracted from views.
"""

import hashlib
import logging
from typing import Optional, List

from django.db import transaction

from ..config import config
from ..models import (
    KnowledgeDocument,
    KnowledgeBaseSettings,
    DocumentStatus,
    DocumentType,
    StorageType,
)
from .storage import R2StorageProvider

logger = logging.getLogger(__name__)


class DocumentUploadService:
    """
    Handles document upload logic (SRP - separated from view).
    """

    class StorageLimitExceeded(Exception):
        """Raised when user's storage limit would be exceeded."""
        pass

    class UnsupportedFileType(Exception):
        """Raised for unsupported file types."""
        pass

    class DuplicateDocument(Exception):
        """Raised when document already exists."""
        def __init__(self, existing_id, existing_filename):
            self.existing_id = existing_id
            self.existing_filename = existing_filename
            super().__init__(f"Duplicate of {existing_filename}")

    # Extension to DocumentType mapping
    EXTENSION_MAP = {
        'pdf': DocumentType.PDF,
        'docx': DocumentType.DOCX,
        'doc': DocumentType.DOCX,
        'txt': DocumentType.TXT,
        'md': DocumentType.MD,
        'markdown': DocumentType.MD,
        'csv': DocumentType.CSV,
        'html': DocumentType.HTML,
        'htm': DocumentType.HTML,
        'json': DocumentType.JSON,
    }

    def __init__(self, storage_provider=None):
        self.config = config
        self.storage = storage_provider or R2StorageProvider()

    def upload(
        self,
        user,
        file,
        tags: Optional[List[str]] = None,
    ) -> KnowledgeDocument:
        """
        Upload and create document record.

        Args:
            user: User uploading the document
            file: Uploaded file object
            tags: Optional list of tags

        Returns:
            Created KnowledgeDocument instance

        Raises:
            StorageLimitExceeded: If storage limit would be exceeded
            UnsupportedFileType: If file type is not supported
            DuplicateDocument: If identical document already exists
        """
        from ..tasks import process_document_task

        tags = tags or []

        # Validate storage limit
        settings = self._get_settings(user)
        storage_limit_bytes = settings.storage_limit_mb * 1024 * 1024
        if settings.total_storage_bytes + file.size > storage_limit_bytes:
            raise self.StorageLimitExceeded()

        # Validate file type
        extension = file.name.rsplit('.', 1)[-1].lower() if '.' in file.name else ''
        doc_type = self.EXTENSION_MAP.get(extension)
        if not doc_type:
            raise self.UnsupportedFileType(f'Unsupported file type: {extension}')

        # Read and hash content
        file_content = file.read()
        content_hash = hashlib.sha256(file_content).hexdigest()

        # Check for duplicates
        existing = KnowledgeDocument.objects.filter(
            user=user,
            content_hash=content_hash
        ).first()
        if existing:
            raise self.DuplicateDocument(existing.id, existing.filename)

        # Create document
        with transaction.atomic():
            document = self._create_document(
                user=user,
                file=file,
                file_content=file_content,
                doc_type=doc_type,
                content_hash=content_hash,
                tags=tags,
            )
            settings.update_stats(documents_delta=1, storage_delta=file.size)

        # Queue processing
        process_document_task.delay(str(document.id))
        return document

    def _create_document(
        self,
        user,
        file,
        file_content: bytes,
        doc_type: str,
        content_hash: str,
        tags: List[str],
    ) -> KnowledgeDocument:
        """Create document with appropriate storage type."""
        # Determine storage type from config
        use_inline = file.size < self.config.inline_storage_threshold_bytes

        if use_inline:
            return KnowledgeDocument.objects.create(
                user=user,
                filename=file.name,
                original_filename=file.name,
                document_type=doc_type,
                mime_type=getattr(file, 'content_type', None) or 'application/octet-stream',
                file_size_bytes=file.size,
                storage_type=StorageType.INLINE,
                content=file_content,
                content_hash=content_hash,
                tags=tags,
                status=DocumentStatus.PENDING,
            )
        else:
            r2_key = f"{user.id}/knowledge/{content_hash}"
            self.storage.upload(self.config.r2_bucket, r2_key, file_content)

            return KnowledgeDocument.objects.create(
                user=user,
                filename=file.name,
                original_filename=file.name,
                document_type=doc_type,
                mime_type=getattr(file, 'content_type', None) or 'application/octet-stream',
                file_size_bytes=file.size,
                storage_type=StorageType.R2,
                r2_bucket=self.config.r2_bucket,
                r2_key=r2_key,
                content_hash=content_hash,
                tags=tags,
                status=DocumentStatus.PENDING,
            )

    def _get_settings(self, user) -> KnowledgeBaseSettings:
        """Get or create user settings."""
        settings, _ = KnowledgeBaseSettings.objects.get_or_create(user=user)
        return settings
