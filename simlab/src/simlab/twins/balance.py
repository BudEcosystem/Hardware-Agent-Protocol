"""Balance twin: the mass of whatever the ledger says is on the pan, with settling, tare and noise.

True gross mass = sum over containers at the ``balance`` site of (container tare mass + liquid mass at 1 g/mL). The
displayed value follows the true mass with a first-order settling time (``SETTLE_TAU_S``), has the tare subtracted, is
corrupted by Gaussian noise (``NOISE_G``) from the balance's own generator and is quantised to the readability
(``READABILITY_G``). Above ``CAPACITY_G`` it reads overload (``None``). Because the mass comes from the ledger, an
under-dispensed well, a missing plate or a dropped slide all change the reading.

``BalanceModel`` is the physics, used both by this BHMS twin and by the SCPI instrument (``instruments/scpi_balance``),
so there is one model whichever protocol reaches it.

Sensing: ``mass`` is ``measured`` (a load cell with noise and quantisation); ``tare`` is verified by it.

Thread-safety: belongs to its world's thread.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from bhms.server.context import DeviceFault
from bhms.server.decorators import Range
from bhms.server.server import DeviceServer
from simlab.simdevice import SensorFault, TwinHost, make_server
from simlab.world import World

BALANCE_SITE = "balance"
CAPACITY_G = 220.0
READABILITY_G = 0.001
NOISE_G = 0.002
SETTLE_TAU_S = 0.8
CONTAINER_MASS_G = {"microplate_96": 40.0, "slide": 1.5, "tube": 10.0, "trough": 25.0}
LIQUID_G_PER_UL = 1e-3


class BalanceModel:
    """Load cell, settling, tare and quantisation over the ledger."""

    def __init__(self, world: World, *, device: str = "balance-1") -> None:
        self.world, self.device = world, device
        self._tare_g = 0.0
        self._to_g = self.true_gross_g()  # the display starts settled on whatever is on the pan
        self._from_g = self._to_g  # the displayed gross value when the true mass last changed
        self._changed_s = world.time_s
        world.on_effect(lambda _effect: self._settling_gross_g())  # notice a load change at the moment it happens

    def true_gross_g(self) -> float:
        ledger, total = self.world.ledger, 0.0
        for container in ledger.containers_at(BALANCE_SITE):
            total += CONTAINER_MASS_G.get(ledger.kind(container), 0.0)
            total += sum(ledger.well(container, w).volume_ul for w in ledger.wells(container)) * LIQUID_G_PER_UL
        return total

    def _settling_gross_g(self) -> float:
        """The unquantised, noiseless displayed gross value now (first-order approach to the true mass)."""
        true = self.true_gross_g()
        now = self.world.time_s
        if abs(true - self._to_g) > 1e-9:  # the load changed since we last looked
            elapsed = now - self._changed_s
            self._from_g = self._to_g + (self._from_g - self._to_g) * math.exp(-max(0.0, elapsed) / SETTLE_TAU_S)
            self._to_g, self._changed_s = true, now
        return self._to_g + (self._from_g - self._to_g) * math.exp(-max(0.0, now - self._changed_s) / SETTLE_TAU_S)

    def settle_time_s(self) -> float:
        """World seconds until the display is within half a readability step of the true mass."""
        self._settling_gross_g()
        residual = abs(self._from_g - self._to_g) * math.exp(-max(0.0, self.world.time_s - self._changed_s) / SETTLE_TAU_S)
        return 0.0 if residual <= READABILITY_G / 2 else SETTLE_TAU_S * math.log(residual / (READABILITY_G / 2))

    def settled(self) -> bool:
        return self.settle_time_s() == 0.0

    def tare(self, cause: str | None) -> float:
        self._tare_g = self._settling_gross_g()
        self.world.record(self.device, "tared", {"tare_g": round(self._tare_g, 6)}, cause)
        return self._tare_g

    def reading_g(self) -> float | None:
        """The balance display: net of tare, noisy, quantised; ``None`` on overload."""
        gross = self._settling_gross_g()
        if gross > CAPACITY_G:
            return None
        noise = float(self.world.rng_for(f"{self.device}.loadcell").normal(0.0, NOISE_G))
        return round(round((gross - self._tare_g + noise) / READABILITY_G) * READABILITY_G, 6)


def build_server(world: World, balance: BalanceModel | None = None, *, state_dir: str | Path | None,
                 durability: str = "process", name: str = "simlab-balance", device_id: str = "balance-1",
                 **kw: Any) -> tuple[DeviceServer, BalanceModel]:
    """The balance as a native BHMS device server (the SCPI adapter reaches the same model over TCP)."""
    model = balance or BalanceModel(world, device=device_id)
    srv = make_server(world, name, state_dir=state_dir, durability=durability, title="SimLab balance", **kw)
    dev = srv.device(device_id, name="Analytical balance", capabilities=["bhms.balance"],
                     resources=[f"{device_id}/pan"], tags=["simlab", "balance"],
                     description="Balance with 1 mg readability and a 220 g capacity; weighs what is on the pan.",
                     identity={"manufacturer": "SimLab", "model": "balance twin", "firmwareVersion": "1"})
    host = TwinHost(world, dev)

    @dev.property(unit="g", evidence="measured", max_rate_hz=10)
    def mass() -> float:
        """Net mass on the pan (g); settles within about 9 s after a load change."""
        host.check_sensor("loadcell")
        value = model.reading_g()
        if value is None:
            raise SensorFault("overload")
        return value

    @dev.property(evidence="measured")
    def stable() -> bool:
        """Whether the reading has settled."""
        host.check_sensor("loadcell")
        return model.settled()

    @dev.action(effect="reversible", idempotency="absolute", completion_evidence="measured", verified_by=["mass"],
                cancel="supported", max_duration_ms=30_000, typical_duration_ms=4000, resources=[f"{device_id}/pan"])
    async def tare(ctx) -> {"tare_g": "g"}:  # noqa: F821
        """Zero the display against what is on the pan now (waits for the reading to settle first)."""
        host.begin(ctx)
        if await host.elapse(ctx, model.settle_time_s(), chunk_s=0.5):
            raise host.canceled(ctx, "tare stopped")
        tare_g = model.tare(ctx.operation_id)
        await ctx.verify("mass", lambda v: abs(v) <= 0.01)
        return host.log.end(ctx.operation_id, {"tare_g": round(tare_g, 4)})

    @dev.action(effect="none", idempotency="relative", completion_evidence="reported", cancel="supported",
                max_duration_ms=30_000, typical_duration_ms=5000)
    async def weigh(ctx, samples: Range(1, 50, unit="1", integer=True) = 5) -> {"mass_g": "g", "samples": "1"}:  # noqa: F821
        """Wait for a stable reading, then average ``samples`` readings."""
        host.begin(ctx)
        if await host.elapse(ctx, model.settle_time_s(), chunk_s=0.5):
            raise host.canceled(ctx, "weighing stopped")
        try:
            host.check_sensor("loadcell")
        except SensorFault as exc:
            raise DeviceFault(str(exc), proof="the load cell produced no reading", effect="none") from exc
        readings = [model.reading_g() for _ in range(int(samples))]
        if any(r is None for r in readings):
            raise DeviceFault("balance overload", proof="nothing was dispensed or moved", effect="none")
        return host.log.end(ctx.operation_id, {"mass_g": round(sum(readings) / len(readings), 4),
                                               "samples": float(len(readings))})

    @dev.on_stop(evidence="reported", max_duration_ms=100)
    async def halt(ctx: Any) -> None:
        return None

    return srv, model
