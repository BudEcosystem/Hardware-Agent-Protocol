"""The material ledger: containers, wells, volumes, solutes and locations.

The ledger is the world's account of matter. A container (plate, slide, pipette channel, tube) has wells; a well has a
volume in microlitres and solute concentrations in mM. ``transfer`` conserves volume exactly, mixes concentrations by
volume weighting, and records what physically happened, including air aspirated when the source was short and liquid
spilled when the destination was full. ``move`` changes where a container is; the world then moves its body.

Locations are named sites, ``"in_gripper"`` or ``"lost"`` (dropped, unrecoverable by the lab's devices).

Thread-safety: owned by one world; not locked.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from simlab.world import World

IN_GRIPPER = "in_gripper"
LOST = "lost"
_EPS = 1e-9


@dataclass(frozen=True)
class WellState:
    """A copy of one well's contents: volume (uL) and solute concentrations (mM)."""

    volume_ul: float
    solutes: dict[str, float]


@dataclass(frozen=True)
class TransferResult:
    """``moved_ul`` left the source; ``shortfall_ul`` was asked for but the source did not have (air);
    ``spilled_ul`` left the source but did not fit in the destination."""

    moved_ul: float
    shortfall_ul: float
    spilled_ul: float = 0.0


@dataclass
class _Well:
    volume_ul: float = 0.0
    solutes: dict[str, float] = field(default_factory=dict)


@dataclass
class _Container:
    kind: str
    site: str
    wells: dict[str, _Well]
    max_volume_ul: float
    meta: dict[str, Any]


class Ledger:
    """Containers, wells and locations of a world."""

    def __init__(self, world: World) -> None:
        self.world = world
        self._containers: dict[str, _Container] = {}

    # ------------------------------------------------------------------ containers

    def add_container(self, container_id: str, kind: str, wells: Mapping[str, Any], site: str, *,
                      max_volume_ul: float = 360.0, meta: dict[str, Any] | None = None) -> None:
        """Register (or replace) a container. ``wells`` maps a well name to ``(volume_ul, solutes)`` or a ``WellState``."""
        built: dict[str, _Well] = {}
        for name, content in wells.items():
            volume, solutes = (content.volume_ul, content.solutes) if isinstance(content, WellState) else content
            if volume < 0 or volume > max_volume_ul + _EPS:
                raise ValueError(f"well {container_id}/{name}: volume {volume} uL is outside 0..{max_volume_ul}")
            built[name] = _Well(float(volume), {k: float(v) for k, v in solutes.items()})
        self._containers[container_id] = _Container(kind, site, built, max_volume_ul, dict(meta or {}))
        self.world.place(container_id, site)

    def container_ids(self) -> list[str]:
        return sorted(self._containers)

    def kind(self, container_id: str) -> str:
        return self._get(container_id).kind

    def meta(self, container_id: str) -> dict[str, Any]:
        return dict(self._get(container_id).meta)

    def wells(self, container_id: str) -> list[str]:
        return sorted(self._get(container_id).wells)

    def _get(self, container_id: str) -> _Container:
        try:
            return self._containers[container_id]
        except KeyError:
            raise KeyError(f"no container {container_id!r} in the ledger") from None

    def _well(self, container_id: str, well: str) -> _Well:
        try:
            return self._get(container_id).wells[well]
        except KeyError:
            raise KeyError(f"container {container_id!r} has no well {well!r}") from None

    # ------------------------------------------------------------------ contents

    def well(self, container_id: str, well: str) -> WellState:
        state = self._well(container_id, well)
        return WellState(state.volume_ul, dict(state.solutes))

    def transfer(self, src: tuple[str, str], dst: tuple[str, str], volume_ul: float,
                 cause: str | None) -> TransferResult:
        """Move up to ``volume_ul`` from ``src`` to ``dst`` (``(container, well)`` pairs).

        The source gives what it has; the shortfall is air (``air_aspirated``). The destination takes what fits;
        the rest is spilled (``spilled``). The destination's concentrations become the volume-weighted mix.
        """
        if volume_ul < 0:
            raise ValueError("transfer volume must be non-negative")
        source, target = self._well(*src), self._well(*dst)
        capacity = self._get(dst[0]).max_volume_ul
        moved = min(volume_ul, source.volume_ul)
        shortfall = volume_ul - moved
        accepted = min(moved, max(0.0, capacity - target.volume_ul))
        spilled = moved - accepted
        carried = dict(source.solutes)
        source.volume_ul = max(0.0, source.volume_ul - moved)
        if accepted > 0:
            total = target.volume_ul + accepted
            for name in sorted(set(target.solutes) | set(carried)):
                target.solutes[name] = (target.volume_ul * target.solutes.get(name, 0.0)
                                        + accepted * carried.get(name, 0.0)) / total
            target.volume_ul = total
        self.world.record("ledger", "transferred", {"src": list(src), "dst": list(dst), "requested_ul": volume_ul,
                                                    "moved_ul": moved}, cause)
        if spilled > _EPS:
            self.world.record("ledger", "spilled", {"dst": list(dst), "volume_ul": spilled}, cause)
        if shortfall > _EPS:
            self.world.record("ledger", "air_aspirated", {"src": list(src), "volume_ul": shortfall}, cause)
        return TransferResult(moved, shortfall, spilled)

    def discard(self, container_id: str, well: str, cause: str | None) -> float:
        """Throw a well's contents away (a discarded tip's liquid); returns the volume discarded (``discarded``)."""
        state = self._well(container_id, well)
        volume = state.volume_ul
        state.volume_ul, state.solutes = 0.0, {}
        if volume > 0:
            self.world.record("ledger", "discarded", {"well": [container_id, well], "volume_ul": volume}, cause)
        return volume

    # ------------------------------------------------------------------ locations

    def location(self, container_id: str) -> str:
        return self._get(container_id).site

    def locations(self) -> dict[str, str]:
        return {cid: c.site for cid, c in sorted(self._containers.items())}

    def containers_at(self, site: str) -> list[str]:
        return sorted(cid for cid, c in self._containers.items() if c.site == site)

    def held(self) -> list[str]:
        return self.containers_at(IN_GRIPPER)

    def move(self, container_id: str, to: str, cause: str | None) -> None:
        container = self._get(container_id)
        origin, container.site = container.site, to
        self.world.place(container_id, to)
        self.world.record("ledger", "container_moved", {"container": container_id, "from": origin, "to": to}, cause)

    def snapshot(self) -> dict[str, Any]:
        return {cid: {"kind": c.kind, "site": c.site,
                      "wells": {w: [round(s.volume_ul, 9), {k: round(v, 9) for k, v in sorted(s.solutes.items())}]
                                for w, s in sorted(c.wells.items())}}
                for cid, c in sorted(self._containers.items())}
