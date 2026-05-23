import os
import unittest
from datetime import datetime, timedelta, timezone

from opensignal_its.services.safety_service import CommandSafetyService


class CommandSafetyServiceTests(unittest.TestCase):
    def setUp(self):
        self._old_key = os.environ.get("OPENSIGNAL_OPERATOR_KEY")

    def tearDown(self):
        if self._old_key is None:
            os.environ.pop("OPENSIGNAL_OPERATOR_KEY", None)
        else:
            os.environ["OPENSIGNAL_OPERATOR_KEY"] = self._old_key

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
