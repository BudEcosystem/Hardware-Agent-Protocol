"""Example upstream 2/3: a simulated syringe pump (``pump-1``) for the gateway example.

Run alone with ``python pump_server.py`` (stdio) or let ``gateway.toml`` spawn it. ``dispense`` needs a lease on
``pump-1/plunger``; the gateway grants it and forwards its own fenced upstream lease. Replace the simulation with your
driver and use ``evidence="measured"`` with a real flow sensor.
"""

import asyncio

from bhms import DeviceServer, Range

srv = DeviceServer("example-pump")
pump = srv.device("pump-1", name="Syringe pump", description="Simulated syringe pump with one plunger.",
                  capabilities=["bhms.liquid.dispense"], resources=["pump-1/plunger"])
pump.report_alive()  # simulated, so reachable once the server runs; a real driver reports life when its link is up
dispensed = {"uL": 0.0}


@pump.property(unit="uL", evidence="simulated")
def dispensed_total() -> float:
    """Total volume dispensed since start."""
    return dispensed["uL"]


@pump.action(effect="irreversible", idempotency="relative", requires_lease=True, completion_evidence="reported",
             max_duration_ms=10_000, resources=["pump-1/plunger"])
async def dispense(ctx, volume: Range(1, 500, unit="uL", step=0.1)) -> {"dispensed": "uL"}:  # noqa: F821
    """Dispense a volume."""
    await asyncio.sleep(0.02)
    dispensed["uL"] += volume
    return {"dispensed": volume}


if __name__ == "__main__":
    srv.run()
