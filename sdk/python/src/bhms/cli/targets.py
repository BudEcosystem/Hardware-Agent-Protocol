"""Where a ``bhms`` command connects: a URL, a device-server script or a gateway configuration.

``resolve(target)`` accepts ``stdio:<command>``, ``unix:<path>``, ``tcp://host:port``, ``ws[s]://...``, ``http[s]://...``,
a path to a ``.py`` device server (spawned over stdio with this interpreter) or a path to a gateway ``.toml`` (run
in-process on a memory transport for the lifetime of the command). With no target the environment variable ``BHMS_URL`` is
used; the bearer token comes from ``--token`` or ``BHMS_TOKEN``.

Errors that a human must fix are :class:`CliError` (message and hint, printed by :func:`run`), never tracebacks.

Thread-safety: one event loop.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import sys
from collections.abc import AsyncIterator, Awaitable
from pathlib import Path
from typing import Any, TypeVar

from bhms.client.client import Client
from bhms.protocol.errors import BhmsError
from bhms.transport.base import TransportClosed

T = TypeVar("T")
URL_PREFIXES = ("stdio:", "unix:", "tcp://", "ws://", "wss://", "http://", "https://")


class CliError(Exception):
    """A problem to show the user as ``error: <message>`` plus an optional ``hint:`` line; ``code`` is the exit status."""

    def __init__(self, message: str, hint: str = "", code: int = 1) -> None:
        super().__init__(message)
        self.message, self.hint, self.code = message, hint, code


def target_or_env(target: str | None) -> str:
    chosen = target or os.environ.get("BHMS_URL")
    if not chosen:
        raise CliError("no target given", "pass --url (a unix:/ws:/http: URL, a server .py or a gateway .toml) or set BHMS_URL",
                       code=2)
    return chosen


@contextlib.asynccontextmanager
async def open_client(target: str | None = None, *, token: str | None = None, timeout: float = 30.0,
                      strict: bool = False) -> AsyncIterator[Client]:
    """Connect to ``target`` (see the module docstring) and close everything on exit."""
    chosen = target_or_env(target)
    token = token or os.environ.get("BHMS_TOKEN")
    if chosen.startswith(URL_PREFIXES):
        try:
            client = await Client.connect(chosen, token=token, timeout=timeout, strict=strict,
                                          client_info={"name": "bhms-cli", "version": "0.1.0"})
        except (OSError, TransportClosed, ValueError, ImportError) as exc:
            raise CliError(f"cannot connect to {chosen}: {exc}", _connect_hint(chosen, exc)) from None
        try:
            yield client
        finally:
            await client.close()
        return
    path = Path(chosen).expanduser()
    if not path.is_file():
        raise CliError(f"{chosen!r} is neither a URL nor an existing file",
                       "use unix:/path, ws://host:port, http://host:port/bhms, a server script (.py) or a gateway config (.toml)",
                       code=2)
    if path.suffix == ".py":
        async with _spawn_script(path, timeout, strict) as client:
            yield client
    elif path.suffix == ".toml":
        async with _in_process_gateway(path, timeout, strict) as client:
            yield client
    else:
        raise CliError(f"don't know how to open {path}", "a server script ends in .py and a gateway config in .toml", code=2)


def _connect_hint(target: str, exc: BaseException) -> str:
    if target.startswith("http") and isinstance(exc, ImportError):
        return "HTTP needs the optional dependency: pip install 'bhms[http]'"
    if isinstance(exc, (FileNotFoundError, ConnectionRefusedError)):
        return "is the server running? start one with `bhms dev server.py` or `python server.py`"
    return "check the URL and that the server speaks BHMS (try `bhms doctor <url>`)"


@contextlib.asynccontextmanager
async def _spawn_script(path: Path, timeout: float, strict: bool) -> AsyncIterator[Client]:
    from bhms.transport import spawn_stdio

    transport = await spawn_stdio([sys.executable, str(path.resolve())], cwd=str(path.resolve().parent))
    try:
        client = await Client.from_transport(transport, timeout=timeout, strict=strict,
                                             client_info={"name": "bhms-cli", "version": "0.1.0"})
    except BaseException as exc:
        await transport.close()
        if isinstance(exc, (BhmsError, asyncio.CancelledError)):
            raise
        raise CliError(f"{path} did not answer server/discover: {exc}",
                       f"run `python {path}` directly to see its error output (stderr is inherited)") from None
    try:
        yield client
    finally:
        await client.close()


@contextlib.asynccontextmanager
async def _in_process_gateway(path: Path, timeout: float, strict: bool) -> AsyncIterator[Client]:
    from bhms.gateway import Gateway, load_config
    from bhms.gateway.config import ConfigError
    from bhms.testing.memory import connect_in_process

    try:
        config = load_config(path)
    except (ConfigError, OSError) as exc:
        raise CliError(f"{path}: {exc}", "fix the gateway configuration (see examples/bhms/gateway.toml)") from None
    gateway = Gateway(config)
    try:
        await gateway.start()
    except ValueError as exc:
        raise CliError(f"{path}: {exc}", "the gateway refused its configuration") from None
    try:
        client = await Client.from_transport(await connect_in_process(gateway.rpc), timeout=timeout, strict=strict,
                                             client_info={"name": "bhms-cli", "version": "0.1.0"})
        try:
            yield client
        finally:
            await client.close()
    finally:
        await gateway.close()


def run(awaitable: Awaitable[T]) -> T:
    """Run ``awaitable`` to completion; a :class:`CliError` or protocol error becomes a printed message and an exit status."""
    import typer
    from rich.console import Console

    err = Console(stderr=True)
    try:
        return asyncio.run(awaitable)  # type: ignore[arg-type]
    except CliError as exc:
        err.print(f"[bold red]error:[/] {exc.message}", highlight=False)
        if exc.hint:
            err.print(f"[dim]hint:[/] {exc.hint}", highlight=False)
        raise typer.Exit(exc.code) from None
    except BhmsError as exc:
        from bhms.bridges import render

        err.print(f"[bold red]{render.summarize_refusal(exc.to_operation_error())}[/]", highlight=False)
        raise typer.Exit(1) from None
    except KeyboardInterrupt:
        raise typer.Exit(130) from None


_QUANTITY = None


def parse_value(raw: str) -> Any:
    """One command-line value: JSON where it parses (``50``, ``true``, ``"x"``, ``{...}``), a quantity (``10uL/min`` ->
    ``{"value": 10, "unit": "uL/min"}``), else the string itself."""
    import json
    import re

    global _QUANTITY
    if _QUANTITY is None:
        _QUANTITY = re.compile(r"^(-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\s*([A-Za-z%][A-Za-z0-9/%.^*-]*)$")
    try:
        return json.loads(raw)
    except ValueError:
        match = _QUANTITY.match(raw.strip())
        if not match:
            return raw
        number = float(match.group(1))
        return {"value": int(number) if number == int(number) and "." not in match.group(1) else number,
                "unit": match.group(2)}


def split_arguments(pairs: list[str]) -> dict[str, Any]:
    """``["volume=50", "rate=10uL/min", "label=a b"]`` -> arguments (see :func:`parse_value`)."""
    out: dict[str, Any] = {}
    for pair in pairs:
        key, sep, raw = pair.partition("=")
        if not sep or not key:
            raise CliError(f"argument {pair!r} is not key=value", "write arguments as name=value, e.g. volume=50 or rate=10uL/min",
                           code=2)
        out[key] = parse_value(raw)
    return out
