import os
import unittest

from opensignal_its.services.auth_service import OperatorAuthService


class OperatorAuthServiceTests(unittest.TestCase):
    def setUp(self):
        self._old_user = os.environ.get("OPENSIGNAL_OPERATOR_USERNAME")
        self._old_pass = os.environ.get("OPENSIGNAL_OPERATOR_PASSWORD")

    def tearDown(self):
        if self._old_user is None:
            os.environ.pop("OPENSIGNAL_OPERATOR_USERNAME", None)
        else:
            os.environ["OPENSIGNAL_OPERATOR_USERNAME"] = self._old_user

        if self._old_pass is None:
            os.environ.pop("OPENSIGNAL_OPERATOR_PASSWORD", None)
        else:
            os.environ["OPENSIGNAL_OPERATOR_PASSWORD"] = self._old_pass

    def test_authenticate_denied_when_password_not_configured(self):
        os.environ.pop("OPENSIGNAL_OPERATOR_PASSWORD", None)
        ok, message = OperatorAuthService.authenticate("operator", "x")
        self.assertFalse(ok)
        self.assertIn("not configured", message)

    def test_authenticate_success_with_matching_credentials(self):
        os.environ["OPENSIGNAL_OPERATOR_USERNAME"] = "alice"
        os.environ["OPENSIGNAL_OPERATOR_PASSWORD"] = "secret"
        ok, message = OperatorAuthService.authenticate("alice", "secret")
        self.assertTrue(ok)
        self.assertIn("successful", message)

    def test_authenticate_denied_for_bad_password(self):
        os.environ["OPENSIGNAL_OPERATOR_USERNAME"] = "alice"
        os.environ["OPENSIGNAL_OPERATOR_PASSWORD"] = "secret"
        ok, message = OperatorAuthService.authenticate("alice", "wrong")
        self.assertFalse(ok)
        self.assertIn("password is invalid", message)


if __name__ == "__main__":
    unittest.main()
