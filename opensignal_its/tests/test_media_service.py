import asyncio
from contextlib import asynccontextmanager
import socket
import unittest

from opensignal_its.models.media import MediaProbeResult, MediaStreamConfig
from opensignal_its.protocols.rtsp import (
    RtspDescribeError,
    RtspUrlValidationError,
    parse_rtsp_url,
    probe_rtsp_describe,
    probe_rtsp_tcp,
    redact_rtsp_url,
)
from opensignal_its.services import MediaService
from opensignal_its.services.media_service import MediaService as ModuleMediaService


@asynccontextmanager
async def _local_rtsp_listener():
    accepted_event = asyncio.Event()

    async def _handle_client(reader, writer):
        accepted_event.set()
        try:
            await reader.read(1)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    server = await asyncio.start_server(_handle_client, host="127.0.0.1", port=0)
    sockets = server.sockets or []
    if not sockets:
        server.close()
        await server.wait_closed()
        raise AssertionError("Failed to bind local RTSP test listener.")

    try:
        yield int(sockets[0].getsockname()[1]), accepted_event
    finally:
        server.close()
        await server.wait_closed()


def _unused_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@asynccontextmanager
async def _local_rtsp_describe_simulator(response_head: bytes, response_body: bytes = b""):
    request_event = asyncio.Event()
    received_request: dict[str, str] = {}

    async def _handle_client(reader, writer):
        try:
            request_bytes = await reader.readuntil(b"\r\n\r\n")
            received_request["text"] = request_bytes.decode("utf-8", errors="replace")
            request_event.set()
            writer.write(response_head + response_body)
            await writer.drain()
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    server = await asyncio.start_server(_handle_client, host="127.0.0.1", port=0)
    sockets = server.sockets or []
    if not sockets:
        server.close()
        await server.wait_closed()
        raise AssertionError("Failed to bind local RTSP DESCRIBE test listener.")

    try:
        yield int(sockets[0].getsockname()[1]), received_request, request_event
    finally:
        server.close()
        await server.wait_closed()


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

    def test_probe_rtsp_tcp_reaches_local_listener(self):
        async def _exercise():
            async with _local_rtsp_listener() as (port, accepted_event):
                endpoint = parse_rtsp_url(f"rtsp://127.0.0.1:{port}/live/main")

                result = await probe_rtsp_tcp(endpoint, timeout_seconds=0.2)

                self.assertTrue(result.is_online)
                self.assertEqual("RTSP endpoint reachable", result.status_text)
                self.assertEqual("tcp", result.extra["transport"])
                self.assertEqual("rtsp", result.extra["scheme"])
                self.assertGreaterEqual(result.latency_ms, 0.0)
                await asyncio.wait_for(accepted_event.wait(), timeout=0.2)

        asyncio.run(_exercise())

    def test_probe_rtsp_describe_reads_local_describe_response(self):
        sdp_body = (
            b"v=0\r\n"
            b"o=- 0 0 IN IP4 127.0.0.1\r\n"
            b"s=OpenSignal ITS\r\n"
            b"m=video 0 RTP/AVP 96\r\n"
        )
        response_head = (
            f"RTSP/1.0 200 OK\r\n"
            f"CSeq: 1\r\n"
            f"Content-Type: application/sdp\r\n"
            f"Content-Length: {len(sdp_body)}\r\n"
            "\r\n"
        ).encode("utf-8")

        async def _exercise():
            async with _local_rtsp_describe_simulator(response_head, sdp_body) as (port, received_request, request_event):
                endpoint = parse_rtsp_url(f"rtsp://user:secret@127.0.0.1:{port}/live/main?profile=1")

                result = await probe_rtsp_describe(endpoint, timeout_seconds=0.2)

                await asyncio.wait_for(request_event.wait(), timeout=0.2)
                self.assertTrue(result.is_online)
                self.assertEqual("RTSP DESCRIBE succeeded", result.status_text)
                self.assertEqual("tcp", result.extra["transport"])
                self.assertEqual("rtsp", result.extra["scheme"])
                self.assertEqual("describe", result.extra["probe"])
                self.assertEqual(200, result.extra["status_code"])
                self.assertEqual("application/sdp", result.extra["content_type"])
                self.assertTrue(result.extra["has_sdp"])
                self.assertIn("m=video", result.raw_data["body_preview"])
                self.assertEqual("RTSP/1.0 200 OK", result.raw_data["status_line"])
                self.assertGreaterEqual(result.latency_ms, 0.0)
                request_text = received_request["text"]
                self.assertIn(
                    f"DESCRIBE rtsp://127.0.0.1:{port}/live/main?profile=1 RTSP/1.0",
                    request_text,
                )
                self.assertIn("Accept: application/sdp", request_text)
                self.assertNotIn("user", request_text)
                self.assertNotIn("secret", request_text)

        asyncio.run(_exercise())

    def test_probe_rtsp_describe_rejects_malformed_response(self):
        response_head = b"NOT RTSP\r\n\r\n"

        async def _exercise():
            async with _local_rtsp_describe_simulator(response_head) as (port, _received_request, request_event):
                endpoint = parse_rtsp_url(f"rtsp://user:secret@127.0.0.1:{port}/live/main")

                with self.assertRaises(RtspDescribeError) as exc_info:
                    await probe_rtsp_describe(endpoint, timeout_seconds=0.2)

                await asyncio.wait_for(request_event.wait(), timeout=0.2)
                self.assertIn("Malformed RTSP DESCRIBE response", str(exc_info.exception))
                self.assertNotIn("secret", str(exc_info.exception))

        asyncio.run(_exercise())

    def test_probe_rtsp_describe_reports_non_2xx_status_structurally(self):
        response_head = (
            "RTSP/1.0 401 Unauthorized\r\n"
            "CSeq: 1\r\n"
            "WWW-Authenticate: Digest realm=\"OpenSignal ITS\"\r\n"
            "Content-Length: 0\r\n"
            "\r\n"
        ).encode("utf-8")

        async def _exercise():
            async with _local_rtsp_describe_simulator(response_head) as (port, _received_request, request_event):
                endpoint = parse_rtsp_url(f"rtsp://user:secret@127.0.0.1:{port}/secure/main")

                with self.assertRaises(RtspDescribeError) as exc_info:
                    await probe_rtsp_describe(endpoint, timeout_seconds=0.2)

                await asyncio.wait_for(request_event.wait(), timeout=0.2)
                error = exc_info.exception
                self.assertEqual(401, error.status_code)
                self.assertEqual("Unauthorized", error.status_reason)
                self.assertEqual("RTSP/1.0 401 Unauthorized", error.status_line)
                self.assertEqual('Digest realm="OpenSignal ITS"', error.headers["www-authenticate"])
                self.assertIn("401 Unauthorized", str(error))
                self.assertNotIn("secret", str(error))

        asyncio.run(_exercise())

    def test_media_service_describe_stream_protocol_reports_success(self):
        sdp_body = (
            b"v=0\r\n"
            b"o=- 0 0 IN IP4 127.0.0.1\r\n"
            b"s=OpenSignal ITS\r\n"
            b"m=video 0 RTP/AVP 96\r\n"
        )
        response_head = (
            f"RTSP/1.0 200 OK\r\n"
            f"CSeq: 1\r\n"
            f"Content-Type: application/sdp\r\n"
            f"Content-Length: {len(sdp_body)}\r\n"
            "\r\n"
        ).encode("utf-8")

        async def _exercise():
            async with _local_rtsp_describe_simulator(response_head, sdp_body) as (port, _received_request, request_event):
                config = MediaStreamConfig(
                    stream_id="cam-describe",
                    name="Describe Camera",
                    url=f"rtsp://user:secret@127.0.0.1:{port}/live/main?profile=1",
                    timeout_seconds=0.2,
                    metadata={"source": f"rtsp://user:secret@127.0.0.1:{port}/live/main?profile=1"},
                )

                status = await MediaService.describe_stream_protocol(config)

                await asyncio.wait_for(request_event.wait(), timeout=0.2)
                self.assertTrue(status.is_online)
                self.assertEqual("RTSP DESCRIBE succeeded", status.status_text)
                self.assertEqual(
                    f"rtsp://***@127.0.0.1:{port}/live/main?profile=1",
                    status.safe_url,
                )
                self.assertEqual("describe", status.extra["probe"])
                self.assertEqual(200, status.extra["status_code"])
                self.assertEqual("application/sdp", status.extra["content_type"])
                self.assertTrue(status.extra["has_sdp"])
                self.assertNotIn("secret", status.status_text)
                self.assertNotIn("secret", str(status.errors))
                self.assertNotIn("secret", str(status.raw_data))
                self.assertNotIn("secret", str(status.extra))

        asyncio.run(_exercise())

    def test_media_service_describe_stream_protocol_reports_non_2xx_status(self):
        response_head = (
            "RTSP/1.0 401 Unauthorized\r\n"
            "CSeq: 1\r\n"
            "WWW-Authenticate: Digest realm=\"OpenSignal ITS\"\r\n"
            "Content-Length: 0\r\n"
            "\r\n"
        ).encode("utf-8")

        async def _exercise():
            async with _local_rtsp_describe_simulator(response_head) as (port, _received_request, request_event):
                config = MediaStreamConfig(
                    stream_id="cam-describe-401",
                    name="Secure Camera",
                    url=f"rtsp://user:secret@127.0.0.1:{port}/secure/main",
                    timeout_seconds=0.2,
                    metadata={"source": f"rtsp://user:secret@127.0.0.1:{port}/secure/main"},
                )

                status = await MediaService.describe_stream_protocol(config)

                await asyncio.wait_for(request_event.wait(), timeout=0.2)
                self.assertFalse(status.is_online)
                self.assertEqual("RTSP DESCRIBE failed", status.status_text)
                self.assertEqual(f"rtsp://***@127.0.0.1:{port}/secure/main", status.safe_url)
                self.assertEqual("describe", status.extra["probe"])
                self.assertEqual(401, status.extra["describe_status_code"])
                self.assertEqual("Unauthorized", status.extra["describe_status_reason"])
                self.assertEqual("RTSP/1.0 401 Unauthorized", status.extra["describe_status_line"])
                self.assertEqual(
                    'Digest realm="OpenSignal ITS"',
                    status.extra["describe_headers"]["www-authenticate"],
                )
                self.assertIn("401 Unauthorized", status.errors[0])
                self.assertNotIn("secret", status.errors[0])
                self.assertNotIn("secret", str(status.extra))

        asyncio.run(_exercise())

    def test_media_service_default_probe_reaches_local_listener(self):
        async def _exercise():
            async with _local_rtsp_listener() as (port, accepted_event):
                config = MediaStreamConfig(
                    stream_id="cam-local",
                    name="Local RTSP",
                    url=f"rtsp://user:secret@127.0.0.1:{port}/live/main?profile=1",
                    timeout_seconds=0.2,
                    metadata={"source": f"rtsp://user:secret@127.0.0.1:{port}/live/main?profile=1"},
                )

                status = await MediaService.check_stream_health(config)

                self.assertTrue(status.is_online)
                self.assertEqual("RTSP endpoint reachable", status.status_text)
                self.assertEqual(
                    f"rtsp://***@127.0.0.1:{port}/live/main?profile=1",
                    status.safe_url,
                )
                self.assertNotIn("secret", status.status_text)
                self.assertNotIn("secret", str(status.errors))
                self.assertNotIn("secret", str(status.raw_data))
                self.assertNotIn("secret", str(status.extra))
                self.assertEqual(port, status.extra["port"])
                self.assertEqual("/live/main?profile=1", status.extra["path_with_query"])
                await asyncio.wait_for(accepted_event.wait(), timeout=0.2)

        asyncio.run(_exercise())

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

    def test_media_service_default_probe_reports_connection_refused_without_leaking_credentials(self):
        port = _unused_tcp_port()
        config = MediaStreamConfig(
            stream_id="cam-refused",
            name="Refused Camera",
            url=f"rtsp://user:secret@127.0.0.1:{port}/offline",
            timeout_seconds=0.1,
            metadata={"source": f"rtsp://user:secret@127.0.0.1:{port}/offline"},
        )

        status = asyncio.run(MediaService.check_stream_health(config))

        self.assertFalse(status.is_online)
        self.assertEqual("RTSP health check failed", status.status_text)
        self.assertEqual(f"rtsp://***@127.0.0.1:{port}/offline", status.safe_url)
        self.assertEqual(port, status.extra["port"])
        self.assertNotIn("secret", " ".join(status.errors))
        self.assertNotIn("secret", str(status.extra))

    def test_services_package_exports_media_service(self):
        self.assertIs(MediaService, ModuleMediaService)

    def test_redact_rtsp_url_hides_credentials(self):
        safe_url = redact_rtsp_url("rtsp://user:secret@camera.example.com/live")

        self.assertEqual("rtsp://***@camera.example.com:554/live", safe_url)
        self.assertNotIn("user", safe_url)
        self.assertNotIn("secret", safe_url)


if __name__ == "__main__":
    unittest.main()