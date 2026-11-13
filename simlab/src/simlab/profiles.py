"""Adapter profiles for the SimLab instruments: what a BHMS integrator would write down from each vendor manual.

A profile is the *client-side knowledge* of an instrument (its register map, node tree or command set). It never refers to
the simulator; the instruments in ``simlab.instruments`` implement the same documented interface independently.
"""

from __future__ import annotations

from simlab.adapters.home_assistant import Entity, HomeAssistantProfile
from simlab.adapters.modbus import ModbusProfile, Register
from simlab.adapters.opcua import Argument, Method, OpcUaProfile, Variable
from simlab.adapters.scpi import Command, Query, ScpiProfile

THERMAL_MODBUS = ModbusProfile(
    device_id="thermal-m1", name="Modbus thermal block",
    description="Temperature controller with a Modbus TCP interface: setpoint and enable registers and a thermistor input.",
    capabilities=("bhms.thermal",),
    safety_summary="Surface up to 99 C; the controller rejects setpoints outside 4 to 99 C.", tag_register=2,
    registers=(
        Register("setpoint", 0, "holding", "Cel", "setpoint temperature", scale=0.1, minimum=4.0, maximum=99.0,
                 writable=True),
        Register("enabled", 1, "holding", None, "heater enable", boolean=True, writable=True),
        Register("temperature", 0, "input", "Cel", "block temperature from the thermistor", scale=0.01, signed=True,
                 evidence="measured", minimum=-50.0, maximum=327.0, invalid_raw=0x7FFF),
        Register("status", 1, "input", None, "status word: bit0 enabled, bit1 within 0.5 C of the setpoint",
                 scale=1.0, minimum=0, maximum=3),
    ),
)

CENTRIFUGE_OPCUA = OpcUaProfile(
    device_id="centrifuge-u1", name="OPC UA centrifuge",
    description="Benchtop centrifuge with an OPC UA server: spin programs, lid control and interlock state.",
    capabilities=("bhms.centrifuge",), namespace_uri="urn:simlab:centrifuge", tag_method=(("Centrifuge",), "Tag"),
    safety_summary="Hazardous when spinning: the unit locks the lid above 0.5 Hz and refuses an unbalanced rotor.",
    variables=(
        Variable("speed", ("Centrifuge", "Speed"), "rotor speed from the tachometer", unit="Hz", evidence="measured",
                 minimum=0.0, maximum=300.0),
        Variable("lid_open", ("Centrifuge", "LidOpen"), "lid switch", kind="boolean", evidence="measured"),
        Variable("lid_locked", ("Centrifuge", "LidLocked"), "interlock state", kind="boolean"),
        Variable("imbalance", ("Centrifuge", "Imbalance"), "rotor imbalance", unit="g", minimum=0.0, maximum=1000.0),
        Variable("state", ("Centrifuge", "State"), "unit state: idle or spinning", kind="string"),
    ),
    methods=(
        Method("start_program", ("Centrifuge",), "StartProgram", "Start a spin: ramp to the speed, hold, brake.",
               arguments=(Argument("speed_hz", "Hz", 1.5, 250.0), Argument("hold_seconds", "s", 1.0, 3600.0)),
               effect="hazardous", idempotency="relative", max_duration_ms=10_000),
        Method("open_lid", ("Centrifuge",), "OpenLid", "Open the lid (refused while the rotor turns).",
               confirm=("lid_open", lambda value, _args: value is True)),
        Method("close_lid", ("Centrifuge",), "CloseLid", "Close the lid.",
               confirm=("lid_open", lambda value, _args: value is False)),
        Method("abort", ("Centrifuge",), "Abort", "Brake the rotor; the lid unlocks when it is slow.",
               effect="reversible", idempotency="idempotent"),
    ),
)

BALANCE_SCPI = ScpiProfile(
    device_id="balance-s1", name="SCPI balance", description="Analytical balance with a SCPI-over-TCP interface.",
    capabilities=("bhms.balance",), idn_prefix="SIMLAB,BALANCE",
    queries=(
        Query("mass", "MEAS:MASS?", "net mass on the pan", unit="g", evidence="measured", minimum=-250.0, maximum=250.0,
              invalid=9.9e37),
        Query("stable", "MEAS:STAB?", "whether the reading has settled", kind="boolean"),
        Query("capacity", "CAP?", "weighing capacity", unit="g", minimum=0.0, maximum=1000.0),
    ),
    commands=(
        Command("tare", "TARE", "Zero the display against the present reading.",
                preconditions="read stable first: taring a settling display leaves a wrong zero"),
    ),
)

FACILITY_HA = HomeAssistantProfile(
    device_id="facility-1", name="Facility (Home Assistant)",
    description="Lab facility lights, a switch and ambient sensors served by a Home Assistant instance.",
    entities=(
        Entity("light.bed_light", "bench light"),
        Entity("light.kitchen_lights", "room lights"),
        Entity("switch.decorative_lights", "indicator beacon"),
        Entity("sensor.outside_temperature", "ambient temperature", unit="Cel", minimum=-60.0, maximum=60.0),
        Entity("sensor.outside_humidity", "ambient relative humidity", unit="%", minimum=0.0, maximum=100.0),
    ),
)
