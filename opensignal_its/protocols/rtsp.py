"""RTSP URL parsing, redaction, and conservative reachability helpers."""

from __future__ import annotations

import asyncio
from time import perf_counter
from typing import Any
from urllib.parse import SplitResult, urlsplit, urlunsplit

from ..models.media import MediaProbeResult, RtspStreamEndpoint

DEFAULT_RTSP_PORT = 554
SUPPORTED_RTSP_SCHEMES = {"rtsp"}


class RtspUrlValidationError(ValueError):
    """Raised when a media stream URL is not a valid RTSP endpoint."""


def _format_host(host: str) -> str:
    if ":" in host and not host.startswith("["):
        return f"[{host}]"
    return host


def _safe_netloc(parts: SplitResult, port: int | None) -> str:
    has_credentials = bool(parts.username or parts.password)
    host = parts.hostname or ""
    tokens: list[str] = []
    if has_credentials:
        tokens.append("***@")
    if host:
        tokens.append(_format_host(host))
    if port is not None:
        tokens.append(f":{port}")
    return "".join(tokens)


def _build_safe_rtsp_url(parts: SplitResult, port: int | None) -> str:
    scheme = (parts.scheme or "rtsp").lower()
    path = parts.path or ""
    query = parts.query or ""
    return urlunsplit((scheme, _safe_netloc(parts, port), path, query, ""))


def redact_rtsp_url(raw_url: str) -> str:
    value = str(raw_url).strip()
    if not value:
        return ""

    try:
        parts = urlsplit(value)
    except ValueError:
        return value

    try:
        explicit_port = parts.port
    except ValueError:
        explicit_port = None

    if parts.hostname or parts.username or parts.password:
        port = explicit_port
        if port is None and (parts.scheme or "").lower() in SUPPORTED_RTSP_SCHEMES:
            port = DEFAULT_RTSP_PORT
        return _build_safe_rtsp_url(parts, port)
    return value


def sanitize_rtsp_text(text: str, raw_url: str, safe_url: str = "") -> str:
    sanitized = str(text)
    original_url = str(raw_url).strip()
    if not original_url:
        return sanitized

    safe_display_url = safe_url or redact_rtsp_url(original_url)
    sanitized = sanitized.replace(original_url, safe_display_url)

    try:
        parts = urlsplit(original_url)
    except ValueError:
        return sanitized

    redacted_netloc = _safe_netloc(parts, None)
    if parts.netloc and redacted_netloc:
        sanitized = sanitized.replace(parts.netloc, redacted_netloc)

    username = parts.username or ""
    password = parts.password or ""
    credentials = [
        username,
        password,
        f"{username}:{password}" if username and password else "",
        f"{username}@" if username else "",
        f"{username}:{password}@" if username and password else "",
    ]
    for credential in credentials:
        if credential:
            sanitized = sanitized.replace(credential, "***")
    return sanitized


def sanitize_rtsp_value(value: Any, raw_url: str, safe_url: str = "") -> Any:
    if isinstance(value, str):
        return sanitize_rtsp_text(value, raw_url, safe_url)
    if isinstance(value, dict):
        return {key: sanitize_rtsp_value(item, raw_url, safe_url) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_rtsp_value(item, raw_url, safe_url) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_rtsp_value(item, raw_url, safe_url) for item in value)
    return value


def parse_rtsp_url(raw_url: str) -> RtspStreamEndpoint:
    value = str(raw_url).strip()
    if not value:
        raise RtspUrlValidationError("Stream URL is required.")

    try:
        parts = urlsplit(value)
    except ValueError as exc:
        raise RtspUrlValidationError(f"Malformed RTSP URL: {exc}") from exc

    scheme = (parts.scheme or "").lower()
    if scheme not in SUPPORTED_RTSP_SCHEMES:
        raise RtspUrlValidationError("RTSP URL must start with rtsp://")

    host = parts.hostname or ""
    if not host:
        raise RtspUrlValidationError("RTSP URL must include a host.")

    try:
        port = parts.port or DEFAULT_RTSP_PORT
    except ValueError as exc:
        raise RtspUrlValidationError(f"RTSP URL port is invalid: {exc}") from exc

    path = parts.path or ""
    query = parts.query or ""
    path_with_query = f"{path}?{query}" if query else path
    safe_url = _build_safe_rtsp_url(parts, port)
    return RtspStreamEndpoint(
        scheme=scheme,
        host=host,
        port=port,
        path=path,
        query=query,
        path_with_query=path_with_query,
        safe_url=safe_url,
    )


async def probe_rtsp_tcp(endpoint: RtspStreamEndpoint, timeout_seconds: float) -> MediaProbeResult:
    started = perf_counter()
    timeout = float(timeout_seconds)
    if timeout <= 0:
        timeout = 0.001
    reader, writer = await asyncio.wait_for(
        asyncio.open_connection(endpoint.host, endpoint.port),
        timeout=timeout,
    )
    del reader
    latency_ms = round((perf_counter() - started) * 1000.0, 3)
    writer.close()
    try:
        await writer.wait_closed()
    except Exception:
        pass
    return MediaProbeResult(
        is_online=True,
        status_text="RTSP endpoint reachable",
        latency_ms=latency_ms,
        extra={
            "transport": "tcp",
            "scheme": endpoint.scheme,
        },
    )