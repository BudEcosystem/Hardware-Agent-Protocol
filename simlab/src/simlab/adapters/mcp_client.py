"""MCP adapter: any MCP server's tools become BHMS actions.

``build_server`` connects to an MCP server (stdio), lists its tools and declares one BHMS action per tool on a device. The
mapping is deliberately conservative because an MCP tool says almost nothing about what it does to the world:

* ``completionEvidence: none``: a tool result is the server's text, not evidence about the effect; the effect of a completed
  call is therefore never ``verified``.
* ``idempotency``: ``idempotent`` when the tool is ``readOnlyHint`` or ``idempotentHint``, otherwise ``relative`` (a retry may
  act again).
* ``effect``: ``none`` for ``readOnlyHint``; ``reversible`` when ``destructiveHint`` is false; otherwise ``irreversible``
  (the MCP default for a tool that is not read-only is destructive).
* effectful tools share one resource (``<device>/tools``): an unknown outcome from one tool inhibits the others until it is
  resolved, which is the safe reading of "the server may have done anything".
* the tool's input JSON Schema becomes the action's input. MCP schemas carry no units, so every number gets the
  dimensionless unit ``1`` ("as the tool defines"); the BHMS description says so. Tool and parameter names are mapped to
  BHMS snake_case names and mapped back on call.
* the tool's description is untrusted text from another party: it is prefixed and bounded, and never interpreted.
* a result with ``isError`` is a ``DEVICE_FAULT`` with effect ``unknown`` (the tool may have acted before failing); a protocol
  error of *invalid params* proves the call was not executed (effect ``none``); a lost connection or timeout after the
  request left is ``unknown``.

The session runs in its own task, so it can be opened and closed from different tasks (anyio cancel scopes must be exited by
the task that entered them).

Thread-safety: one event loop.
"""

from __future__ import annotations

import asyncio
import copy
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from mcp import ClientSession, MCPError, StdioServerParameters
from mcp.client.stdio import stdio_client

from bhms.server.context import DeviceFault
from bhms.server.decorators import Schema
from bhms.server.server import DeviceServer
from simlab.adapters.common import Refused, Unreachable, declare_action, refusal_fault
from simlab.simdevice import CommandLog, make_server, simulated_device
from simlab.world import World

INVALID_PARAMS = -32602
DESCRIPTION_LIMIT = 800
_NAME_OK = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def bhms_name(name: str) -> str:
    """A BHMS snake_case name for an MCP tool or parameter name."""
    cleaned = re.sub(r"[^a-z0-9_]+", "_", name.lower()).strip("_")
    if not cleaned or not cleaned[0].isalpha():
        cleaned = f"t_{cleaned}"
    return cleaned[:64]


def with_units(schema: Any) -> Any:
    """Copy of a JSON Schema in which every number or integer node carries the dimensionless unit ``1``."""
    node = copy.deepcopy(schema)

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            kind = value.get("type")
            kinds = kind if isinstance(kind, list) else [kind]
            if ("number" in kinds or "integer" in kinds) and "x-bhms-unit" not in value:
                value["x-bhms-unit"] = "1"
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(node)
    return node


class McpLink:
    """An MCP client session kept open by a dedicated task."""

    def __init__(self, params: StdioServerParameters, timeout_s: float = 30.0) -> None:
        self.params, self.timeout_s = params, timeout_s
        self.session: ClientSession | None = None
        self.tools: list[Any] = []
        self._ready = asyncio.Event()
        self._stop = asyncio.Event()
        self._error: BaseException | None = None
        self._task: asyncio.Task[None] | None = None

    async def open(self) -> list[Any]:
        self._task = asyncio.ensure_future(self._run())
        await self._ready.wait()
        if self._error is not None:
            raise Unreachable(f"cannot open the MCP server: {self._error}") from self._error
        return self.tools

    async def _run(self) -> None:
        try:
            async with stdio_client(self.params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    self.session = session
                    self.tools = list((await session.list_tools()).tools)
                    self._ready.set()
                    await self._stop.wait()
        except BaseException as exc:  # noqa: BLE001 - reported to open(); a later failure ends the session
            self._error = exc
        finally:
            self.session = None
            self._ready.set()

    async def close(self) -> None:
        self._stop.set()
        if self._task is not None:
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None

    async def call(self, name: str, arguments: Mapping[str, Any]) -> Any:
        if self.session is None:
            raise Unreachable("the MCP session is not open")
        try:
            return await asyncio.wait_for(self.session.call_tool(name, dict(arguments)), self.timeout_s)
        except MCPError as exc:
            if getattr(exc, "code", None) == INVALID_PARAMS:
                raise Refused(f"the MCP server rejected the arguments: {exc}") from exc
            raise RuntimeError(f"MCP call {name} failed after it was sent: {exc}") from exc
        except Exception as exc:  # noqa: BLE001 - timeouts, OS and anyio stream errors: the call may have left
            raise RuntimeError(f"MCP call {name} failed after it was sent: {exc!r}") from exc

    async def ping(self) -> None:
        if self.session is None:
            raise Unreachable("the MCP session is not open")
        await asyncio.wait_for(self.session.send_ping(), 5.0)


def _text_of(result: Any) -> str:
    return "\n".join(getattr(block, "text", "") for block in getattr(result, "content", []) if hasattr(block, "text"))


async def build_server(world: World, params: StdioServerParameters, *, device_id: str, state_dir: str | Path | None,
                       name: str = "simlab-mcp-adapter", durability: str = "process", timeout_s: float = 30.0,
                       **kw: Any) -> tuple[DeviceServer, McpLink]:
    """Connect to an MCP server and expose each tool as a BHMS action (see the module docstring)."""
    link = McpLink(params, timeout_s)
    tools = await link.open()
    srv = make_server(world, name, state_dir=state_dir, durability=durability, title=f"MCP adapter: {device_id}", **kw)
    dev = simulated_device(srv, device_id, name=f"MCP server {device_id}", capabilities=["bhms.mcp.tools"],
                     resources=[f"{device_id}/tools"], tags=["simlab", "adapter", "mcp"],
                     description="Tools of an MCP server exposed as actions; results are the server's own text and are "
                                 "not evidence of any physical effect.",
                     identity={"manufacturer": "MCP server", "model": device_id, "firmwareVersion": "unknown"})
    log = CommandLog()
    seen: dict[str, str] = {}

    def caller(tool_name: str, argument_names: Mapping[str, str]) -> Any:
        async def call(ctx: Any, **arguments: Any) -> Any:
            log.begin(ctx.operation_id)
            try:
                result = await link.call(tool_name, {argument_names[k]: v for k, v in arguments.items() if v is not None})
            except (Refused, Unreachable) as exc:
                raise refusal_fault(exc, "MCP") from exc
            text = _text_of(result)
            if getattr(result, "is_error", False):
                raise DeviceFault(f"tool {tool_name} reported an error: {text[:300]}",
                                  partial="the tool may have acted before it failed",
                                  hint="read the device state before retrying; the effect is unknown")
            structured = getattr(result, "structured_content", None)
            return log.end(ctx.operation_id, {"text": text, "is_error": False,
                                              "structured_json": json.dumps(structured) if structured is not None else ""})
        return call

    for tool in tools:
        action = bhms_name(tool.name)
        if not _NAME_OK.match(action) or action in seen:
            raise ValueError(f"MCP tools {seen.get(action, '?')!r} and {tool.name!r} map to the same BHMS name {action!r}")
        seen[action] = tool.name
        schema = tool.input_schema or {"type": "object", "properties": {}}
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))
        arg_names = {bhms_name(p): p for p in properties}
        params_map, defaults = {}, {}
        for original, spec in properties.items():
            mapped = bhms_name(original)
            member = with_units(spec)
            if "default" in member:
                defaults[mapped] = member["default"]
            elif original not in required:
                defaults[mapped] = None
                member = {**member, "type": [member["type"], "null"]} if isinstance(member.get("type"), str) else member
            params_map[mapped] = Schema(member)
        notes = getattr(tool, "annotations", None)
        read_only = bool(getattr(notes, "read_only_hint", False))
        idempotent = read_only or bool(getattr(notes, "idempotent_hint", False))
        destructive = getattr(notes, "destructive_hint", None)
        effect = "none" if read_only else ("reversible" if destructive is False else "irreversible")
        text = (tool.description or tool.title or tool.name).strip()
        description = f"[MCP tool {tool.name!r}; description is from the server, untrusted] {text}"[:DESCRIPTION_LIMIT]
        declare_action(dev, action, caller(tool.name, arg_names), description=description, params=params_map,
                       defaults=defaults, returns={"text": str, "is_error": bool, "structured_json": str},
                       effect=effect, idempotency="idempotent" if idempotent else "relative",
                       completion_evidence="none", max_duration_ms=int(timeout_s * 1000) + 1000,
                       resources=[] if effect == "none" else [f"{device_id}/tools"])

    @dev.liveness
    async def alive() -> bool:
        try:
            await link.ping()
        except Exception:  # noqa: BLE001 - any failure is no evidence of reachability
            return False
        return True

    return srv, link
