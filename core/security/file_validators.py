"""
File type validation utilities.

Provides magic byte validation for:
- Video files (MP4, WebM, MOV, AVI)
- Audio files (MP3, WAV, OGG, FLAC, M4A, WebM audio)
- Document files (PDF, DOCX, XLSX, PPTX)

Security principle: Never trust Content-Type headers from clients.
Always validate actual file content using magic bytes/signatures.
"""

import logging

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────
# Video Signatures
# ─────────────────────────────────────────────────────────

VIDEO_SIGNATURES = {
    # MP4/M4V (ftyp box indicates MP4 container)
    # Format: ....ftyp where .... is size (4 bytes)
    b'ftyp': 'video/mp4',  # Check at offset 4
    # WebM (starts with EBML header 0x1A45DFA3)
    b'\x1a\x45\xdf\xa3': 'video/webm',
    # AVI (RIFF....AVI )
    b'RIFF': 'video/x-msvideo',  # Need to check for AVI at offset 8
    # MOV (also uses ftyp, detected as MP4)
}

ALLOWED_VIDEO_TYPES = {
    'video/mp4',
    'video/webm',
    'video/quicktime',
    'video/x-msvideo',
    'video/x-matroska',
}


def validate_video_magic_bytes(content: bytes) -> str | None:
    """
    Validate video file by checking magic bytes.

    Args:
        content: Raw file bytes (at least first 12 bytes needed)

    Returns:
        Detected MIME type if valid video, None if invalid/unknown
    """
    if len(content) < 12:
        return None

    # Check for MP4/MOV (ftyp at offset 4)
    if content[4:8] == b'ftyp':
        # Check specific brand for MOV vs MP4
        brand = content[8:12]
        if brand in (b'qt  ', b'moov'):
            return 'video/quicktime'
        return 'video/mp4'

    # Check for WebM/Matroska (EBML header)
    if content[:4] == b'\x1a\x45\xdf\xa3':
        # Could be WebM or MKV - both use EBML
        # WebM is technically a subset of Matroska
        return 'video/webm'

    # Check for AVI (RIFF....AVI )
    if content[:4] == b'RIFF' and content[8:12] == b'AVI ':
        return 'video/x-msvideo'

    return None


# ─────────────────────────────────────────────────────────
# Audio Signatures
# ─────────────────────────────────────────────────────────

AUDIO_SIGNATURES = {
    # MP3 (ID3 tag or sync word)
    b'ID3': 'audio/mpeg',              # ID3v2 tag
    b'\xff\xfb': 'audio/mpeg',         # MP3 sync word (MPEG-1 Layer 3)
    b'\xff\xfa': 'audio/mpeg',         # MP3 sync word variant
    b'\xff\xf3': 'audio/mpeg',         # MP3 sync word (MPEG-2 Layer 3)
    b'\xff\xf2': 'audio/mpeg',         # MP3 sync word variant
    # WAV (RIFF....WAVE)
    b'RIFF': 'audio/wav',              # Need to check for WAVE at offset 8
    # OGG (OggS)
    b'OggS': 'audio/ogg',
    # FLAC
    b'fLaC': 'audio/flac',
    # M4A (MP4 container for audio)
    # Uses same ftyp as video, detected by content
    # WebM audio - same as video WebM
}

ALLOWED_AUDIO_TYPES = {
    'audio/mpeg',
    'audio/mp3',
    'audio/wav',
    'audio/wave',
    'audio/x-wav',
    'audio/ogg',
    'audio/flac',
    'audio/mp4',
    'audio/m4a',
    'audio/x-m4a',
    'audio/webm',
}


def validate_audio_magic_bytes(content: bytes) -> str | None:
    """
    Validate audio file by checking magic bytes.

    Args:
        content: Raw file bytes

    Returns:
        Detected MIME type if valid audio, None if invalid/unknown
    """
    if len(content) < 12:
        return None

    # MP3 with ID3 tag
    if content[:3] == b'ID3':
        return 'audio/mpeg'

    # MP3 sync word (various MPEG audio layer 3 variants)
    if content[:2] in (b'\xff\xfb', b'\xff\xfa', b'\xff\xf3', b'\xff\xf2'):
        return 'audio/mpeg'

    # WAV (RIFF....WAVE)
    if content[:4] == b'RIFF' and content[8:12] == b'WAVE':
        return 'audio/wav'

    # OGG Vorbis/Opus
    if content[:4] == b'OggS':
        return 'audio/ogg'

    # FLAC
    if content[:4] == b'fLaC':
        return 'audio/flac'

    # M4A (MP4 audio) - ftyp box with audio brand
    if content[4:8] == b'ftyp':
        brand = content[8:12]
        if brand in (b'M4A ', b'mp42', b'isom'):
            return 'audio/mp4'

    # WebM audio (same EBML header as video)
    if content[:4] == b'\x1a\x45\xdf\xa3':
        return 'audio/webm'

    return None


# ─────────────────────────────────────────────────────────
# Document Signatures
# ─────────────────────────────────────────────────────────

DOCUMENT_SIGNATURES = {
    # PDF
    b'%PDF': 'application/pdf',
    # ZIP-based formats (DOCX, XLSX, PPTX, ODT, etc.)
    b'PK\x03\x04': 'application/zip',  # Need further detection
    # Legacy Office formats
    b'\xd0\xcf\x11\xe0': 'application/msword',  # OLE Compound Document
}

ALLOWED_DOCUMENT_TYPES = {
    'application/pdf',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',  # DOCX
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',  # XLSX
    'application/vnd.openxmlformats-officedocument.presentationml.presentation',  # PPTX
    'application/vnd.ms-excel',
    'application/vnd.ms-powerpoint',
    'text/plain',
    'text/csv',
}


def validate_document_magic_bytes(content: bytes, filename: str | None = None) -> str | None:
    """
    Validate document file by checking magic bytes.

    For ZIP-based formats (DOCX, XLSX, PPTX), uses filename extension
    as a hint since they all share the PK signature.

    Args:
        content: Raw file bytes
        filename: Original filename (helps distinguish Office formats)

    Returns:
        Detected MIME type if valid document, None if invalid/unknown
    """
    if len(content) < 8:
        return None

    # PDF
    if content[:4] == b'%PDF':
        return 'application/pdf'

    # ZIP-based Office formats (DOCX, XLSX, PPTX)
    if content[:4] == b'PK\x03\x04':
        # Use filename extension to determine specific type
        if filename:
            ext = filename.lower().split('.')[-1] if '.' in filename else ''
            ext_to_mime = {
                'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                'docm': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                'xlsm': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
                'pptm': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
                'odt': 'application/vnd.oasis.opendocument.text',
                'ods': 'application/vnd.oasis.opendocument.spreadsheet',
                'odp': 'application/vnd.oasis.opendocument.presentation',
            }
            if ext in ext_to_mime:
                return ext_to_mime[ext]
        # Generic ZIP/Office document
        return 'application/zip'

    # Legacy Office formats (OLE Compound Document)
    if content[:4] == b'\xd0\xcf\x11\xe0':
        # Could be DOC, XLS, or PPT - use filename
        if filename:
            ext = filename.lower().split('.')[-1] if '.' in filename else ''
            if ext == 'doc':
                return 'application/msword'
            elif ext == 'xls':
                return 'application/vnd.ms-excel'
            elif ext == 'ppt':
                return 'application/vnd.ms-powerpoint'
        return 'application/msword'

    return None


# ─────────────────────────────────────────────────────────
# Unified File Validation
# ─────────────────────────────────────────────────────────

def get_file_category(mime_type: str) -> str | None:
    """
    Determine the category of a file based on its MIME type.

    Args:
        mime_type: MIME type string

    Returns:
        Category string ('image', 'video', 'audio', 'document') or None
    """
    if not mime_type:
        return None

    if mime_type.startswith('image/'):
        return 'image'
    elif mime_type.startswith('video/'):
        return 'video'
    elif mime_type.startswith('audio/'):
        return 'audio'
    elif mime_type in ALLOWED_DOCUMENT_TYPES or mime_type.startswith('text/'):
        return 'document'

    return None


def validate_file_type(
    content: bytes,
    claimed_mime_type: str | None = None,
    filename: str | None = None,
) -> tuple[str | None, str | None]:
    """
    Validate file content and detect its actual type.

    This is the main entry point for file validation. It checks magic bytes
    to determine the actual file type, regardless of what the client claims.

    Args:
        content: Raw file bytes
        claimed_mime_type: MIME type claimed by client (for reference)
        filename: Original filename (helps with Office format detection)

    Returns:
        Tuple of (detected_mime_type, category) where category is
        'image', 'video', 'audio', 'document', or None if unknown
    """
    # Import here to avoid circular imports
    from security.image import validate_image_magic_bytes

    # Try image first (most common for uploads)
    detected = validate_image_magic_bytes(content)
    if detected:
        return detected, 'image'

    # Try video
    detected = validate_video_magic_bytes(content)
    if detected:
        return detected, 'video'

    # Try audio
    detected = validate_audio_magic_bytes(content)
    if detected:
        return detected, 'audio'

    # Try document
    detected = validate_document_magic_bytes(content, filename)
    if detected:
        return detected, 'document'

    # Unknown file type
    logger.warning(
        f"Unknown file type: claimed={claimed_mime_type}, "
        f"filename={filename}, first_bytes={content[:16].hex() if content else 'empty'}"
    )
    return None, None
