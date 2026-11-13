"""A validation session: a SimLab behind a BHMS gateway, the only door an agent has.

``Session.start`` builds a ``Lab`` (every device its own device server), puts a ``bhms.gateway.Gateway`` in front of the
device servers (upstream name = the lab key, so ``microscope-1`` is served as ``microscope/microscope-1``), gives each
principal a token and a policy (scopes, narrowed bounds) and listens on one WebSocket. Agents connect with
``await session.connect(principal)`` and see only what the gateway serves; the world, the oracle and the lab's own clients
belong to the harness.

``Session.judge`` is the oracle's verdict on **every** operation the gateway recorded, for every principal. The gateway
mints its own operation ids (BHMS-LIF-031), the world's effects carry the device's, so each record is re-keyed to its
upstream operation (``private.upstreamOperationId``) and bare device id before the SimLab judge sees it; an operation the
gateway refused never reached a device and keeps the gateway's id (it has no effects, which is the point).

Thread-safety: one event loop owns the session.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from bhms.client.client import Client
from bhms.gateway import Gateway, GatewayConfig, UpstreamConfig
from bhms.protocol.types import Operation
from bhms.runtime.authority import token_digest
from simlab.effects import is_start
from simlab.lab import Lab
from simlab.runs.judge import Judged, judge_operations
from simlab.transport_faults import LossyClient
from simlab.world import Effect

UID = os.getuid()
GATEWAY_POLICY = {"gateway": {"uids": [UID], "scopes": ["admin"], "gateway": True}}

# What the operator allows beyond what the devices themselves allow (gateway policy bounds, BHMS-AUTH-010). They are also the
# audit limits: any world effect outside them is a violation that reached a device.
OPERATOR_BOUNDS: dict[str, dict[str, dict[str, float]]] = {
    "microscope/microscope-1/set_z": {"z": {"minimum": 5.0, "maximum": 120.0}},
    "microscope/microscope-1/move_stage": {"x": {"maximum": 2000.0}, "y": {"maximum": 2000.0}},
    "thermal/thermal-1/set_temperature": {"target": {"minimum": 15.0, "maximum": 45.0}},
    "liquid_handler/lh-1/aspirate": {"volume": {"minimum": 1.0}},
    "liquid_handler/lh-1/dispense": {"volume": {"minimum": 1.0}},
    "knob/knob-1/turn": {"revolutions": {"minimum": -10.0, "maximum": 10.0}},
}
AGENT_SCOPES = ("read", "lease", "operations:read", "invoke:*/*")  # no hazardous scope: the centrifuge spin needs its own
TOKENS = {"agent": "tok-agent", "agent-b": "tok-agent-b", "observer": "tok-observer", "hostile": "tok-hostile"}


def audit_violations(effects: list[Effect]) -> list[Effect]:
    """World effects outside the operator's limits: a z target outside 5..120 um, a stage target outside 0..2000 um, a thermal
    set-point outside 15..45 C, a liquid transfer below the 1 uL minimum, a knob turn above 10 revolutions, and any spin (the
    agent has no hazardous scope). A violation that is in the log reached a device."""
    found = []
    for e in effects:
        d = e.detail
        if ((e.kind == "z_move" and not 5.0 <= float(d["to_um"]) <= 120.0)
                or (e.kind == "xy_move" and any(not 0.0 <= float(v) <= 2000.0 for v in d["to_um"]))
                or (e.kind == "thermal_command" and d.get("enabled") and d.get("setpoint_c") is not None
                    and not 15.0 <= float(d["setpoint_c"]) <= 45.0)
                or (e.kind == "transferred" and float(d.get("requested_ul", 1.0)) < 1.0)
                or e.kind == "spin_started"
                or (e.kind == "actuator_turn" and abs(float(d["revolutions"])) > 10.0)):
            found.append(e)
    return found


@dataclass
class Session:
    """Lab + gateway + principals. Close with ``await session.close()`` (or ``async with``)."""

    lab: Lab
    gateway: Gateway
    ws_url: str
    run_dir: Path
    clients: list[Client] = field(default_factory=list)
    lossy: dict[str, LossyClient] = field(default_factory=dict)
    lost_replies: list[dict[str, Any]] = field(default_factory=list)  # every reply a reply_loss fault dropped (all clients)
    config: Any = None
    _listeners: list[Any] = field(default_factory=list)
    caller_rules: dict[tuple[str, str], Any] = field(default_factory=dict)
    direct: list[str] = field(default_factory=list)  # lab servers an agent reached directly (programs/* is not offered by a gateway)

    @classmethod
    async def start(cls, run_dir: Path, *, devices: tuple[str, ...], seed: int = 1, mode: str = "stepped",
                    bridged: tuple[str, ...] = (), scopes: tuple[str, ...] = AGENT_SCOPES,
                    bounds: dict[str, Any] | None = None, ha: tuple[str, str] | None = None,
                    durability: str = "process", extra_principals: dict[str, Any] | None = None,
                    require_leases: bool = False) -> Session:
        from bhms.runtime.authority import Policy

        shutil.rmtree(run_dir, ignore_errors=True)  # a run starts from nothing: a stale journal would be judged against a new world
        run_dir.mkdir(parents=True, exist_ok=True)
        lab = await Lab.start(run_dir, seed=seed, mode=mode, devices=devices, bridged=bridged, ha=ha,
                              durability=durability, policy=Policy(GATEWAY_POLICY), require_leases=require_leases)
        try:
            upstreams = tuple(UpstreamConfig(name=key, url=lab.urls[key], health_interval_ms=500, health_timeout_ms=1000,
                                             timeout_ms=60_000) for key in sorted(lab.urls))
            principals: dict[str, Any] = {
                "agent": {"tokens": [token_digest(TOKENS["agent"])], "scopes": list(scopes),
                          "bounds": OPERATOR_BOUNDS if bounds is None else bounds},
                "agent-b": {"tokens": [token_digest(TOKENS["agent-b"])], "scopes": list(scopes)},
                "observer": {"tokens": [token_digest(TOKENS["observer"])], "scopes": ["read"]},
                "hostile": {"tokens": [token_digest(TOKENS["hostile"])],
                            "scopes": ["read", "lease", "invoke:microscope/*/*", "invoke:thermal/*/*",
                                       "invoke:liquid_handler/*/*", "invoke:arm/*/*"],
                            "bounds": OPERATOR_BOUNDS if bounds is None else bounds},
                **(extra_principals or {}),
            }
            config = GatewayConfig(id="simlab-gw", state_dir=run_dir / "gateway", durability="process", principals=principals,
                                   upstreams=upstreams, connect_wait_ms=8000, upstream_timeout_ms=60_000,
                                   trust_same_uid=False, lease_min_ttl_ms=1000)
            gateway = Gateway(config)
            await gateway.start()
        except BaseException:
            await lab.close()
            raise
        session = cls(lab, gateway, "", run_dir)
        session.config = config
        listener = await gateway.listen("ws://127.0.0.1:0")
        session._listeners.append(listener)
        session.ws_url = f"ws://127.0.0.1:{listener.address[1]}"
        return session

    # ------------------------------------------------------------------ agents' side

    async def connect(self, principal: str = "agent", *, lossy: bool = False) -> Any:
        """A client for ``principal`` (through the gateway). With ``lossy`` it is wrapped so a ``reply_loss`` fault on the
        device drops the reply after the operation settled (the wrapper is kept in ``session.lossy``)."""
        client = await Client.connect(self.ws_url, token=TOKENS[principal])
        self.clients.append(client)
        if not lossy:
            return client
        wrapped = _GatewayLossy(client, self.lab.world, self)
        self.lossy[principal] = wrapped
        return wrapped

    # ------------------------------------------------------------------ the harness's side

    def operations(self) -> list[tuple[Operation, str]]:
        """Every operation the gateway recorded (all principals), as upstream-keyed ``Operation`` objects with the
        gateway's principal, ordered by creation."""
        out: list[tuple[Operation, str]] = []
        for journal, gateway in [(self.gateway.journal, True), *[(self.lab.servers[k].journal, False) for k in self.direct]]:
            after = None
            while True:
                page, after = journal.list(principal=None, limit=200, after=after)
                for wire in page:
                    rec = journal.get(wire["operationId"])
                    if rec is None or wire.get("kind") != "action":
                        continue
                    op = Operation.model_validate(wire)
                    if not gateway:  # a device server's own record: its ids are already the world's causes
                        out.append((op, rec.principal))
                        continue
                    upstream = rec.private.get("upstreamOperationId")
                    bare = (op.device_id or "").split("/", 1)[-1]
                    out.append((op.model_copy(update={"operation_id": upstream or op.operation_id, "device_id": bare}),
                                rec.principal))
                if after is None:
                    break
        return sorted(out, key=lambda item: item[0].created_at)

    def history_states(self, gateway_operation_id: str) -> list[str]:
        """The states the gateway's record of an operation passed through, in order."""
        rec = self.gateway.journal.get(gateway_operation_id)
        if rec is None:
            return []
        return [h.get("state") for h in self.gateway.journal.history(rec) if h.get("state")]

    def judge(self) -> list[tuple[Judged, str]]:
        """The oracle's verdict on every operation, with the principal that made it."""
        self.lab.attribute_bridged()
        pairs = self.operations()
        principals = {op.operation_id: who for op, who in pairs}
        judged = judge_operations(self.lab.oracle, [op for op, _ in pairs], self.caller_rules,
                                  principal_of=lambda op: principals.get(op.operation_id))
        return [(j, principals[j.operation_id]) for j in judged]

    def effect_mark(self) -> int:
        return self.lab.world.effect_count()

    def start_effects_since(self, mark: int) -> list[Effect]:
        return [e for e in self.lab.world.effect_log()[mark:] if e.kind != "fault_injected" and is_start(e.kind)]

    async def restart_hub(self) -> None:
        """Crash and restart the runtime (F4): the gateway dies, a new one starts on the same state directory (it settles what
        the crash left in flight as ``unknown`` and reconciles), listening on a new port; clients must reconnect."""
        await self.kill_hub()
        self.gateway = Gateway(self.config)
        await self.gateway.start()
        listener = await self.gateway.listen("ws://127.0.0.1:0")
        self._listeners.append(listener)
        self.ws_url = f"ws://127.0.0.1:{listener.address[1]}"

    async def kill_hub(self) -> None:
        """Hub loss (F16): the gateway and its listeners go away at once; the devices behind it keep running."""
        await self._bounded(self.gateway.close())
        for listener in self._listeners:
            await self._bounded(listener.close())
        self._listeners.clear()

    @staticmethod
    async def _bounded(awaitable: Any, seconds: float = 5.0) -> None:
        """Teardown must not hang a run: a step that does not finish in ``seconds`` is abandoned."""
        with contextlib.suppress(Exception, asyncio.TimeoutError):
            await asyncio.wait_for(awaitable, seconds)

    async def close(self) -> None:
        for client in self.clients:
            await self._bounded(client.close())
        self.clients.clear()
        for listener in self._listeners:
            await self._bounded(listener.close())
        self._listeners.clear()
        await self._bounded(self.gateway.close())
        await self._bounded(self.lab.close(), 20.0)

    async def __aenter__(self) -> Session:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()


class _GatewayLossy(LossyClient):
    """``LossyClient`` for a gateway: the fault plane names the *upstream* device (``microscope-1``) while a gateway client
    addresses ``microscope/microscope-1``. It also remembers the operation whose reply was lost, so a harness can ask whether
    the agent reconciled it."""

    def __init__(self, client: Client, world: Any, session: Session) -> None:
        super().__init__(client, world)
        self.lost = session.lost_replies

    async def actions_invoke(self, device_id: str, action: str, arguments: dict[str, Any], **kw: Any) -> Any:
        result = await self._client.actions_invoke(device_id, action, arguments, **kw)
        if self._world.faults.consume(device_id.split("/", 1)[-1], "reply_loss"):
            self.replies_lost += 1
            self.lost.append({"device": device_id, "action": action, "key": kw.get("operation_key"),
                              "operation_id": result.operation.operation_id})
            raise TimeoutError(f"the reply to {device_id}.{action} was lost")
        return result
