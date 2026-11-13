"""``conformance-device``: the deterministic simulated device server every BHMS SDK ships (Task 7 targets it).

Run it with ``python -m bhms.testing.conformance_device [unix:/path | ws://127.0.0.1:port] [--state-dir DIR]
[--memory]`` (stdio by default), or build it in-process with :func:`build`.

Behavioural contract (the conformance runner relies on every line of it):

Server
    ``serverInfo.name`` is ``conformance-device``. Capabilities: devices, observations (``minIntervalMs`` 20),
    operations (durable unless ``--memory``), stop, subscriptions, leases (``minTtlMs`` 50, ``maxTtlMs`` 600000,
    ``maxWaitMs`` 30000), events, programs (registry), and the extension ``org.bhms/conformance`` with the methods
    below. Every number is exact and every delay is fixed, so outcomes are reproducible.

Device ``axis-1`` — a simulated linear axis (resources ``axis-1/motion``, ``axis-1/clamp``)
    * ``position`` (mm, ``measured``, observable, ``maxRateHz`` 50): the simulated encoder. It reads the true
      position unless the fault ``encoder_disagrees`` is set (then it reports position + 1 mm) or ``sensor_invalid``
      (acquisition fails → ``quality: invalid``, ``value: null``).
    * ``counter`` (``1``, ``reported``): the number of physical commands the device has executed (every action
      handler that reached the device increments it exactly once). This is the device-side counter that proves "no
      effect" and "exactly one effect".
    * ``temperature`` (Cel, ``measured``, ``validity_ms`` 1000, constant 21.5): the property that can be made stale on
      command — after the fault ``sensor_stale`` every acquisition carries 10 000 ms of latency, so observations are
      ``stale``, fail every ``maxAgeMs`` ≤ 10 000 and fail ``requiresFresh``.
    * ``fifo`` (``1``, ``readEffect: transaction``, ``requiresLease``, resources ``axis-1/motion``): each fresh
      acquisition pops one value and increments ``fifo_reads`` (a device transaction).
    * ``move_to(position: 0–200 mm, multipleOf 0.1)`` — ``absolute``, ``reversible``, ``completionEvidence: measured``
      (``verifiedBy: position``), ``cancel: supported``, ``maxDurationMs`` 5000; takes 20 ms; verified when the encoder
      agrees within 0.05 mm.
    * ``pulse(count: 1–100)`` — ``relative``, ``reversible``, ``reported``; adds ``count`` to ``pulses``; takes 1 ms.
    * ``slow_move(duration_ms: 1–60000 ms, default 1000)`` — ``relative``, ``cancel: supported``, ``maxDurationMs``
      61000; honours cancellation within 5 ms and then ends ``canceled`` (``effect: unverified``).
    * ``clamp(force: 0–100 %)`` — ``requiresLease: true`` on ``axis-1/clamp``, ``onLeaseLoss: cancel``, ``cancel:
      supported``, ``maxDurationMs`` 10000; holds for 50 ms.
    * ``fault()`` — ``irreversible``; always ends ``failed`` with ``DEVICE_FAULT`` (``mayHaveActed: true``) after
      incrementing ``counter``.
    * Stop procedure: halts motion, ends a pending ``hang``, and returns (``stopEvidence: reported``).
    * Reconcile hook: answers from the device-side command log — ``completed`` (with the recorded result) when the
      command finished, ``failed`` (``mayHaveActed: true``) when it started but did not finish, ``failed``
      (``mayHaveActed: false``, ``effect: none``) when it never reached the device.

Device ``pump-1`` — a syringe pump (resource ``pump-1/plunger``)
    * ``pressure`` (kPa, ``measured``, observable, 101.3; ``sensor_invalid`` applies), ``dispensed_volume``
      (uL, ``measured``).
    * ``dispense(volume: 1–1000 uL, multipleOf 0.1)`` — ``irreversible``, ``relative``, ``requiresLease: true``,
      ``requiresFresh: [{pressure, 1000}]``, ``completionEvidence: measured`` (``verifiedBy: dispensed_volume``),
      ``cancel: supported``, ``maxDurationMs`` 60000; takes 10 ms.
    * No stop procedure (``stop: unsupported``).

Faults — ``x-conformance/inject {"fault": <name>}`` (not an operation; works even when the journal is read-only)
    ``none`` (clear all), ``sensor_invalid``, ``sensor_valid``, ``sensor_stale``, ``encoder_disagrees``,
    ``fail_next`` (the next physical command raises ``DeviceFault``), ``crash_next`` (the next handler raises an
    unexpected error after acting → ``unknown``), ``hang_next`` (the next command never finishes until stopped or
    cancelled), ``journal_readonly`` / ``journal_writable`` (SQLite ``query_only``), ``offline`` / ``online``
    (device status of ``axis-1``). ``x-conformance/counters`` returns ``{"counter", "pulses", "fifo_reads", "stops",
    "log"}`` where ``log`` lists ``[operationId, "start"|"done"]`` entries of the device-side command log.

Thread-safety: one event loop.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass, field
from typing import Any

from bhms.protocol.errors import BhmsError
from bhms.server.context import Canceled, DeviceFault, Reading, Reconciled
from bhms.server.decorators import Range
from bhms.server.server import DeviceServer

FAULTS = ("none", "sensor_invalid", "sensor_valid", "sensor_stale", "encoder_disagrees", "fail_next", "crash_next",
          "hang_next", "journal_readonly", "journal_writable", "offline", "online")


@dataclass
class Simulator:
    """The device side of the link: true state, counters, the command log and armed faults."""

    position: float = 0.0
    pulses: int = 0
    counter: int = 0
    fifo_reads: int = 0
    stops: int = 0
    volume: float = 0.0
    sensor: str = "valid"
    encoder_offset: float = 0.0
    armed: set[str] = field(default_factory=set)
    log: list[tuple[str, str]] = field(default_factory=list)
    results: dict[str, Any] = field(default_factory=dict)
    halt: asyncio.Event = field(default_factory=asyncio.Event)

    def begin(self, operation_id: str) -> None:
        """A command reached the device: count it, log it, then apply armed faults."""
        self.counter += 1
        self.log.append((operation_id, "start"))
        if "fail_next" in self.armed:
            self.armed.discard("fail_next")
            raise DeviceFault("injected device fault", partial="the command started")

    async def end(self, operation_id: str, result: Any, cancelled: asyncio.Event) -> Any:
        """The command finished: log it (after an armed hang or crash)."""
        if "hang_next" in self.armed:
            self.armed.discard("hang_next")
            self.halt.clear()
            halted = asyncio.ensure_future(self.halt.wait())
            canceled = asyncio.ensure_future(cancelled.wait())
            await asyncio.wait({halted, canceled}, return_when=asyncio.FIRST_COMPLETED)
            halted.cancel()
            canceled.cancel()
            raise Canceled(effect="unverified", detail="a hung command was released by stop or cancel")
        if "crash_next" in self.armed:
            self.armed.discard("crash_next")
            raise RuntimeError("injected adapter crash after the device acted")
        self.log.append((operation_id, "done"))
        self.results[operation_id] = result
        return result


def build(*, state_dir: str | None = None, memory: bool = False, **server_kw: Any) -> tuple[DeviceServer, Simulator]:
    """The conformance device server and its simulator (see the module docstring)."""
    sim = Simulator()
    if memory:
        server_kw["store"] = None
    srv = DeviceServer("conformance-device", title="BHMS conformance device", state_dir=state_dir,
                       observation_min_interval_ms=20, lease_min_ttl_ms=50,
                       instructions="Deterministic simulated devices for conformance testing; nothing is physical.",
                       **server_kw)
    _axis(srv, sim)
    _pump(srv, sim)

    async def inject(params: dict[str, Any], ctx: Any) -> dict[str, Any]:
        fault = params.get("fault")
        if fault not in FAULTS:
            raise BhmsError("INVALID_ARGUMENT", f"unknown fault {fault!r}", field="fault", bound=list(FAULTS),
                            hint=f"use one of {', '.join(FAULTS)}")
        srv.authenticate(ctx)
        axis = srv.devices["axis-1"]
        if fault == "none":
            sim.armed.clear()
            sim.sensor, sim.encoder_offset = "valid", 0.0
            axis.set_status(None)
        elif fault in ("sensor_invalid", "sensor_valid", "sensor_stale"):
            sim.sensor = fault.split("_", 1)[1]
        elif fault == "encoder_disagrees":
            sim.encoder_offset = 1.0
        elif fault in ("fail_next", "crash_next", "hang_next"):
            sim.armed.add(fault)
        elif fault in ("journal_readonly", "journal_writable"):
            srv.store.set_writable(fault == "journal_writable")
        else:
            axis.set_status("offline" if fault == "offline" else None)
            if fault == "online":
                axis.report_alive()
        return {"resultType": "complete", "fault": fault}

    async def counters(params: dict[str, Any], ctx: Any) -> dict[str, Any]:
        srv.authenticate(ctx)
        return {"resultType": "complete", "counter": sim.counter, "pulses": sim.pulses, "fifo_reads": sim.fifo_reads,
                "stops": sim.stops, "log": [list(entry) for entry in sim.log]}

    srv.extension("org.bhms/conformance", {"version": "1", "faults": list(FAULTS)},
                  {"x-conformance/inject": inject, "x-conformance/counters": counters})
    return srv, sim


def _sensor_reading(sim: Simulator, value: Any) -> Any:
    if sim.sensor == "invalid":
        raise RuntimeError("injected sensor failure")
    if sim.sensor == "stale":
        return Reading(value, latency_ms=10_000.0)
    return value


def _axis(srv: DeviceServer, sim: Simulator) -> None:
    axis = srv.device("axis-1", name="Conformance axis", capabilities=["bhms.axis.linear"], tags=["conformance"],
                      resources=["axis-1/motion", "axis-1/clamp"],
                      description="Deterministic simulated linear axis with device-side command counters.",
                      identity={"manufacturer": "BHMS", "model": "conformance-axis", "firmwareVersion": "1"})
    axis.report_alive()

    @axis.liveness
    def alive() -> bool:
        return True

    @axis.property(unit="mm", evidence="measured", max_rate_hz=50)
    def position() -> float:
        """Encoder position."""
        return _sensor_reading(sim, round(sim.position + sim.encoder_offset, 6))

    @axis.property(evidence="reported")
    def counter() -> Range(0, 2_000_000_000, unit="1", integer=True):
        """Physical commands executed by the device."""
        return sim.counter

    @axis.property(unit="Cel", evidence="measured", validity_ms=1000)
    def temperature() -> float:
        """Housing temperature; can be made stale with the sensor_stale fault."""
        return _sensor_reading(sim, 21.5)

    @axis.property(evidence="reported", read_effect="transaction", requires_lease=True, resources=["axis-1/motion"])
    def fifo() -> Range(0, 2_000_000_000, unit="1", integer=True):
        """Pops one value from the device FIFO (a device transaction)."""
        sim.fifo_reads += 1
        return sim.fifo_reads

    @axis.action(effect="reversible", idempotency="absolute", completion_evidence="measured",
                 verified_by=["position"], cancel="supported", max_duration_ms=5000, typical_duration_ms=20,
                 resources=["axis-1/motion"])
    async def move_to(ctx, position: Range(0, 200, unit="mm", step=0.1)) -> {"position": "mm"}:  # noqa: F821
        """Move to an absolute position (20 ms)."""
        sim.begin(ctx.operation_id)
        if await ctx.wait_cancelled(0.02):
            raise Canceled(effect="unverified", detail="stopped before reaching the target")
        sim.position = position
        measured = await ctx.verify("position", lambda v: abs(v - position) <= 0.05)
        return await sim.end(ctx.operation_id, {"position": measured if measured is not None else position}, ctx.cancelled)

    @axis.action(effect="reversible", idempotency="relative", max_duration_ms=1000, resources=["axis-1/motion"])
    async def pulse(ctx, count: Range(1, 100, unit="1", integer=True)) -> {"pulses": Range(0, 2_000_000_000,  # noqa: F821
                                                                                         unit="1", integer=True)}:
        """Add count pulses (1 ms)."""
        sim.begin(ctx.operation_id)
        await asyncio.sleep(0.001)
        sim.pulses += count
        return await sim.end(ctx.operation_id, {"pulses": sim.pulses}, ctx.cancelled)

    @axis.action(effect="reversible", idempotency="relative", cancel="supported", max_duration_ms=61_000,
                 resources=["axis-1/motion"])
    async def slow_move(ctx, duration_ms: Range(1, 60_000, unit="ms", integer=True) = 1000) -> None:
        """Move slowly for duration_ms; honours cancellation within 5 ms."""
        sim.begin(ctx.operation_id)
        if await ctx.wait_cancelled(duration_ms / 1000):
            raise Canceled(effect="unverified", detail=f"canceled ({ctx.cancel_reason})")
        await sim.end(ctx.operation_id, {}, ctx.cancelled)

    @axis.action(effect="reversible", idempotency="absolute", requires_lease=True, on_lease_loss="cancel",
                 cancel="supported", max_duration_ms=10_000, resources=["axis-1/clamp"])
    async def clamp(ctx, force: Range(0, 100, unit="%")) -> None:
        """Clamp with a force for 50 ms (needs a lease on axis-1/clamp)."""
        sim.begin(ctx.operation_id)
        if await ctx.wait_cancelled(0.05):
            raise Canceled(effect="unverified", detail=f"released ({ctx.cancel_reason})")
        await sim.end(ctx.operation_id, {}, ctx.cancelled)

    @axis.action(effect="irreversible", idempotency="relative", max_duration_ms=1000, resources=["axis-1/motion"])
    async def fault(ctx) -> None:
        """Always fails with a device fault after acting."""
        sim.begin(ctx.operation_id)
        raise DeviceFault("the conformance device reports a fault", partial="counter incremented")

    @axis.on_stop(evidence="reported", max_duration_ms=100)
    async def halt(ctx: Any) -> None:
        sim.stops += 1
        sim.halt.set()

    @axis.reconcile
    async def reconcile(op: dict[str, Any]) -> Reconciled:
        entries = {state for op_id, state in sim.log if op_id == op["operationId"]}
        if "done" in entries:
            return Reconciled("completed", evidence="device command log: done", result=sim.results.get(
                op["operationId"], {}))
        if "start" in entries:
            return Reconciled("failed", evidence="device command log: started, not finished",
                              message="interrupted; partial effect possible", may_have_acted=True)
        return Reconciled("failed", evidence="device command log has no record", effect="none",
                          message="the command never reached the device", may_have_acted=False)


def _pump(srv: DeviceServer, sim: Simulator) -> None:
    pump = srv.device("pump-1", name="Conformance pump", capabilities=["bhms.liquid.dispense"], tags=["conformance"],
                      resources=["pump-1/plunger"], description="Simulated syringe pump with a pressure precondition.")
    pump.report_alive()

    @pump.property(unit="kPa", evidence="measured", max_rate_hz=50)
    def pressure() -> float:
        """Line pressure."""
        return _sensor_reading(sim, 101.3)

    @pump.property(unit="uL", evidence="measured")
    def dispensed_volume() -> float:
        """Volume dispensed by the last dispense."""
        return sim.volume

    @pump.action(effect="irreversible", idempotency="relative", requires_lease=True, requires_fresh={"pressure": 1000},
                 completion_evidence="measured", verified_by=["dispensed_volume"], cancel="supported",
                 max_duration_ms=60_000)
    async def dispense(ctx, volume: Range(1, 1000, unit="uL", step=0.1)) -> {"dispensed": "uL"}:  # noqa: F821
        """Dispense a volume (10 ms)."""
        sim.begin(ctx.operation_id)
        if await ctx.wait_cancelled(0.01):
            raise Canceled(effect="unverified", detail="stopped early")
        sim.volume = volume
        measured = await ctx.verify("dispensed_volume", lambda v: abs(v - volume) <= 0.05)
        return await sim.end(ctx.operation_id, {"dispensed": measured if measured is not None else volume}, ctx.cancelled)


def main(argv: list[str] | None = None) -> None:
    """Command-line entry point (``python -m bhms.testing.conformance_device``)."""
    parser = argparse.ArgumentParser(prog="conformance-device", description=__doc__.split("\n\n")[0])
    parser.add_argument("url", nargs="?", default=None, help="unix:<path> or ws://127.0.0.1:<port>; stdio if absent")
    parser.add_argument("--state-dir", default=None, help="directory of the durable store")
    parser.add_argument("--memory", action="store_true", help="non-durable in-memory store (new epoch each start)")
    args = parser.parse_args(argv)
    srv, _ = build(state_dir=args.state_dir, memory=args.memory)
    srv.run(args.url)


if __name__ == "__main__":
    main(sys.argv[1:])
