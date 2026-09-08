import io
import sys
import unittest
from pathlib import Path
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from app.main import app


class TestVerifyImageEndpoint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._client_ctx = TestClient(app)
        cls.client = cls._client_ctx.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls._client_ctx.__exit__(None, None, None)

    def _make_jpeg_bytes(self, color=(120, 180, 220), w=200, h=200):
        img = Image.new("RGB", (w, h), color=color)
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=90)
        return buf.getvalue()

    def test_verify_image_valid_jpg(self):
        """Test uploading a valid JPG image without claim."""
        img_bytes = self._make_jpeg_bytes()
        files = {"file": ("test_photo.jpg", img_bytes, "image/jpeg")}
        response = self.client.post("/api/v1/verify-image", files=files)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("image_result", data)
        self.assertIsNotNone(data["image_result"]["verdict"])
        self.assertIn("probabilities", data["image_result"])
        self.assertIn("fake", data["image_result"]["probabilities"])
        self.assertIn("real", data["image_result"]["probabilities"])

    def test_verify_image_with_claim_combined(self):
        """Test uploading a valid image with an associated claim (multimodal)."""
        img_bytes = self._make_jpeg_bytes()
        files = {"file": ("storm.jpg", img_bytes, "image/jpeg")}
        data = {"claim": "Earth is the third planet from the Sun"}
        response = self.client.post("/api/v1/verify-image", files=files, data=data)

        self.assertEqual(response.status_code, 200)
        res = response.json()
        self.assertIn("image_result", res)
        self.assertIn("verdict", res)
        self.assertIn("joint_assessment", res)
        self.assertIsNotNone(res["joint_assessment"])

    def test_verify_image_missing_file(self):
        """Test submitting request with empty/no file."""
        response = self.client.post("/api/v1/verify-image", files={})
        self.assertEqual(response.status_code, 422)  # FastAPI validation error

    def test_verify_image_unsupported_extension(self):
        """Test submitting an unsupported file type (e.g. .pdf or .txt)."""
        files = {"file": ("document.pdf", b"%PDF-1.4...", "application/pdf")}
        response = self.client.post("/api/v1/verify-image", files=files)

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data.get("error"), "invalid_file_type")

    def test_verify_image_empty_bytes(self):
        """Test submitting an empty file."""
        files = {"file": ("empty.jpg", b"", "image/jpeg")}
        response = self.client.post("/api/v1/verify-image", files=files)

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data.get("error"), "empty_file")

    def test_verify_image_exceeds_size_limit(self):
        """Test submitting a file exceeding the 10MB limit."""
        large_bytes = b"0" * (11 * 1024 * 1024)
        files = {"file": ("huge.jpg", large_bytes, "image/jpeg")}
        response = self.client.post("/api/v1/verify-image", files=files)

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data.get("error"), "file_too_large")


if __name__ == "__main__":
    unittest.main()
