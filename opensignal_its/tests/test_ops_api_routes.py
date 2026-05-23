import importlib
import os
import tempfile
import unittest
from pathlib import Path


class OpsApiRoutesTests(unittest.TestCase):
    def setUp(self):
        self._env = {
            "OPENSIGNAL_OPS_API_ENABLED": os.environ.get("OPENSIGNAL_OPS_API_ENABLED"),
            "OPENSIGNAL_OPS_API_TOKEN": os.environ.get("OPENSIGNAL_OPS_API_TOKEN"),
            "OPENSIGNAL_OPS_API_TOKEN_HASH": os.environ.get("OPENSIGNAL_OPS_API_TOKEN_HASH"),
            "OPENSIGNAL_OPS_API_TOKEN_HASHES": os.environ.get("OPENSIGNAL_OPS_API_TOKEN_HASHES"),
        }

    def tearDown(self):
        for key, value in self._env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    @staticmethod
    def _load_app_module():
        import opensignal_its.opensignal_its as app_module

        return importlib.reload(app_module)

    @staticmethod
    def _ops_routes(app_module) -> dict[str, object]:
        routes = getattr(app_module, "OPS_API_ENDPOINTS", None)
        if isinstance(routes, dict):
            return dict(routes)
        return {}

    def test_ops_routes_registered_when_enabled(self):
        os.environ["OPENSIGNAL_OPS_API_ENABLED"] = "true"
        os.environ.pop("OPENSIGNAL_OPS_API_TOKEN", None)
        os.environ.pop("OPENSIGNAL_OPS_API_TOKEN_HASH", None)
        os.environ.pop("OPENSIGNAL_OPS_API_TOKEN_HASHES", None)

        app_module = self._load_app_module()
        routes = self._ops_routes(app_module)

        self.assertIn("/api/ops/health", routes)
        self.assertIn("/api/ops/alarms", routes)
        self.assertIn("/api/ops/alarm-history", routes)
        self.assertIn("/api/ops/audit-export", routes)

    def test_ops_routes_not_registered_when_disabled(self):
        os.environ["OPENSIGNAL_OPS_API_ENABLED"] = "false"

        app_module = self._load_app_module()
        routes = self._ops_routes(app_module)

        self.assertEqual({}, routes)

    def test_ops_route_denies_invalid_token(self):
        os.environ["OPENSIGNAL_OPS_API_ENABLED"] = "true"
        os.environ["OPENSIGNAL_OPS_API_TOKEN"] = "secret-token"

        app_module = self._load_app_module()
        routes = self._ops_routes(app_module)
        payload = routes["/api/ops/health"](api_token="wrong-token")

        self.assertFalse(payload["ok"])
        self.assertIn("invalid token", payload["error"])

    def test_ops_route_allows_when_token_valid(self):
        os.environ["OPENSIGNAL_OPS_API_ENABLED"] = "true"
        os.environ["OPENSIGNAL_OPS_API_TOKEN"] = "secret-token"

        app_module = self._load_app_module()
        routes = self._ops_routes(app_module)
        payload = routes["/api/ops/alarm-history"](
            limit=5,
            action_filter="all",
            actor_contains="",
            key_contains="",
            api_token="secret-token",
        )

        self.assertTrue(payload["ok"])
        self.assertIn("rows", payload)
        self.assertLessEqual(int(payload["count"]), 5)

    def test_ops_audit_export_route_returns_exported_path(self):
        os.environ["OPENSIGNAL_OPS_API_ENABLED"] = "true"
        os.environ["OPENSIGNAL_OPS_API_TOKEN"] = "secret-token"

        app_module = self._load_app_module()
        routes = self._ops_routes(app_module)

        with tempfile.TemporaryDirectory() as tmp:
            target = str(Path(tmp) / "ops" / "report.json")
            payload = routes["/api/ops/audit-export"](
                file_path=target,
                command_limit=10,
                snapshot_limit=10,
                api_token="secret-token",
            )

        self.assertTrue(payload["ok"])
        self.assertEqual(target, payload["file_path"])


if __name__ == "__main__":
    unittest.main()
