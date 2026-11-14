"""Assemble a whole SimLab: one world, every twin as its own BHMS device server, optional protocol-bridged devices.

``Lab.start`` builds a ``World`` and serves each device on its own Unix socket (one ``DeviceServer`` per device, as on a
real bench), then connects BHMS clients to them. Three devices can be reached either natively or through their real
protocol (``bridged``): the thermal block over Modbus TCP, the centrifuge over OPC UA and the balance over SCPI/TCP; each
protocol instrument serves the *same* model as the native twin, and the BHMS adapter in front of it knows only the
protocol. The oracle is available as ``lab.oracle``; agents are given the clients and nothing else.

Thread-safety: one event loop owns the lab.
"""

from __future__ import annotations

import contextlib
import shutil
import tempfile
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from bhms.client.client import Client
from bhms.runtime.authority import Policy
from bhms.server.server import DeviceServer
from simlab.adapters import modbus as modbus_adapter
from simlab.adapters import opcua as opcua_adapter
from simlab.adapters import scpi as scpi_adapter
from simlab.instruments.journal import attribute
from simlab.instruments.modbus_thermal import ModbusThermalInstrument
from simlab.instruments.opcua_centrifuge import OpcUaCentrifugeInstrument
from simlab.instruments.scpi_balance import ScpiBalanceInstrument
from simlab.oracle import Oracle
from simlab.profiles import BALANCE_SCPI, CENTRIFUGE_OPCUA, THERMAL_MODBUS
from simlab.scene import BENCH
from simlab.twins import arm, balance, centrifuge, clock, knob_actuator, liquid_handler, microscope, notice, plate_reader, thermal
from simlab.twins.microscope import FrameStore
from simlab.world import SceneParams, World

NATIVE = ("arm", "microscope", "liquid_handler", "plate_reader", "balance", "thermal", "centrifuge")
BRIDGEABLE = ("balance", "thermal", "centrifuge")
EXTRA = ("knob", "notice", "clock", "cell")  # Actuator Node and the adversarial notice board: started only when asked for


def demand_leases(server: DeviceServer) -> None:
    """Declare every effectful action of ``server`` ``requiresLease`` (BHMS-LSE-010), as a bench that wants exclusive access
    would. "As declared", the twins require a lease only for hazardous actions (BHMS-DEV-033). Since BHMS-LSE-014 that no
    longer leaves a leased resource open: while a lease is held on a resource, every action that uses it is refused unless the
    request presents that lease, the holder's own requests included (the hostile suite's four "as declared" reaches of
    2026-11-13 predate that rule and are refused now). What this switch still adds is that an action cannot start at all
    without a lease. The SDK offers no per-server switch, so the specs are replaced."""
    for device in server.devices.values():
        for name, spec in list(device.actions.items()):
            if spec.effect != "none" and not spec.requires_lease:
                device.actions[name] = replace(spec, requires_lease=True,
                                               on_lease_loss="cancel" if spec.cancel == "supported" else "finish")


@dataclass
class Lab:
    """A running lab; use ``await Lab.start(...)`` and ``await lab.close()`` (or ``async with``)."""

    world: World
    run_dir: Path
    servers: dict[str, DeviceServer] = field(default_factory=dict)
    clients: dict[str, Client] = field(default_factory=dict)
    twins: dict[str, Any] = field(default_factory=dict)
    device_ids: dict[str, str] = field(default_factory=dict)
    require_leases: bool = False  # declare every effectful action requiresLease (see ``demand_leases``)
    urls: dict[str, str] = field(default_factory=dict)  # each device server's own socket (a gateway's upstream url)
    oracle: Oracle = field(init=False)
    _cleanup: list[Any] = field(default_factory=list)
    _bridges: list[tuple[Any, Any]] = field(default_factory=list)  # (instrument journal, adapter link)
    instruments: dict[str, Any] = field(default_factory=dict)  # bridged devices' protocol instruments
    socket_dir: Path = field(default_factory=lambda: Path(tempfile.mkdtemp(prefix="simlab-")))

    def __post_init__(self) -> None:
        self.oracle = Oracle(self.world)

    # ------------------------------------------------------------------ construction

    @classmethod
    async def start(cls, run_dir: Path, *, seed: int = 1, mode: str = "stepped", devices: tuple[str, ...] = NATIVE,
                    bridged: tuple[str, ...] = (), durability: str = "process", strict: bool = False,
                    params: SceneParams | None = None, ha: tuple[str, str] | None = None,
                    policy: Policy | None = None, require_leases: bool = False) -> Lab:
        """Start the lab. ``bridged`` devices (subset of balance, thermal, centrifuge) are reached over their protocols;
        ``ha=(url, token)`` adds the Home Assistant facility adapter.
        ``policy`` is every device server's authorization policy (a gateway in front of the lab needs its principal marked
        ``gateway`` there, BHMS-OPS-037); the default is the SDK's (same-uid peers are admin)."""
        run_dir.mkdir(parents=True, exist_ok=True)
        world = World(BENCH, seed=seed, mode=mode, params=params)  # type: ignore[arg-type]
        lab = cls(world, run_dir)
        lab.require_leases = require_leases
        try:
            await lab._build(devices, bridged, durability, strict, ha, policy)
        except BaseException:
            await lab.close()
            raise
        return lab

    async def _serve(self, key: str, server: DeviceServer, device_id: str, strict: bool) -> None:
        url = f"unix:{self.socket_dir}/{key}.sock"  # short path: AF_UNIX paths are limited to 108 bytes
        if self.require_leases:
            demand_leases(server)
        listener = await server.listen(url)
        self._cleanup.append(server.close)  # cleanup runs in reverse: stop listening, then close the server
        self._cleanup.append(listener.close)
        self.servers[key] = server
        self.device_ids[key] = device_id
        self.urls[key] = url
        self.clients[key] = await Client.connect(url, strict=strict)

    async def _build(self, devices: tuple[str, ...], bridged: tuple[str, ...], durability: str, strict: bool,
                     ha: tuple[str, str] | None, policy: Policy | None = None) -> None:
        world, state = self.world, self.run_dir / "state"
        for name in bridged:
            if name not in BRIDGEABLE:
                raise ValueError(f"{name!r} cannot be bridged; choose from {BRIDGEABLE}")
        kw: dict[str, Any] = {"durability": durability, "strict": strict}
        if policy is not None:
            kw["policy"] = policy
        if "cell" in devices:  # arm, liquid handler and plate reader on ONE server: a program can span them
            srv, self.twins["arm"] = arm.build_server(world, state_dir=state / "cell", **kw)
            _, self.twins["liquid_handler"] = liquid_handler.build_server(world, state_dir=state / "cell", into=srv, **kw)
            _, self.twins["plate_reader"] = plate_reader.build_server(world, state_dir=state / "cell", into=srv, **kw)
            await self._serve("cell", srv, "lh-1", strict)
        if "arm" in devices:
            srv, self.twins["arm"] = arm.build_server(world, state_dir=state / "arm", **kw)
            await self._serve("arm", srv, "arm-1", strict)
        if "microscope" in devices:
            frames = FrameStore(self.run_dir / "frames")
            twin = microscope.MicroscopeTwin(world, device="microscope-1", frames=frames)
            srv, self.twins["microscope"] = microscope.build_server(world, twin, state_dir=state / "microscope", **kw)
            await self._serve("microscope", srv, "microscope-1", strict)
        if "liquid_handler" in devices:
            srv, self.twins["liquid_handler"] = liquid_handler.build_server(world, state_dir=state / "lh", **kw)
            await self._serve("liquid_handler", srv, "lh-1", strict)
        if "plate_reader" in devices:
            srv, self.twins["plate_reader"] = plate_reader.build_server(world, state_dir=state / "reader", **kw)
            await self._serve("plate_reader", srv, "reader-1", strict)
        if "balance" in devices:
            await self._balance("balance" in bridged, state, kw, strict)
        if "thermal" in devices:
            await self._thermal("thermal" in bridged, state, kw, strict)
        if "centrifuge" in devices:
            await self._centrifuge("centrifuge" in bridged, state, kw, strict)
        if "knob" in devices:
            srv, self.twins["knob"] = knob_actuator.build_server(world, state_dir=state / "knob", **kw)
            await self._serve("knob", srv, "knob-1", strict)
        if "clock" in devices:
            srv, self.twins["clock"] = clock.build_server(world, state_dir=state / "clock", **kw)
            await self._serve("clock", srv, "clock-1", strict)
        if "notice" in devices:
            srv, self.twins["notice"] = notice.build_server(world, state_dir=state / "notice", **kw)
            await self._serve("notice", srv, "notice-1", strict)
        if ha is not None:
            from simlab.adapters import home_assistant
            from simlab.profiles import FACILITY_HA
            srv, link = home_assistant.build_server(world, FACILITY_HA, ha[0], ha[1], state_dir=state / "ha",
                                                    durability=durability, strict=strict,
                                                    **({} if policy is None else {"policy": policy}))
            self._cleanup.append(link.close)
            await self._serve("facility", srv, FACILITY_HA.device_id, strict)

    async def _balance(self, bridge: bool, state: Path, kw: dict[str, Any], strict: bool) -> None:
        if not bridge:
            srv, self.twins["balance"] = balance.build_server(self.world, state_dir=state / "balance", **kw)
            return await self._serve("balance", srv, "balance-1", strict)
        model = balance.BalanceModel(self.world, device=BALANCE_SCPI.device_id)
        instrument = ScpiBalanceInstrument(self.world, model, device=BALANCE_SCPI.device_id)
        port = await instrument.start()
        self._cleanup.append(instrument.stop)
        srv, link = scpi_adapter.build_server(self.world, BALANCE_SCPI, "127.0.0.1", port, state_dir=state / "balance",
                                              **kw)
        self._cleanup.append(link.close)
        self._bridges.append((instrument.journal, link))
        self.instruments["balance"] = instrument
        self.twins["balance"] = model
        await self._serve("balance", srv, BALANCE_SCPI.device_id, strict)

    async def _thermal(self, bridge: bool, state: Path, kw: dict[str, Any], strict: bool) -> None:
        if not bridge:
            srv, self.twins["thermal"] = thermal.build_server(self.world, state_dir=state / "thermal", **kw)
            return await self._serve("thermal", srv, "thermal-1", strict)
        model = thermal.ThermalModel(self.world, device=THERMAL_MODBUS.device_id)
        instrument = ModbusThermalInstrument(self.world, model, device=THERMAL_MODBUS.device_id)
        port = await instrument.start()
        self._cleanup.append(instrument.stop)
        srv, link = modbus_adapter.build_server(self.world, THERMAL_MODBUS, "127.0.0.1", port,
                                                state_dir=state / "thermal", **kw)
        self._cleanup.append(link.close)
        self._bridges.append((instrument.journal, link))
        self.instruments["thermal"] = instrument
        self.twins["thermal"] = model
        await self._serve("thermal", srv, THERMAL_MODBUS.device_id, strict)

    async def _centrifuge(self, bridge: bool, state: Path, kw: dict[str, Any], strict: bool) -> None:
        if not bridge:
            srv, self.twins["centrifuge"] = centrifuge.build_server(self.world, state_dir=state / "centrifuge", **kw)
            return await self._serve("centrifuge", srv, "centrifuge-1", strict)
        model = centrifuge.CentrifugeModel(self.world, device=CENTRIFUGE_OPCUA.device_id)
        instrument = OpcUaCentrifugeInstrument(self.world, model, device=CENTRIFUGE_OPCUA.device_id)
        endpoint = await instrument.start()
        self._cleanup.append(instrument.stop)
        srv, link = opcua_adapter.build_server(self.world, CENTRIFUGE_OPCUA, endpoint, state_dir=state / "centrifuge",
                                               **kw)
        self._cleanup.append(link.close)
        self._bridges.append((instrument.journal, link))
        self.instruments["centrifuge"] = instrument
        self.twins["centrifuge"] = model
        await self._serve("centrifuge", srv, CENTRIFUGE_OPCUA.device_id, strict)

    # ------------------------------------------------------------------ use

    def attribute_bridged(self, extra_links: list[Any] | None = None) -> None:
        """Give the effects of protocol-bridged instruments their causes by joining the adapters' sent tokens with each
        instrument's journal (``instruments.journal.attribute``). ``extra_links`` are further adapter links (a second adapter
        to the same instrument) of a lab's instrument; their tokens are merged. Raises ``AttributionError`` when the join
        cannot be proven. Call before judging; it is idempotent."""
        for journal, link in self._bridges:
            sent = dict(link.log.sent)
            for other in extra_links or []:
                sent.update(other.log.sent)
            for seq, operation_id in attribute(journal, sent).items():
                self.oracle.attribute(seq, operation_id)

    def client(self, key: str) -> Client:
        return self.clients[key]

    async def close(self) -> None:
        for client in self.clients.values():
            with contextlib.suppress(Exception):
                await client.close()
        self.clients.clear()
        for cleanup in reversed(self._cleanup):
            with contextlib.suppress(Exception):
                await cleanup()
        self._cleanup.clear()
        shutil.rmtree(self.socket_dir, ignore_errors=True)

    async def __aenter__(self) -> Lab:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()
