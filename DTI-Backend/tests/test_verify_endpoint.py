import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies import get_pipeline
from app.config import settings


class MockSuccessPipeline:
    def __init__(self, response):
        self.response = response

    def verify_claim(self, claim: str):
        res = dict(self.response)
        res["claim"] = claim
        return res


class MockErrorPipeline:
    def verify_claim(self, claim: str):
        raise Exception("Simulated AI model crash")


class MockTimeoutPipeline:
    def verify_claim(self, claim: str):
        time.sleep(0.5)
        return {}


class TestVerifyEndpoint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._client_ctx = TestClient(app)
        cls.client = cls._client_ctx.__enter__()
        cls.mock_response = {
            "claim": "Test headline",
            "normalized_claim": "test headline",
            "verdict": "True",
            "confidence": 0.95,
            "summary": "This is a test summary.",
            "explanation": "This is a test explanation.",
        }

    @classmethod
    def tearDownClass(cls):
        cls._client_ctx.__exit__(None, None, None)

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_verify_valid_claim(self):
        app.dependency_overrides[get_pipeline] = lambda: MockSuccessPipeline(self.mock_response)
        response = self.client.post("/api/v1/verify", json={"claim": "This is a valid test claim."})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["claim"], "This is a valid test claim.")
        self.assertEqual(data["verdict"], "True")
        self.assertAlmostEqual(data["confidence"], 0.95)

    def test_verify_empty_claim(self):
        response = self.client.post("/api/v1/verify", json={"claim": ""})
        self.assertEqual(response.status_code, 422)

    def test_verify_too_long_claim(self):
        long_claim = "A" * 501
        response = self.client.post("/api/v1/verify", json={"claim": long_claim})
        self.assertEqual(response.status_code, 422)

    def test_verify_pipeline_error(self):
        app.dependency_overrides[get_pipeline] = lambda: MockErrorPipeline()
        response = self.client.post("/api/v1/verify", json={"claim": "Will crash"})
        self.assertEqual(response.status_code, 500)
        err = response.json()["error"]
        code = err["code"] if isinstance(err, dict) else err
        self.assertIn(code, ["INTERNAL_ERROR", "pipeline_error"])

    def test_verify_pipeline_timeout(self):
        original_timeout = settings.VERIFY_TIMEOUT_SECONDS
        try:
            settings.VERIFY_TIMEOUT_SECONDS = 0.1
            app.dependency_overrides[get_pipeline] = lambda: MockTimeoutPipeline()
            response = self.client.post("/api/v1/verify", json={"claim": "Will timeout"})
            self.assertEqual(response.status_code, 504)
            err = response.json()["error"]
            code = err["code"] if isinstance(err, dict) else err
            self.assertIn(code, ["GATEWAY_TIMEOUT", "verification_timeout"])
        finally:
            settings.VERIFY_TIMEOUT_SECONDS = original_timeout


if __name__ == "__main__":
    unittest.main()