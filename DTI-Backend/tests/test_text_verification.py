import os
import sys
import unittest
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
research_dir = backend_dir.parent / "research" / "research"

sys.path.insert(0, str(backend_dir))
sys.path.insert(0, str(research_dir))

from fastapi.testclient import TestClient
from app.main import app
from text_verification.claim_processing.claim_normalizer import normalize_headline_to_claim
from text_verification.pipeline.verify_pipeline import VerificationPipeline


class TestTextVerification(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._client_ctx = TestClient(app)
        cls.client = cls._client_ctx.__enter__()
        cls.pipeline = VerificationPipeline()

    @classmethod
    def tearDownClass(cls):
        cls._client_ctx.__exit__(None, None, None)

    def test_claim_normalizer_factual(self):
        """Standard headlines should normalize to clean claims."""
        headline = "Report: NASA confirms new water ice discovered on the Moon"
        claim = normalize_headline_to_claim(headline)
        self.assertEqual(claim, "New water ice discovered on the Moon")

    def test_claim_normalizer_non_claim(self):
        """Questions and how-to articles should return NOT_A_CLAIM."""
        self.assertEqual(normalize_headline_to_claim("What to know about the eclipse?"), "NOT_A_CLAIM")
        self.assertEqual(normalize_headline_to_claim("How to make homemade sourdough bread"), "NOT_A_CLAIM")
        self.assertEqual(normalize_headline_to_claim(""), "NOT_A_CLAIM")

    def test_pipeline_non_claim_verdict(self):
        """Non-claims should immediately yield UNVERIFIABLE without error."""
        res = self.pipeline.verify_claim("How to fix a leaky faucet?")
        self.assertEqual(res["verdict"], "UNVERIFIABLE")
        self.assertIn("not a verifiable factual claim", res["summary"].lower())

    def test_pipeline_special_characters(self):
        """Claims with quotes, dashes, and unicode should be handled cleanly."""
        claim = '“Global renewable energy capacity surged by 50% in 2023”, IEA says.'
        res = self.pipeline.verify_claim(claim)
        self.assertIn("verdict", res)
        self.assertIn("confidence", res)
        self.assertIsNotNone(res["summary"])

    def test_verify_endpoint_empty_claim(self):
        """POST /api/v1/verify with empty claim should return 422 validation error."""
        response = self.client.post("/api/v1/verify", json={"claim": ""})
        self.assertEqual(response.status_code, 422)

    def test_verify_endpoint_too_long_claim(self):
        """POST /api/v1/verify with > 500 characters should return 422 validation error."""
        long_claim = "A" * 501
        response = self.client.post("/api/v1/verify", json={"claim": long_claim})
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
