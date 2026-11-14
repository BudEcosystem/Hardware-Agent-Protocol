"""Operational commands: ``ls``, ``describe``, ``read``, ``call``, ``ops``, ``wait``, ``cancel``, ``stop``.

``describe``, ``read``, ``call``, ``wait``, ``cancel`` and ``stop`` run the same code as the agent tools
(:class:`bhms.bridges.core.AgentBridge`), so a person sees exactly the summary, refusal text and lease handling a model
sees. ``--json`` prints ``{summary, data | error}`` for scripts. Exit status: 0 ok, 1 refused or failed, 3 not settled.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.table import Table

from bhms.bridges import AgentBridge, ToolResult, render
from bhms.cli.targets import open_client, run, split_arguments
from bhms.protocol.types import to_wire

UrlOpt = Annotated[str | None, typer.Option("--url", "-u", envvar="BHMS_URL", help="Server URL, server .py or gateway .toml.")]
TokenOpt = Annotated[str | None, typer.Option("--token", envvar="BHMS_TOKEN", help="Bearer token (prefer the environment).")]
JsonOpt = Annotated[bool, typer.Option("--json", help="Machine-readable output: {summary, data | error}.")]

STATUS_STYLE = {"online": "green", "degraded": "yellow", "offline": "red", "unknown": "yellow"}


def emit(result: ToolResult, as_json: bool, console: Console) -> int:
    """Print a tool result; returns the exit status."""
    if as_json:
        typer.echo(json.dumps(result.function_output(), indent=2, ensure_ascii=False))
    else:
        style = "red" if result.is_error else None
        console.print(result.summary, style=style, highlight=False, soft_wrap=True, markup=False)
        if result.block:
            console.print(result.block, highlight=False, soft_wrap=True, markup=False)
    if result.is_error:
        op = (result.data or {}).get("operation") or {}
        return 3 if op.get("state") == "unknown" else 1
    op = (result.data or {}).get("operation")
    if op and op.get("state") not in render.SETTLED:
        return 3
    return 0


def _age(timestamp: str) -> str:
    try:
        then = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return "?"
    return render.duration(max((datetime.now(timezone.utc) - then).total_seconds() * 1000, 0)) + " ago"


def register(app: typer.Typer) -> None:
    out = Console(highlight=False)

    @app.command("ls")
    def ls(url: UrlOpt = None, token: TokenOpt = None, text: Annotated[str | None, typer.Option(help="Words in name, summary or tags.")] = None,
           capability: Annotated[str | None, typer.Option(help="Capability id or prefix.*")] = None,
           tag: Annotated[str | None, typer.Option()] = None, status: Annotated[str | None, typer.Option()] = None,
           as_json: JsonOpt = False) -> None:
        """List devices."""
        async def go() -> None:
            filt = {k: v for k, v in {"text": text, "capability": capability, "tag": tag, "status": status}.items() if v}
            async with open_client(url, token=token) as client:
                devices = [d async for d in client.iter_devices(filter=filt or None)]
            if as_json:
                typer.echo(json.dumps([to_wire(d) for d in devices], indent=2, ensure_ascii=False))
                return
            if not devices:
                out.print("no devices match" if filt else "the server has no devices")
                return
            table = Table(box=None, pad_edge=False, header_style="bold")
            for column in ("DEVICE", "NAME", "STATUS", "CAPABILITIES", "ACTIONS", "PROPERTIES"):
                table.add_column(column, overflow="fold", no_wrap=column == "DEVICE")
            for d in devices:
                table.add_row(d.device_id, render.cut(d.name, 40), f"[{STATUS_STYLE.get(d.status, 'white')}]{d.status}[/]",
                              ", ".join(d.capabilities), ", ".join(d.actions) or "-", ", ".join(d.properties) or "-")
            out.print(table)
        run(go())

    @app.command("describe")
    def describe(device: Annotated[str, typer.Argument(help="Device id.")], url: UrlOpt = None, token: TokenOpt = None,
                 full: Annotated[bool, typer.Option("--full", help="Print the complete description as JSON.")] = False,
                 as_json: JsonOpt = False) -> None:
        """Describe one device: actions with units and bounds, properties, effects, leases, stop behaviour."""
        async def go() -> int:
            async with open_client(url, token=token) as client:
                result = await AgentBridge(client).call("bhms_describe", {"device_id": device})
            if full and result.data:
                typer.echo(json.dumps(result.data["description"], indent=2, ensure_ascii=False))
                return 0
            return emit(result, as_json, out)
        raise typer.Exit(run(go()))

    @app.command("read")
    def read(device: Annotated[str, typer.Argument()], prop: Annotated[str, typer.Argument(metavar="PROPERTY")], url: UrlOpt = None,
             token: TokenOpt = None, max_age_ms: Annotated[int | None, typer.Option(help="Maximum acceptable age.")] = None,
             fresh: Annotated[bool, typer.Option("--fresh", help="Require a new measurement.")] = False,
             as_json: JsonOpt = False) -> None:
        """Read a property: value, unit, evidence, quality and age."""
        async def go() -> int:
            args: dict[str, Any] = {"device_id": device, "property": prop}
            if max_age_ms is not None:
                args["max_age_ms"] = max_age_ms
            if fresh:
                args["fresh"] = True
            async with open_client(url, token=token) as client:
                return emit(await AgentBridge(client).call("bhms_read", args), as_json, out)
        raise typer.Exit(run(go()))

    @app.command("call", context_settings={"ignore_unknown_options": False})
    def call(device: Annotated[str, typer.Argument()], action: Annotated[str, typer.Argument()],
             pairs: Annotated[list[str] | None, typer.Argument(metavar="[KEY=VALUE]...", help="Arguments: volume=50, "
                                                               "rate=10uL/min, name=\"x\", flags=true.")] = None,
             url: UrlOpt = None, token: TokenOpt = None,
             args_json: Annotated[str | None, typer.Option("--args", help="Arguments as a JSON object.")] = None,
             key: Annotated[str | None, typer.Option("--key", "-k", help="operation_key for safe retry.")] = None,
             wait_ms: Annotated[int, typer.Option(help="Wait up to this long for the outcome.")] = 5000,
             verified: Annotated[bool, typer.Option("--verified", help="Fail unless the effect is verified by measurement.")] = False,
             as_json: JsonOpt = False) -> None:
        """Invoke an action: `bhms call pump-1 dispense volume=50 --key run-42`."""
        async def go() -> int:
            arguments = json.loads(args_json) if args_json else {}
            arguments.update(split_arguments(pairs or []))
            args: dict[str, Any] = {"device_id": device, "action": action, "arguments": arguments, "wait_ms": wait_ms}
            if key:
                args["operation_key"] = key
            if verified:
                args["require_verified"] = True
            async with open_client(url, token=token) as client:
                bridge = AgentBridge(client)
                try:
                    return emit(await bridge.call("bhms_invoke", args), as_json, out)
                finally:
                    await bridge.aclose()
        raise typer.Exit(run(go()))

    @app.command("ops")
    def ops(url: UrlOpt = None, token: TokenOpt = None, device: Annotated[str | None, typer.Option()] = None,
            state: Annotated[str | None, typer.Option(help="accepted, running, completed, failed, canceled, unknown...")] = None,
            limit: Annotated[int, typer.Option(help="Newest first.")] = 20, as_json: JsonOpt = False) -> None:
        """List recent operations."""
        async def go() -> None:
            async with open_client(url, token=token) as client:
                ops_ = []
                async for op in client.iter_operations(device_id=device, state=state, limit=min(limit, 100)):
                    ops_.append(op)
                    if len(ops_) >= limit:
                        break
            if as_json:
                typer.echo(json.dumps([to_wire(o) for o in ops_], indent=2, ensure_ascii=False))
                return
            if not ops_:
                out.print("no operations")
                return
            table = Table(box=None, pad_edge=False, header_style="bold")
            for column in ("OPERATION", "WHAT", "STATE", "EFFECT", "UPDATED"):
                table.add_column(column, overflow="fold", no_wrap=column in ("OPERATION", "WHAT"))
            colors = {"completed": "green", "failed": "red", "unknown": "red", "running": "cyan", "canceled": "yellow"}
            for o in ops_:
                what = f"{o.device_id}.{o.action}" if o.kind == "action" else f"program {str(o.program_digest)[7:19]}"
                table.add_row(o.operation_id, what, f"[{colors.get(o.state, 'white')}]{o.state}[/]", o.effect, _age(o.updated_at))
            out.print(table)
        run(go())

    @app.command("wait")
    def wait(operation: Annotated[str, typer.Argument()], url: UrlOpt = None, token: TokenOpt = None,
             timeout: Annotated[float, typer.Option(help="Seconds to wait in total.")] = 60.0, as_json: JsonOpt = False) -> None:
        """Wait for an operation to settle (exit 3 when it has not by the timeout)."""
        async def go() -> int:
            deadline = time.monotonic() + timeout
            async with open_client(url, token=token) as client:
                bridge = AgentBridge(client)
                while True:
                    left = max(int((deadline - time.monotonic()) * 1000), 0)
                    result = await bridge.call("bhms_operation", {"operation_id": operation, "wait_ms": min(left, 30_000)})
                    state = ((result.data or {}).get("operation") or {}).get("state")
                    if result.error or state in render.SETTLED or left <= 0:
                        return emit(result, as_json, out)
        raise typer.Exit(run(go()))

    @app.command("cancel")
    def cancel(operation: Annotated[str, typer.Argument()], url: UrlOpt = None, token: TokenOpt = None,
               reason: Annotated[str | None, typer.Option()] = None, as_json: JsonOpt = False) -> None:
        """Ask an operation to stop (a request: check the reported cancel state)."""
        async def go() -> int:
            args = {"operation_id": operation, **({"reason": reason} if reason else {})}
            async with open_client(url, token=token) as client:
                return emit(await AgentBridge(client).call("bhms_cancel", args), as_json, out)
        raise typer.Exit(run(go()))

    @app.command("resolve")
    def resolve(operation: Annotated[str, typer.Argument(help="The unknown operation.")], url: UrlOpt = None, token: TokenOpt = None,
                state: Annotated[str | None, typer.Option(help="completed or failed: record this resolution if the device "
                                                           "cannot say what happened. Needs --basis.")] = None,
                basis: Annotated[str | None, typer.Option(help="What was inspected, by whom, and what was found.")] = None,
                effect: Annotated[str | None, typer.Option(help="unverified (an operator's report never verifies; use "
                                                            "--nothing-happened for effect none).")] = None,
                result: Annotated[str | None, typer.Option(help="With --state completed: the result as JSON, valid for "
                                                            "the action's output.")] = None,
                nothing_happened: Annotated[bool, typer.Option("--nothing-happened", help="With --state failed: there is "
                                                               "proof that the device did not act (effect none).")] = False,
                as_json: JsonOpt = False) -> None:
        """For operators: ask the device again about an unknown operation, or resolve it with evidence.

        Without --state the server only re-runs reconciliation. With --state and --basis it records your resolution when
        the device still cannot say (device evidence always wins). Needs the admin or operations:resolve scope.
        Exit status: 0 resolved, 3 still unknown, 1 refused, 2 usage."""
        if (state is None) != (basis is None):
            raise typer.BadParameter("give --state and --basis together (or neither, to only ask the device again)")
        try:
            stated = json.loads(result) if result is not None else None
        except ValueError as exc:
            raise typer.BadParameter(f"--result is not JSON: {exc}") from None

        async def go() -> int:
            kw: dict[str, Any] = {"state": state, "basis": basis, "effect": "none" if nothing_happened else effect}
            if nothing_happened:
                kw["may_have_acted"] = False
            if result is not None:
                kw["result"] = stated
            async with open_client(url, token=token) as client:
                data = to_wire(await client.operations_resolve(operation, **kw))
            op = data["operation"]
            last = [h for h in op.get("history", []) if h.get("kind") == "reconciliation"][-1:]
            block = None
            if last and op["state"] != "unknown":
                who = f"operator {last[0]['operator']['principal']}" if "operator" in last[0] else "device evidence"
                block = f"resolved by {who}: {last[0].get('detail', '')}"
            status = emit(ToolResult(render.summarize_operation(op), data, block=block), as_json, out)
            return 3 if op["state"] == "unknown" else status
        raise typer.Exit(run(go()))

    @app.command("stop")
    def stop(devices: Annotated[list[str] | None, typer.Argument(metavar="[DEVICE]...", help="Devices to stop.")] = None,
             all_devices: Annotated[bool, typer.Option("--all", help="Stop every device the server controls.")] = False,
             reason: Annotated[str, typer.Option(help="Recorded with the stop.")] = "operator request (bhms CLI)",
             url: UrlOpt = None, token: TokenOpt = None, as_json: JsonOpt = False) -> None:
        """Stop devices now (their stop procedure, their operations, their leases). Not an emergency stop."""
        async def go() -> int:
            if bool(devices) == all_devices:
                from bhms.cli.targets import CliError

                raise CliError("name the devices to stop, or pass --all (not both)", "e.g. `bhms stop pump-1` or `bhms stop --all`",
                               code=2)
            args: dict[str, Any] = {"reason": reason}
            args.update({"all": True} if all_devices else {"device_ids": list(devices or [])})
            async with open_client(url, token=token) as client:
                return emit(await AgentBridge(client).call("bhms_stop", args), as_json, out)
        raise typer.Exit(run(go()))
