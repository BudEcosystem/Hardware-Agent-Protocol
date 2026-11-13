"""``bhms dev <server.py | url | gateway.toml>``: an interactive inspector built on rich.

It connects (spawning a server script over stdio), shows the devices and keeps a live feed of operations, events and device
changes (``subscriptions/listen``) above the prompt. Commands: ``ls``, ``describe <n|id>``, ``read <n|id> <property>``,
``invoke [<n|id> [action]]`` (prompts for every argument from the action's input schema, showing units and bounds, validating
as you type), ``ops``, ``wait <op>``, ``cancel <op>``, ``stop <n|id>... | all``, ``reload`` (restart a script target),
``help``, ``quit``. ``describe``, ``read``, ``invoke``, ``cancel`` and ``stop`` use the agent tools' code
(:class:`bhms.bridges.core.AgentBridge`), so leases, refusals and summaries are exactly what a model would get.

Input is read line by line (``input()``), so the inspector also works when scripted through a pipe or a pseudo-terminal.
Thread-safety: one event loop; line input runs in daemon threads.
"""

from __future__ import annotations

import asyncio
import contextlib
import secrets
import shlex
import threading
from contextlib import AsyncExitStack
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from bhms.bridges import AgentBridge, ToolResult, render
from bhms.cli.targets import CliError, open_client, parse_value, run
from bhms.client.client import Client
from bhms.protocol.errors import BhmsError
from bhms.protocol.types import to_wire
from bhms.server.validation import ArgumentValidator

HELP = """\
ls                         list devices (numbered)
describe <n|id>            actions with units and bounds, properties, stop behaviour
read <n|id> <property>     value, evidence, quality, age
invoke [<n|id> [action]]   prompts for each argument; shows units and bounds; retry-safe key added
ops                        recent operations
wait <op> | cancel <op>    wait for / ask to cancel an operation
stop <n|id>... | all       stop devices now
reload                     restart the server script and reconnect
help | quit"""
STATE_STYLE = {"completed": "green", "failed": "red", "unknown": "bold red", "canceled": "yellow", "running": "cyan"}


class Inspector:
    """The interactive session; ``run()`` returns when the user quits or input ends."""

    def __init__(self, target: str, *, token: str | None = None, console: Console | None = None) -> None:
        self.target, self.token = target, token
        self.console = console or Console(highlight=False)
        self.client: Client | None = None
        self.bridge: AgentBridge | None = None
        self.devices: list[Any] = []
        self._stack: AsyncExitStack | None = None
        self._feed: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------ connection

    async def connect(self) -> None:
        stack = AsyncExitStack()
        try:
            self.client = await stack.enter_async_context(open_client(self.target, token=self.token))
        except BaseException:
            await stack.aclose()
            raise
        self._stack = stack
        self.bridge = AgentBridge(self.client)
        server = self.client.server
        assert server is not None
        principal = f" as {server.principal.id}" if server.principal else ""
        self.console.print(f"[bold]connected[/] to {escape(server.server_info.name)} {escape(server.server_info.version)}"
                           f"{principal}, protocol {self.client.version}")
        self._feed = asyncio.get_running_loop().create_task(self._watch(self.client), name="bhms-inspector-feed")

    async def disconnect(self) -> None:
        if self._feed is not None:
            self._feed.cancel()
            await asyncio.gather(self._feed, return_exceptions=True)
            self._feed = None
        if self.bridge is not None:
            await self.bridge.aclose()
        if self._stack is not None:
            await self._stack.aclose()
            self._stack = None
        self.client = self.bridge = None

    async def _watch(self, client: Client) -> None:
        """Print operations, events and device-list changes as they happen."""
        try:
            subscription = await client.subscribe(devices_list_changed=True, operations={"all": True}, events={})
        except BhmsError as exc:
            self.console.print(f"[yellow]live feed unavailable:[/] {escape(exc.message)} ({escape(exc.hint)})")
            return
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # the feed is a convenience: never take the inspector down
            self.console.print(f"[yellow]live feed unavailable:[/] {escape(str(exc))}")
            return
        for refused in getattr(subscription.acknowledged, "refused", None) or []:
            self.console.print(f"[yellow]live feed:[/] {escape(str(refused.path))} refused: {escape(refused.hint)}")
        try:
            async with subscription:
                async for note in subscription:
                    await self._show(note.method, note.params)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.console.print(f"[yellow]live feed ended:[/] {escape(str(exc))}")
            return
        self.console.print(f"[yellow]live feed ended ({subscription.end_reason}); `reload` or restart to listen again[/]")

    async def _show(self, method: str, params: Any) -> None:
        if method == "notifications/operation":
            op = to_wire(params.operation)
            style = STATE_STYLE.get(op["state"], "white")
            description = await self.bridge.description_for_operation(op) if self.bridge and op["state"] == "completed" else None
            line = render.summarize_operation(op, keyed=True, description=description, wait_hint=False)
            self.console.print(f"[dim]▸[/] [{style}]{escape(line)}[/]")
        elif method == "notifications/event":
            e = params.event
            where = f" {e.device_id}" if e.device_id else ""
            message = f": {escape(render.quote(e.message))}" if e.message else ""
            self.console.print(f"[dim]▸ event[/] {e.severity} {escape(e.type)}{where}{message}")
        elif method == "notifications/devices/listChanged":
            self.console.print("[dim]▸ device list changed (type `ls`)[/]")

    # ------------------------------------------------------------------ input

    async def read_line(self, prompt: str) -> str | None:
        """One line from the user, or None at end of input. Runs ``input()`` in a daemon thread so quitting never blocks."""
        loop = asyncio.get_running_loop()
        future: asyncio.Future[str | None] = loop.create_future()

        def worker() -> None:
            try:
                line: str | None = input(prompt)
            except EOFError:
                line = None
            except Exception:
                line = None
            loop.call_soon_threadsafe(lambda: future.done() or future.set_result(line))

        threading.Thread(target=worker, daemon=True, name="bhms-inspector-input").start()
        return await future

    # ------------------------------------------------------------------ commands

    async def run(self) -> None:
        await self.connect()
        try:
            await self.cmd_ls()
            self.console.print("type `help` for commands, `invoke` to act, `quit` to leave")
            while True:
                line = await self.read_line("bhms> ")
                if line is None:
                    self.console.print()
                    return
                try:
                    words = shlex.split(line)
                except ValueError as exc:
                    self.console.print(f"[red]{escape(str(exc))}[/]")
                    continue
                if not words:
                    continue
                if words[0] in ("quit", "exit", "q"):
                    return
                try:
                    await self.dispatch(words[0], words[1:])
                except BhmsError as exc:
                    self.console.print(f"[red]{escape(render.summarize_refusal(exc.to_operation_error()))}[/]")
                except CliError as exc:
                    self.console.print(f"[red]{escape(exc.message)}[/] {escape(exc.hint)}")
                except (asyncio.CancelledError, KeyboardInterrupt):
                    raise
                except Exception as exc:
                    self.console.print(f"[red]{type(exc).__name__}: {escape(str(exc))}[/]")
        finally:
            await self.disconnect()

    async def dispatch(self, command: str, args: list[str]) -> None:
        handlers = {"ls": self.cmd_ls, "devices": self.cmd_ls, "describe": self.cmd_describe, "d": self.cmd_describe,
                    "read": self.cmd_read, "invoke": self.cmd_invoke, "call": self.cmd_invoke, "ops": self.cmd_ops,
                    "wait": self.cmd_wait, "cancel": self.cmd_cancel, "stop": self.cmd_stop, "reload": self.cmd_reload,
                    "help": self.cmd_help, "?": self.cmd_help}
        handler = handlers.get(command)
        if handler is None:
            self.console.print(f"unknown command {escape(command)!r}; type `help`")
            return
        await handler(args)

    def _device(self, ref: str) -> str:
        if ref.isdigit() and 1 <= int(ref) <= len(self.devices):
            return str(self.devices[int(ref) - 1].device_id)
        return ref

    def _print(self, result: ToolResult) -> None:
        self.console.print(result.summary, style="red" if result.is_error else None, soft_wrap=True, markup=False)
        if result.block:
            self.console.print(result.block, soft_wrap=True, markup=False)

    async def cmd_help(self, args: list[str] | None = None) -> None:
        self.console.print(HELP)

    async def cmd_ls(self, args: list[str] | None = None) -> None:
        assert self.client is not None
        self.devices = [d async for d in self.client.iter_devices()]
        if not self.devices:
            self.console.print("the server has no devices")
            return
        table = Table(box=None, pad_edge=False, header_style="bold")
        for column in ("#", "DEVICE", "NAME", "STATUS", "ACTIONS", "PROPERTIES"):
            table.add_column(column, overflow="fold", no_wrap=column == "DEVICE")
        for i, d in enumerate(self.devices, 1):
            color = {"online": "green", "offline": "red"}.get(d.status, "yellow")
            table.add_row(str(i), d.device_id, render.cut(d.name, 40), f"[{color}]{d.status}[/]", ", ".join(d.actions) or "-",
                          ", ".join(d.properties) or "-")
        self.console.print(table)

    async def cmd_describe(self, args: list[str]) -> None:
        assert self.bridge is not None
        if not args:
            raise CliError("describe which device?", "describe <n|id>, numbers come from `ls`")
        self._print(await self.bridge.call("bhms_describe", {"device_id": self._device(args[0])}))

    async def cmd_read(self, args: list[str]) -> None:
        assert self.bridge is not None
        if len(args) < 2:
            raise CliError("read which property?", "read <n|id> <property>")
        self._print(await self.bridge.call("bhms_read", {"device_id": self._device(args[0]), "property": args[1]}))

    async def cmd_invoke(self, args: list[str]) -> None:
        assert self.bridge is not None
        device = self._device(args[0]) if args else await self._choose("device", [d.device_id for d in self.devices])
        description = await self.bridge.description(device)
        actions = description.get("actions") or {}
        if not actions:
            self.console.print(f"{escape(device)} has no actions")
            return
        action = args[1] if len(args) > 1 else await self._choose("action", list(actions))
        spec = actions.get(action)
        if spec is None:
            raise CliError(f"{device} has no action {action!r}", f"actions: {', '.join(actions)}")
        self.console.print(escape(render._action_line(action, spec, 0)))
        arguments = await self.prompt_arguments(spec["input"])
        key = f"insp-{secrets.token_hex(4)}"
        self.console.print(f"sending with operation_key [bold]{key}[/] (retry-safe)")
        self._print(await self.bridge.call("bhms_invoke", {"device_id": device, "action": action, "arguments": arguments,
                                                           "operation_key": key}))

    async def _choose(self, what: str, options: list[str]) -> str:
        for i, option in enumerate(options, 1):
            self.console.print(f"  {i}. {escape(option)}")
        while True:
            answer = await self.read_line(f"{what} (number or name): ")
            if answer is None:
                raise CliError("input ended")
            answer = answer.strip()
            if answer.isdigit() and 1 <= int(answer) <= len(options):
                return options[int(answer) - 1]
            if answer in options:
                return answer
            self.console.print(f"[red]choose one of the listed {what}s[/]")

    async def prompt_arguments(self, input_schema: dict[str, Any]) -> dict[str, Any]:
        """Ask for every argument of an action: label from the schema (type, unit, bounds, default), validate each answer."""
        required = set(input_schema.get("required") or [])
        values: dict[str, Any] = {}
        for name, node in (input_schema.get("properties") or {}).items():
            label = render.argument_text(name, node, name in required)
            while True:
                answer = await self.read_line(f"  {label}{'' if name in required else ' [Enter to skip]'}: ")
                if answer is None:
                    raise CliError("input ended")
                answer = answer.strip()
                if not answer:
                    if name in required:
                        self.console.print("  [red]required[/]")
                        continue
                    break
                try:
                    value = parse_value(answer)
                    ArgumentValidator({"type": "object", "additionalProperties": False, "properties": {name: node}}).admit(
                        {name: value})
                except BhmsError as exc:
                    self.console.print(f"  [red]{escape(exc.message)}[/] {escape(exc.hint)}")
                    continue
                values[name] = value
                break
        return values

    async def cmd_ops(self, args: list[str] | None = None) -> None:
        assert self.client is not None
        table = Table(box=None, pad_edge=False, header_style="bold")
        for column in ("OPERATION", "WHAT", "STATE", "EFFECT"):
            table.add_column(column, overflow="fold", no_wrap=column in ("OPERATION", "WHAT"))
        count = 0
        async for op in self.client.iter_operations(limit=20):
            what = f"{op.device_id}.{op.action}" if op.kind == "action" else "program"
            table.add_row(op.operation_id, what, f"[{STATE_STYLE.get(op.state, 'white')}]{op.state}[/]", op.effect)
            count += 1
            if count >= 20:
                break
        self.console.print(table if count else "no operations yet")

    async def cmd_wait(self, args: list[str]) -> None:
        assert self.bridge is not None
        if not args:
            raise CliError("wait for which operation?", "wait <operation id>")
        self._print(await self.bridge.call("bhms_operation", {"operation_id": args[0], "wait_ms": 30_000}))

    async def cmd_cancel(self, args: list[str]) -> None:
        assert self.bridge is not None
        if not args:
            raise CliError("cancel which operation?", "cancel <operation id>")
        self._print(await self.bridge.call("bhms_cancel", {"operation_id": args[0], "reason": "inspector"}))

    async def cmd_stop(self, args: list[str]) -> None:
        assert self.bridge is not None
        if not args:
            raise CliError("stop which devices?", "stop <n|id>... or stop all")
        payload: dict[str, Any] = {"reason": "inspector stop"}
        payload.update({"all": True} if args == ["all"] else {"device_ids": [self._device(a) for a in args]})
        self._print(await self.bridge.call("bhms_stop", payload))

    async def cmd_reload(self, args: list[str] | None = None) -> None:
        await self.disconnect()
        await self.connect()
        await self.cmd_ls()


def register(app: typer.Typer) -> None:
    @app.command("dev")
    def dev(target: Annotated[str, typer.Argument(help="A server script (.py), URL or gateway .toml.")],
            token: Annotated[str | None, typer.Option("--token", envvar="BHMS_TOKEN")] = None) -> None:
        """Start the interactive inspector: devices, describe, read, invoke with prompts, live operations and events."""
        async def go() -> None:
            with contextlib.suppress(asyncio.CancelledError):
                await Inspector(target, token=token).run()
        run(go())
