#!/usr/bin/env python3
"""Smoke test the packaged server the way `uvx` runs it.

This launches an MCP-server command over stdio, performs the JSON-RPC
`initialize` handshake, and asserts the server identifies itself correctly and
lists at least one tool. It exercises the *built artifact* in an isolated
environment, so it catches failures our normal pytest suite cannot:

  * an undeclared runtime dependency (present in the dev venv, absent in uvx),
  * a packaging defect (a module/file not shipped in the wheel, a wrong
    `[project.scripts]` entry point, a broken `src/` layout).

Usage (the trailing argv is the command to run, exactly as uvx would):

    python scripts/smoke_test_uvx.py -- uvx --from dist/<wheel> mcp-server-kalshi
    python scripts/smoke_test_uvx.py -- uvx mcp-server-kalshi@0.2.1   # from PyPI

Exits 0 on success, non-zero (with a diagnosis) on any failure.
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
from typing import IO

EXPECTED_SERVER_NAME = "kalshi-server"
TIMEOUT_SECONDS = 90  # uvx may resolve/download deps on the first run


def _reader(stream: IO[str], q: queue.Queue[str | None]) -> None:
    for line in stream:
        q.put(line)
    q.put(None)  # sentinel: stream closed


def _send(proc: subprocess.Popen[str], message: dict[str, object]) -> None:
    assert proc.stdin is not None
    proc.stdin.write(json.dumps(message) + "\n")
    proc.stdin.flush()


def _await_response(
    q: queue.Queue[str | None], want_id: int, deadline: float
) -> dict[str, object]:
    """Read newline-delimited JSON-RPC until we see the response with `want_id`."""
    while time.monotonic() < deadline:
        try:
            line = q.get(timeout=deadline - time.monotonic())
        except queue.Empty:
            break
        if line is None:
            raise SystemExit("server closed stdout before responding")
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            # Not JSON-RPC (stray logging on stdout would itself be a bug for a
            # stdio server, but don't fail the handshake on it).
            continue
        if msg.get("id") == want_id:
            return msg
    raise SystemExit(f"timed out waiting for response id={want_id}")


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2

    # Force the safe default env so the smoke test never touches real money.
    env = {**os.environ, "KALSHI_ENV": "demo"}

    proc = subprocess.Popen(
        argv,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        bufsize=1,
    )

    out_q: queue.Queue[str | None] = queue.Queue()
    threading.Thread(target=_reader, args=(proc.stdout, out_q), daemon=True).start()

    deadline = time.monotonic() + TIMEOUT_SECONDS
    try:
        _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "uvx-smoke-test", "version": "0"},
                },
            },
        )
        init = _await_response(out_q, 1, deadline)

        result = init.get("result", {})
        name = result.get("serverInfo", {}).get("name")
        if name != EXPECTED_SERVER_NAME:
            raise SystemExit(
                f"unexpected serverInfo.name: {name!r} (want {EXPECTED_SERVER_NAME!r})"
            )

        # Complete the handshake, then confirm the tool registry is live.
        _send(proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})
        _send(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tools = _await_response(out_q, 2, deadline).get("result", {}).get("tools", [])
        if not tools:
            raise SystemExit("tools/list returned no tools")

        print(
            f"OK: '{name}' v{result.get('serverInfo', {}).get('version')} "
            f"booted via `{argv[0]}` and served {len(tools)} tools."
        )
        return 0
    except SystemExit as exc:
        stderr = proc.stderr.read() if proc.stderr else ""
        print(f"SMOKE TEST FAILED: {exc}", file=sys.stderr)
        if stderr.strip():
            print("---- server stderr ----", file=sys.stderr)
            print(stderr, file=sys.stderr)
        return 1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--":
        args = args[1:]
    raise SystemExit(main(args))
