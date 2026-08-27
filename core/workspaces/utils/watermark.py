"""
Watermark utilities for image processing.

Provides functions to apply watermarks to images for sharing and downloads.
"""

import io
from typing import Optional


def apply_watermark(
    image_data: bytes,
    position: str = 'bottom-right',
    text: str = 'Sterna',
    opacity: float = 0.6
) -> Optional[bytes]:
    """
    Apply a text watermark to an image.

    Args:
        image_data: Raw image bytes
        position: One of 'bottom-right', 'bottom-left', 'top-right', 'top-left'
        text: Watermark text
        opacity: Watermark opacity (0.0 to 1.0)

    Returns:
        Watermarked image as bytes (JPEG format), or None if processing fails
    """
    from PIL import Image, ImageDraw, ImageFont

    # Open the image
    img: Image.Image = Image.open(io.BytesIO(image_data))

    # Convert to RGBA for transparency support
    if img.mode != 'RGBA':
        img = img.convert('RGBA')

    # Create a transparent overlay for the watermark
    overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Calculate font size based on image dimensions (roughly 2-3% of smallest dimension)
    min_dim = min(img.width, img.height)
    font_size = max(16, int(min_dim * 0.025))

    # Try to use a nice font, fall back to default
    font: "ImageFont.FreeTypeFont | ImageFont.ImageFont"
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
    except (IOError, OSError):
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", font_size)
        except (IOError, OSError):
            font = ImageFont.load_default()

    # Get text bounding box
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    # Calculate position with padding
    padding = int(min_dim * 0.02)

    if position == 'bottom-right':
        x = img.width - text_width - padding
        y = img.height - text_height - padding
    elif position == 'bottom-left':
        x = padding
        y = img.height - text_height - padding
    elif position == 'top-right':
        x = img.width - text_width - padding
        y = padding
    elif position == 'top-left':
        x = padding
        y = padding
    else:  # Default to bottom-right
        x = img.width - text_width - padding
        y = img.height - text_height - padding

    # Draw text shadow for better visibility
    shadow_offset = max(1, font_size // 20)
    shadow_color = (0, 0, 0, int(255 * opacity * 0.5))
    draw.text((x + shadow_offset, y + shadow_offset), text, font=font, fill=shadow_color)

    # Draw main text
    text_color = (255, 255, 255, int(255 * opacity))
    draw.text((x, y), text, font=font, fill=text_color)

    # Composite the overlay onto the image
    watermarked = Image.alpha_composite(img, overlay)

    # Convert back to RGB for JPEG compatibility
    output = io.BytesIO()
    watermarked = watermarked.convert('RGB')
    watermarked.save(output, format='JPEG', quality=95)
    output.seek(0)

    return output.read()
