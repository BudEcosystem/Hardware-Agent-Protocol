"""``bhms gateway <config>`` and ``bhms mcp <target>``: the long-running processes."""

from __future__ import annotations

import os
import sys
from typing import Annotated

import typer

from bhms.cli.targets import CliError, open_client, run


def register(app: typer.Typer) -> None:
    @app.command("gateway")
    def gateway(config: Annotated[str, typer.Argument(help="Gateway TOML (see examples/bhms/gateway.toml).")],
                verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Log at INFO.")] = False) -> None:
        """Run a gateway: aggregates device servers behind one endpoint with policy, leases and a journal."""
        from bhms.gateway.__main__ import main as gateway_main

        raise typer.Exit(gateway_main([config, *(["-v"] if verbose else [])]))

    @app.command("mcp")
    def mcp(target: Annotated[str, typer.Argument(help="Gateway/server URL, a server .py or a gateway .toml.")],
            http: Annotated[str | None, typer.Option("--http", metavar="HOST:PORT", help="Serve Streamable HTTP instead "
                                                     "of stdio (at /mcp).")] = None,
            http_token: Annotated[str | None, typer.Option("--http-token", envvar="BHMS_MCP_TOKEN",
                                                           help="Bearer token required from MCP HTTP clients.")] = None,
            token: Annotated[str | None, typer.Option("--token", envvar="BHMS_TOKEN", help="Token for the BHMS target.")] = None
            ) -> None:
        """Serve the eight BHMS agent tools to any MCP client (Claude, Cursor, ...): `bhms mcp demo/server.py`."""
        from bhms.bridges import mcp as bridge

        try:
            bridge._require_mcp()
        except ImportError as exc:
            raise CliError(str(exc), "pip install 'bhms[mcp]'") from None

        async def go() -> None:
            async with open_client(target, token=token) as client:
                if http:
                    host, _, port = http.rpartition(":")
                    if not host or not port.isdigit():
                        raise CliError(f"--http {http!r} is not HOST:PORT", "e.g. --http 127.0.0.1:8770", code=2)
                    print(f"bhms mcp: Streamable HTTP on http://{host}:{port}/mcp", file=sys.stderr)
                    try:
                        await bridge.serve_http(client, host.strip("[]"), int(port), token=http_token)
                    except ValueError as exc:
                        raise CliError(str(exc), "") from None
                else:
                    await bridge.serve_stdio(client)
        os.environ.setdefault("PYTHONUNBUFFERED", "1")
        run(go())
