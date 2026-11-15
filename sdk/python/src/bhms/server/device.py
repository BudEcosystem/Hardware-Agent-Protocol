"""A device on a :class:`~bhms.server.server.DeviceServer`: decorators, description, digest and summary.

A :class:`Device` collects properties, actions, device events and safety hooks declared with decorators, and builds
its ``DeviceDescription`` (spec/bhms/04-devices.md §4.3) from them: validated against the schema, deep-checked for units
(BHMS-DEV-041), with ``digest = "sha256:" + hex(sha256(JCS(description without digest)))`` (BHMS-DEV-021). The
description is cached and immutable for its digest (BHMS-DEV-020); any later declaration change produces a new digest
and a ``notifications/devices/listChanged`` (BHMS-DEV-023).

Example::

    stage = srv.device("stage-z", capabilities=["bhms.axis.linear"], resources=["stage-z"])

    @stage.property(unit="um", evidence="measured")
    def position() -> float:
        return encoder.read()

    @stage.action(effect="reversible", idempotency="absolute", max_duration_ms=5000, cancel="supported")
    async def move_to(ctx, target: Range(0, 200, unit="um")) -> {"position": "um"}:
        await motor.move(target, cancelled=ctx.cancelled)
        return {"position": await ctx.verify("position", lambda v: abs(v - target) < 0.5)}

    @stage.on_stop(evidence="reported")
    async def halt(ctx):
        await motor.halt()

Hooks: ``on_stop`` (the commissioned stop procedure, BHMS-AUTH-021), ``on_hold`` (``onLeaseLoss: "hold"``,
BHMS-LSE-012), ``reconcile`` (resolve an ``unknown`` operation from device evidence, BHMS-OPS-005) and ``liveness``
(reachability evidence for ``status``, BHMS-DEV-012).

Thread-safety: declare everything before serving; runtime methods (:meth:`publish`, :meth:`emit`) run on the server's
event loop.
"""

from __future__ import annotations

import builtins
import re
import sys
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from bhms.protocol import schema as schema_module
from bhms.protocol.canonical import canonical, digest
from bhms.protocol.errors import BhmsError
from bhms.server.decorators import (ActionSpec, DescriptionError, PropertySpec, build_action, build_property,
                                    schema_for)
from bhms.server.validation import ArgumentValidator, check_units

if TYPE_CHECKING:
    from bhms.server.server import DeviceServer

DEVICE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
CORE_EVENT_TYPES = frozenset({"device.online", "device.offline", "device.degraded", "device.replaced",
                              "device.epoch", "device.fault", "operation.state", "operation.resolved", "stop", "lease.revoked",
                              "lease.expired", "policy.changed"})
SUMMARY_SOFT_LIMIT = 1600  # BHMS-DEV-011 SHOULD (about 400 tokens)
SUMMARY_HARD_LIMIT = 4096  # BHMS-DEV-011 MUST


MAX_STOP_DURATION_MS = 86_400_000  # safety.stopMaxDurationMs is at most one day (§4.7), as a program's maxDurationMs


class StopSpec:
    """The commissioned stop procedure: ``handler(ctx)``; returning normally means the procedure finished."""

    def __init__(self, handler: Callable[..., Any], evidence: str, max_duration_ms: int | None) -> None:
        if evidence not in ("measured", "reported"):
            raise DescriptionError("on_stop evidence must be 'measured' or 'reported' (a stop without evidence is "
                                   "never confirmed, BHMS-AUTH-022)")
        if max_duration_ms is not None and (type(max_duration_ms) is not int
                                            or not 0 <= max_duration_ms <= MAX_STOP_DURATION_MS):
            raise DescriptionError(f"on_stop max_duration_ms must be an integer from 0 to {MAX_STOP_DURATION_MS} "
                                   f"(one day; safety.stopMaxDurationMs, §4.7), got {max_duration_ms!r}")
        self.handler, self.evidence, self.max_duration_ms = handler, evidence, max_duration_ms


class Device:
    """One device: declarations, description and runtime helpers. Create with :meth:`DeviceServer.device`
    (``Device(None, ...)`` builds a standalone device for description generation only)."""

    def __init__(self, server: DeviceServer | None, device_id: str, *, name: str | None = None, description: str = "",
                 summary: str | None = None, capabilities: list[str] | tuple[str, ...] = (),
                 tags: list[str] | tuple[str, ...] = (), resources: list[str] | tuple[str, ...] = (),
                 identity: dict[str, str] | None = None, on_disconnect: str = "unknown",
                 safety_summary: str | None = None, liveness_s: float = 60.0,
                 extensions: dict[str, Any] | None = None) -> None:
        if not DEVICE_ID.match(device_id):
            raise DescriptionError(f"device id {device_id!r} must match {DEVICE_ID.pattern} (BHMS §4.1)")
        if on_disconnect not in ("continue", "hold", "stop", "unknown"):
            raise DescriptionError("on_disconnect must be continue, hold, stop or unknown")
        self.server = server
        self.device_id = device_id
        self.name = name or device_id
        self.text = description
        self.summary_text = summary
        self.capabilities = tuple(capabilities)
        self.tags = tuple(tags)
        self.resources = tuple(resources)
        self.identity = identity
        self.on_disconnect = on_disconnect
        self.safety_summary = safety_summary
        self.liveness_s = liveness_s
        self.bound_allowance_ms = 0
        """Added to each action's ``maxDurationMs`` when the server bounds an operation: a bridge whose link adds latency
        (a BHMS-Compact link, BHMS-CMP-052) sets it; the description is unchanged."""
        self.extensions = extensions
        self.properties: dict[str, PropertySpec] = {}
        self.actions: dict[str, ActionSpec] = {}
        self.events: dict[str, dict[str, Any]] = {}
        self.stop_spec: StopSpec | None = None
        self.hold_handler: Callable[..., Any] | None = None
        self.reconcile_handler: Callable[..., Any] | None = None
        self.liveness_handler: Callable[..., Any] | None = None
        self._description: dict[str, Any] | None = None
        self._fixed: dict[str, Any] | None = None
        self._validators: dict[str, ArgumentValidator] = {}
        self._output_validators: dict[str, Any] = {}
        self._event_validators: dict[str, Any] = {}
        self._alive_at: float | None = None
        self._forced_status: str | None = None
        self._probe_failed = False
        self.liveness_interval_s: float | None = None
        self.liveness_timeout_s: float = 5.0

    # ------------------------------------------------------------------ declarations

    def property(self, fn: Callable[..., Any] | None = None, **options: Any) -> Any:
        """Declare a property. Use as ``@device.property(unit="mm", evidence="measured")`` on a getter, or call
        ``device.property(name="temperature", schema=Range(...), evidence="measured")`` for a push-only property whose
        values the device publishes with :meth:`publish`.

        Options: ``unit``, ``evidence`` (default ``reported``), ``observable`` (default True), ``read_effect``
        (``none``/``transaction``), ``max_rate_hz``, ``requires_lease``, ``resources``, ``validity_ms`` (age after
        which a retained value is ``stale``), ``timeout_ms`` (acquisition bound; default 1000), ``schema``,
        ``description``, ``name``, ``blocking`` (run a sync getter in a worker thread).

        The getter takes no argument, or receives this device through a parameter named ``device`` (or annotated
        ``Device``); any other parameter must have a default and keeps it (closures such as ``register=register``). The
        choice is by declaration, never by the number of parameters; an ambiguous signature is a ``DescriptionError``.
        """
        if fn is None and ("schema" in options and "name" in options):
            spec = build_property(None, **options)
            self._add_property(spec)
            return spec

        localns = sys._getframe(1).f_locals  # where the decorator is applied: resolves local annotation names

        def decorate(getter: Callable[..., Any]) -> Callable[..., Any]:
            self._add_property(build_property(getter, localns=localns, **options))
            return getter

        return decorate(fn) if fn is not None else decorate

    def _add_property(self, spec: PropertySpec) -> None:
        if not NAME.match(spec.name):
            raise DescriptionError(f"property name {spec.name!r} must be snake_case ({NAME.pattern})")
        unknown = [r for r in spec.resources if r not in self.resources]
        if unknown:
            raise DescriptionError(f"property {spec.name!r}: resources {unknown} are not declared by the device")
        self.properties[spec.name] = spec
        self.invalidate()

    def action(self, fn: Callable[..., Any] | None = None, **options: Any) -> Any:
        """Declare an action from a handler ``async def name(ctx, arg: Annotation = default, ...) -> output``.

        Options: ``effect`` and ``idempotency`` (required), ``max_duration_ms`` (required unless ``effect="none"``),
        ``requires_lease``, ``completion_evidence`` (default ``reported``), ``cancel`` (default ``unsupported``; declare
        ``supported`` only when the handler honours ``ctx.cancelled``), ``resources`` (default: the device's resources
        for effectful actions), ``on_lease_loss``, ``requires_fresh`` (``{"pressure": 1000}``), ``verified_by``,
        ``typical_duration_ms``, ``preconditions``, ``description``, ``name``, ``output``, ``blocking``.
        """
        localns = sys._getframe(1).f_locals  # where the decorator is applied: resolves local annotation names

        def decorate(handler: Callable[..., Any]) -> Callable[..., Any]:
            spec = build_action(handler, device_resources=self.resources, localns=localns, **options)
            if not NAME.match(spec.name):
                raise DescriptionError(f"action name {spec.name!r} must be snake_case ({NAME.pattern})")
            self.actions[spec.name] = spec
            self.invalidate()
            return handler

        return decorate(fn) if fn is not None else decorate

    def remove_action(self, name: str) -> None:
        """Withdraw an action (the description gets a new digest; admitted operations are unaffected)."""
        self.actions.pop(name)
        self.invalidate()

    def event(self, event_type: str, *, data: Any = None, description: str = "") -> None:
        """Declare a device-specific event type (BHMS-EVT-003); ``data`` is a ``{member: unit-or-annotation}`` map
        or a :class:`~bhms.server.decorators.SchemaType`."""
        if event_type in CORE_EVENT_TYPES:
            raise DescriptionError(f"event type {event_type!r} is a core type; device events must not reuse it")
        if not re.match(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)*$", event_type) or len(event_type) > 64:
            raise DescriptionError(f"event type {event_type!r} must be dotted snake_case of at most 64 characters")
        entry: dict[str, Any] = {"description": description}
        if data is not None:
            entry["data"] = schema_for(data, where=f"event {event_type!r} data")
        self.events[event_type] = entry
        self.invalidate()

    def on_stop(self, fn: Callable[..., Any] | None = None, *, evidence: str = "reported",
                max_duration_ms: int | None = None) -> Any:
        """Register the commissioned stop procedure (``safety.stop: "supported"``)."""
        def decorate(handler: Callable[..., Any]) -> Callable[..., Any]:
            self.stop_spec = StopSpec(handler, evidence, max_duration_ms)
            self.invalidate()
            return handler

        return decorate(fn) if fn is not None else decorate

    def on_hold(self, fn: Callable[..., Any]) -> Callable[..., Any]:
        """Register the hold command used by ``onLeaseLoss: "hold"`` (BHMS-LSE-012): ``async def hold(ctx)``."""
        self.hold_handler = fn
        return fn

    def reconcile(self, fn: Callable[..., Any]) -> Callable[..., Any]:
        """Register ``async def reconcile(op) -> Reconciled | None`` to resolve ``unknown`` operations from device
        evidence (BHMS-OPS-005).

        The server calls it for each of the device's ``unknown`` operations: after a restart, whenever the device
        **returns** (its status becomes ``online`` after ``offline``, ``degraded`` or ``unknown``: once per return),
        on ``operations/resolve`` and on :meth:`DeviceServer.reconcile`. Each call is bounded by the server's
        ``reconcile_timeout_s``. Return None (or raise) when the device cannot say what happened: the operation then
        stays ``unknown``; success is never assumed."""
        self.reconcile_handler = fn
        return fn

    def liveness(self, fn: Callable[..., Any] | None = None, *, interval_s: float | None = None,
                 timeout_s: float = 5.0) -> Any:
        """Register the liveness probe ``def alive() -> bool`` (sync or async): ``@device.liveness`` or
        ``@device.liveness(interval_s=5)``.

        A true result is reachability evidence (BHMS-DEV-012). A false result, an exception or no answer within
        ``timeout_s`` is evidence that the device is unreachable: its status becomes ``offline`` until a later probe (or
        any other evidence of life: a successful acquisition, a completed action) succeeds.

        The probe runs once when the server starts. With ``interval_s`` (or the server's ``liveness_interval_s`` default;
        both off unless set) it also runs every ``interval_s`` seconds, so a bridge whose instrument died stops
        reporting its last status. A device declared after the server started begins probing with
        :meth:`DeviceServer.start_liveness`.
        """
        if interval_s is not None and interval_s <= 0:
            raise ValueError("liveness interval_s must be positive (omit it to leave periodic probing off)")
        if timeout_s <= 0:
            raise ValueError("liveness timeout_s must be positive")

        def register(probe: Callable[..., Any]) -> Callable[..., Any]:
            self.liveness_handler = probe
            self.liveness_interval_s, self.liveness_timeout_s = interval_s, timeout_s
            return probe

        return register if fn is None else register(fn)

    # ------------------------------------------------------------------ description

    def invalidate(self) -> None:
        """Drop the cached description (the next one gets a new digest) and tell subscribers (BHMS-DEV-023)."""
        had = self._description is not None
        self._description = None
        self._validators.clear()
        self._output_validators.clear()
        self._event_validators.clear()
        if had and self.server is not None:
            self.server._device_changed(self)

    def _safety(self) -> dict[str, Any]:
        if self.stop_spec is not None:
            out: dict[str, Any] = {"stop": "supported", "stopEvidence": self.stop_spec.evidence}
            if self.stop_spec.max_duration_ms is not None:
                out["stopMaxDurationMs"] = self.stop_spec.max_duration_ms
        else:
            out = {"stop": "unsupported", "stopEvidence": "none"}
        out["onDisconnect"] = self.on_disconnect
        out["summary"] = self.safety_summary or (
            "stop runs the device's commissioned stop procedure, cancels its operations and revokes its leases"
            if self.stop_spec is not None else
            "no commissioned stop procedure; stop only cancels operations and revokes leases")
        return out

    @classmethod
    def from_description(cls, server: DeviceServer | None, description: dict[str, Any], *,
                         run: Callable[[str], Callable[..., Any]], read: Callable[[str], Callable[..., Any]],
                         hold: Callable[..., Any] | None = None, stop: Callable[..., Any] | None = None,
                         read_timeout_ms: int = 2000) -> Device:
        """A device whose ``DeviceDescription`` is given, not derived from decorated handlers (a bridge that serves a
        device it did not write, such as a BHMS-Compact endpoint described by a sidecar file).

        The description is served as given with its digest recomputed (BHMS-DEV-021) after the schema and unit checks;
        ``run(action)`` returns that action's handler ``async def (ctx, **arguments)``, ``read(property)`` the getter of a
        property, ``stop`` the commissioned stop procedure (required exactly when ``safety.stop`` is ``supported``) and
        ``hold`` the ``onLeaseLoss: hold`` command. ``read_timeout_ms`` bounds one acquisition.
        """
        from bhms.server.decorators import ActionSpec, PropertySpec

        body = {k: v for k, v in description.items() if k != "digest"}
        for member in ("deviceId", "actions", "properties", "safety", "resources", "capabilities"):
            if member not in body:
                raise DescriptionError(f"the description has no {member!r} member")
        safety = body["safety"]
        dev = cls(server, body["deviceId"], name=body.get("name"), description=body.get("description", ""),
                  capabilities=body["capabilities"], tags=body.get("tags", ()), resources=body["resources"],
                  identity=body.get("identity"), on_disconnect=safety.get("onDisconnect", "unknown"),
                  safety_summary=safety.get("summary"), extensions=body.get("extensions"))
        for name, a in body["actions"].items():
            dev.actions[name] = ActionSpec(
                name, run(name), a["input"], a.get("output"), a["effect"], a["idempotency"], a["cancel"],
                a["completionEvidence"], a["maxDurationMs"], a["requiresLease"], tuple(a["resources"]),
                a.get("description", ""), tuple(a["input"].get("properties") or {}), "ctx",
                tuple(a.get("verifiedBy", ())), a.get("typicalDurationMs"), a.get("onLeaseLoss"),
                tuple((f["property"], f["maxAgeMs"]) for f in a.get("requiresFresh", ())), a.get("preconditions"))
        for name, p in body["properties"].items():
            dev.properties[name] = PropertySpec(
                name, read(name), p["schema"], p["evidence"], p["observable"], p["readEffect"], p.get("description", ""),
                p.get("maxRateHz"), p.get("requiresLease", False), tuple(p.get("resources", ())), None, read_timeout_ms)
        dev.hold_handler = hold
        if (safety.get("stop") == "supported") != (stop is not None):
            raise DescriptionError(f"device {dev.device_id!r}: safety.stop is {safety.get('stop')!r} but "
                                   f"{'no' if stop is None else 'a'} stop procedure was given")
        if stop is not None:
            dev.stop_spec = StopSpec(stop, safety.get("stopEvidence", "reported"), safety.get("stopMaxDurationMs"))
        dev._check(body)
        body["digest"] = digest(body)
        try:
            schema_module.validate("DeviceDescription", body)
        except BhmsError as exc:
            raise DescriptionError(f"device {dev.device_id!r}: the description is invalid at "
                                   f"{exc.field or '/'}: {exc.message}") from None
        if len(canonical(dev.summary("unknown", body))) > SUMMARY_HARD_LIMIT:
            raise DescriptionError(f"device {dev.device_id!r}: its summary exceeds {SUMMARY_HARD_LIMIT} bytes "
                                   "(BHMS-DEV-011)")
        dev._fixed = body
        return dev

    def description(self) -> dict[str, Any]:
        """The current ``DeviceDescription`` (cached; raises :class:`DescriptionError` if declarations are invalid)."""
        if self._fixed is not None:
            return self._fixed
        if self._description is not None:
            return self._description
        body: dict[str, Any] = {
            "deviceId": self.device_id, "name": self.name, "description": self.text,
            "capabilities": list(self.capabilities), "tags": list(self.tags), "resources": list(self.resources),
            "properties": {n: p.describe() for n, p in sorted(self.properties.items())},
            "actions": {n: a.describe() for n, a in sorted(self.actions.items())},
            "safety": self._safety()}
        if self.identity:
            body["identity"] = dict(self.identity)
        if self.events:
            body["events"] = dict(sorted(self.events.items()))
        if self.extensions:
            body["extensions"] = self.extensions
        self._check(body)
        body["digest"] = digest(body)
        try:
            schema_module.validate("DeviceDescription", body)
        except BhmsError as exc:
            raise DescriptionError(f"device {self.device_id!r}: the generated description is invalid at "
                                   f"{exc.field or '/'}: {exc.message}") from None
        size = len(canonical(self.summary("unknown", body)))
        if size > SUMMARY_HARD_LIMIT:
            raise DescriptionError(f"device {self.device_id!r}: summary is {size} bytes; the limit is "
                                   f"{SUMMARY_HARD_LIMIT} (BHMS-DEV-011); shorten name, summary or tags")
        self._description = body
        return body

    def _check(self, body: dict[str, Any]) -> None:
        where = f"device {self.device_id!r}"
        for name, prop in body["properties"].items():
            _units(prop["schema"], f"{where} property {name}")
        for name, action in body["actions"].items():
            _units(action["input"], f"{where} action {name} input")
            if "output" in action:
                _units(action["output"], f"{where} action {name} output")
            for prop in action.get("verifiedBy", []):
                if prop not in body["properties"]:
                    raise DescriptionError(f"{where} action {name}: verified_by names unknown property {prop!r}")
            for index, fresh in enumerate(action.get("requiresFresh", [])):
                if fresh["property"] not in body["properties"]:
                    raise DescriptionError(f"{where} action {name}: requires_fresh[{index}] names unknown property "
                                           f"{fresh['property']!r} (BHMS-DEV-034)")
            if action.get("onLeaseLoss") == "hold" and self.hold_handler is None:
                raise DescriptionError(f"{where} action {name}: on_lease_loss='hold' needs a @device.on_hold handler")
        for event_type, entry in body.get("events", {}).items():
            if "data" in entry:
                _units(entry["data"], f"{where} event {event_type} data")

    @builtins.property  # the class defines a property() decorator method
    def digest(self) -> str:
        return self.description()["digest"]

    def summary(self, status: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        """The ``DeviceSummary`` for ``devices/list`` (BHMS-DEV-011)."""
        desc = body if body is not None else self.description()
        text = self.summary_text if self.summary_text is not None else _first_sentences(desc["description"])
        return {"deviceId": self.device_id, "name": self.name, "summary": text[:280],
                "capabilities": list(self.capabilities), "tags": list(self.tags), "status": status,
                "digest": desc.get("digest", "sha256:" + "0" * 64), "actions": sorted(desc["actions"]),
                "properties": sorted(desc["properties"])}

    # ------------------------------------------------------------------ validators

    def validator(self, action: str) -> ArgumentValidator:
        """The cached argument validator of ``action``."""
        found = self._validators.get(action)
        if found is None:
            found = self._validators[action] = ArgumentValidator(self.actions[action].input)
        return found

    def output_validator(self, action: str) -> Any:
        found = self._output_validators.get(action)
        if found is None:
            output = self.actions[action].output
            found = self._output_validators[action] = schema_module.compile_schema(output if output is not None
                                                                                   else True)
        return found

    def event_validator(self, event_type: str) -> Any:
        found = self._event_validators.get(event_type)
        if found is None:
            data = self.events[event_type].get("data", True)
            found = self._event_validators[event_type] = schema_module.compile_schema(data)
        return found

    # ------------------------------------------------------------------ status

    def report_alive(self) -> None:
        """Record reachability evidence now (BHMS-DEV-012); the server also does this on every successful acquisition
        and every completed action. Evidence of life ends an ``offline`` that a failed liveness probe caused (a status
        forced with :meth:`set_status` stays until it is cleared)."""
        previous = self.status
        self._alive_at = time.monotonic()
        self._probe_failed = False
        self._changed_from(previous)

    def report_unreachable(self) -> None:
        """Record evidence that the device does not answer (a failed liveness probe): its status is ``offline`` until
        :meth:`report_alive` is called again."""
        previous = self.status
        self._probe_failed = True
        self._changed_from(previous)

    def set_status(self, status: str | None) -> None:
        """Force ``offline`` or ``degraded`` (``None`` returns to evidence-based ``online``/``offline``/``unknown``)."""
        if status not in (None, "offline", "degraded"):
            raise ValueError("set_status takes 'offline', 'degraded' or None")
        previous = self.status
        self._forced_status = status
        self._changed_from(previous)

    def _changed_from(self, previous: str) -> None:
        if self.status != previous and self.server is not None:
            self.server._status_changed(self, previous)

    @builtins.property  # the class defines a property() decorator method
    def status(self) -> str:
        """``offline``/``degraded`` when forced; ``offline`` after a failed liveness probe; ``online`` with evidence
        within ``liveness_s``; else ``unknown``."""
        if self._forced_status is not None:
            return self._forced_status
        if self._probe_failed:
            return "offline"
        if self._alive_at is not None and time.monotonic() - self._alive_at <= self.liveness_s:
            return "online"
        return "unknown"

    # ------------------------------------------------------------------ runtime helpers

    async def publish(self, property: str, value: Any, *, quality: str = "valid", uncertainty: float | None = None,
                      source: str | None = None, latency_ms: float = 0.0) -> dict[str, Any]:
        """Record a new acquisition the device pushed (for subscriptions and later reads) and return its
        ``Observation``. ``latency_ms`` is the bounded acquisition latency added to the age (BHMS-OBS-003)."""
        return await self.server.observations.publish(self, property, value, quality=quality,
                                                      uncertainty=uncertainty, source=source,
                                                      latency_ms=latency_ms)

    def emit(self, event_type: str, data: dict[str, Any] | None = None, *, severity: str = "info",
             message: str | None = None, operation_id: str | None = None) -> dict[str, Any]:
        """Append a device event (declared types only, data validated, BHMS-EVT-003); ``device.fault`` is allowed
        too. Returns the recorded ``Event``."""
        if event_type != "device.fault":
            if event_type not in self.events:
                raise DescriptionError(f"event type {event_type!r} is not declared on {self.device_id!r}; declare it "
                                       "with device.event(...) first (BHMS-EVT-003)")
            errors = list(self.event_validator(event_type).iter_errors(data if data is not None else {}))
            if errors:
                raise ValueError(f"event {event_type!r} data does not match its declared schema: "
                                 f"{errors[0].message}")
        return self.server.events.append(event_type, severity=severity, device_id=self.device_id,
                                         operation_id=operation_id, message=message, data=data)


def _units(schema: Any, where: str) -> None:
    try:
        check_units(schema, where)
    except ValueError as exc:
        raise DescriptionError(str(exc)) from None


def _first_sentences(text: str) -> str:
    text = " ".join(text.split())
    if len(text) <= 280:
        return text
    cut = text[:280]
    stop = cut.rfind(". ")
    return cut[:stop + 1] if stop > 40 else cut[:277] + "..."


__all__ = ["Device", "StopSpec"]
