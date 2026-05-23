import os
import hashlib
import unittest
from datetime import datetime, timedelta, timezone

from opensignal_its.services.safety_service import CommandSafetyService


class CommandSafetyServiceTests(unittest.TestCase):
    def setUp(self):
        self._keys = {
            "OPENSIGNAL_OPERATOR_KEY": os.environ.get("OPENSIGNAL_OPERATOR_KEY"),
            "OPENSIGNAL_OPERATOR_KEY_HASH": os.environ.get("OPENSIGNAL_OPERATOR_KEY_HASH"),
            "OPENSIGNAL_OPERATOR_KEY_HASHES": os.environ.get("OPENSIGNAL_OPERATOR_KEY_HASHES"),
        }

    def tearDown(self):
        for key, value in self._keys.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_unlock_denied_when_key_not_configured(self):
        os.environ.pop("OPENSIGNAL_OPERATOR_KEY", None)
        ok, message, until = CommandSafetyService.unlock_write_mode("x", 60)
        self.assertFalse(ok)
        self.assertEqual("", until)
        self.assertIn("not configured", message)

    def test_unlock_success_when_key_matches(self):
        os.environ["OPENSIGNAL_OPERATOR_KEY"] = "abc123"
        ok, message, until = CommandSafetyService.unlock_write_mode("abc123", 60)
        self.assertTrue(ok)
        self.assertNotEqual("", until)
        self.assertIn("unlocked", message)

    def test_unlock_success_when_key_hash_matches(self):
        digest = hashlib.sha256("abc123".encode("utf-8")).hexdigest()
        os.environ.pop("OPENSIGNAL_OPERATOR_KEY", None)
        os.environ["OPENSIGNAL_OPERATOR_KEY_HASH"] = f"sha256:{digest}"
        ok, message, until = CommandSafetyService.unlock_write_mode("abc123", 60)
        self.assertTrue(ok)
        self.assertNotEqual("", until)
        self.assertIn("unlocked", message)

    def test_evaluate_denies_expired_unlock(self):
        past = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
        decision = CommandSafetyService.evaluate_command(False, past)
        self.assertFalse(decision.allowed)
        self.assertIn("expired", decision.reason)

    def test_evaluate_allows_probe_mode(self):
        decision = CommandSafetyService.evaluate_command(True, "")
        self.assertTrue(decision.allowed)


if __name__ == "__main__":
    unittest.main()
