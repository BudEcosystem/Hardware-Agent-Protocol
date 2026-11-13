"""Plate reader twin: Beer-Lambert absorbance computed from the ledger's concentrations, plus detector noise.

For a well holding volume V (uL) with solute concentrations c_s (mM), the absorbance at wavelength lambda is

    A = sum_s eps_s(lambda) * c_s * l + A_blank,     l = V / well_area   (path length, cm)

with eps_s a Gaussian absorption band (``BANDS``: peak wavelength, width, peak extinction in 1/(mM cm)) and a plate
blank of ``BLANK_A``. The detector adds Gaussian noise (sigma ``NOISE_A``) from its own generator. An empty well reads the
blank. The plate being read is whatever the ledger says is at the ``reader`` site, so a plate the arm dropped is simply
not there and an under-dispensed well reads low: cross-device consequences come from the shared world.

Sensing: ``read_absorbance`` is the measurement; the detector is a modelled optical sensor, so its output is evidence
``measured`` in the sense of OBS (it is acquired through a noisy sensor model, independent of the device's bookkeeping).
``plate_present`` is a ``measured`` plate-detect switch.

Thread-safety: belongs to its world's thread.
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

from bhms.server.context import DeviceFault
from bhms.server.decorators import Array, Range, Text
from bhms.server.server import DeviceServer
from simlab.simdevice import SensorFault, TwinHost, make_server, simulated_device
from simlab.world import World

READER_SITE = "reader"
WELL_AREA_CM2 = 0.32  # flat-bottom 96-well plate
BLANK_A = 0.04
NOISE_A = 0.003
FIRST_S, PER_WELL_S = 1.5, 0.05
# solute -> (peak wavelength nm, 1-sigma width nm, peak extinction 1/(mM cm))
BANDS = {"dye": (560.0, 40.0, 1.2), "blue_dye": (620.0, 35.0, 2.0), "yellow_dye": (450.0, 30.0, 0.9),
         "protein": (280.0, 25.0, 0.6)}
_WELL = re.compile(r"^([A-H])(1[0-2]|[1-9])$")


def extinction(solute: str, wavelength_nm: float) -> float:
    """eps of a solute at a wavelength, 1/(mM cm); 0 for solutes that do not absorb in the band model."""
    if solute not in BANDS:
        return 0.0
    peak, width, eps_max = BANDS[solute]
    return eps_max * math.exp(-0.5 * ((wavelength_nm - peak) / width) ** 2)


class PlateReaderTwin:
    """The reader in a world; see the module docstring."""

    def __init__(self, world: World, *, device: str = "reader-1") -> None:
        self.world, self.device = world, device

    def plate(self) -> str | None:
        ledger = self.world.ledger
        found = [c for c in ledger.containers_at(READER_SITE) if ledger.kind(c).startswith("microplate")]
        return found[0] if found else None

    def true_absorbance(self, container: str, well: str, wavelength_nm: float) -> float:
        state = self.world.ledger.well(container, well)
        path_cm = state.volume_ul * 1e-3 / WELL_AREA_CM2  # uL -> cm^3 -> cm
        return BLANK_A + path_cm * sum(extinction(s, wavelength_nm) * c for s, c in state.solutes.items())

    def duration_s(self, wells: int) -> float:
        return FIRST_S + PER_WELL_S * wells

    def read(self, wells: list[str], wavelength_nm: float, cause: str | None, *, sigma: float = NOISE_A) -> list[float]:
        """Absorbance of ``wells`` of the plate on the reader (raises ``LookupError`` when none is there)."""
        container = self.plate()
        if container is None:
            raise LookupError("no plate on the reader")
        rng = self.world.rng_for(f"{self.device}.detector")
        truth = [self.true_absorbance(container, w, wavelength_nm) for w in wells]
        values = [round(t + float(rng.normal(0.0, sigma)), 4) for t in truth]
        self.world.record(self.device, "plate_read", {"container": container, "wells": list(wells),
                                                      "wavelength_nm": wavelength_nm, "sigma": sigma,
                                                      "true_absorbance": [round(t, 6) for t in truth]}, cause)
        return values


def build_server(world: World, reader: PlateReaderTwin | None = None, *, state_dir: str | Path | None,
                 durability: str = "process", name: str = "simlab-plate-reader", device_id: str = "reader-1",
                 **kw: Any) -> tuple[DeviceServer, PlateReaderTwin]:
    """The plate reader as a BHMS device server."""
    twin = reader or PlateReaderTwin(world, device=device_id)
    srv = make_server(world, name, state_dir=state_dir, durability=durability, title="SimLab plate reader", **kw)
    dev = simulated_device(srv, device_id, name="Absorbance plate reader", capabilities=["bhms.reader.absorbance"],
                     resources=[f"{device_id}/optics"], tags=["simlab", "reader"],
                     description="Absorbance reader for 96-well plates placed on its stage.",
                     identity={"manufacturer": "SimLab", "model": "plate reader twin", "firmwareVersion": "1"})
    host = TwinHost(world, dev)

    @dev.property(evidence="measured")
    def plate_present() -> bool:
        """Whether a microplate is on the stage (plate-detect switch)."""
        host.check_sensor("plate_detect")
        return twin.plate() is not None

    @dev.action(effect="none", idempotency="relative", completion_evidence="reported", cancel="supported",
                max_duration_ms=60_000, typical_duration_ms=6000)
    async def read_absorbance(ctx, wavelength: Range(340, 750, unit="nm"),  # noqa: F821
                              wells: Array(Text(pattern=r"^[A-H](1[0-2]|[1-9])$"), min_items=1, max_items=96)
                              ) -> {"wells": Array(Text()), "absorbance": Array(Range(-1, 5, unit="1"))}:  # noqa: F821
        """Measure absorbance (OD) at a wavelength (nm) in the listed wells of the plate on the stage."""
        host.begin(ctx)
        if twin.plate() is None:
            raise DeviceFault("no plate on the reader stage", proof="the stage plate-detect switch is open",
                              effect="none", hint="move a plate to the reader first")
        if await host.elapse(ctx, twin.duration_s(len(wells))):
            raise host.canceled(ctx, "reading stopped")
        try:
            host.check_sensor("detector")
        except SensorFault as exc:
            raise DeviceFault(str(exc), proof="the detector produced no reading", effect="none") from exc
        values = twin.read(list(wells), float(wavelength), ctx.operation_id)
        return host.log.end(ctx.operation_id, {"wells": list(wells), "absorbance": values})

    @dev.on_stop(evidence="reported", max_duration_ms=100)
    async def halt(ctx: Any) -> None:
        return None

    return srv, twin
