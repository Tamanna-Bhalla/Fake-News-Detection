import io
import sys
import os
import unittest
from pathlib import Path
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.image_service import ImageManipulationDetector, ForensicAnalyzer, get_image_detector


class TestImageManipulationDetector(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.detector = get_image_detector()

    def _create_synthetic_photo(self, w=400, h=300, noise_std=4.0, quality=90):
        """Helper to create a photographic image with uniform sensor noise and JPEG compression."""
        x = np.linspace(0, 1, w)
        y = np.linspace(0, 1, h)
        xx, yy = np.meshgrid(x, y)
        base = (0.5 + 0.3 * np.sin(xx * 2.0) + 0.2 * np.cos(yy * 2.0)) * 200
        noise = np.random.normal(0, noise_std, (h, w))
        arr = np.clip(base + noise, 0, 255).astype(np.uint8)
        img = Image.fromarray(arr).convert("RGB")
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=quality)
        return buf.getvalue()

    def _create_spliced_photo(self, w=400, h=300):
        """Helper to create a tampered image with foreign patch insertion and mismatched compression."""
        base_bytes = self._create_synthetic_photo(w=w, h=h, noise_std=3.0, quality=75)
        img = Image.open(io.BytesIO(base_bytes)).convert("RGB")

        # Foreign spliced patch with different noise and edge
        patch = np.random.normal(128, 40, (100, 100, 3)).astype(np.uint8)
        patch_img = Image.fromarray(patch)
        img.paste(patch_img, (150, 100))

        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=95)
        return buf.getvalue()

    def test_authentic_image_detection(self):
        """Authentic image should be classified with high authenticity probability."""
        b = self._create_synthetic_photo()
        res = self.detector.predict(b)

        self.assertFalse(res["is_fake"])
        self.assertIn(res["verdict"], ["Authentic", "Likely Authentic"])
        self.assertGreaterEqual(res["probabilities"]["real"], 0.50)
        self.assertLessEqual(res["probabilities"]["fake"], 0.50)
        self.assertAlmostEqual(res["probabilities"]["real"] + res["probabilities"]["fake"], 1.0, places=3)
        self.assertIsNone(res["error"])

    def test_spliced_image_detection(self):
        """Spliced image with inconsistent compression and noise should be detected as manipulated."""
        b = self._create_spliced_photo()
        res = self.detector.predict(b)

        self.assertTrue(res["is_fake"])
        self.assertIn(res["verdict"], ["Manipulated / Tampered", "Suspicious / Potential Manipulation"])
        self.assertGreaterEqual(res["probabilities"]["fake"], 0.50)
        self.assertIsNotNone(res["heatmap_base64"])
        self.assertTrue(res["heatmap_base64"].startswith("data:image/png;base64,"))

    def test_very_small_image_handling(self):
        """Extremely small images (e.g. 16x16) should not crash the pipeline."""
        img = Image.new("RGB", (16, 16), color=(100, 150, 200))
        buf = io.BytesIO()
        img.save(buf, "PNG")
        res = self.detector.predict(buf.getvalue())

        self.assertIsNotNone(res["verdict"])
        self.assertIsNone(res["error"])

    def test_rgba_transparent_image_handling(self):
        """RGBA images with alpha transparency should be converted cleanly without error."""
        img = Image.new("RGBA", (100, 100), color=(255, 0, 0, 128))
        buf = io.BytesIO()
        img.save(buf, "PNG")
        res = self.detector.predict(buf.getvalue())

        self.assertIsNotNone(res["verdict"])
        self.assertIsNone(res["error"])

    def test_grayscale_image_handling(self):
        """Grayscale (mode L) images should be parsed and processed cleanly."""
        img = Image.new("L", (120, 120), color=128)
        buf = io.BytesIO()
        img.save(buf, "JPEG")
        res = self.detector.predict(buf.getvalue())

        self.assertIsNotNone(res["verdict"])
        self.assertIsNone(res["error"])

    def test_corrupted_bytes_handling(self):
        """Corrupted/random bytes should return a clean error dict without throwing unhandled exceptions."""
        corrupted = b"NOT_A_VALID_IMAGE_FILE_HEADER_GARBAGE_BYTES_12345"
        res = self.detector.predict(corrupted)

        self.assertIsNone(res["is_fake"])
        self.assertIsNotNone(res["error"])
        self.assertIn("Invalid image", res["error"])

    def test_heatmap_generation(self):
        """Heatmap should generate a non-empty valid PNG data URI."""
        ela = np.zeros((100, 100), dtype=np.float32)
        ela[30:60, 30:60] = 50.0  # Simulated anomaly patch
        noise = np.zeros((100, 100), dtype=np.float32)
        noise[30:60, 30:60] = 10.0

        b64 = ForensicAnalyzer.generate_heatmap(ela, noise)
        self.assertTrue(b64.startswith("data:image/png;base64,"))
        self.assertGreater(len(b64), 100)


if __name__ == "__main__":
    unittest.main()
