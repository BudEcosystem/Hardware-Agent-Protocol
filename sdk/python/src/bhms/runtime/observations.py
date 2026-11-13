"""Observations: acquisition, retention, freshness and rate-limited subscriptions (spec/bhms/05-observations.md).

:class:`ObservationHub` owns one retained sample per ``(deviceId, property)`` and turns samples into ``Observation``
objects at response time:

* a getter that raises, times out or returns ``None`` (or a value that fails the property schema) yields
  ``quality: "invalid"`` and ``value: null`` — never zero, a default or the previous sample (BHMS-OBS-001);
* ``ageMs`` is computed on the monotonic clock from the *start* of the acquisition plus the declared bounded latency,
  so it never under-states the age and wall-clock steps cannot shrink it; an unbounded latency gives
  ``acquiredAt``/``ageMs`` ``null`` and fails every ``maxAgeMs`` (BHMS-OBS-003); re-reading never refreshes it;
* ``sequence`` increases by one per acquisition; ``epoch`` is minted per process because sequences restart with it
  (BHMS-OBS-004); numeric values carry ``unit`` (BHMS-OBS-005);
* ``properties/read`` honours ``maxAgeMs`` and ``fresh`` or answers ``STALE`` naming the parameter (BHMS-OBS-010); a
  fresh acquisition of a ``transaction`` property needs an ``invoke`` scope on ``<deviceId>/<property>`` and, when the
  property requires one, a lease (BHMS-OBS-011, BHMS-AUTH-012); an unknown property is ``INVALID_ARGUMENT`` listing
  the property names (BHMS-OBS-012);
* :meth:`ObservationHub.require_fresh` enforces an action's ``requiresFresh`` (BHMS-OBS-030);
* subscriptions are delivered at most once per ``max(minIntervalMs, capabilities.observations.minIntervalMs)`` per
  subscriber, with the latest sample sent when the floor ends, except that a change of ``quality`` is delivered at once
  (BHMS-OBS-021, BHMS-LIF-043). While a property with a getter and ``readEffect: "none"`` has subscribers it is polled
  at that rate; ``transaction`` properties are never polled (BHMS-OBS-022). Values over 64 KiB are never sent
  (BHMS-EVT-030).

Thread-safety: one event loop.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import math
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from bhms.protocol import schema as schema_module
from bhms.protocol.canonical import canonical
from bhms.protocol.errors import BhmsError
from bhms.runtime.operations import iso, now_ns
from bhms.server.context import Reading
from bhms.server.decorators import PropertySpec

if TYPE_CHECKING:
    from bhms.runtime.authority import Principal
    from bhms.server.device import Device
    from bhms.server.server import DeviceServer

log = logging.getLogger("bhms.observations")
MAX_NOTIFICATION_BYTES = 64 * 1024


@dataclass
class Sample:
    """One acquisition as retained by the server."""

    value: Any
    quality: str
    evidence: str
    started_mono: float | None  # monotonic start of the acquisition (None: unbounded latency)
    acquired_ns: int | None
    received_ns: int
    latency_ms: float
    sequence: int
    uncertainty: float | None = None
    source: str | None = None


@dataclass
class _Subscriber:
    deliver: Callable[[dict[str, Any]], None]
    floor_s: float
    last_mono: float = -math.inf
    last_quality: str | None = None
    pending: asyncio.TimerHandle | None = None


@dataclass
class _PropertyState:
    sample: Sample | None = None
    sequence: int = 0
    subscribers: list[_Subscriber] = field(default_factory=list)
    poller: asyncio.Task[None] | None = None


class ObservationHub:
    """Retained observations and their subscribers for one server; see the module docstring."""

    def __init__(self, server: DeviceServer, *, min_interval_ms: int = 50) -> None:
        self.server = server
        self.min_interval_ms = min_interval_ms
        self.epoch = f"{server.store.epoch}:{secrets.token_hex(4)}"
        self._state: dict[tuple[str, str], _PropertyState] = {}
        self._validators: dict[tuple[str, str], Any] = {}

    def _slot(self, device_id: str, prop: str) -> _PropertyState:
        state = self._state.get((device_id, prop))
        if state is None:
            state = self._state[(device_id, prop)] = _PropertyState()
        return state

    # ------------------------------------------------------------------ presentation

    def present(self, spec: PropertySpec, sample: Sample) -> dict[str, Any]:
        """The ``Observation`` of ``sample`` as of now (age and staleness are computed at response time)."""
        if sample.started_mono is None:
            age = None
        else:
            age = math.ceil((time.monotonic() - sample.started_mono) * 1000 + sample.latency_ms)
        quality = sample.quality
        if quality == "valid" and spec.validity_ms is not None and (age is None or age > spec.validity_ms):
            quality = "stale"
        obs: dict[str, Any] = {"value": sample.value if sample.quality in ("valid", "stale") else None}
        if spec.unit is not None:
            obs["unit"] = spec.unit
        obs.update(evidence=sample.evidence, quality=quality,
                   acquiredAt=iso(sample.acquired_ns) if sample.acquired_ns is not None else None,
                   receivedAt=iso(sample.received_ns), ageMs=age)
        if sample.uncertainty is not None:
            obs["uncertainty"] = sample.uncertainty
        obs.update(sequence=sample.sequence, epoch=self.epoch)
        if sample.source is not None:
            obs["source"] = sample.source[:128]
        return obs

    def _validator(self, device: Device, spec: PropertySpec) -> Any:
        key = (device.device_id, spec.name)
        found = self._validators.get(key)
        if found is None:
            found = self._validators[key] = schema_module.compile_schema(spec.schema)
        return found

    def _record(self, device: Device, spec: PropertySpec, value: Any, quality: str, *, evidence: str | None,
                started_mono: float | None, acquired_ns: int | None, latency_ms: float | None,
                uncertainty: float | None, source: str | None) -> Sample:
        state = self._slot(device.device_id, spec.name)
        if quality in ("valid", "stale"):
            if value is None and not _allows_null(spec.schema):
                quality, value = "invalid", None
            elif not self._validator(device, spec).is_valid(value):
                log.error("%s.%s produced %r, which does not match its schema; reported as invalid",
                          device.device_id, spec.name, value)
                quality, value = "invalid", None
        else:
            value = None
        if latency_ms is None:
            started_mono, acquired_ns, latency_ms = None, None, 0.0
        state.sequence += 1
        sample = Sample(value, quality, evidence or spec.evidence, started_mono, acquired_ns, now_ns(),
                        float(latency_ms), state.sequence, uncertainty, source)
        previous = state.sample
        state.sample = sample
        if quality == "valid":
            device.report_alive()
        self._fan_out(device, spec, state, sample, previous)
        return sample

    # ------------------------------------------------------------------ acquisition

    async def acquire(self, device: Device, spec: PropertySpec) -> Sample:
        """Run the getter once and record the result (any failure is an ``invalid`` sample)."""
        if spec.getter is None:
            raise BhmsError("STALE", f"{device.device_id}.{spec.name} has no getter; its values are published by the "
                            "device", field="fresh", bound=True,
                            hint="read without fresh/maxAgeMs to get the latest published value, or subscribe")
        started = time.monotonic()
        acquired = now_ns()
        try:
            value = await self._call_getter(device, spec)
        except asyncio.TimeoutError:
            log.warning("%s.%s acquisition exceeded %d ms", device.device_id, spec.name, spec.timeout_ms)
            return self._record(device, spec, None, "invalid", evidence=None, started_mono=started,
                                acquired_ns=acquired, latency_ms=0.0, uncertainty=None,
                                source=f"timeout after {spec.timeout_ms} ms")
        except Exception as exc:  # noqa: BLE001 - a failed measurement is reported, never substituted
            log.warning("%s.%s acquisition failed: %s", device.device_id, spec.name, exc)
            return self._record(device, spec, None, "invalid", evidence=None, started_mono=started,
                                acquired_ns=acquired, latency_ms=0.0, uncertainty=None, source=None)
        if isinstance(value, Reading):
            return self._record(device, spec, value.value, value.quality, evidence=value.evidence,
                                started_mono=started, acquired_ns=value.acquired_at_ns or acquired,
                                latency_ms=value.latency_ms, uncertainty=value.uncertainty, source=value.source)
        return self._record(device, spec, value, "valid", evidence=None, started_mono=started, acquired_ns=acquired,
                            latency_ms=0.0, uncertainty=None, source=None)

    async def _call_getter(self, device: Device, spec: PropertySpec) -> Any:
        getter = spec.getter
        assert getter is not None
        args = (device,) if spec.takes_ctx else ()
        timeout = spec.timeout_ms / 1000
        if inspect.iscoroutinefunction(getter):
            return await asyncio.wait_for(getter(*args), timeout)
        if spec.blocking:
            return await asyncio.wait_for(asyncio.to_thread(getter, *args), timeout)
        return getter(*args)

    async def publish(self, device: Device, prop: str, value: Any, *, quality: str = "valid",
                      uncertainty: float | None = None, source: str | None = None,
                      latency_ms: float | None = 0.0, evidence: str | None = None) -> dict[str, Any]:
        """Record a value the device pushed; returns its ``Observation``."""
        spec = self.spec(device, prop)
        if quality not in ("valid", "invalid", "unknown"):
            raise ValueError("publish quality must be valid, invalid or unknown")
        started = time.monotonic() - latency_ms / 1000 if latency_ms is not None else None
        sample = self._record(device, spec, value, quality, evidence=evidence, started_mono=started,
                              acquired_ns=now_ns() - int((latency_ms or 0) * 1e6), latency_ms=None if latency_ms is None
                              else 0.0, uncertainty=uncertainty, source=source)
        return self.present(spec, sample)

    # ------------------------------------------------------------------ reads

    def spec(self, device: Device, prop: str, field: str = "property") -> PropertySpec:
        spec = device.properties.get(prop)
        if spec is None:
            names = ", ".join(sorted(device.properties)) or "none"
            raise BhmsError("INVALID_ARGUMENT", f"{device.device_id} has no property {prop!r}", field=field,
                            hint=f"properties of {device.device_id}: {names}")
        return spec

    def _authorize_acquisition(self, device: Device, spec: PropertySpec, principal: Principal | None,
                               lease_id: str | None) -> None:
        if spec.read_effect != "transaction" or principal is None:
            return
        if not principal.can_invoke(device.device_id, spec.name, device.capabilities):
            raise BhmsError("UNAUTHORIZED", f"a fresh read of {device.device_id}.{spec.name} starts a device "
                            "transaction and needs an invoke scope", field="property",
                            hint=f"ask for scope invoke:{device.device_id}/{spec.name}, or read the retained "
                                 "observation without fresh/maxAgeMs (BHMS-AUTH-012)")
        if spec.requires_lease:
            resources = spec.resources or device.resources
            if lease_id is None:
                held = self.server.leases.held_by(principal.id, resources)
                if held is None:
                    raise BhmsError("LEASE_REQUIRED", f"a fresh read of {device.device_id}.{spec.name} needs a lease "
                                    f"on {', '.join(resources)}", field="property",
                                    hint=f"acquire a lease on {', '.join(resources)} with leases/acquire first, or "
                                         "read the retained observation without fresh/maxAgeMs")
                lease_id = held.lease_id
            self.server.leases.check(principal, lease_id, resources)

    async def read(self, device: Device, prop: str, *, max_age_ms: int | None = None, fresh: bool | None = None,
                   principal: Principal | None = None, lease_id: str | None = None,
                   internal: bool = False) -> dict[str, Any]:
        """``properties/read`` semantics (§5.2); ``internal`` reads run under an operation's own authority."""
        spec = self.spec(device, prop)
        state = self._slot(device.device_id, prop)
        requested = time.monotonic()
        sample = state.sample
        if not fresh and sample is not None:
            if max_age_ms is None:
                return self.present(spec, sample)
            current = self.present(spec, sample)
            if current["ageMs"] is not None and current["ageMs"] <= max_age_ms:
                return current
        if spec.getter is None:
            if sample is None:
                return self._unknown(spec)
            what, bound = ("fresh", True) if fresh else ("maxAgeMs", max_age_ms)
            raise BhmsError("STALE", f"{device.device_id}.{prop} cannot be acquired on demand and its latest value "
                            f"does not satisfy {what}", field=what, bound=bound,
                            hint="this property is published by the device; read it without fresh/maxAgeMs, or "
                                 "subscribe to it")
        if not internal:
            self._authorize_acquisition(device, spec, principal, lease_id)
        sample = await self.acquire(device, spec)
        observation = self.present(spec, sample)
        if fresh and (sample.started_mono is None or sample.started_mono < requested):
            raise BhmsError("STALE", f"{device.device_id}.{prop}: no acquisition started after the request",
                            field="fresh", bound=True, hint="retry; the device did not acquire a new value")
        if max_age_ms is not None and (observation["ageMs"] is None or observation["ageMs"] > max_age_ms):
            raise BhmsError("STALE", f"{device.device_id}.{prop}: the newest observation is "
                            f"{observation['ageMs']} ms old, above maxAgeMs {max_age_ms}", field="maxAgeMs",
                            bound=max_age_ms, hint="ask for a larger maxAgeMs or check the device's acquisition "
                                                   "latency")
        return observation

    def _unknown(self, spec: PropertySpec) -> dict[str, Any]:
        obs: dict[str, Any] = {"value": None}
        if spec.unit is not None:
            obs["unit"] = spec.unit
        obs.update(evidence=spec.evidence, quality="unknown", acquiredAt=None, receivedAt=iso(now_ns()), ageMs=None,
                   sequence=0, epoch=self.epoch)
        return obs

    async def require_fresh(self, device: Device, requirements: tuple[tuple[str, int], ...],
                            principal: Principal | None, lease_id: str | None) -> dict[str, dict[str, Any]]:
        """Hold a ``valid`` observation no older than ``maxAgeMs`` for each requirement, or refuse with ``STALE``
        naming ``requiresFresh[i]`` (BHMS-OBS-030)."""
        held: dict[str, dict[str, Any]] = {}
        for index, (prop, max_age) in enumerate(requirements):
            spec = self.spec(device, prop)
            state = self._slot(device.device_id, prop)
            obs = self.present(spec, state.sample) if state.sample is not None else None
            if not _fresh_enough(obs, max_age) and spec.getter is not None:
                if spec.read_effect != "transaction" or principal is None or \
                        principal.can_invoke(device.device_id, spec.name, device.capabilities):
                    obs = self.present(spec, await self.acquire(device, spec))
            if not _fresh_enough(obs, max_age):
                quality = obs["quality"] if obs else "unknown"
                age = obs["ageMs"] if obs else None
                raise BhmsError("STALE", f"{device.device_id}.{prop} has no valid observation within {max_age} ms",
                                field=f"requiresFresh[{index}]", bound={"property": prop, "maxAgeMs": max_age},
                                hint=f"{prop} is {quality} (age {age} ms); restore the sensor or wait for a valid "
                                     "reading before retrying")
            held[prop] = obs  # type: ignore[assignment]
        return held

    # ------------------------------------------------------------------ subscriptions

    def subscribe(self, device: Device, prop: str, min_interval_ms: int | None,
                  deliver: Callable[[dict[str, Any]], None]) -> Callable[[], None]:
        """Deliver ``{"deviceId", "property", "observation"}`` on new acquisitions; returns the unsubscribe function."""
        spec = self.spec(device, prop)
        state = self._slot(device.device_id, prop)
        floor_ms = max(min_interval_ms or 0, self.min_interval_ms)
        sub = _Subscriber(deliver, floor_ms / 1000)
        state.subscribers.append(sub)
        self._ensure_poller(device, spec, state)

        def unsubscribe() -> None:
            if sub in state.subscribers:
                state.subscribers.remove(sub)
            if sub.pending is not None:
                sub.pending.cancel()
            if not state.subscribers and state.poller is not None:
                state.poller.cancel()
                state.poller = None

        return unsubscribe

    def _ensure_poller(self, device: Device, spec: PropertySpec, state: _PropertyState) -> None:
        if state.poller is not None or spec.getter is None or spec.read_effect != "none" or not state.subscribers:
            return
        state.poller = asyncio.get_running_loop().create_task(self._poll(device, spec, state),
                                                              name=f"bhms-poll-{device.device_id}.{spec.name}")

    async def _poll(self, device: Device, spec: PropertySpec, state: _PropertyState) -> None:
        try:
            while state.subscribers:
                interval = min(s.floor_s for s in state.subscribers)
                if spec.max_rate_hz:
                    interval = max(interval, 1 / spec.max_rate_hz)
                started = time.monotonic()
                await self.acquire(device, spec)
                await asyncio.sleep(max(0.0, interval - (time.monotonic() - started)))
        except asyncio.CancelledError:
            pass
        except Exception:  # noqa: BLE001 - polling stops but the server keeps running
            log.exception("polling %s.%s failed", device.device_id, spec.name)
        finally:
            if state.poller is asyncio.current_task():
                state.poller = None

    def _fan_out(self, device: Device, spec: PropertySpec, state: _PropertyState, sample: Sample,
                 previous: Sample | None) -> None:
        if not state.subscribers:
            return
        loop = asyncio.get_running_loop()
        for sub in list(state.subscribers):
            now = time.monotonic()
            quality_changed = sub.last_quality is not None and sub.last_quality != sample.quality
            if now - sub.last_mono >= sub.floor_s or quality_changed:
                if sub.pending is not None:
                    sub.pending.cancel()
                    sub.pending = None
                self._deliver(device, spec, state, sub)
            elif sub.pending is None:
                sub.pending = loop.call_at(loop.time() + (sub.last_mono + sub.floor_s - now),
                                           self._deliver, device, spec, state, sub)

    def _deliver(self, device: Device, spec: PropertySpec, state: _PropertyState, sub: _Subscriber) -> None:
        sub.pending = None
        if state.sample is None or sub not in state.subscribers:
            return
        params = {"deviceId": device.device_id, "property": spec.name,
                  "observation": self.present(spec, state.sample)}
        if len(canonical(params["observation"])) > MAX_NOTIFICATION_BYTES:
            log.error("%s.%s observation exceeds 64 KiB; not sent (BHMS-EVT-030)", device.device_id, spec.name)
            return
        sub.last_mono = time.monotonic()
        sub.last_quality = state.sample.quality
        sub.deliver(params)

    def close(self) -> None:
        for state in self._state.values():
            if state.poller is not None:
                state.poller.cancel()
            for sub in state.subscribers:
                if sub.pending is not None:
                    sub.pending.cancel()


def _allows_null(schema: dict[str, Any]) -> bool:
    kind = schema.get("type")
    return kind == "null" or (isinstance(kind, list) and "null" in kind) or None in schema.get("enum", [0])


def _fresh_enough(obs: dict[str, Any] | None, max_age: int) -> bool:
    return obs is not None and obs["quality"] == "valid" and obs["ageMs"] is not None and obs["ageMs"] <= max_age


__all__ = ["MAX_NOTIFICATION_BYTES", "ObservationHub", "Sample"]
