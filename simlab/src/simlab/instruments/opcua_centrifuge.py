"""An OPC UA centrifuge: an asyncua server whose address space is the centrifuge twin's state.

The instrument a lab would integrate: an OPC UA server with an object ``Centrifuge`` holding variables and methods. Variable
reads are computed from the shared ``CentrifugeModel`` at the world's present time (asyncua value callbacks), and method
calls drive it, so the BHMS OPC UA adapter talks to it as it would to a real unit. (It lives in the SimLab process because it
reads and writes the one shared world; the protocol boundary is the TCP socket.)

Address space (namespace ``urn:simlab:centrifuge``), under ``Objects/Centrifuge``::

    Speed        Double   Hz, rotor speed (tachometer)
    LidOpen      Boolean
    LidLocked    Boolean  true while the rotor turns
    Imbalance    Double   g, largest opposite-position mass difference
    State        String   "idle" | "spinning"
    StartProgram(SpeedHz: Double, HoldSeconds: Double) -> (Ok: Boolean, Message: String)
    OpenLid() / CloseLid() / Abort() -> (Ok: Boolean, Message: String)

A method returns ``Ok = false`` with the reason when the interlock refuses (lid open, imbalance, lid locked); nothing moves
then. While the unit has no power (``power_loss`` fault) variable reads return ``BadNoCommunication`` and method calls fail
with the same status.

Thread-safety: runs on the world's event loop.
"""

from __future__ import annotations

import socket
from typing import Any

from asyncua import Server, ua, uamethod

from simlab.twins.centrifuge import TACH_SIGMA_HZ, CentrifugeModel
from simlab.world import World

NAMESPACE = "urn:simlab:centrifuge"
OBJECT = "Centrifuge"


def free_port(host: str = "127.0.0.1") -> int:
    with socket.socket() as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


class OpcUaCentrifugeInstrument:
    """Serves a ``CentrifugeModel`` over OPC UA."""

    def __init__(self, world: World, model: CentrifugeModel, *, host: str = "127.0.0.1", port: int = 0,
                 device: str = "centrifuge-1") -> None:
        self.world, self.model, self.device, self.host = world, model, device, host
        self.port = port or free_port(host)
        self._server = Server()
        self.endpoint = f"opc.tcp://{host}:{self.port}/simlab/centrifuge"

    def _powered(self) -> bool:
        return not self.world.faults.active(self.device, "power_loss")

    def _value_callback(self, getter: Any, variant: ua.VariantType) -> Any:
        def callback(_nodeid: ua.NodeId, _attr: ua.AttributeIds) -> ua.DataValue:
            if not self._powered():
                return ua.DataValue(StatusCode=ua.StatusCode(ua.StatusCodes.BadNoCommunication))
            return ua.DataValue(ua.Variant(getter(), variant))
        return callback

    def _tach(self) -> float:
        noise = float(self.world.rng_for(f"{self.device}.opcua").normal(0.0, TACH_SIGMA_HZ))
        return max(0.0, self.model.speed_hz() + noise)

    async def start(self) -> str:
        """Start the server; returns the endpoint URL."""
        server = self._server
        await server.init()
        server.set_endpoint(self.endpoint)
        server.set_server_name("SimLab centrifuge")
        index = await server.register_namespace(NAMESPACE)
        obj = await server.nodes.objects.add_object(index, OBJECT)
        aspace = server.iserver.aspace
        for name, getter, variant in (
                ("Speed", self._tach, ua.VariantType.Double),
                ("LidOpen", lambda: self.model.lid_open, ua.VariantType.Boolean),
                ("LidLocked", self.model.lid_locked, ua.VariantType.Boolean),
                ("Imbalance", lambda: round(self.model.imbalance_g(), 4), ua.VariantType.Double),
                ("State", lambda: "spinning" if self.model.running() else "idle", ua.VariantType.String)):
            node = await obj.add_variable(index, name, _initial(variant), variant)
            aspace.set_attribute_value_callback(node.nodeid, ua.AttributeIds.Value, self._value_callback(getter, variant))

        def reply(ok: bool, message: str) -> tuple[bool, str]:
            return ok, message

        def guarded(action: Any) -> Any:
            def run(*args: Any) -> tuple[bool, str]:
                if not self._powered():
                    raise ua.UaStatusCodeError(ua.StatusCodes.BadNoCommunication)
                try:
                    return reply(True, action(*args) or "ok")
                except (PermissionError, ValueError) as exc:
                    return reply(False, str(exc))
            return run

        start = guarded(lambda speed, hold: f"program accepted, {self.model.start(float(speed), float(hold), None):.1f} s")
        open_lid = guarded(lambda: self.model.set_lid(True, None))
        close_lid = guarded(lambda: self.model.set_lid(False, None))
        abort = guarded(lambda: self.model.abort(None))

        @uamethod
        async def start_program(_parent: Any, speed_hz: float, hold_seconds: float) -> tuple[bool, str]:
            return start(speed_hz, hold_seconds)

        @uamethod
        async def open_lid_method(_parent: Any) -> tuple[bool, str]:
            return open_lid()

        @uamethod
        async def close_lid_method(_parent: Any) -> tuple[bool, str]:
            return close_lid()

        @uamethod
        async def abort_method(_parent: Any) -> tuple[bool, str]:
            return abort()

        outputs = [ua.VariantType.Boolean, ua.VariantType.String]
        await obj.add_method(index, "StartProgram", start_program, [ua.VariantType.Double, ua.VariantType.Double], outputs)
        await obj.add_method(index, "OpenLid", open_lid_method, [], outputs)
        await obj.add_method(index, "CloseLid", close_lid_method, [], outputs)
        await obj.add_method(index, "Abort", abort_method, [], outputs)
        await server.start()
        return self.endpoint

    async def stop(self) -> None:
        await self._server.stop()


def _initial(variant: ua.VariantType) -> Any:
    return {ua.VariantType.Double: 0.0, ua.VariantType.Boolean: False, ua.VariantType.String: ""}[variant]
