"""Media stream validation and health probing services."""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

from ..models.media import MediaProbeResult, MediaStreamConfig, MediaStreamStatus, RtspStreamEndpoint
from ..protocols.rtsp import (
    parse_rtsp_url,
    probe_rtsp_describe,
    probe_rtsp_tcp,
    redact_rtsp_url,
    RtspDescribeError,
    sanitize_rtsp_text,
    sanitize_rtsp_value,
)

MediaProbe = Callable[[MediaStreamConfig, RtspStreamEndpoint], Awaitable[MediaProbeResult]]


class MediaService:
    """Validate and probe media stream health without decoding frames."""

    @staticmethod
    def validate_stream_config(stream_config: MediaStreamConfig) -> RtspStreamEndpoint:
        return parse_rtsp_url(stream_config.url)

    @staticmethod
    async def _default_probe(
        stream_config: MediaStreamConfig,
        endpoint: RtspStreamEndpoint,
    ) -> MediaProbeResult:
        return await probe_rtsp_tcp(endpoint, timeout_seconds=stream_config.timeout_seconds)

    @staticmethod
    async def _describe_probe(
        stream_config: MediaStreamConfig,
        endpoint: RtspStreamEndpoint,
    ) -> MediaProbeResult:
        return await probe_rtsp_describe(endpoint, timeout_seconds=stream_config.timeout_seconds)

    @staticmethod
    def _status_from_result(
        stream_config: MediaStreamConfig,
        endpoint: RtspStreamEndpoint,
        result: MediaProbeResult,
    ) -> MediaStreamStatus:
        raw_url = stream_config.url
        safe_url = endpoint.safe_url
        sanitized_status_text = sanitize_rtsp_text(result.status_text, raw_url, safe_url)
        status_text = sanitized_status_text or (
            "RTSP endpoint reachable" if result.is_online else "RTSP endpoint unreachable"
        )
        extra = sanitize_rtsp_value(result.extra, raw_url, safe_url)
        extra.update(
            {
                "scheme": endpoint.scheme,
                "host": endpoint.host,
                "port": endpoint.port,
                "path": endpoint.path,
                "query": endpoint.query,
                "path_with_query": endpoint.path_with_query,
                "metadata": sanitize_rtsp_value(stream_config.metadata, raw_url, safe_url),
            }
        )
        return MediaStreamStatus(
            stream_id=stream_config.stream_id,
            name=stream_config.name,
            enabled=stream_config.enabled,
            is_online=result.is_online,
            status_text=status_text,
            safe_url=safe_url,
            latency_ms=result.latency_ms,
            errors=[sanitize_rtsp_text(error, raw_url, safe_url) for error in result.errors],
            raw_data=sanitize_rtsp_value(result.raw_data, raw_url, safe_url),
            extra=extra,
        )

    @staticmethod
    async def check_stream_health(
        stream_config: MediaStreamConfig,
        probe: MediaProbe | None = None,
    ) -> MediaStreamStatus:
        raw_url = stream_config.url
        safe_url = redact_rtsp_url(raw_url)
        try:
            endpoint = MediaService.validate_stream_config(stream_config)
            safe_url = endpoint.safe_url
        except ValueError as exc:
            return MediaStreamStatus(
                stream_id=stream_config.stream_id,
                name=stream_config.name,
                enabled=stream_config.enabled,
                is_online=False,
                status_text="Invalid stream configuration",
                safe_url=safe_url,
                errors=[sanitize_rtsp_text(str(exc), raw_url, safe_url)],
                extra={
                    "metadata": sanitize_rtsp_value(stream_config.metadata, raw_url, safe_url),
                },
            )

        if not stream_config.enabled:
            return MediaStreamStatus(
                stream_id=stream_config.stream_id,
                name=stream_config.name,
                enabled=False,
                is_online=False,
                status_text="Stream disabled",
                safe_url=endpoint.safe_url,
                extra={
                    "scheme": endpoint.scheme,
                    "host": endpoint.host,
                    "port": endpoint.port,
                    "path": endpoint.path,
                    "query": endpoint.query,
                    "path_with_query": endpoint.path_with_query,
                    "metadata": sanitize_rtsp_value(stream_config.metadata, raw_url, endpoint.safe_url),
                },
            )

        selected_probe = probe or MediaService._default_probe
        timeout = float(stream_config.timeout_seconds)
        if timeout <= 0:
            timeout = 0.001
        try:
            probe_result = await asyncio.wait_for(
                selected_probe(stream_config, endpoint),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            return MediaStreamStatus(
                stream_id=stream_config.stream_id,
                name=stream_config.name,
                enabled=stream_config.enabled,
                is_online=False,
                status_text="RTSP health check timed out",
                safe_url=endpoint.safe_url,
                errors=[f"RTSP probe timed out after {stream_config.timeout_seconds:g}s."],
                extra={
                    "scheme": endpoint.scheme,
                    "host": endpoint.host,
                    "port": endpoint.port,
                    "path": endpoint.path,
                    "query": endpoint.query,
                    "path_with_query": endpoint.path_with_query,
                    "metadata": sanitize_rtsp_value(stream_config.metadata, raw_url, endpoint.safe_url),
                },
            )
        except Exception as exc:
            return MediaStreamStatus(
                stream_id=stream_config.stream_id,
                name=stream_config.name,
                enabled=stream_config.enabled,
                is_online=False,
                status_text="RTSP health check failed",
                safe_url=endpoint.safe_url,
                errors=[sanitize_rtsp_text(str(exc), raw_url, endpoint.safe_url)],
                extra={
                    "scheme": endpoint.scheme,
                    "host": endpoint.host,
                    "port": endpoint.port,
                    "path": endpoint.path,
                    "query": endpoint.query,
                    "path_with_query": endpoint.path_with_query,
                    "metadata": sanitize_rtsp_value(stream_config.metadata, raw_url, endpoint.safe_url),
                },
            )

        return MediaService._status_from_result(stream_config, endpoint, probe_result)

    @staticmethod
    async def describe_stream_protocol(
        stream_config: MediaStreamConfig,
        probe: MediaProbe | None = None,
    ) -> MediaStreamStatus:
        raw_url = stream_config.url
        safe_url = redact_rtsp_url(raw_url)
        try:
            endpoint = MediaService.validate_stream_config(stream_config)
            safe_url = endpoint.safe_url
        except ValueError as exc:
            return MediaStreamStatus(
                stream_id=stream_config.stream_id,
                name=stream_config.name,
                enabled=stream_config.enabled,
                is_online=False,
                status_text="Invalid stream configuration",
                safe_url=safe_url,
                errors=[sanitize_rtsp_text(str(exc), raw_url, safe_url)],
                extra={
                    "probe": "describe",
                    "metadata": sanitize_rtsp_value(stream_config.metadata, raw_url, safe_url),
                },
            )

        if not stream_config.enabled:
            return MediaStreamStatus(
                stream_id=stream_config.stream_id,
                name=stream_config.name,
                enabled=False,
                is_online=False,
                status_text="Stream disabled",
                safe_url=endpoint.safe_url,
                extra={
                    "probe": "describe",
                    "scheme": endpoint.scheme,
                    "host": endpoint.host,
                    "port": endpoint.port,
                    "path": endpoint.path,
                    "query": endpoint.query,
                    "path_with_query": endpoint.path_with_query,
                    "metadata": sanitize_rtsp_value(stream_config.metadata, raw_url, endpoint.safe_url),
                },
            )

        selected_probe = probe or MediaService._describe_probe
        timeout = float(stream_config.timeout_seconds)
        if timeout <= 0:
            timeout = 0.001
        try:
            probe_result = await asyncio.wait_for(
                selected_probe(stream_config, endpoint),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            return MediaStreamStatus(
                stream_id=stream_config.stream_id,
                name=stream_config.name,
                enabled=stream_config.enabled,
                is_online=False,
                status_text="RTSP DESCRIBE timed out",
                safe_url=endpoint.safe_url,
                errors=[f"RTSP DESCRIBE probe timed out after {stream_config.timeout_seconds:g}s."],
                extra={
                    "probe": "describe",
                    "scheme": endpoint.scheme,
                    "host": endpoint.host,
                    "port": endpoint.port,
                    "path": endpoint.path,
                    "query": endpoint.query,
                    "path_with_query": endpoint.path_with_query,
                    "metadata": sanitize_rtsp_value(stream_config.metadata, raw_url, endpoint.safe_url),
                },
            )
        except Exception as exc:
            extra = {
                "probe": "describe",
                "scheme": endpoint.scheme,
                "host": endpoint.host,
                "port": endpoint.port,
                "path": endpoint.path,
                "query": endpoint.query,
                "path_with_query": endpoint.path_with_query,
                "metadata": sanitize_rtsp_value(stream_config.metadata, raw_url, endpoint.safe_url),
            }
            if isinstance(exc, RtspDescribeError):
                extra.update(
                    {
                        "describe_status_code": exc.status_code,
                        "describe_status_reason": sanitize_rtsp_text(exc.status_reason, raw_url, endpoint.safe_url),
                        "describe_status_line": sanitize_rtsp_text(exc.status_line, raw_url, endpoint.safe_url),
                        "describe_headers": sanitize_rtsp_value(exc.headers, raw_url, endpoint.safe_url),
                    }
                )
            return MediaStreamStatus(
                stream_id=stream_config.stream_id,
                name=stream_config.name,
                enabled=stream_config.enabled,
                is_online=False,
                status_text="RTSP DESCRIBE failed",
                safe_url=endpoint.safe_url,
                errors=[sanitize_rtsp_text(str(exc), raw_url, endpoint.safe_url)],
                extra=extra,
            )

        return MediaService._status_from_result(stream_config, endpoint, probe_result)