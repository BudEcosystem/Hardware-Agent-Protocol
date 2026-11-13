"""A small test device server used by the DeviceServer tests (real server, real sockets, real SQLite)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from bhms import DeviceServer, Range
from bhms.client.client import Client
from bhms.server.context import Canceled, DeviceFault, Reconciled


@dataclass
class Axis:
    """Simulated axis state shared with the test (the device side of the link)."""

    position: float = 0.0
    commands: dict[str, int] = field(default_factory=lambda: {"move_to": 0, "slow": 0, "explode": 0, "fault": 0,
                                                               "stubborn": 0, "jog": 0})
    gate: asyncio.Event = field(default_factory=asyncio.Event)
    sensor_ok: bool = True
    stops: int = 0
    holds: int = 0
    reconcile_answer: Any = None


def build(tmp_path, *, name: str = "test-server", **kw: Any) -> tuple[DeviceServer, Axis]:
    axis = Axis()
    kw.setdefault("state_dir", tmp_path)
    srv = DeviceServer(name, **kw)
    dev = srv.device("axis-1", name="Axis 1", description="Simulated linear axis for tests.",
                     capabilities=["bhms.axis.linear"], tags=["test"], resources=["axis-1"])
    dev.report_alive()

    @dev.property(unit="mm", evidence="measured")
    def position() -> float:
        if not axis.sensor_ok:
            raise RuntimeError("encoder disconnected")
        return axis.position

    @dev.action(effect="reversible", idempotency="absolute", completion_evidence="measured", max_duration_ms=2000,
                cancel="supported", verified_by=["position"])
    async def move_to(ctx, target: Range(0, 200, unit="mm", step=0.1)) -> {"position": "mm"}:  # noqa: F821
        """Move to an absolute position."""
        axis.commands["move_to"] += 1
        await asyncio.sleep(0.01)
        axis.position = target
        measured = await ctx.verify("position", lambda v: abs(v - target) < 0.05)
        return {"position": measured if measured is not None else target}

    @dev.action(effect="reversible", idempotency="relative", max_duration_ms=5000, cancel="supported")
    async def slow(ctx, distance: Range(-10, 10, unit="mm") = 1.0) -> {"position": "mm"}:  # noqa: F821
        """Move by a distance, waiting for the test's gate; honours cancellation."""
        axis.commands["slow"] += 1
        await ctx.progress(0.5)
        waiter = asyncio.ensure_future(axis.gate.wait())
        cancel = asyncio.ensure_future(ctx.cancelled.wait())
        await asyncio.wait({waiter, cancel}, return_when=asyncio.FIRST_COMPLETED)
        waiter.cancel()
        cancel.cancel()
        if ctx.cancelled.is_set():
            raise Canceled(effect="unverified", detail="stopped before the gate opened")
        axis.position += distance
        return {"position": axis.position}

    @dev.action(effect="reversible", idempotency="relative", max_duration_ms=150, cancel="unsupported")
    async def stubborn(ctx) -> None:
        """Ignores cancellation and overruns its duration bound."""
        axis.commands["stubborn"] += 1
        await asyncio.sleep(0.4)

    @dev.action(effect="reversible", idempotency="relative", max_duration_ms=5000)
    async def explode(ctx) -> None:
        """A handler bug after dispatch: the outcome is unknown."""
        axis.commands["explode"] += 1
        raise ValueError("driver crashed")

    @dev.action(effect="irreversible", idempotency="relative", max_duration_ms=5000)
    async def fault(ctx) -> None:
        """The device reports a fault."""
        axis.commands["fault"] += 1
        raise DeviceFault("motor stalled at 12.5 mm", partial="moved 2.5 mm")

    @dev.action(effect="none", idempotency="idempotent")
    def info(ctx) -> {"commands": Range(0, 1e9, unit="1", integer=True)}:  # noqa: F821
        """Read-only computation."""
        return {"commands": sum(axis.commands.values())}

    @dev.reconcile
    async def reconcile(op):
        return axis.reconcile_answer

    @dev.on_stop(evidence="reported")
    async def halt(ctx):
        axis.stops += 1
        axis.gate.set()

    return srv, axis


async def serve(srv: DeviceServer, tmp_path, *, name: str = "s.sock") -> tuple[str, Any]:
    path = str(tmp_path / name)
    listener = await srv.listen(f"unix:{path}")
    return f"unix:{path}", listener


async def connect(url: str, **kw: Any) -> Client:
    return await Client.connect(url, **kw)


__all__ = ["Axis", "Reconciled", "build", "connect", "serve"]
