import os
import unittest

from opensignal_its.services import maintenance_scheduler


class _FakeScheduler:
    def __init__(self, daemon=True):
        self.daemon = daemon
        self.jobs = []
        self.started = False
        self.stopped = False

    def add_job(self, func, trigger, seconds, id, replace_existing, max_instances, coalesce):
        self.jobs.append(
            {
                "func": func,
                "trigger": trigger,
                "seconds": seconds,
                "id": id,
                "replace_existing": replace_existing,
                "max_instances": max_instances,
                "coalesce": coalesce,
            }
        )

    def start(self):
        self.started = True

    def shutdown(self, wait=False):
        self.stopped = True


class MaintenanceSchedulerTests(unittest.TestCase):
    def setUp(self):
        self._old_env = {
            "OPENSIGNAL_ENABLE_RETENTION_SCHEDULER": os.environ.get("OPENSIGNAL_ENABLE_RETENTION_SCHEDULER"),
            "OPENSIGNAL_RETENTION_SCHEDULE_SECONDS": os.environ.get("OPENSIGNAL_RETENTION_SCHEDULE_SECONDS"),
        }
        self._old_scheduler_cls = maintenance_scheduler.BackgroundScheduler
        maintenance_scheduler.stop_retention_scheduler()

    def tearDown(self):
        maintenance_scheduler.stop_retention_scheduler()
        maintenance_scheduler.BackgroundScheduler = self._old_scheduler_cls
        for key, value in self._old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_scheduler_not_started_when_disabled(self):
        os.environ["OPENSIGNAL_ENABLE_RETENTION_SCHEDULER"] = "false"
        ok, message = maintenance_scheduler.start_retention_scheduler()
        self.assertFalse(ok)
        self.assertIn("disabled", message)

    def test_scheduler_starts_when_enabled(self):
        os.environ["OPENSIGNAL_ENABLE_RETENTION_SCHEDULER"] = "true"
        os.environ["OPENSIGNAL_RETENTION_SCHEDULE_SECONDS"] = "600"
        maintenance_scheduler.BackgroundScheduler = _FakeScheduler

        ok, message = maintenance_scheduler.start_retention_scheduler()

        self.assertTrue(ok)
        self.assertIn("started", message)
        status = maintenance_scheduler.scheduler_status()
        self.assertTrue(status["running"])
        self.assertEqual(600, status["interval_seconds"])

    def test_scheduler_status_reports_config_error(self):
        os.environ["OPENSIGNAL_ENABLE_RETENTION_SCHEDULER"] = "true"
        os.environ["OPENSIGNAL_RETENTION_SCHEDULE_SECONDS"] = "bad"

        status = maintenance_scheduler.scheduler_status()

        self.assertTrue(status["enabled"])
        self.assertFalse(status["running"])
        self.assertEqual(None, status["interval_seconds"])
        self.assertIn("must be an integer", status["error"])

    def test_scheduler_rejects_too_small_interval(self):
        os.environ["OPENSIGNAL_ENABLE_RETENTION_SCHEDULER"] = "true"
        os.environ["OPENSIGNAL_RETENTION_SCHEDULE_SECONDS"] = "60"

        with self.assertRaises(ValueError):
            maintenance_scheduler.start_retention_scheduler()


if __name__ == "__main__":
    unittest.main()
