"""``bhms gateway <config>`` and ``bhms mcp <target>``: the long-running processes."""

from __future__ import annotations

import os
import sys
from typing import Annotated

import typer

from bhms.cli.targets import CliError, open_client, run


def _check_policy(path: str | None, *, as_json: bool, strict: bool) -> int:
    """``bhms gateway check-policy``: exit status 0 (also with warnings, unless ``strict``), 1 strict with warnings, 2 usage."""
    import json

    from bhms.gateway.config import ConfigError, load_config
    from bhms.gateway.policy_check import check_policy, collect_devices
    from bhms.runtime.authority import Policy

    if path is None:
        print("error: check-policy needs the gateway TOML: bhms gateway check-policy <config>", file=sys.stderr)
        return 2
    try:
        config = load_config(path)
        principals = Policy(config.principals, trust_same_uid=config.trust_same_uid).principals
    except (ConfigError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    report = check_policy(principals, run(collect_devices(config)))
    print(json.dumps(report.wire(), indent=2) if as_json else report.render())
    return 1 if strict and report.warning_count else 0


def register(app: typer.Typer) -> None:
    @app.command("gateway")
    def gateway(config: Annotated[str, typer.Argument(help="Gateway TOML (see examples/bhms/gateway.toml), or the word "
                                                      "check-policy followed by the TOML.")],
                checked: Annotated[str | None, typer.Argument(metavar="[CONFIG]", help="With check-policy: the gateway TOML "
                                                              "whose policy is checked.")] = None,
                verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Log at INFO.")] = False,
                as_json: Annotated[bool, typer.Option("--json", help="check-policy: print the report as JSON.")] = False,
                strict: Annotated[bool, typer.Option("--strict", help="check-policy: exit 1 when there is a warning.")] = False
                ) -> None:
        """Run a gateway: aggregates device servers behind one endpoint with policy, leases and a journal.

        `bhms gateway check-policy <config>` does not serve: it starts the configured upstreams, reads their devices and
        lists, per principal and scope, which devices and actions each scope matches, with a warning for every scope that
        matches nothing (for example `invoke:bench/*`, which must be `invoke:bench/*/*` behind a gateway) and for a
        principal that may act on a device it may not stop."""
        if config == "check-policy":
            raise typer.Exit(_check_policy(checked, as_json=as_json, strict=strict))
        if checked is not None:
            raise typer.BadParameter(f"unexpected argument {checked!r}; did you mean: bhms gateway check-policy {config}")
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
