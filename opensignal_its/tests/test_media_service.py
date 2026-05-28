import asyncio
import unittest

from opensignal_its.models.media import MediaProbeResult, MediaStreamConfig
from opensignal_its.protocols.rtsp import RtspUrlValidationError, parse_rtsp_url, redact_rtsp_url
from opensignal_its.services import MediaService
from opensignal_its.services.media_service import MediaService as ModuleMediaService


class MediaServiceTests(unittest.TestCase):
    def test_parse_rtsp_url_normalizes_default_port_and_redacts_credentials(self):
        endpoint = parse_rtsp_url("rtsp://user:secret@camera.example.com/live/main?profile=1")

        self.assertEqual("rtsp", endpoint.scheme)
        self.assertEqual("camera.example.com", endpoint.host)
        self.assertEqual(554, endpoint.port)
        self.assertEqual("/live/main", endpoint.path)
        self.assertEqual("profile=1", endpoint.query)
        self.assertEqual("/live/main?profile=1", endpoint.path_with_query)
        self.assertEqual(
            "rtsp://***@camera.example.com:554/live/main?profile=1",
            endpoint.safe_url,
        )
        self.assertNotIn("user", endpoint.safe_url)
        self.assertNotIn("secret", endpoint.safe_url)

    def test_parse_rtsp_url_preserves_explicit_port_and_path_query(self):
        endpoint = parse_rtsp_url("rtsp://camera.example.com:8554/cam/stream?transport=tcp")

        self.assertEqual(8554, endpoint.port)
        self.assertEqual("/cam/stream", endpoint.path)
        self.assertEqual("transport=tcp", endpoint.query)
        self.assertEqual(
            "rtsp://camera.example.com:8554/cam/stream?transport=tcp",
            endpoint.safe_url,
        )

    def test_parse_rtsp_url_rejects_invalid_values(self):
        invalid_values = [
            "",
            "http://camera.example.com/live",
            "rtsp:///live",
            "rtsp://camera.example.com:bad/live",
        ]

        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaises(RtspUrlValidationError):
                    parse_rtsp_url(value)

    def test_media_service_returns_invalid_config_status_without_raising(self):
        config = MediaStreamConfig(
            stream_id="cam-1",
            name="Main Camera",
            url="http://user:secret@camera.example.com/live",
            metadata={"note": "rtsp://user:secret@camera.example.com/live"},
        )

        status = asyncio.run(MediaService.check_stream_health(config))

        self.assertFalse(status.is_online)
        self.assertEqual("Invalid stream configuration", status.status_text)
        self.assertEqual("http://***@camera.example.com/live", status.safe_url)
        self.assertTrue(any("rtsp://" in error for error in status.errors))
        self.assertNotIn("secret", " ".join(status.errors))
        self.assertNotIn("secret", str(status.extra))

    def test_media_service_uses_injected_probe_and_sanitizes_results(self):
        config = MediaStreamConfig(
            stream_id="cam-1",
            name="Main Camera",
            url="rtsp://user:secret@camera.example.com/live/main?profile=1",
            timeout_seconds=0.2,
            metadata={"source": "rtsp://user:secret@camera.example.com/live/main?profile=1"},
        )

        async def _fake_probe(stream_config, endpoint):
            self.assertEqual("cam-1", stream_config.stream_id)
            self.assertEqual("camera.example.com", endpoint.host)
            return MediaProbeResult(
                is_online=True,
                status_text="Reachable via rtsp://user:secret@camera.example.com/live/main?profile=1",
                latency_ms=12.5,
                errors=["ignored user:secret credential echo"],
                raw_data={
                    "echo": "rtsp://user:secret@camera.example.com/live/main?profile=1",
                },
                extra={
                    "note": "user:secret",
                },
            )

        status = asyncio.run(MediaService.check_stream_health(config, probe=_fake_probe))

        self.assertTrue(status.is_online)
        self.assertEqual(
            "rtsp://***@camera.example.com:554/live/main?profile=1",
            status.safe_url,
        )
        self.assertIn("rtsp://***@camera.example.com:554/live/main?profile=1", status.status_text)
        self.assertNotIn("secret", status.status_text)
        self.assertNotIn("secret", " ".join(status.errors))
        self.assertNotIn("secret", str(status.raw_data))
        self.assertNotIn("secret", str(status.extra))
        self.assertEqual(12.5, status.latency_ms)
        self.assertEqual(554, status.extra["port"])
        self.assertEqual("/live/main?profile=1", status.extra["path_with_query"])

    def test_media_service_returns_timeout_status_for_slow_probe(self):
        config = MediaStreamConfig(
            stream_id="cam-2",
            name="Slow Camera",
            url="rtsp://user:secret@camera.example.com/live",
            timeout_seconds=0.01,
        )

        async def _slow_probe(_stream_config, _endpoint):
            await asyncio.sleep(0.05)
            return MediaProbeResult(is_online=True, status_text="should not arrive")

        status = asyncio.run(MediaService.check_stream_health(config, probe=_slow_probe))

        self.assertFalse(status.is_online)
        self.assertEqual("RTSP health check timed out", status.status_text)
        self.assertTrue(any("timed out" in error for error in status.errors))
        self.assertEqual("rtsp://***@camera.example.com:554/live", status.safe_url)
        self.assertNotIn("secret", " ".join(status.errors))

    def test_media_service_returns_failed_status_without_leaking_credentials(self):
        config = MediaStreamConfig(
            stream_id="cam-3",
            name="Broken Camera",
            url="rtsp://user:secret@camera.example.com/live",
            timeout_seconds=0.2,
        )

        async def _failing_probe(_stream_config, _endpoint):
            raise RuntimeError("Probe failed for rtsp://user:secret@camera.example.com/live")

        status = asyncio.run(MediaService.check_stream_health(config, probe=_failing_probe))

        self.assertFalse(status.is_online)
        self.assertEqual("RTSP health check failed", status.status_text)
        self.assertIn("rtsp://***@camera.example.com:554/live", status.errors[0])
        self.assertNotIn("secret", status.errors[0])

    def test_services_package_exports_media_service(self):
        self.assertIs(MediaService, ModuleMediaService)

    def test_redact_rtsp_url_hides_credentials(self):
        safe_url = redact_rtsp_url("rtsp://user:secret@camera.example.com/live")

        self.assertEqual("rtsp://***@camera.example.com:554/live", safe_url)
        self.assertNotIn("user", safe_url)
        self.assertNotIn("secret", safe_url)


if __name__ == "__main__":
    unittest.main()