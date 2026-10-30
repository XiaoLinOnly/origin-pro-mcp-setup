#!/usr/bin/env python3
"""Probe a local origin-pro MCP server over stdio.

Examples:
    python probe_mcp.py --call list_worksheets
    python probe_mcp.py --in-process --call list_worksheets
    python probe_mcp.py --attach --call list_worksheets

The probe only performs an MCP handshake, tools/list and one tool call.
It does not close Origin windows spawned by the server.
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path


def find_exe(explicit: str | None) -> str:
    if explicit:
        return explicit
    env_exe = os.environ.get("ORIGIN_PRO_MCP_EXE")
    if env_exe:
        return env_exe
    found = shutil.which("origin-pro-mcp")
    if found:
        return found
    for name in ("origin-pro-mcp.exe", "origin-pro-mcp"):
        candidate = Path.home() / ".local" / "bin" / name
        if candidate.exists():
            return str(candidate)
    raise SystemExit(
        "origin-pro-mcp executable not found. Pass --exe, set "
        "ORIGIN_PRO_MCP_EXE, or install it with uv."
    )


class Server:
    def __init__(self, exe: str, *, daemon: bool, attach: bool) -> None:
        env = os.environ.copy()
        env["ORIGIN_PRO_MCP_USE_DAEMON"] = "1" if daemon else "0"
        env["ORIGIN_PRO_MCP_ATTACH"] = "1" if attach else "0"
        env["PYTHONUNBUFFERED"] = "1"
        self.proc = subprocess.Popen(
            [exe],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=env,
        )
        self.queue: queue.Queue = queue.Queue()
        threading.Thread(
            target=self._reader, args=(self.proc.stdout, "out"), daemon=True
        ).start()
        threading.Thread(
            target=self._reader, args=(self.proc.stderr, "err"), daemon=True
        ).start()

    def _reader(self, stream, kind: str) -> None:
        for line in stream:
            self.queue.put((kind, line.rstrip("\n")))
        self.queue.put((kind, None))

    def send(self, payload: dict) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(json.dumps(payload) + "\n")
        self.proc.stdin.flush()

    def wait_for(self, request_id: int, timeout: float) -> dict:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                kind, line = self.queue.get(timeout=1.0)
            except queue.Empty:
                continue
            if kind == "err":
                if line is not None:
                    print(f"STDERR: {line}", file=sys.stderr)
                continue
            if line is None:
                raise RuntimeError("server closed stdout before replying")
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if message.get("id") == request_id:
                return message
        raise TimeoutError(f"no response for request id {request_id}")

    def close(self) -> None:
        if self.proc.poll() is None:
            try:
                if self.proc.stdin is not None:
                    self.proc.stdin.close()
            except OSError:
                pass
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.terminate()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", help="path to origin-pro-mcp executable")
    parser.add_argument(
        "--in-process",
        action="store_true",
        help="run the MCP server in-process (USE_DAEMON=0) instead of the daemon",
    )
    parser.add_argument(
        "--attach",
        action="store_true",
        help="attach to an already-open Origin (USE_DAEMON=1, ATTACH=1)",
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="explicitly use the daemon-backed server (default)",
    )
    parser.add_argument(
        "--call",
        default="list_worksheets",
        help="tool name to invoke (default: list_worksheets)",
    )
    parser.add_argument(
        "--args",
        default="{}",
        help='tool arguments as JSON (default: "{}")',
    )
    parser.add_argument(
        "--verbose", action="store_true", help="print every tool name"
    )
    parser.add_argument(
        "--timeout", type=float, default=180.0, help="seconds per request"
    )
    args = parser.parse_args()

    try:
        call_args = json.loads(args.args)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"--args is not valid JSON: {exc}")

    exe = find_exe(args.exe)
    daemon = not args.in_process
    if args.daemon:
        daemon = True
    if args.attach and args.in_process:
        print(
            "warning: --attach with --in-process; the in-process server always "
            "uses Origin.ApplicationSI",
            file=sys.stderr,
        )

    server = Server(exe, daemon=daemon, attach=args.attach)
    try:
        server.send(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "origin-pro-probe", "version": "0.0.0"},
                },
            }
        )
        init = server.wait_for(1, args.timeout)
        info = init.get("result", {}).get("serverInfo", {})
        print(f"INIT: {info.get('name', '?')} {info.get('version', '')}".strip())

        server.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        server.send(
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
        )
        tools_message = server.wait_for(2, args.timeout)
        tools = tools_message.get("result", {}).get("tools", [])
        names = [tool.get("name", "?") for tool in tools]
        print(f"TOOL COUNT: {len(names)}")
        if args.verbose:
            print("TOOLS:", ", ".join(names))
        else:
            preview = ", ".join(names[:8])
            print(f"TOOLS: {preview}{' ...' if len(names) > 8 else ''}")

        server.send(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": args.call, "arguments": call_args},
            }
        )
        call = server.wait_for(3, args.timeout)
        result = call.get("result", {})
        texts = [
            item.get("text", "")
            for item in result.get("content", [])
            if item.get("type") == "text"
        ]
        print("CALL:", "\n".join(texts)[:4000])
        if result.get("isError"):
            print("CALL FAILED (isError=true)", file=sys.stderr)
            return 1
        return 0
    except Exception as exc:
        print(f"PROBE FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        server.close()


if __name__ == "__main__":
    raise SystemExit(main())
