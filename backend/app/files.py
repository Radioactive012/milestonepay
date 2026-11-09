import re
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError

MAX_FILE_BYTES = 10 * 1024 * 1024
PREVIEW_MAX_SIDE = 900
WATERMARK = "UNPAID PREVIEW"
IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}


def safe_filename(name: str | None) -> str:
    base = (name or "file").replace("\\", "/").rsplit("/", 1)[-1]
    cleaned = re.sub(r"[^A-Za-z0-9._ -]", "_", base).strip(" .")
    return cleaned[:120] or "file"


def make_preview(data: bytes, content_type: str | None) -> bytes | None:
    """A smaller JPEG copy with the watermark tiled across it, or None if it isn't an image."""
    if content_type not in IMAGE_TYPES:
        return None
    try:
        with Image.open(BytesIO(data)) as original:
            image = original.convert("RGBA")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        return None

    image.thumbnail((PREVIEW_MAX_SIDE, PREVIEW_MAX_SIDE))
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    size = max(14, image.width // 14)
    font = ImageFont.load_default(size=size)
    row_height = size * 3
    for row, y in enumerate(range(-image.height, image.height * 2, row_height)):
        offset = (row % 2) * size * 4
        for x in range(-image.width, image.width * 2, size * 9):
            draw.text(
                (x + offset, y),
                WATERMARK,
                font=font,
                fill=(255, 255, 255, 120),
                stroke_width=max(1, size // 12),
                stroke_fill=(0, 0, 0, 120),
            )
    watermarked = Image.alpha_composite(image, overlay.rotate(30)).convert("RGB")
    buffer = BytesIO()
    watermarked.save(buffer, "JPEG", quality=70)
    return buffer.getvalue()
