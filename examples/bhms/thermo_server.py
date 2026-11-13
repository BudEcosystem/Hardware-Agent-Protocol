"""Example upstream 3/3: a read-only thermometer (``thermo-1``) for the gateway example.

It has no actions: agents can read and subscribe to ``temperature`` through the gateway but never act on it.
"""

import math
import time

from bhms import DeviceServer

srv = DeviceServer("example-thermo")
thermo = srv.device("thermo-1", name="Bench thermometer", description="Simulated bench temperature sensor.",
                    capabilities=["bhms.sensor.temperature"])
thermo.report_alive()


@thermo.property(unit="Cel", evidence="simulated", max_rate_hz=10)
def temperature() -> float:
    """Bench temperature (a slow sine around 21 Cel)."""
    return 21.0 + 0.5 * math.sin(time.time() / 30)


if __name__ == "__main__":
    srv.run()
