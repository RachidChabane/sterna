"""
Image security utilities.

Provides:
- Magic byte validation to verify actual file content (prevents MIME spoofing)
- Image re-encoding to strip EXIF metadata and prevent polyglot attacks
- Format detection and conversion utilities

Security measures:
1. Don't trust Content-Type headers - validate actual bytes
2. Re-encode images to strip metadata (GPS, camera info, embedded scripts)
3. Resize oversized images to prevent resource exhaustion
4. Validate image is actually renderable
"""

import io
import logging
from typing import Any, Dict, Tuple

logger = logging.getLogger(__name__)


# Magic bytes for image file type validation
# These are the first bytes of each image format
IMAGE_SIGNATURES = {
    b'\xff\xd8\xff': 'image/jpeg',           # JPEG (FFD8FF)
    b'\x89PNG\r\n\x1a\n': 'image/png',       # PNG
    b'GIF87a': 'image/gif',                   # GIF87a
    b'GIF89a': 'image/gif',                   # GIF89a
    b'RIFF': 'image/webp',                    # WebP (needs WEBP check at bytes 8-12)
}

# Allowed image MIME types
ALLOWED_IMAGE_TYPES = {'image/jpeg', 'image/png', 'image/gif', 'image/webp'}


def validate_image_magic_bytes(content: bytes) -> str | None:
    """
    Validate image file by checking magic bytes.

    This prevents MIME type spoofing attacks where an attacker uploads
    a malicious file (HTML, SVG with JS, etc.) with a fake image Content-Type.

    Args:
        content: Raw file bytes

    Returns:
        Detected MIME type if valid image, None if invalid/unknown
    """
    if len(content) < 12:
        return None

    # Check each signature
    for signature, mime_type in IMAGE_SIGNATURES.items():
        if content.startswith(signature):
            # Special handling for WebP (RIFF....WEBP format)
            if signature == b'RIFF':
                if content[8:12] != b'WEBP':
                    continue
            return mime_type

    return None


def get_image_format_from_mime(mime_type: str) -> str:
    """
    Convert MIME type to PIL format string.

    Args:
        mime_type: Image MIME type (e.g., 'image/jpeg')

    Returns:
        PIL format string (e.g., 'JPEG')
    """
    formats = {
        'image/jpeg': 'JPEG',
        'image/png': 'PNG',
        'image/gif': 'GIF',
        'image/webp': 'WEBP',
    }
    return formats.get(mime_type, 'PNG')


def sanitize_image(
    content: bytes,
    target_format: str = 'PNG',
    max_dimension: int = 4096,
    quality: int = 85,
) -> tuple[bytes, str]:
    """
    Re-encode image to strip metadata and ensure it's a valid image.

    This is a critical security measure that prevents:
    - EXIF data leakage (GPS coordinates, camera serial, timestamps)
    - Malicious payloads hidden in image metadata
    - Polyglot files (files valid as multiple formats, e.g., GIFAR)
    - Corrupted/malformed images that could exploit parser bugs

    Args:
        content: Raw image bytes
        target_format: Output format ('JPEG', 'PNG', 'WEBP', 'GIF')
        max_dimension: Maximum width/height (images larger are resized)
        quality: Output quality for lossy formats (1-100)

    Returns:
        Tuple of (sanitized_content, mime_type)

    Raises:
        ValueError: If image is invalid, corrupted, or cannot be processed
    """
    try:
        from PIL import Image

        # Open and verify the image is valid
        img: Image.Image = Image.open(io.BytesIO(content))
        img.verify()  # Verify it's a valid image (can only call once)

        # Re-open after verify (verify() leaves file in invalid state)
        img = Image.open(io.BytesIO(content))

        original_format = img.format
        logger.debug(f"Image format: {original_format}, size: {len(content)} bytes")

        # Handle animated GIFs specially - detect BEFORE any modifications
        # Animated GIFs: validate only, return original to preserve all frames
        # Re-encoding animated GIFs loses frames when color modes are converted
        if original_format == 'GIF':
            try:
                n_frames = getattr(img, 'n_frames', 1)
                is_animated = n_frames > 1
            except Exception:
                is_animated = False

            if is_animated:
                # For animated GIFs, just validate dimensions and return original
                # Stripping metadata would require complex frame-by-frame processing
                if img.width <= max_dimension and img.height <= max_dimension:
                    logger.debug(f"Animated GIF with {n_frames} frames - preserving original")
                    return content, 'image/gif'
                else:
                    # Animated GIF too large - can't safely resize, log warning
                    logger.warning(
                        f"Animated GIF too large ({img.width}x{img.height}), "
                        f"exceeds {max_dimension}px but resizing would lose animation"
                    )
                    # Still return original - better than losing animation
                    return content, 'image/gif'

        # Convert color modes as needed (for non-animated images)
        if img.mode in ('RGBA', 'P', 'LA'):
            if target_format.upper() == 'JPEG':
                # JPEG doesn't support transparency - add white background
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                if img.mode in ('RGBA', 'LA'):
                    # Paste with alpha mask
                    alpha = img.split()[-1]
                    background.paste(img, mask=alpha)
                else:
                    background.paste(img)
                img = background
            elif img.mode == 'P':
                img = img.convert('RGBA')
        elif img.mode not in ('RGB', 'L', 'RGBA'):
            img = img.convert('RGB')

        # Resize if too large (prevents resource exhaustion)
        if img.width > max_dimension or img.height > max_dimension:
            img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
            logger.info(f"Resized image from larger than {max_dimension}px to {img.size}")

        # Re-encode to strip ALL metadata
        output = io.BytesIO()

        format_config: Dict[str, Tuple[str, str, Dict[str, Any]]] = {
            'JPEG': ('JPEG', 'image/jpeg', {'quality': quality, 'optimize': True}),
            'PNG': ('PNG', 'image/png', {'optimize': True}),
            'WEBP': ('WEBP', 'image/webp', {'quality': quality}),
            'GIF': ('GIF', 'image/gif', {}),
        }

        fmt, mime_type, save_kwargs = format_config.get(
            target_format.upper(),
            ('PNG', 'image/png', {'optimize': True})
        )

        # Note: Animated GIFs are handled early (returned original content)
        # Only static images reach this point
        img.save(output, format=fmt, **save_kwargs)

        return output.getvalue(), mime_type

    except Exception as e:
        logger.warning(f"Image sanitization failed: {e}")
        raise ValueError(f"Invalid or corrupted image: {e}")
