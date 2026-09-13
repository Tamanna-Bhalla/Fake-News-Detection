import io
import sys
import unittest
from pathlib import Path
from PIL import Image
from fastapi import HTTPException, UploadFile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.utils.validators import validate_claim_text, stream_and_validate_image_upload


class TestValidators(unittest.IsolatedAsyncioTestCase):
    def _create_image_bytes(self, width=100, height=100, fmt="JPEG", color=(100, 150, 200)):
        img = Image.new("RGB", (width, height), color=color)
        buf = io.BytesIO()
        img.save(buf, fmt)
        return buf.getvalue()

    def test_validate_claim_text_valid(self):
        claim = "  NASA discovers water ice on lunar poles.  "
        clean = validate_claim_text(claim)
        self.assertEqual(clean, "NASA discovers water ice on lunar poles.")

    def test_validate_claim_text_unicode_nfc(self):
        # Decomposed e + acute accent vs composed é
        decomposed = "e\u0301vénement"
        composed = "événement"
        clean = validate_claim_text(decomposed)
        self.assertEqual(clean, composed)

    def test_validate_claim_text_strips_control_chars(self):
        claim = "Breaking news\x00\x07: Significant event\x1f confirmed."
        clean = validate_claim_text(claim)
        self.assertEqual(clean, "Breaking news: Significant event confirmed.")

    def test_validate_claim_text_too_short(self):
        with self.assertRaises(HTTPException) as ctx:
            validate_claim_text("Hi")
        self.assertEqual(ctx.exception.status_code, 422)

    def test_validate_claim_text_whitespace_only(self):
        with self.assertRaises(HTTPException) as ctx:
            validate_claim_text("      ")
        self.assertEqual(ctx.exception.status_code, 422)

    def test_validate_claim_text_too_long(self):
        with self.assertRaises(HTTPException) as ctx:
            validate_claim_text("a" * 501)
        self.assertEqual(ctx.exception.status_code, 422)

    async def test_stream_and_validate_image_valid_jpeg(self):
        img_bytes = self._create_image_bytes(120, 120, "JPEG")
        upload = UploadFile(filename="photo.jpg", file=io.BytesIO(img_bytes))
        bytes_out, meta = await stream_and_validate_image_upload(upload)
        self.assertEqual(bytes_out, img_bytes)
        self.assertEqual(meta["format"], "JPEG")
        self.assertEqual(meta["width"], 120)
        self.assertEqual(meta["height"], 120)

    async def test_stream_and_validate_image_valid_png(self):
        img_bytes = self._create_image_bytes(80, 80, "PNG")
        upload = UploadFile(filename="chart.png", file=io.BytesIO(img_bytes))
        bytes_out, meta = await stream_and_validate_image_upload(upload)
        self.assertEqual(meta["format"], "PNG")

    async def test_stream_and_validate_image_empty_file(self):
        upload = UploadFile(filename="empty.jpg", file=io.BytesIO(b""))
        with self.assertRaises(HTTPException) as ctx:
            await stream_and_validate_image_upload(upload)
        self.assertEqual(ctx.exception.status_code, 400)

    async def test_stream_and_validate_image_oversized_413(self):
        # 11 MB simulated file
        large_stream = io.BytesIO(b"X" * (11 * 1024 * 1024))
        upload = UploadFile(filename="oversized.jpg", file=large_stream)
        with self.assertRaises(HTTPException) as ctx:
            await stream_and_validate_image_upload(upload)
        self.assertEqual(ctx.exception.status_code, 413)
        self.assertIn("10 MB", ctx.exception.detail)

    async def test_stream_and_validate_image_unsupported_format_415(self):
        upload = UploadFile(filename="doc.pdf", file=io.BytesIO(b"%PDF-1.4 header text"))
        with self.assertRaises(HTTPException) as ctx:
            await stream_and_validate_image_upload(upload)
        self.assertEqual(ctx.exception.status_code, 415)

    async def test_stream_and_validate_image_corrupted_bytes_415(self):
        upload = UploadFile(filename="corrupt.jpg", file=io.BytesIO(b"\xff\xd8\xff\xe0CORRUPTED_GARBAGE"))
        with self.assertRaises(HTTPException) as ctx:
            await stream_and_validate_image_upload(upload)
        self.assertIn(ctx.exception.status_code, [415, 422])

    async def test_stream_and_validate_image_resolution_too_small_422(self):
        img_bytes = self._create_image_bytes(16, 16, "JPEG")
        upload = UploadFile(filename="tiny.jpg", file=io.BytesIO(img_bytes))
        with self.assertRaises(HTTPException) as ctx:
            await stream_and_validate_image_upload(upload)
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertIn("too small", ctx.exception.detail)

    async def test_stream_and_validate_image_resolution_too_large_422(self):
        # We don't allocate a 5000x5000 image in memory; we check dimensions bounds
        img = Image.new("RGB", (4097, 35), color=(0, 0, 0))
        buf = io.BytesIO()
        img.save(buf, "JPEG")
        upload = UploadFile(filename="wide.jpg", file=io.BytesIO(buf.getvalue()))
        with self.assertRaises(HTTPException) as ctx:
            await stream_and_validate_image_upload(upload)
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertIn("too large", ctx.exception.detail)


if __name__ == "__main__":
    unittest.main()
