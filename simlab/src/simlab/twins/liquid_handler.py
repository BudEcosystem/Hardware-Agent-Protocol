"""Liquid handler twin: one pipetting channel, a tip rack, a deck and a reservoir, over the material ledger.

The channel is a ledger container (``lh_channel``, one well ``tip``) so aspiration and dispense are ordinary ledger
transfers: volume is conserved, solutes mix by volume, an over-aspiration takes air (``air_aspirated``) and an
over-dispense into a full well spills (``spilled``). The twin adds the mechanics of a handler: a tip must be on before
liquid moves, tips run out, labware must be on the deck position that is addressed, and everything takes world time
(``MOVE_S`` of travel plus volume at ``RATE_UL_S``).

Sensing (documented because honesty depends on it): ``channel_volume`` is a **measured** value from a modelled
pressure/capacitance sensor (true tip volume plus Gaussian noise, sigma 0.2 uL); that sensor is what verifies
aspirate and dispense, and what sees air: when a well was short, the measured volume is below the commanded volume and
the action fails with ``DEVICE_FAULT`` (``air_aspirated`` in the world's log). ``tip_attached`` and ``tips_remaining``
are ``reported`` by the handler's own counters.

Thread-safety: belongs to its world's thread.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bhms.server.context import DeviceFault
from bhms.server.decorators import OneOf, Range, Text
from bhms.server.server import DeviceServer
from simlab.ledger import TransferResult
from simlab.simdevice import TwinHost, make_server
from simlab.world import World

CHANNEL = "lh_channel"
TIP_WELL = "tip"
POSITIONS = {"deck": "lh_deck", "reservoir": "lh_reservoir"}
WELL_PATTERN = r"^[A-H](1[0-2]|[1-9])$"
MOVE_S = 1.0
RATE_UL_S = 100.0
TIP_CAPACITY_UL = 200.0
TIPS_IN_RACK = 96
VOLUME_SIGMA_UL = 0.2
VOLUME_TOLERANCE_UL = 1.0


class LiquidHandlerTwin:
    """The handler in a world; see the module docstring."""

    def __init__(self, world: World, *, device: str = "lh-1") -> None:
        self.world, self.device = world, device
        self.tips_remaining = TIPS_IN_RACK
        self.tip_attached = False
        world.ledger.add_container(CHANNEL, "pipette_channel", {TIP_WELL: (0.0, {})}, "in_lh",
                                   max_volume_ul=TIP_CAPACITY_UL)
        world.ledger.add_container("reservoir", "trough", {"A1": (20_000.0, {"dye": 2.0})}, "lh_reservoir",
                                   max_volume_ul=50_000.0)

    # ------------------------------------------------------------------ truth

    def channel_volume_ul(self) -> float:
        return self.world.ledger.well(CHANNEL, TIP_WELL).volume_ul

    def labware_at(self, position: str) -> str | None:
        """The container on a deck position (``deck`` or ``reservoir``) that has wells, if any."""
        ledger = self.world.ledger
        found = [c for c in ledger.containers_at(POSITIONS[position]) if ledger.wells(c)]
        return found[0] if found else None

    def duration_s(self, volume_ul: float = 0.0) -> float:
        return MOVE_S + volume_ul / RATE_UL_S

    # ------------------------------------------------------------------ commands (state changes happen here)

    def pick_up_tip(self, cause: str | None) -> None:
        if self.tip_attached:
            raise RuntimeError("a tip is already attached")
        if self.tips_remaining <= 0:
            raise RuntimeError("the tip rack is empty")
        self.tips_remaining -= 1
        self.tip_attached = True
        self.world.record(self.device, "tip_picked", {"tips_remaining": self.tips_remaining}, cause)

    def eject_tip(self, cause: str | None) -> None:
        """Drop the tip (and whatever liquid is still in it, which is discarded and recorded)."""
        self.world.ledger.discard(CHANNEL, TIP_WELL, cause)
        self.tip_attached = False
        self.world.record(self.device, "tip_ejected", {}, cause)

    def aspirate(self, position: str, well: str, volume_ul: float, cause: str | None) -> TransferResult:
        labware = self.labware_at(position)
        self._require_tip_and_labware(labware, position)
        return self.world.ledger.transfer((labware, well), (CHANNEL, TIP_WELL), volume_ul, cause)

    def dispense(self, position: str, well: str, volume_ul: float, cause: str | None) -> TransferResult:
        labware = self.labware_at(position)
        self._require_tip_and_labware(labware, position)
        return self.world.ledger.transfer((CHANNEL, TIP_WELL), (labware, well), volume_ul, cause)

    def _require_tip_and_labware(self, labware: str | None, position: str) -> None:
        if not self.tip_attached:
            raise RuntimeError("no tip is attached")
        if labware is None:
            raise LookupError(f"no labware on the {position} position")

    # ------------------------------------------------------------------ simulated-time wrappers for tests

    def pipette(self, source: tuple[str, str], target: tuple[str, str], volume_ul: float,
                cause: str | None) -> TransferResult:
        """Synchronous aspirate + dispense (tip handling included) for scripted agents and tests."""
        if not self.tip_attached:
            self.pick_up_tip(cause)
        self.world.step(self.duration_s(volume_ul))
        taken = self.aspirate(source[0], source[1], volume_ul, cause)
        self.world.step(self.duration_s(volume_ul))
        self.dispense(target[0], target[1], taken.moved_ul, cause)
        return taken


# ---------------------------------------------------------------------------------------------------- BHMS server


def build_server(world: World, handler: LiquidHandlerTwin | None = None, *, state_dir: str | Path | None,
                 durability: str = "process", name: str = "simlab-liquid-handler", device_id: str = "lh-1",
                 **kw: Any) -> tuple[DeviceServer, LiquidHandlerTwin]:
    """The liquid handler as a BHMS device server (evidence labels in the module docstring)."""
    lh = handler or LiquidHandlerTwin(world, device=device_id)
    srv = make_server(world, name, state_dir=state_dir, durability=durability, title="SimLab liquid handler", **kw)
    dev = srv.device(device_id, name="Liquid handler", capabilities=["bhms.liquid.handler"],
                     resources=[f"{device_id}/channel", f"{device_id}/tips"], tags=["simlab", "liquid"],
                     description="Single-channel pipetting robot: picks up tips, aspirates from and dispenses into "
                                 "labware on its deck or reservoir position.",
                     identity={"manufacturer": "SimLab", "model": "liquid handler twin", "firmwareVersion": "1"})
    host = TwinHost(world, dev)

    @dev.property(unit="uL", evidence="measured", max_rate_hz=10)
    def channel_volume() -> float:
        """Liquid in the tip (uL), from the pressure/capacitance sensor."""
        return max(0.0, host.measure("volume", lh.channel_volume_ul(), VOLUME_SIGMA_UL))

    @dev.property(evidence="reported")
    def tip_attached() -> bool:
        """Whether a tip is on the channel."""
        return lh.tip_attached

    @dev.property(unit="1", evidence="reported")
    def tips_remaining() -> float:
        """Tips left in the rack."""
        return float(lh.tips_remaining)

    async def work(ctx, seconds: float) -> None:
        if await host.elapse(ctx, seconds):
            raise host.canceled(ctx, "stopped mid-operation")

    def guard(action: Any) -> Any:
        """Turn a refusal by the mechanics (no tip, no labware) into a device fault with proof of no effect."""
        try:
            return action()
        except (RuntimeError, LookupError) as exc:
            raise DeviceFault(str(exc), proof="the handler refused before moving liquid", effect="none") from exc

    @dev.action(effect="reversible", idempotency="relative", completion_evidence="reported", cancel="supported",
                max_duration_ms=10_000, typical_duration_ms=1000, resources=[f"{device_id}/tips"])
    async def pick_up_tip(ctx) -> {"tips_remaining": "1"}:  # noqa: F821
        """Pick up a fresh tip from the rack."""
        host.begin(ctx)
        await work(ctx, MOVE_S)
        guard(lambda: lh.pick_up_tip(ctx.operation_id))
        return host.log.end(ctx.operation_id, {"tips_remaining": float(lh.tips_remaining)})

    @dev.action(effect="irreversible", idempotency="absolute", completion_evidence="reported", cancel="supported",
                max_duration_ms=10_000, typical_duration_ms=1000, resources=[f"{device_id}/tips"])
    async def eject_tip(ctx) -> None:
        """Eject the tip into waste (liquid left in it is discarded)."""
        host.begin(ctx)
        await work(ctx, MOVE_S)
        lh.eject_tip(ctx.operation_id)
        host.log.end(ctx.operation_id, {})

    @dev.action(effect="reversible", idempotency="relative", completion_evidence="measured",
                verified_by=["channel_volume"], cancel="supported", max_duration_ms=30_000, typical_duration_ms=2000,
                resources=[f"{device_id}/channel"])
    async def aspirate(ctx, position: OneOf(*POSITIONS), well: Text(pattern=WELL_PATTERN),  # noqa: F821
                       volume: Range(0.5, TIP_CAPACITY_UL, unit="uL")) -> {"aspirated": "uL", "air": "uL"}:  # noqa: F821
        """Aspirate ``volume`` uL from a well. Fails with a device fault when the well was short (air aspirated)."""
        host.begin(ctx)
        await work(ctx, lh.duration_s(volume))
        before = lh.channel_volume_ul()
        taken = guard(lambda: lh.aspirate(position, well, volume, ctx.operation_id))
        expected = before + volume
        measured = await ctx.verify("channel_volume", lambda v: abs(v - expected) <= VOLUME_TOLERANCE_UL)
        if taken.shortfall_ul > 0:
            raise DeviceFault(f"the well held only {taken.moved_ul:.1f} of the {volume:.1f} uL requested; "
                              f"{taken.shortfall_ul:.1f} uL of air was aspirated",
                              partial=f"{taken.moved_ul:.1f} uL aspirated", hint="check the well volume before retrying")
        if measured is None:
            return host.log.end(ctx.operation_id, {"aspirated": volume, "air": 0.0})  # unverified: no sensor reading
        return host.log.end(ctx.operation_id, {"aspirated": round(measured - before, 3), "air": 0.0})

    @dev.action(effect="irreversible", idempotency="relative", completion_evidence="measured",
                verified_by=["channel_volume"], cancel="supported", max_duration_ms=30_000, typical_duration_ms=2000,
                resources=[f"{device_id}/channel"])
    async def dispense(ctx, position: OneOf(*POSITIONS), well: Text(pattern=WELL_PATTERN),  # noqa: F821
                       volume: Range(0.5, TIP_CAPACITY_UL, unit="uL")) -> {"dispensed": "uL", "spilled": "uL"}:  # noqa: F821
        """Dispense ``volume`` uL from the tip into a well (a full well spills the excess)."""
        host.begin(ctx)
        await work(ctx, lh.duration_s(volume))
        before = lh.channel_volume_ul()
        moved = guard(lambda: lh.dispense(position, well, volume, ctx.operation_id))
        expected = max(0.0, before - volume)
        measured = await ctx.verify("channel_volume", lambda v: abs(v - expected) <= VOLUME_TOLERANCE_UL)
        if moved.spilled_ul > 0 or moved.shortfall_ul > 0:
            raise DeviceFault(f"dispense of {volume:.1f} uL did not complete as asked: {moved.moved_ul:.1f} uL left "
                              f"the tip, {moved.spilled_ul:.1f} uL spilled", partial=f"{moved.moved_ul:.1f} uL moved",
                              hint="check the tip volume and the well capacity")
        got = round(before - measured, 3) if measured is not None else volume
        return host.log.end(ctx.operation_id, {"dispensed": got, "spilled": 0.0})

    @dev.on_stop(evidence="reported", max_duration_ms=100)
    async def halt(ctx: Any) -> None:
        return None  # the handler's motions are bounded and cooperative: cancel (set by stop) ends them

    return srv, lh
