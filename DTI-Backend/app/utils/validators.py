import io
import re
import unicodedata
from typing import Dict, Any, Tuple
from fastapi import UploadFile, HTTPException
from PIL import Image, UnidentifiedImageError
from PIL.Image import DecompressionBombError

# Enforce decompression bomb defense
Image.MAX_IMAGE_PIXELS = 25_000_000

# Allowed decoded image formats
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP", "BMP", "TIFF", "GIF"}
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
MIN_IMAGE_DIMENSION = 32
MAX_IMAGE_DIMENSION = 4096


def validate_claim_text(claim: str, min_len: int = 3, max_len: int = 500) -> str:
    """
    Sanitizes and strictly validates text claims:
      - Applies Unicode NFC normalization
      - Strips invisible non-printable control characters
      - Enforces minimum and maximum length bounds
      - Rejects whitespace-only or empty strings
    """
    if not claim:
        raise HTTPException(
            status_code=422,
            detail="Claim cannot be empty."
        )

    # Unicode normalization (NFC)
    normalized = unicodedata.normalize("NFC", claim)

    # Strip ASCII and Unicode control characters (except standard whitespace: space, newline, tab)
    sanitized = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\x9F]", "", normalized).strip()

    if len(sanitized) < min_len:
        raise HTTPException(
            status_code=422,
            detail=f"Claim is too short. Minimum length is {min_len} characters."
        )

    if len(sanitized) > max_len:
        raise HTTPException(
            status_code=422,
            detail=f"Claim exceeds maximum allowed length ({max_len} characters)."
        )

    return sanitized


async def stream_and_validate_image_upload(
    file: UploadFile,
    max_size: int = MAX_FILE_SIZE_BYTES
) -> Tuple[bytes, Dict[str, Any]]:
    """
    Streams file upload in chunks to enforce size limits safely without memory spikes,
    then executes comprehensive image security checks with Pillow:
      - Memory streaming byte counter (HTTP 413)
      - Decompression bomb guard (Image.MAX_IMAGE_PIXELS)
      - Header and byte stream verification (Image.verify)
      - Decoded format inspection (HTTP 415)
      - Resolution bounds enforcement (HTTP 422)
    """
    if not file or not file.filename:
        raise HTTPException(
            status_code=422,
            detail="Image file is required."
        )

    total_bytes = 0
    chunks = []
    chunk_size = 1024 * 1024  # 1 MB

    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        total_bytes += len(chunk)
        if total_bytes > max_size:
            raise HTTPException(
                status_code=413,
                detail=f"Image file exceeds the maximum size limit of {max_size // (1024 * 1024)} MB."
            )
        chunks.append(chunk)

    if total_bytes == 0:
        raise HTTPException(
            status_code=400,
            detail="Uploaded image file is empty (0 bytes)."
        )

    image_bytes = b"".join(chunks)

    # Validate image decoding with Pillow
    try:
        buffer = io.BytesIO(image_bytes)
        with Image.open(buffer) as img:
            # 1. Structural integrity verification
            img.verify()

        # Re-open required by Pillow documentation after verify()
        buffer.seek(0)
        with Image.open(buffer) as img:
            img_format = (img.format or "").upper()
            width, height = img.size
            n_frames = getattr(img, "n_frames", 1)

            if img_format not in ALLOWED_IMAGE_FORMATS:
                raise HTTPException(
                    status_code=415,
                    detail=f"Unsupported image format '{img_format}'. Supported formats: {', '.join(sorted(ALLOWED_IMAGE_FORMATS))}."
                )

            if width < MIN_IMAGE_DIMENSION or height < MIN_IMAGE_DIMENSION:
                raise HTTPException(
                    status_code=422,
                    detail=f"Image dimensions too small ({width}x{height}px). Minimum resolution is {MIN_IMAGE_DIMENSION}x{MIN_IMAGE_DIMENSION}px."
                )

            if width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION:
                raise HTTPException(
                    status_code=422,
                    detail=f"Image dimensions too large ({width}x{height}px). Maximum resolution is {MAX_IMAGE_DIMENSION}x{MAX_IMAGE_DIMENSION}px."
                )

            metadata = {
                "format": img_format,
                "width": width,
                "height": height,
                "n_frames": n_frames,
                "size_bytes": total_bytes
            }

            return image_bytes, metadata

    except DecompressionBombError as e:
        raise HTTPException(
            status_code=422,
            detail="Image rejected: pixel count exceeds security limits (decompression bomb protection)."
        ) from e

    except UnidentifiedImageError as e:
        raise HTTPException(
            status_code=415,
            detail="Cannot identify image: file is corrupted or not a recognized image format."
        ) from e

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=422,
            detail=f"Image validation failed: {type(e).__name__}"
        ) from e
