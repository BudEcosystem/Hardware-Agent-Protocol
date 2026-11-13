"""SimLab: a simulated laboratory with one shared physical world.

``World`` (MuJoCo scene, clock, effect log) + ``Ledger`` (materials) + ``FaultPlane`` + ``Oracle`` (ground truth, hidden
from agents) form the physical side; the twins in ``simlab.twins`` are BHMS device servers that read and write it, and
``simlab.adapters`` bridge Modbus, OPC UA, SCPI, Home Assistant and MCP into BHMS.
"""
