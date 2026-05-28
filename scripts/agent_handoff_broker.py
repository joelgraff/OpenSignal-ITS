#!/usr/bin/env python3
"""Watch a shared inbox file and trigger a command when it changes.

The broker is generic: one instance watches the planning inbox and another
watches the development inbox. Each broker only wakes when its inbox file
changes, and it persists the last processed snapshot so restarts do not
immediately re-trigger on stale content.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from string import Template


VERSION_LINE_RE = re.compile(r"^\s*version\s*:\s*(.+?)\s*$", re.IGNORECASE)


@dataclasses.dataclass(slots=True)
class FileSnapshot:
    path: Path
    exists: bool
    content: str
    digest: str
    mtime_ns: int
    size: int
    version_text: str | None
    version_number: int | None


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _default_state_file(name: str) -> Path:
    return _repo_root() / ".cache" / "agent-brokers" / f"{name}.json"


def _extract_version(content: str) -> tuple[str | None, int | None]:
    lines = content.splitlines()
    window = lines[:40]

    def _scan(candidate_lines: list[str]) -> tuple[str | None, int | None]:
        for line in candidate_lines:
            match = VERSION_LINE_RE.match(line)
            if match is None:
                continue
            version_text = match.group(1).strip().strip("\"'")
            if version_text.isdigit():
                return version_text, int(version_text)
            return version_text, None
        return None, None

    if window and window[0].strip() == "---":
        frontmatter_lines: list[str] = []
        for line in window[1:]:
            if line.strip() == "---":
                break
            frontmatter_lines.append(line)
        version_text, version_number = _scan(frontmatter_lines)
        if version_text is not None:
            return version_text, version_number

    return _scan(window)


def _snapshot(path: Path) -> FileSnapshot:
    if not path.exists():
        return FileSnapshot(
            path=path,
            exists=False,
            content="",
            digest="",
            mtime_ns=0,
            size=0,
            version_text=None,
            version_number=None,
        )

    content = path.read_text(encoding="utf-8")
    stat_result = path.stat()
    version_text, version_number = _extract_version(content)
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return FileSnapshot(
        path=path,
        exists=True,
        content=content,
        digest=digest,
        mtime_ns=stat_result.st_mtime_ns,
        size=stat_result.st_size,
        version_text=version_text,
        version_number=version_number,
    )


def _load_state(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None

    try:
        raw_text = path.read_text(encoding="utf-8")
        loaded = json.loads(raw_text)
        if isinstance(loaded, dict):
            return loaded
    except Exception as exc:  # pragma: no cover - defensive logging path
        print(f"[broker] warning: unable to load state file {path}: {exc}", file=sys.stderr)
    return None


def _write_state(path: Path, snapshot: FileSnapshot) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "digest": snapshot.digest,
        "exists": snapshot.exists,
        "mtime_ns": snapshot.mtime_ns,
        "size": snapshot.size,
        "version_text": snapshot.version_text,
        "version_number": snapshot.version_number,
        "seen_at": datetime.now(timezone.utc).isoformat(),
    }
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp_path.replace(path)


def _snapshot_from_state(path: Path, state: dict[str, object] | None) -> FileSnapshot | None:
    if state is None:
        return None

    digest = str(state.get("digest", ""))
    mtime_ns = int(state.get("mtime_ns", 0) or 0)
    size = int(state.get("size", 0) or 0)
    version_text_value = state.get("version_text")
    version_number_value = state.get("version_number")
    try:
        version_number = None if version_number_value is None else int(version_number_value)
    except (TypeError, ValueError):
        version_number = None

    return FileSnapshot(
        path=path,
        exists=bool(state.get("exists", True)),
        content="",
        digest=digest,
        mtime_ns=mtime_ns,
        size=size,
        version_text=str(version_text_value) if version_text_value is not None else None,
        version_number=version_number,
    )


def _should_trigger(current: FileSnapshot, previous: FileSnapshot | None) -> bool:
    if not current.exists:
        return False

    if previous is None:
        return True

    if not previous.exists:
        return True

    if current.version_number is not None and previous.version_number is not None:
        return current.version_number > previous.version_number

    return current.digest != previous.digest


def _command_context(args: argparse.Namespace, snapshot: FileSnapshot) -> dict[str, str]:
    return {
        "name": args.name,
        "inbox": str(args.inbox),
        "outbox": str(args.outbox),
        "digest": snapshot.digest,
        "mtime_ns": str(snapshot.mtime_ns),
        "size": str(snapshot.size),
        "version_text": snapshot.version_text or "",
        "version_number": "" if snapshot.version_number is None else str(snapshot.version_number),
        "repo_root": str(_repo_root()),
    }


def _render_command(template: str, context: dict[str, str]) -> str:
    return Template(template).safe_substitute(context)


def _run_command(command_template: str, args: argparse.Namespace, snapshot: FileSnapshot) -> int:
    context = _command_context(args, snapshot)
    command = _render_command(command_template, context)
    if not command.strip():
        return 0

    env = os.environ.copy()
    env.update(
        {
            "BROKER_NAME": args.name,
            "BROKER_INBOX": str(args.inbox),
            "BROKER_OUTBOX": str(args.outbox),
            "BROKER_INBOX_DIGEST": snapshot.digest,
            "BROKER_INBOX_MTIME_NS": str(snapshot.mtime_ns),
            "BROKER_INBOX_SIZE": str(snapshot.size),
            "BROKER_INBOX_VERSION_TEXT": snapshot.version_text or "",
            "BROKER_INBOX_VERSION_NUMBER": "" if snapshot.version_number is None else str(snapshot.version_number),
            "BROKER_REPO_ROOT": str(_repo_root()),
        }
    )

    print(f"[{args.name}] dispatching command: {command}")
    completed = subprocess.run(
        command,
        shell=True,
        cwd=_repo_root(),
        env=env,
        check=False,
    )
    return completed.returncode


def _dump_snapshot(snapshot: FileSnapshot, *, name: str) -> None:
    print(
        f"[{name}] inbox updated: digest={snapshot.digest} "
        f"version={snapshot.version_text or 'n/a'} size={snapshot.size}"
    )
    print(f"[{name}] --- inbox begin ---")
    if snapshot.content:
        end = "" if snapshot.content.endswith("\n") else "\n"
        print(snapshot.content, end=end)
    print(f"[{name}] --- inbox end ---")


def _prime_state(state_file: Path, snapshot: FileSnapshot, *, name: str) -> None:
    if snapshot.exists:
        print(
            f"[{name}] priming state with current inbox digest={snapshot.digest} "
            f"version={snapshot.version_text or 'n/a'}"
        )
        _write_state(state_file, snapshot)
    else:
        print(f"[{name}] inbox is missing; waiting for {snapshot.path} to appear.")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True, help="Friendly broker name used in log messages.")
    parser.add_argument("--inbox", required=True, type=Path, help="Prompt file watched for updates.")
    parser.add_argument("--outbox", required=True, type=Path, help="Response file paired with the inbox.")
    parser.add_argument(
        "--command-template",
        default="",
        help=(
            "Optional shell command template run when the inbox changes. "
            "Supports $name, $inbox, $outbox, $digest, $mtime_ns, $size, $version_text, $version_number, and $repo_root."
        ),
    )
    parser.add_argument(
        "--poll-seconds",
        type=float,
        default=30.0,
        help="How often to re-check the inbox when no filesystem event source is used.",
    )
    parser.add_argument(
        "--state-file",
        type=Path,
        default=None,
        help="Path used to persist the last processed inbox snapshot.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    if args.inbox.resolve() == args.outbox.resolve():
        raise SystemExit("Inbox and outbox must point to different files.")

    state_file = args.state_file or _default_state_file(args.name)
    state_file.parent.mkdir(parents=True, exist_ok=True)

    loaded_state = _load_state(state_file)
    previous_snapshot = _snapshot_from_state(args.inbox, loaded_state)
    current_snapshot = _snapshot(args.inbox)

    if previous_snapshot is None:
        _prime_state(state_file, current_snapshot, name=args.name)
        previous_snapshot = current_snapshot

    print(
        f"[{args.name}] watching inbox={args.inbox} outbox={args.outbox} "
        f"every {args.poll_seconds:.1f}s"
    )
    print(f"[{args.name}] state file: {state_file}")

    while True:
        time.sleep(args.poll_seconds)
        current_snapshot = _snapshot(args.inbox)
        if not _should_trigger(current_snapshot, previous_snapshot):
            continue

        print(
            f"[{args.name}] change detected: digest={current_snapshot.digest} "
            f"version={current_snapshot.version_text or 'n/a'}"
        )

        if args.command_template:
            command_code = _run_command(args.command_template, args, current_snapshot)
            if command_code != 0:
                print(f"[{args.name}] command exited with code {command_code}.", file=sys.stderr)
        else:
            _dump_snapshot(current_snapshot, name=args.name)

        _write_state(state_file, current_snapshot)
        previous_snapshot = current_snapshot


if __name__ == "__main__":
    raise SystemExit(main())