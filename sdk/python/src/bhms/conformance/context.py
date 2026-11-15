"""The :class:`Context` every check receives: a main connection, helpers that speak raw BHMS, and the device lookups.

Nothing here imports a server: everything is plain JSON over a :class:`~bhms.conformance.wire.Wire`. The conformance
device's documented extension (``x-conformance/inject``) is used only for fault injection; counters are read through the
device's own ``counter`` property so that the same check also runs behind a gateway.

Thread-safety: one event loop; a context belongs to one run.
"""

from __future__ import annotations

import asyncio
import contextlib
import random
import time
from collections.abc import AsyncIterator
from typing import Any

from bhms.conformance.core import CheckFailed, NotApplicable, Skipped
from bhms.conformance.targets import Target
from bhms.conformance.wire import _UNSET, Recorder, Response, Wire
from bhms.protocol.canonical import digest as jcs_digest

SETTLED = frozenset({"completed", "failed", "canceled", "rejected", "unknown"})
TERMINAL = frozenset({"completed", "failed", "canceled", "rejected"})
CONFORMANCE_EXTENSION = "org.bhms/conformance"


class Context:
    """State shared by the checks of one run."""

    def __init__(self, target: Target, recorder: Recorder, wire: Wire, discover: dict[str, Any], *, strict: bool = False,
                 allow_effects: bool = False, seed: int = 0, device_target: Target | None = None,
                 asserted: tuple[str, ...] = (), fault_wires: dict[str, Wire] | None = None, physical: bool = False,
                 physical_ok: bool = False) -> None:
        self.target, self.recorder, self.wire = target, recorder, wire
        self.asserted = tuple(asserted) or tuple(target.conformance_devices)
        self.fault_wires = dict(fault_wires or {})
        """namespace ('' for a direct server) -> a connection to the conformance device that owns it (fault channel)."""
        self.physical, self.physical_ok = physical, physical_ok
        self.discover_result = discover
        self.strict, self.allow_effects, self.seed = strict, allow_effects, seed
        self.rand = random.Random(seed)
        self.device_target = device_target
        self._counter = 0
        self._summaries: list[dict[str, Any]] | None = None
        self._descriptions: dict[str, dict[str, Any]] = {}
        self.extra_wires: list[Wire] = []
        self.restarts = 0
        self.agent: Any = None
        self.function_tools: list[dict[str, Any]] | None = None
        self.warnings: list[str] = []
        self.axis_id: str | None = None
        self.pump_id: str | None = None
        self.axis_ids: list[str] = []
        self.pump_ids: list[str] = []

    # ------------------------------------------------------------------ facts

    @property
    def caps(self) -> dict[str, Any]:
        return self.discover_result.get("capabilities", {})

    @property
    def limits(self) -> dict[str, Any]:
        return self.discover_result.get("limits", {})

    @property
    def declares_extension(self) -> bool:
        """The server itself declares the conformance extension (capabilities.extensions)."""
        return CONFORMANCE_EXTENSION in (self.caps.get("extensions") or {})

    @property
    def conformance_declared(self) -> bool:
        """The target is a conformance device by declaration: the extension, an explicit assertion of device ids, or the
        runner's own ``compact-gateway`` fixture (its endpoints are the reference C endpoints the runner built and drives
        over fault-injecting links, so the compact profile is claimable from it; Task 14 learning 11)."""
        return self.declares_extension or bool(self.asserted) or getattr(self.target, "compact", None) is not None

    @property
    def effects_allowed(self) -> bool:
        """Effectful checks may run: the target declares itself a conformance device, or ``--allow-effects`` was given; on a
        physical target ``--physical-ok`` is also required."""
        permitted = self.conformance_declared or self.allow_effects
        return permitted and (not self.physical or self.physical_ok)

    @property
    def has_extension(self) -> bool:
        """A fault-injection channel exists (the server's own extension or a direct connection to an upstream)."""
        return self.declares_extension or bool(self.fault_wires)

    @property
    def has_principals(self) -> bool:
        return bool(self.target.tokens)

    @property
    def is_conformance_device(self) -> bool:
        return self.axis_id is not None and self.pump_id is not None

    @property
    def is_gateway(self) -> bool:
        return self.target.is_gateway or "gateway" in self.caps

    def unique(self, prefix: str = "k") -> str:
        """A key that no earlier request of this run (or earlier run) used."""
        self._counter += 1
        return f"{prefix}-{self.seed:x}-{int(time.time() * 1000):x}-{self._counter}"

    # ------------------------------------------------------------------ assertions

    def warn(self, message: str) -> None:
        """Record a SHOULD-level finding of the running check (reported with the result; the check still passes)."""
        self.warnings.append(message)

    def fail(self, message: str, ids: tuple[str, ...] = ()) -> None:
        raise CheckFailed(message, ids)

    def expect(self, condition: Any, message: str, ids: tuple[str, ...] = ()) -> None:
        """Assert; ``ids`` names the requirement(s) of the running check that this assertion proves."""
        if not condition:
            raise CheckFailed(message, ids)

    def skip(self, reason: str) -> None:
        raise Skipped(reason)

    def not_applicable(self, reason: str) -> None:
        raise NotApplicable(reason)

    def result(self, response: Response, what: str = "", ids: tuple[str, ...] = ()) -> dict[str, Any]:
        """The result of a response that must be a success (``ids``: the requirements a failure is about)."""
        if response.result is None:
            raise CheckFailed(f"{what or response.request.get('method', 'request')} should succeed but got: {response.describe()}", ids)
        return response.result

    def refused(self, response: Response, code: str, *, field: str | None = None, may_have_acted: bool | None = False,
                what: str = "", ids: tuple[str, ...] = ()) -> dict[str, Any]:
        """Assert that ``response`` is the BHMS error ``code`` (naming ``field`` when given) and return its ``data``."""
        label = what or response.request.get("method", "request")
        if response.error is None or response.code != code:
            raise CheckFailed(f"{label} should be refused with {code} but got: {response.describe()}", ids)
        if field is not None and response.data.get("field") != field:
            raise CheckFailed(f"{label}: {code} should name field {field!r}, named {response.data.get('field')!r}", ids)
        if may_have_acted is not None and response.data.get("mayHaveActed") is not may_have_acted:
            raise CheckFailed(f"{label}: {code} should carry mayHaveActed {may_have_acted}, carries {response.data.get('mayHaveActed')!r}", ids)
        return response.data

    # ------------------------------------------------------------------ requests

    async def call(self, method: str, params: dict[str, Any] | None = None, *, wire: Wire | None = None, meta: Any = _UNSET,
                   timeout: float = 30.0) -> Response:
        return await (wire or self.wire).request(method, params, meta=meta, timeout=timeout)

    async def ok(self, method: str, params: dict[str, Any] | None = None, **kw: Any) -> dict[str, Any]:
        return self.result(await self.call(method, params, **kw), method)

    @contextlib.asynccontextmanager
    async def fresh_wire(self, role: str | None = None) -> AsyncIterator[Wire]:
        """A new connection (a new server process for stdio targets); ``role`` selects a principal of a gateway fixture."""
        wire = Wire(await self.target.connect_extra(role), self.recorder, f"extra{len(self.extra_wires) + 1}").start()
        self.extra_wires.append(wire)
        try:
            yield wire
        finally:
            await wire.close()

    async def reconnect_base(self, transport: Any) -> None:
        old = self.wire
        self.wire = Wire(transport, self.recorder, f"main{self.restarts + 1}").start()
        self.restarts += 1
        with contextlib.suppress(Exception):
            await old.close()
        self._summaries = None
        self._descriptions.clear()
        self.discover_result = await self.ok("server/discover")

    # ------------------------------------------------------------------ devices

    async def devices(self, *, refresh: bool = False) -> list[dict[str, Any]]:
        if self._summaries is None or refresh:
            out: list[dict[str, Any]] = []
            cursor = None
            while True:
                params: dict[str, Any] = {"limit": 100}
                if cursor:
                    params["cursor"] = cursor
                page = await self.ok("devices/list", params)
                out.extend(page.get("devices", []))
                cursor = page.get("nextCursor")
                if not cursor or len(out) > 100_000:
                    break
            self._summaries = out
        return self._summaries

    async def describe(self, device_id: str) -> dict[str, Any]:
        if device_id not in self._descriptions:
            result = await self.ok("devices/describe", {"deviceId": device_id})
            self._descriptions[device_id] = result["description"]
        return self._descriptions[device_id]

    async def descriptions(self) -> dict[str, dict[str, Any]]:
        return {d["deviceId"]: await self.describe(d["deviceId"]) for d in await self.devices()}

    async def locate(self) -> None:
        """Find the conformance device's ``axis-1`` and ``pump-1`` (a gateway serves them as ``<ns>/axis-1``). Devices are
        taken for conformance devices only by declaration (the extension's device list, or the ids asserted with
        ``--conformance-device``); with ``--allow-effects`` and no declaration, by name."""
        self.axis_id = self.pump_id = None
        self.axis_ids = []
        self.pump_ids = []
        if not self.effects_allowed:
            return
        extension = (self.caps.get("extensions") or {}).get(CONFORMANCE_EXTENSION) or {}
        names = set(extension.get("devices") or ["axis-1", "pump-1"]) if self.declares_extension else None
        for summary in await self.devices():
            device_id = summary["deviceId"]
            tail = device_id.rsplit("/", 1)[-1]
            if self.declares_extension and tail not in (names or ()):
                continue
            if not self.declares_extension and self.asserted and device_id not in self.asserted:
                continue
            if tail == "axis-1" and "move_to" in summary.get("actions", []):
                self.axis_ids.append(device_id)
            if tail == "pump-1" and "dispense" in summary.get("actions", []):
                self.pump_ids.append(device_id)
        self.axis_id = self.axis_ids[0] if self.axis_ids else None
        self.pump_id = self.pump_ids[0] if self.pump_ids else None

    def axis(self) -> str:
        if not self.axis_id:
            raise NotApplicable("the target has no conformance device axis-1")
        return self.axis_id

    def pump(self) -> str:
        if not self.pump_id:
            raise NotApplicable("the target has no conformance device pump-1")
        return self.pump_id

    # ------------------------------------------------------------------ actions and operations

    async def invoke(self, device: str, action: str, arguments: dict[str, Any] | None = None, *, wire: Wire | None = None,
                     **members: Any) -> Response:
        """``actions/invoke`` (``members`` are camelCase request members: ``operationKey``, ``waitMs``, ``leaseId``...)."""
        params = {"deviceId": device, "action": action, "arguments": arguments or {}, **members}
        return await self.call("actions/invoke", params, wire=wire, timeout=60.0)

    async def invoke_op(self, device: str, action: str, arguments: dict[str, Any] | None = None, **members: Any) -> dict[str, Any]:
        """An invoke that must be admitted; returns the operation."""
        result = self.result(await self.invoke(device, action, arguments, **members), f"actions/invoke {action}")
        return result["operation"]

    async def get_op(self, operation_id: str, *, wire: Wire | None = None) -> dict[str, Any]:
        return (await self.ok("operations/get", {"operationId": operation_id}, wire=wire))["operation"]

    async def settle(self, operation_id: str, timeout: float = 15.0, *, states: frozenset[str] = SETTLED) -> dict[str, Any]:
        """Wait (with ``operations/wait``) until the operation is in ``states``; returns the operation with history."""
        deadline = time.monotonic() + timeout
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                raise CheckFailed(f"operation {operation_id} did not settle within {timeout}s")
            result = await self.ok("operations/wait", {"operationId": operation_id, "timeoutMs": int(min(left, 5) * 1000)})
            if result["operation"]["state"] in states:
                return result["operation"]

    async def run(self, device: str, action: str, arguments: dict[str, Any] | None = None, **members: Any) -> dict[str, Any]:
        """Invoke and wait until settled."""
        op = await self.invoke_op(device, action, arguments, **members)
        return op if op["state"] in SETTLED else await self.settle(op["operationId"])

    async def read(self, device: str, prop: str, **members: Any) -> Response:
        return await self.call("properties/read", {"deviceId": device, "property": prop, **members})

    async def counter(self, device: str | None = None) -> int:
        """The device-side command counter, read through the device's ``counter`` property (a fresh acquisition)."""
        result = await self.ok("properties/read", {"deviceId": device or self.axis(), "property": "counter", "fresh": True})
        return int(result["observation"]["value"])

    async def operations_count(self, **filters: Any) -> int:
        total, cursor = 0, None
        while True:
            params = {**filters, "limit": 100, **({"cursor": cursor} if cursor else {})}
            page = await self.ok("operations/list", params)
            total += len(page["operations"])
            cursor = page.get("nextCursor")
            if not cursor:
                return total

    # ------------------------------------------------------------------ faults (conformance extension)

    def _fault_wire(self, device: str | None) -> Wire:
        if self.declares_extension and not self.fault_wires:
            return self.wire
        namespace = (device or self.axis_id or "").split("/", 1)[0] if "/" in (device or self.axis_id or "") else ""
        wire = self.fault_wires.get(namespace) or self.fault_wires.get("")
        if wire is None:
            raise Skipped("the target has no fault-injection channel (extension org.bhms/conformance not declared and no --upstream "
                          f"connection for {namespace or 'this server'!r})")
        return wire

    async def inject(self, fault: str, device: str | None = None) -> None:
        """Arm or clear a fault in the conformance device that owns ``device`` (default: axis-1): through the server's own
        extension, or, behind a gateway, through the runner's direct connection to that upstream (``--upstream``)."""
        await self.ok("x-conformance/inject", {"fault": fault}, wire=self._fault_wire(device))

    async def counters(self, device: str | None = None) -> dict[str, Any]:
        """The conformance extension's device-side counters (``holds``, ``log`` ...)."""
        return await self.ok("x-conformance/counters", {}, wire=self._fault_wire(device))

    async def reset(self) -> None:
        """Clear faults, cancel running operations and release leases so that the next check starts clean (conformance
        devices only: nothing is sent to a device the runner has not identified as one)."""
        if self.has_extension and (self.axis_id or self.pump_id):
            for wire in (self.fault_wires.values() if self.fault_wires else [self.wire]):
                with contextlib.suppress(Exception):
                    await self.ok("x-conformance/inject", {"fault": "none"}, wire=wire)
                    await self.ok("x-conformance/inject", {"fault": "journal_writable"}, wire=wire)
        if self.axis_id or self.pump_id:
            with contextlib.suppress(Exception):
                await self.call("stop", {"reason": "conformance reset", "deviceIds": [*self.axis_ids, *self.pump_ids]})
                await asyncio.sleep(0.02)

    # ------------------------------------------------------------------ misc

    @staticmethod
    def digest_of(description: dict[str, Any]) -> str:
        body = {k: v for k, v in description.items() if k != "digest"}
        return jcs_digest(body)
