#!/usr/bin/env python3
"""Small TCP proxy for QMD MCP IPv4 compatibility.

QMD's HTTP MCP server can bind to ::1 only on macOS. Some Solar callers use
127.0.0.1 explicitly, so this proxy binds IPv4 localhost and forwards bytes to
the existing IPv6 listener.
"""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path


async def pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while True:
            data = await reader.read(65536)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


async def handle(
    client_reader: asyncio.StreamReader,
    client_writer: asyncio.StreamWriter,
    target_host: str,
    target_port: int,
) -> None:
    try:
        target_reader, target_writer = await asyncio.open_connection(target_host, target_port)
    except Exception:
        client_writer.close()
        await client_writer.wait_closed()
        return
    await asyncio.gather(
        pipe(client_reader, target_writer),
        pipe(target_reader, client_writer),
        return_exceptions=True,
    )


async def main_async() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--listen-host", default="127.0.0.1")
    parser.add_argument("--listen-port", type=int, default=8181)
    parser.add_argument("--target-host", default="::1")
    parser.add_argument("--target-port", type=int, default=8181)
    parser.add_argument("--pid-file", default=str(Path.home() / ".solar" / "harness" / "run" / "qmd-mcp-ipv4-proxy.pid"))
    args = parser.parse_args()

    pid_file = Path(args.pid_file).expanduser()
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(str(os.getpid()) + "\n")
    try:
        server = await asyncio.start_server(
            lambda r, w: handle(r, w, args.target_host, args.target_port),
            args.listen_host,
            args.listen_port,
        )
        async with server:
            await server.serve_forever()
    finally:
        try:
            if pid_file.read_text().strip() == str(os.getpid()):
                pid_file.unlink()
        except OSError:
            pass
    return 0


def main() -> int:
    try:
        return asyncio.run(main_async())
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
