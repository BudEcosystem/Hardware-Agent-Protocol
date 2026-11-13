"""``bhms doctor [TARGET]``: checks the environment and, with a target, connectivity, identity and descriptions.

Every check prints ``ok``, ``warn`` or ``FAIL`` with what to do; the exit status is 1 when any check fails. Secrets are never
printed (the OpenAI key is reported only as present or absent).
"""

from __future__ import annotations

import importlib
import importlib.metadata
import os
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.markup import escape

from bhms.cli.targets import CliError, open_client, run

OK, WARN, FAIL = "ok", "warn", "FAIL"
DEPENDENCIES = (("orjson", True, ""), ("pydantic", True, ""), ("websockets", True, ""), ("jsonschema", True, ""),
                ("rfc8785", True, ""), ("rich", True, ""), ("typer", True, ""),
                ("aiohttp", False, "needed for http:// targets and listeners: pip install 'bhms[http]'"),
                ("mcp", False, "needed for `bhms mcp`: pip install 'bhms[mcp]'"),
                ("openai", False, "needed for the OpenAI agent loop: pip install 'bhms[openai]'"))


@dataclass(frozen=True, slots=True)
class Check:
    status: str
    name: str
    detail: str
    fix: str = ""


def environment_checks() -> list[Check]:
    checks = [Check(OK if sys.version_info >= (3, 11) else FAIL, "python", sys.version.split()[0],
                    "" if sys.version_info >= (3, 11) else "BHMS needs Python 3.11 or newer")]
    for module, required, fix in DEPENDENCIES:
        try:
            importlib.import_module(module)
            try:
                version = importlib.metadata.version(module)
            except importlib.metadata.PackageNotFoundError:
                version = "installed"
            checks.append(Check(OK, module, version))
        except ImportError:
            checks.append(Check(FAIL if required else WARN, module, "missing", fix or f"pip install {module}"))
    try:
        from bhms.protocol import schema

        checks.append(Check(OK, "schema", f"bhms.schema.json, protocol {schema.load_schema()['x-bhms-protocolVersion']}"))
    except Exception as exc:  # a broken install must be reported, not raised
        checks.append(Check(FAIL, "schema", str(exc), "reinstall bhms"))
    from bhms.server.server import default_state_dir

    state = default_state_dir()
    probe = state
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    if not os.access(probe, os.W_OK):
        checks.append(Check(FAIL, "state dir", f"{state} (cannot write to {probe})", "set BHMS_STATE_DIR to a writable directory"))
    else:
        free = shutil.disk_usage(probe).free / 2**30
        status = OK if free >= 1 else WARN
        checks.append(Check(status, "state dir", f"{state} ({free:.1f} GiB free)",
                            "" if status == OK else "SQLite journals fsync on every dispatch; free some disk space"))
    key_file = Path.home() / ".config" / "hms" / "openai.env"
    has_key = bool(os.environ.get("OPENAI_API_KEY")) or key_file.is_file()
    checks.append(Check(OK if has_key else WARN, "openai key", "present" if has_key else "absent",
                        "" if has_key else "only needed for the agent loop: set OPENAI_API_KEY or ~/.config/hms/openai.env"))
    return checks


async def connectivity_checks(target: str, token: str | None) -> list[Check]:
    from bhms.bridges import render
    from bhms.protocol import schema
    from bhms.protocol.errors import BhmsError
    from bhms.protocol.types import to_wire

    checks: list[Check] = []
    started = time.perf_counter()
    try:
        async with open_client(target, token=token, timeout=15) as client:
            took = (time.perf_counter() - started) * 1000
            server = client.server
            assert server is not None
            checks.append(Check(OK, "connect", f"{server.server_info.name} {server.server_info.version}, protocol "
                                f"{client.version}, {took:.0f} ms (connect + server/discover)"))
            principal = server.principal
            checks.append(Check(OK if principal else WARN, "principal", f"{principal.id} scopes {', '.join(principal.scopes)}"
                                if principal else "not reported", "" if principal else "the server does not say who you are"))
            caps = to_wire(server.capabilities)
            checks.append(Check(OK, "capabilities", ", ".join(k for k in caps if k != "extensions") or "none"))
            listing = [d async for d in client.iter_devices()]
            checks.append(Check(OK if listing else WARN, "devices", f"{len(listing)} listed",
                                "" if listing else "the server has no devices"))
            bad: list[str] = []
            big: list[str] = []
            for summary in listing[:20]:
                try:
                    description = to_wire((await client.devices_describe(summary.device_id)).description)
                    schema.validate("DeviceDescription", description)
                except BhmsError as exc:
                    bad.append(f"{summary.device_id}: {exc.message}")
                    continue
                if render.estimate_tokens(render.signature_block(description, max_tokens=10**6)) > render.SIGNATURE_TOKENS:
                    big.append(summary.device_id)
            if listing:
                checks.append(Check(FAIL if bad else OK, "descriptions", "; ".join(bad[:3]) if bad else
                                    f"{min(len(listing), 20)} valid against the schema", "fix the device declarations" if bad else ""))
            if big:
                checks.append(Check(WARN, "agent signature", f"{', '.join(big[:3])}: over {render.SIGNATURE_TOKENS} tokens",
                                    "agents see elided details; split the device or shorten descriptions"))
            offline = [d.device_id for d in listing if d.status != "online"]
            if offline:
                checks.append(Check(WARN, "status", f"not online: {', '.join(offline[:5])}", "check the device links"))
    except CliError as exc:
        checks.append(Check(FAIL, "connect", exc.message, exc.hint))
    except BhmsError as exc:
        checks.append(Check(FAIL, "connect", f"{exc.code}: {exc.message}", exc.hint))
    except Exception as exc:  # report any other failure as a check
        checks.append(Check(FAIL, "connect", f"{type(exc).__name__}: {exc}", "run with a working target, see `bhms --help`"))
    return checks


def register(app: typer.Typer) -> None:
    @app.command("doctor")
    def doctor(target: Annotated[str | None, typer.Argument(help="Server URL, .py or .toml to check as well.")] = None,
               token: Annotated[str | None, typer.Option("--token", envvar="BHMS_TOKEN")] = None) -> None:
        """Check the environment and, with a target, connectivity, identity and device descriptions."""
        console = Console(highlight=False)

        async def go() -> int:
            checks = environment_checks()
            chosen = target or os.environ.get("BHMS_URL")
            if chosen:
                checks += await connectivity_checks(chosen, token)
            styles = {OK: "green", WARN: "yellow", FAIL: "bold red"}
            for c in checks:
                console.print(f"[{styles[c.status]}]{c.status:>4}[/]  {c.name:<16} {escape(c.detail)}", soft_wrap=True)
                if c.fix and c.status != OK:
                    console.print(f"      [dim]-> {escape(c.fix)}[/]", soft_wrap=True)
            failed = sum(c.status == FAIL for c in checks)
            console.print(f"\n{len(checks)} checks, {failed} failed" + ("" if chosen else "; pass a target to check connectivity"))
            return 1 if failed else 0
        raise typer.Exit(run(go()))
