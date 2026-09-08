import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from app.main import app


class TestHealthEndpoint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._client_ctx = TestClient(app)
        cls.client = cls._client_ctx.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls._client_ctx.__exit__(None, None, None)

    def test_health_check_status_ok(self):
        """GET /api/v1/health should return status 'ok' and 200 code."""
        response = self.client.get("/api/v1/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("pipeline_ready", data)
        self.assertIn("version", data)


if __name__ == "__main__":
    unittest.main()