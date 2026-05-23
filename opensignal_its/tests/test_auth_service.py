import os
import hashlib
import unittest

from opensignal_its.services.auth_service import OperatorAuthService


class OperatorAuthServiceTests(unittest.TestCase):
    def setUp(self):
        self._keys = {
            "OPENSIGNAL_OPERATOR_USERNAME": os.environ.get("OPENSIGNAL_OPERATOR_USERNAME"),
            "OPENSIGNAL_OPERATOR_PASSWORD": os.environ.get("OPENSIGNAL_OPERATOR_PASSWORD"),
            "OPENSIGNAL_OPERATOR_PASSWORD_HASH": os.environ.get("OPENSIGNAL_OPERATOR_PASSWORD_HASH"),
            "OPENSIGNAL_OPERATOR_PASSWORD_HASHES": os.environ.get("OPENSIGNAL_OPERATOR_PASSWORD_HASHES"),
            "OPENSIGNAL_ADMIN_USERNAME": os.environ.get("OPENSIGNAL_ADMIN_USERNAME"),
            "OPENSIGNAL_ADMIN_PASSWORD": os.environ.get("OPENSIGNAL_ADMIN_PASSWORD"),
            "OPENSIGNAL_ADMIN_PASSWORD_HASH": os.environ.get("OPENSIGNAL_ADMIN_PASSWORD_HASH"),
            "OPENSIGNAL_ADMIN_RECOVERY_KEY": os.environ.get("OPENSIGNAL_ADMIN_RECOVERY_KEY"),
            "OPENSIGNAL_ADMIN_RECOVERY_KEY_HASH": os.environ.get("OPENSIGNAL_ADMIN_RECOVERY_KEY_HASH"),
        }

    def tearDown(self):
        for key, value in self._keys.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

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

    def test_authenticate_success_with_password_hash(self):
        os.environ["OPENSIGNAL_OPERATOR_USERNAME"] = "alice"
        digest = hashlib.sha256("secret".encode("utf-8")).hexdigest()
        os.environ.pop("OPENSIGNAL_OPERATOR_PASSWORD", None)
        os.environ["OPENSIGNAL_OPERATOR_PASSWORD_HASH"] = f"sha256:{digest}"

        ok, message = OperatorAuthService.authenticate("alice", "secret")
        self.assertTrue(ok)
        self.assertIn("successful", message)

    def test_authenticate_with_role_for_admin(self):
        os.environ["OPENSIGNAL_ADMIN_USERNAME"] = "root"
        os.environ["OPENSIGNAL_ADMIN_PASSWORD"] = "admin-secret"
        ok, message, role = OperatorAuthService.authenticate_with_role("root", "admin-secret")
        self.assertTrue(ok)
        self.assertIn("Admin login successful", message)
        self.assertEqual("admin", role)

    def test_validate_admin_recovery_key_accepts_hash(self):
        digest = hashlib.sha256("recover-secret".encode("utf-8")).hexdigest()
        os.environ["OPENSIGNAL_ADMIN_RECOVERY_KEY_HASH"] = f"sha256:{digest}"
        ok, message = OperatorAuthService.validate_admin_recovery_key("recover-secret")
        self.assertTrue(ok)
        self.assertIn("accepted", message)

    def test_authenticate_denied_for_bad_password(self):
        os.environ["OPENSIGNAL_OPERATOR_USERNAME"] = "alice"
        os.environ["OPENSIGNAL_OPERATOR_PASSWORD"] = "secret"
        ok, message = OperatorAuthService.authenticate("alice", "wrong")
        self.assertFalse(ok)
        self.assertIn("password is invalid", message)


if __name__ == "__main__":
    unittest.main()
