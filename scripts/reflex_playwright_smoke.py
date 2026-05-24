#!/usr/bin/env python3
"""Run a Playwright auth smoke against a temporary Reflex dev session."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

import reflex_boot_smoke


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _npx_executable() -> str:
    executable = shutil.which("npx")
    if executable is None:
        raise RuntimeError("npx is required to run the Playwright smoke test.")
    return executable


def _playwright_command(args: argparse.Namespace) -> list[str]:
    command = [
        _npx_executable(),
        "--yes",
        "playwright",
        "test",
        args.spec,
        "--config",
        args.config,
        "--browser",
        "chromium",
        "--workers",
        "1",
        "--reporter",
        args.reporter,
    ]
    return command


def _install_browser(args: argparse.Namespace) -> int:
    command = [_npx_executable(), "--yes", "playwright", "install", "chromium"]
    return subprocess.run(command, cwd=_repo_root(), check=False).returncode


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frontend-port", type=int, default=3002)
    parser.add_argument("--backend-port", type=int, default=8001)
    parser.add_argument("--environment", default="dev")
    parser.add_argument("--max-frontend-attempts", type=int, default=5)
    parser.add_argument("--startup-timeout", type=float, default=180.0)
    parser.add_argument("--probe-timeout", type=float, default=30.0)
    parser.add_argument("--spec", default="tests/e2e/auth-smoke.spec.cjs")
    parser.add_argument("--config", default="playwright.config.cjs")
    parser.add_argument("--reporter", default="list")
    parser.add_argument("--install-browser", action="store_true")
    parser.add_argument("--operator-username", default="operator")
    parser.add_argument("--operator-password", default="operatorpass123456")
    parser.add_argument("--admin-username", default="admin")
    parser.add_argument("--admin-password", default="adminpass123456")
    parser.add_argument("--admin-recovery-key", default="recoverypass123456")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    repo_root = _repo_root()

    if args.install_browser:
        install_code = _install_browser(args)
        if install_code != 0:
            return install_code

    server_env = {
        "OPENSIGNAL_OPERATOR_USERNAME": args.operator_username,
        "OPENSIGNAL_OPERATOR_PASSWORD": args.operator_password,
        "OPENSIGNAL_ADMIN_USERNAME": args.admin_username,
        "OPENSIGNAL_ADMIN_PASSWORD": args.admin_password,
        "OPENSIGNAL_ADMIN_RECOVERY_KEY": args.admin_recovery_key,
        "OPENSIGNAL_OPS_API_ALLOW_UNAUTHENTICATED": "true",
    }

    process: subprocess.Popen[str] | None = None
    try:
        process, app_url, backend_url, frontend_port, backend_port = reflex_boot_smoke.start_reflex_server(
            frontend_port=args.frontend_port,
            backend_port=args.backend_port,
            environment=args.environment,
            max_frontend_attempts=args.max_frontend_attempts,
            startup_timeout=args.startup_timeout,
            probe_timeout=args.probe_timeout,
            extra_env=server_env,
        )

        print(
            f"[e2e] Running Playwright auth smoke against frontend={frontend_port} "
            f"backend={backend_port}."
        )

        env = os.environ.copy()
        env.update(server_env)
        env.update(
            {
                "PLAYWRIGHT_BASE_URL": app_url,
                "PLAYWRIGHT_BACKEND_URL": backend_url,
                "PLAYWRIGHT_ADMIN_USERNAME": args.admin_username,
                "PLAYWRIGHT_ADMIN_PASSWORD": args.admin_password,
            }
        )

        completed = subprocess.run(
            _playwright_command(args),
            cwd=repo_root,
            env=env,
            check=False,
        )
        return completed.returncode
    finally:
        if process is not None:
            reflex_boot_smoke.terminate_process(process)


if __name__ == "__main__":
    raise SystemExit(main())