#!/usr/bin/env python3
"""Run a full Reflex boot smoke check with frontend port retry."""

from __future__ import annotations

import argparse
import os
import select
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


class FrontendPortInUseError(RuntimeError):
    """Raised when Reflex reports that the requested frontend port is busy."""


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _first_free_port(start_port: int) -> int:
    for port in range(start_port, 65536):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
        return port
    raise RuntimeError(f"Unable to find a free TCP port starting at {start_port}.")


def _terminate_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return

    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def _collect_remaining_output(process: subprocess.Popen[str]) -> str:
    if process.stdout is None:
        return ""
    remainder = process.stdout.read() or ""
    if remainder:
        sys.stdout.write(remainder)
        sys.stdout.flush()
    return remainder


def _read_startup_urls(
    process: subprocess.Popen[str],
    startup_timeout: float,
) -> tuple[str, str, str]:
    if process.stdout is None:
        raise RuntimeError("Reflex boot smoke requires stdout capture.")

    app_url: str | None = None
    backend_url: str | None = None
    output_lines: list[str] = []
    deadline = time.monotonic() + startup_timeout

    while time.monotonic() < deadline:
        remaining = max(0.0, deadline - time.monotonic())
        ready, _, _ = select.select([process.stdout], [], [], min(0.25, remaining))
        if ready:
            line = process.stdout.readline()
            if line:
                sys.stdout.write(line)
                sys.stdout.flush()
                output_lines.append(line)
                stripped = line.strip()

                if stripped.startswith("App running at:"):
                    app_url = stripped[len("App running at:") :].strip()
                elif stripped.startswith("Backend running at:"):
                    backend_url = stripped[len("Backend running at:") :].strip()
                elif "Frontend port:" in stripped and "already in use" in stripped:
                    output = "".join(output_lines) + _collect_remaining_output(process)
                    raise FrontendPortInUseError(output)

            elif process.poll() is not None:
                break

        if app_url and backend_url:
            return app_url, backend_url, "".join(output_lines)

        if process.poll() is not None:
            break

    output = "".join(output_lines) + _collect_remaining_output(process)
    if process.poll() is not None:
        raise RuntimeError(
            f"Reflex exited before startup completed with code {process.returncode}.\n{output}"
        )
    raise RuntimeError(f"Timed out waiting for Reflex startup.\n{output}")


def _wait_for_http(
    url: str,
    timeout: float,
    required_substring: str,
) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None

    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=min(5.0, timeout)) as response:
                body = response.read().decode("utf-8", errors="replace")
            if required_substring not in body:
                last_error = RuntimeError(
                    f"{url} responded without expected marker {required_substring!r}."
                )
            else:
                return
        except Exception as exc:  # pragma: no cover - exercised via runtime smoke
            last_error = exc
        time.sleep(1.0)

    raise RuntimeError(f"Timed out probing {url}: {last_error}")


def _run_boot_smoke(args: argparse.Namespace) -> int:
    frontend_port = args.frontend_port
    repo_root = _repo_root()

    for attempt in range(1, args.max_frontend_attempts + 1):
        backend_port = _first_free_port(args.backend_port)
        print(
            f"[smoke] Attempt {attempt}/{args.max_frontend_attempts}: "
            f"frontend={frontend_port} backend={backend_port}"
        )

        command = [
            sys.executable,
            "-m",
            "reflex",
            "run",
            "--env",
            args.environment,
            "--frontend-port",
            str(frontend_port),
            "--backend-port",
            str(backend_port),
        ]

        process = subprocess.Popen(
            command,
            cwd=repo_root,
            env=os.environ.copy(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        try:
            try:
                app_url, _, _ = _read_startup_urls(process, args.startup_timeout)
            except FrontendPortInUseError:
                print(f"[smoke] Frontend port {frontend_port} is busy; retrying {frontend_port + 1}.")
                frontend_port += 1
                continue

            _wait_for_http(app_url, timeout=args.probe_timeout, required_substring="__reflex")
            _wait_for_http(
                f"http://127.0.0.1:{backend_port}/ping",
                timeout=args.probe_timeout,
                required_substring="pong",
            )
            print(
                f"[smoke] Reflex boot smoke succeeded on frontend={frontend_port} "
                f"backend={backend_port}."
            )
            return 0
        finally:
            _terminate_process(process)

    print(
        f"[smoke] Exhausted {args.max_frontend_attempts} frontend attempts starting at "
        f"{args.frontend_port}.",
        file=sys.stderr,
    )
    return 1


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frontend-port", type=int, default=3002)
    parser.add_argument("--backend-port", type=int, default=8001)
    parser.add_argument("--environment", default="dev")
    parser.add_argument("--max-frontend-attempts", type=int, default=5)
    parser.add_argument("--startup-timeout", type=float, default=180.0)
    parser.add_argument("--probe-timeout", type=float, default=30.0)
    return parser.parse_args()


def main() -> int:
    try:
        return _run_boot_smoke(_parse_args())
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())