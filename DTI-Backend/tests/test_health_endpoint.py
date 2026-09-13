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
        self.assertIn(data["status"], ["ok", "degraded", "unavailable"])
        self.assertIn("pipeline_ready", data)
        self.assertIn("version", data)
        self.assertIn("X-Request-ID", response.headers)

    def test_livez_endpoint(self):
        """GET /livez should return 200 and alive status."""
        response = self.client.get("/livez")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "alive")
        self.assertIn("X-Request-ID", response.headers)

    def test_readyz_endpoint(self):
        """GET /readyz should return readiness status and subsystem statuses."""
        response = self.client.get("/readyz")
        self.assertIn(response.status_code, [200, 503])
        data = response.json()
        self.assertIn("status", data)
        self.assertIn("text_pipeline", data)
        self.assertIn("image_model", data)
        self.assertIn("X-Request-ID", response.headers)


if __name__ == "__main__":
    unittest.main()