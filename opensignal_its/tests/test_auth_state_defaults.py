import importlib
import os
import unittest

import reflex as rx


class AuthStateDefaultTests(unittest.TestCase):
    def setUp(self):
        self._saved_env = os.environ.get("OPENSIGNAL_ENV")
        self._saved_disable_login = os.environ.get("OPENSIGNAL_DISABLE_LOGIN")

    def tearDown(self):
        if self._saved_env is None:
            os.environ.pop("OPENSIGNAL_ENV", None)
        else:
            os.environ["OPENSIGNAL_ENV"] = self._saved_env
        if self._saved_disable_login is None:
            os.environ.pop("OPENSIGNAL_DISABLE_LOGIN", None)
        else:
            os.environ["OPENSIGNAL_DISABLE_LOGIN"] = self._saved_disable_login
        import opensignal_its.states.auth_state as auth_state_module

        importlib.reload(auth_state_module)

    @staticmethod
    def _load_probe():
        import opensignal_its.states.auth_state as auth_state_module

        auth_state_module = importlib.reload(auth_state_module)

        class _AuthProbe(auth_state_module.AuthStateMixin, rx.State):
            pass

        return _AuthProbe(_reflex_internal_init=True)

    def test_login_disabled_by_default_in_dev(self):
        os.environ.pop("OPENSIGNAL_ENV", None)
        os.environ.pop("OPENSIGNAL_DISABLE_LOGIN", None)

        probe = self._load_probe()

        self.assertTrue(probe.is_authenticated)
        self.assertEqual("local-access", probe.current_operator)
        self.assertEqual("admin", probe.current_role)
        self.assertEqual("Login disabled for local development.", probe.auth_notice)

    def test_login_required_in_production_like_env_without_bypass(self):
        os.environ["OPENSIGNAL_ENV"] = "production"
        os.environ.pop("OPENSIGNAL_DISABLE_LOGIN", None)

        probe = self._load_probe()

        self.assertFalse(probe.is_authenticated)
        self.assertEqual("", probe.current_operator)
        self.assertEqual("viewer", probe.current_role)
        self.assertEqual("Operator not authenticated.", probe.auth_notice)

    def test_login_bypass_remains_available_when_explicitly_enabled(self):
        os.environ["OPENSIGNAL_DISABLE_LOGIN"] = "true"

        probe = self._load_probe()

        self.assertTrue(probe.is_authenticated)
        self.assertEqual("local-access", probe.current_operator)
        self.assertEqual("admin", probe.current_role)
        self.assertEqual("Login disabled for local development.", probe.auth_notice)


if __name__ == "__main__":
    unittest.main()