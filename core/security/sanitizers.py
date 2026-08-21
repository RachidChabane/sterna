"""
Content sanitization utilities.

Provides:
- Filename sanitization to prevent path traversal and header injection
- Content-Disposition header safe formatting

Security considerations:
- Filenames can contain path traversal sequences (../, etc.)
- Filenames in HTTP headers can cause header injection
- Unicode characters can be used for homograph attacks
- Null bytes can truncate strings in some contexts
"""

import re
import unicodedata
import logging

logger = logging.getLogger(__name__)


# Characters that are dangerous in filenames (cross-platform)
DANGEROUS_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# Path traversal patterns
PATH_TRAVERSAL = re.compile(r'\.\.[\\/]|[\\/]\.\.|\.\.$')

# Characters that could cause HTTP header injection
HEADER_INJECTION_CHARS = re.compile(r'[\r\n]')

# Maximum filename length (most filesystems support 255 bytes)
MAX_FILENAME_LENGTH = 200


def sanitize_filename(
    filename: str,
    max_length: int = MAX_FILENAME_LENGTH,
    allow_unicode: bool = True,
    default_name: str = 'file',
) -> str:
    """
    Sanitize a filename to prevent security issues.

    This function:
    1. Removes path components (keeps only basename)
    2. Removes dangerous characters (<>:"/\\|?* and control chars)
    3. Removes path traversal sequences (../)
    4. Normalizes Unicode to prevent homograph attacks
    5. Truncates to safe length while preserving extension
    6. Handles empty/whitespace-only names

    Args:
        filename: The original filename from user input
        max_length: Maximum allowed length (default 200)
        allow_unicode: Whether to allow non-ASCII characters
        default_name: Fallback name if sanitization results in empty string

    Returns:
        Sanitized filename safe for filesystem and HTTP headers
    """
    if not filename:
        return default_name

    # Normalize Unicode (NFC form - composed characters)
    filename = unicodedata.normalize('NFC', filename)

    # Remove any path components - keep only the basename
    # Handle both Unix and Windows path separators
    filename = filename.replace('\\', '/').split('/')[-1]

    # Remove null bytes (can truncate strings in C-based code)
    filename = filename.replace('\x00', '')

    # Remove dangerous characters
    filename = DANGEROUS_CHARS.sub('', filename)

    # Remove header injection characters
    filename = HEADER_INJECTION_CHARS.sub('', filename)

    # Remove path traversal patterns
    filename = PATH_TRAVERSAL.sub('', filename)

    # Strip leading/trailing whitespace and dots
    filename = filename.strip('. \t')

    # If not allowing unicode, transliterate to ASCII
    if not allow_unicode:
        filename = unicodedata.normalize('NFKD', filename)
        filename = filename.encode('ascii', 'ignore').decode('ascii')

    # Handle empty result
    if not filename:
        return default_name

    # Truncate while preserving extension
    if len(filename) > max_length:
        # Split name and extension
        if '.' in filename:
            name_part, ext = filename.rsplit('.', 1)
            ext = '.' + ext
            # Ensure extension isn't too long
            if len(ext) > 20:
                ext = ext[:20]
            # Truncate name part
            max_name_len = max_length - len(ext)
            if max_name_len > 0:
                filename = name_part[:max_name_len] + ext
            else:
                filename = name_part[:max_length]
        else:
            filename = filename[:max_length]

    return filename


def sanitize_content_disposition(
    filename: str,
    disposition_type: str = 'inline',
) -> str:
    """
    Generate a safe Content-Disposition header value.

    This properly encodes the filename according to RFC 5987 to handle
    Unicode characters and special characters safely.

    Args:
        filename: The filename to include in the header
        disposition_type: 'inline' (display in browser) or 'attachment' (download)

    Returns:
        Safe Content-Disposition header value
    """
    # First sanitize the filename
    safe_filename = sanitize_filename(filename, allow_unicode=False)

    # For ASCII-only filenames, use simple format
    if safe_filename.isascii():
        # Escape quotes in filename
        escaped = safe_filename.replace('"', '\\"')
        return f'{disposition_type}; filename="{escaped}"'

    # For Unicode, use RFC 5987 encoding (UTF-8'')
    # Also provide ASCII fallback for older clients
    ascii_name = sanitize_filename(filename, allow_unicode=False)
    escaped_ascii = ascii_name.replace('"', '\\"')

    # URL-encode the UTF-8 filename
    from urllib.parse import quote
    utf8_name = quote(sanitize_filename(filename, allow_unicode=True))

    return (
        f"{disposition_type}; "
        f'filename="{escaped_ascii}"; '
        f"filename*=UTF-8''{utf8_name}"
    )


def get_safe_extension(filename: str, default: str = '') -> str:
    """
    Extract and validate file extension from filename.

    Args:
        filename: Original filename
        default: Default extension if none found

    Returns:
        Lowercase extension without dot, or default
    """
    if not filename or '.' not in filename:
        return default

    ext = filename.rsplit('.', 1)[-1].lower()

    # Validate extension (alphanumeric only, max 10 chars)
    if ext.isalnum() and len(ext) <= 10:
        return ext

    return default
