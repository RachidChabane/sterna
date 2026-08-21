"""
Centralized security utilities for file validation and sanitization.

This module provides:
- Image validation (magic bytes) and sanitization (metadata stripping)
- Document/video/audio file type validation
- Filename sanitization to prevent header injection
- Internal service authentication utilities

Usage:
    from security import validate_image, sanitize_image, validate_file_type
    from security import sanitize_filename, verify_service_token
"""

from .image import (
    IMAGE_SIGNATURES,
    ALLOWED_IMAGE_TYPES,
    validate_image_magic_bytes,
    sanitize_image,
    get_image_format_from_mime,
)

from .file_validators import (
    VIDEO_SIGNATURES,
    AUDIO_SIGNATURES,
    DOCUMENT_SIGNATURES,
    ALLOWED_VIDEO_TYPES,
    ALLOWED_AUDIO_TYPES,
    ALLOWED_DOCUMENT_TYPES,
    validate_video_magic_bytes,
    validate_audio_magic_bytes,
    validate_document_magic_bytes,
    validate_file_type,
    get_file_category,
)

from .sanitizers import (
    sanitize_filename,
    sanitize_content_disposition,
)

from .service_auth import (
    verify_service_token,
    require_service_auth,
    ServiceAuthenticationFailed,
)

__all__ = [
    # Image utilities
    'IMAGE_SIGNATURES',
    'ALLOWED_IMAGE_TYPES',
    'validate_image_magic_bytes',
    'sanitize_image',
    'get_image_format_from_mime',
    # File validators
    'VIDEO_SIGNATURES',
    'AUDIO_SIGNATURES',
    'DOCUMENT_SIGNATURES',
    'ALLOWED_VIDEO_TYPES',
    'ALLOWED_AUDIO_TYPES',
    'ALLOWED_DOCUMENT_TYPES',
    'validate_video_magic_bytes',
    'validate_audio_magic_bytes',
    'validate_document_magic_bytes',
    'validate_file_type',
    'get_file_category',
    # Sanitizers
    'sanitize_filename',
    'sanitize_content_disposition',
    # Service auth
    'verify_service_token',
    'require_service_auth',
    'ServiceAuthenticationFailed',
]
