"""RTSP URL parsing, redaction, conservative reachability, and bounded DESCRIBE helpers."""

from __future__ import annotations

import asyncio
from time import perf_counter
from typing import Any
from urllib.parse import SplitResult, urlsplit, urlunsplit

from ..models.media import MediaProbeResult, RtspStreamEndpoint

DEFAULT_RTSP_PORT = 554
MAX_RTSP_HEADER_BYTES = 8192
SUPPORTED_RTSP_SCHEMES = {"rtsp"}


class RtspUrlValidationError(ValueError):
    """Raised when a media stream URL is not a valid RTSP endpoint."""


class RtspDescribeError(RuntimeError):
    """Raised when a bounded RTSP DESCRIBE probe cannot parse a valid response."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        status_reason: str = "",
        status_line: str = "",
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.status_reason = status_reason
        self.status_line = status_line
        self.headers = dict(headers or {})


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


def _build_request_uri(endpoint: RtspStreamEndpoint) -> str:
    path_with_query = endpoint.path_with_query or endpoint.path or "/"
    if not path_with_query.startswith("/"):
        path_with_query = f"/{path_with_query}"
    return f"{endpoint.scheme}://{_format_host(endpoint.host)}:{endpoint.port}{path_with_query}"


def _parse_rtsp_response_head(response_head: bytes) -> tuple[str, int, str, dict[str, str]]:
    header_text = response_head.decode("utf-8", errors="replace").split("\r\n\r\n", 1)[0]
    lines = header_text.split("\r\n")
    if not lines or not lines[0].startswith("RTSP/"):
        raise RtspDescribeError("Malformed RTSP DESCRIBE response status line.")

    status_parts = lines[0].split(" ", 2)
    if len(status_parts) < 2:
        raise RtspDescribeError("Malformed RTSP DESCRIBE response status line.")
    try:
        status_code = int(status_parts[1])
    except ValueError as exc:
        raise RtspDescribeError("Malformed RTSP DESCRIBE response status line.") from exc

    reason = status_parts[2].strip() if len(status_parts) > 2 else ""
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if not line:
            continue
        if ":" not in line:
            raise RtspDescribeError("Malformed RTSP DESCRIBE response header.")
        name, value = line.split(":", 1)
        headers[name.strip().lower()] = value.strip()
    return lines[0], status_code, reason, headers


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


async def probe_rtsp_describe(endpoint: RtspStreamEndpoint, timeout_seconds: float) -> MediaProbeResult:
    started = perf_counter()
    timeout = float(timeout_seconds)
    if timeout <= 0:
        timeout = 0.001

    reader, writer = await asyncio.wait_for(
        asyncio.open_connection(endpoint.host, endpoint.port),
        timeout=timeout,
    )
    request_uri = _build_request_uri(endpoint)
    request = (
        f"DESCRIBE {request_uri} RTSP/1.0\r\n"
        "CSeq: 1\r\n"
        "Accept: application/sdp\r\n"
        "\r\n"
    ).encode("utf-8")

    try:
        writer.write(request)
        await asyncio.wait_for(writer.drain(), timeout=timeout)
        try:
            response_head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=timeout)
        except asyncio.IncompleteReadError as exc:
            raise RtspDescribeError("Incomplete RTSP DESCRIBE response headers.") from exc

        if len(response_head) > MAX_RTSP_HEADER_BYTES:
            raise RtspDescribeError("RTSP DESCRIBE response headers were too large.")

        status_line, status_code, reason, headers = _parse_rtsp_response_head(response_head)
        if status_code < 200 or status_code >= 300:
            detail = f"{status_code} {reason}".strip()
            raise RtspDescribeError(
                f"RTSP DESCRIBE failed with status {detail}.",
                status_code=status_code,
                status_reason=reason,
                status_line=status_line,
                headers=headers,
            )

        content_length = 0
        raw_content_length = headers.get("content-length", "").strip()
        if raw_content_length:
            try:
                content_length = int(raw_content_length)
            except ValueError as exc:
                raise RtspDescribeError("Malformed RTSP DESCRIBE content-length header.") from exc
            if content_length < 0:
                raise RtspDescribeError("Malformed RTSP DESCRIBE content-length header.")

        response_body = b""
        if content_length:
            try:
                response_body = await asyncio.wait_for(reader.readexactly(content_length), timeout=timeout)
            except asyncio.IncompleteReadError as exc:
                raise RtspDescribeError("Incomplete RTSP DESCRIBE response body.") from exc

        body_text = response_body.decode("utf-8", errors="replace")
        content_type = headers.get("content-type", "")
        latency_ms = round((perf_counter() - started) * 1000.0, 3)
        return MediaProbeResult(
            is_online=True,
            status_text="RTSP DESCRIBE succeeded",
            latency_ms=latency_ms,
            raw_data={
                "status_line": status_line,
                "body_preview": body_text[:200],
            },
            extra={
                "transport": "tcp",
                "scheme": endpoint.scheme,
                "probe": "describe",
                "describe_uri": request_uri,
                "status_code": status_code,
                "status_reason": reason,
                "content_type": content_type,
                "content_length": content_length,
                "has_sdp": content_type.lower().startswith("application/sdp") or body_text.lstrip().startswith("v="),
            },
        )
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass