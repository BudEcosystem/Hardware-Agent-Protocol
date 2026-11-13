"""Home Assistant adapter: lights, switches and sensors of a Home Assistant instance as a BHMS device (WebSocket API).

``HomeAssistantProfile`` names the entities the integrator exposes; nothing else is reachable (an agent cannot call an
arbitrary service on an arbitrary entity: the entity argument is an enumeration built from the profile, and the service is
fixed by the action). Over one authenticated WebSocket the adapter speaks Home Assistant's documented WebSocket API
(``auth``, ``get_states``, ``call_service``).

Honesty rules specific to Home Assistant:

* an entity state is what an integration *reports*; a state of ``unavailable`` or ``unknown`` is an invalid observation, never
  the string "unavailable" passed as a value, and sensors are ``reported`` (the profile may label a sensor ``measured``);
* ``call_service`` succeeds for any entity id, existing or not (the bridge would otherwise report a phantom success); the
  adapter therefore checks that the entity exists *before* calling, and that proves nothing happened when it does not;
* a service call is acknowledged, not completed: the adapter reads the state back and completes ``reported`` (effect
  unverified) when the state matches, and fails with an unknown effect when it does not, so a light that ignored the command
  is not reported as on.

Thread-safety: one event loop; one WebSocket, requests serialised by a lock.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import websockets

from bhms.server.context import DeviceFault, Reconciled
from bhms.server.decorators import OneOf, Range
from bhms.server.server import DeviceServer
from simlab.adapters.common import Refused, Unreachable, declare_action, declare_property, refusal_fault
from simlab.simdevice import CommandLog, make_server, simulated_device
from simlab.world import World

SWITCHABLE = ("light", "switch")


@dataclass(frozen=True)
class Entity:
    entity_id: str
    description: str
    unit: str | None = None  # for numeric sensors: the BHMS unit of the state
    evidence: str = "reported"
    minimum: float | None = None
    maximum: float | None = None

    @property
    def name(self) -> str:
        return self.entity_id.replace(".", "_")

    @property
    def domain(self) -> str:
        return self.entity_id.split(".", 1)[0]


@dataclass(frozen=True)
class HomeAssistantProfile:
    device_id: str
    name: str
    description: str
    entities: tuple[Entity, ...]
    capabilities: tuple[str, ...] = ("bhms.facility",)
    safety_summary: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class HomeAssistantLink:
    """An authenticated Home Assistant WebSocket session."""

    def __init__(self, url: str, token: str, timeout_s: float = 5.0) -> None:
        self.ws_url = url.rstrip("/").replace("http://", "ws://").replace("https://", "wss://") + "/api/websocket"
        self._token, self.timeout_s = token, timeout_s
        self._ws: Any = None
        self._next_id = 0
        self._lock = asyncio.Lock()

    async def close(self) -> None:
        if self._ws is not None:
            await self._ws.close()
            self._ws = None

    async def _ensure(self) -> None:
        if self._ws is not None:
            return
        try:
            ws = await asyncio.wait_for(websockets.connect(self.ws_url, max_size=16 * 1024 * 1024), self.timeout_s)
            hello = json.loads(await asyncio.wait_for(ws.recv(), self.timeout_s))
            if hello.get("type") != "auth_required":
                raise Unreachable(f"unexpected greeting {hello.get('type')!r}")
            await ws.send(json.dumps({"type": "auth", "access_token": self._token}))
            verdict = json.loads(await asyncio.wait_for(ws.recv(), self.timeout_s))
        except (OSError, asyncio.TimeoutError, websockets.WebSocketException) as exc:
            raise Unreachable(f"cannot open the Home Assistant WebSocket: {exc or 'timeout'}") from exc
        if verdict.get("type") != "auth_ok":
            await ws.close()
            raise Unreachable(f"Home Assistant refused the token: {verdict.get('message', verdict.get('type'))}")
        self._ws = ws

    async def request(self, payload: dict[str, Any]) -> Any:
        """Send one command and return its ``result``; ``Refused`` when HA answers ``success: false`` (not executed)."""
        async with self._lock:
            await self._ensure()
            self._next_id += 1
            message = {"id": self._next_id, **payload}
            try:
                await self._ws.send(json.dumps(message))
                while True:
                    reply = json.loads(await asyncio.wait_for(self._ws.recv(), self.timeout_s))
                    if reply.get("id") == self._next_id and reply.get("type") == "result":
                        break
            except (OSError, asyncio.TimeoutError, websockets.WebSocketException) as exc:
                self._ws = None
                raise RuntimeError(f"Home Assistant did not answer after the request left: {exc or 'timeout'}") from exc
            if not reply.get("success"):
                raise Refused(f"{reply.get('error', {}).get('code')}: {reply.get('error', {}).get('message')}")
            return reply.get("result")

    async def states(self) -> dict[str, dict[str, Any]]:
        return {state["entity_id"]: state for state in await self.request({"type": "get_states"})}


async def access_token(base_url: str, refresh_token: str, timeout_s: float = 10.0) -> str:
    """Exchange a long-lived refresh token for an access token (Home Assistant's ``/auth/token``)."""
    import httpx

    client_id = base_url.rstrip("/") + "/"
    async with httpx.AsyncClient(base_url=base_url, timeout=timeout_s) as http:
        response = await http.post("/auth/token", data={"client_id": client_id, "grant_type": "refresh_token",
                                                        "refresh_token": refresh_token})
        response.raise_for_status()
        return str(response.json()["access_token"])


def build_server(world: World, profile: HomeAssistantProfile, url: str, token: str, *, state_dir: str | Path | None,
                 durability: str = "process", name: str = "simlab-ha-adapter", timeout_s: float = 5.0,
                 **kw: Any) -> tuple[DeviceServer, HomeAssistantLink]:
    """The BHMS server for a Home Assistant instance. The adapter never reads the world."""
    srv = make_server(world, name, state_dir=state_dir, durability=durability, title=f"Home Assistant: {profile.name}",
                      **kw)
    dev = simulated_device(srv, profile.device_id, name=profile.name, description=profile.description,
                     capabilities=list(profile.capabilities), resources=[f"{profile.device_id}/services"],
                     tags=["simlab", "adapter", "home-assistant"], safety_summary=profile.safety_summary,
                     identity={"manufacturer": "Home Assistant", "model": profile.name, "firmwareVersion": "unknown"})
    link = HomeAssistantLink(url, token, timeout_s)
    log = CommandLog()
    entities = {e.entity_id: e for e in profile.entities}
    switchable = sorted(e.entity_id for e in profile.entities if e.domain in SWITCHABLE)

    def reader(entity: Entity) -> Any:
        async def read_value() -> Any:
            state = (await link.states()).get(entity.entity_id)
            if state is None:
                raise RuntimeError(f"{entity.entity_id} does not exist in Home Assistant")
            value = state["state"]
            if value in ("unavailable", "unknown"):
                raise RuntimeError(f"{entity.entity_id} is {value}")
            return float(value) if entity.unit is not None else value
        return read_value

    for entity in profile.entities:
        schema = Range(entity.minimum, entity.maximum, unit=entity.unit) if entity.unit else str
        declare_property(dev, entity.name, reader(entity), schema, evidence=entity.evidence,
                         description=f"{entity.description} (Home Assistant entity {entity.entity_id})")

    def service(verb: str) -> Any:
        expected = "on" if verb == "turn_on" else "off"

        async def call(ctx: Any, entity: str) -> Any:
            log.begin(ctx.operation_id)
            try:
                present = await link.states()
                if entity not in present:
                    raise Refused(f"{entity} does not exist in Home Assistant (a service call would silently succeed)")
                if present[entity]["state"] == "unavailable":
                    raise Refused(f"{entity} is unavailable")
                await link.request({"type": "call_service", "domain": entity.split(".", 1)[0], "service": verb,
                                    "target": {"entity_id": entity}})
            except (Refused, Unreachable) as exc:
                raise refusal_fault(exc, "Home Assistant") from exc
            await asyncio.sleep(0.2)  # the state machine updates after the integration confirms
            state = (await link.states()).get(entity, {}).get("state")
            if state != expected:
                raise DeviceFault(f"{entity} is {state!r} after {verb}", partial="the service call was accepted",
                                  hint="read the entity state before retrying")
            return log.end(ctx.operation_id, {"state": state})
        return call

    for verb in ("turn_on", "turn_off"):
        if not switchable:
            break
        declare_action(dev, verb, service(verb), description=f"Call the Home Assistant {verb} service on a light or switch.",
                       params={"entity": OneOf(*switchable)}, returns={"state": str}, effect="reversible",
                       idempotency="absolute", completion_evidence="reported", max_duration_ms=15_000,
                       resources=[f"{profile.device_id}/services"])

    @dev.reconcile
    async def reconcile(op: dict[str, Any]) -> Reconciled | None:
        verb = op.get("action")
        entity = op.get("arguments", {}).get("entity")
        if verb not in ("turn_on", "turn_off") or entity not in entities:
            return None
        try:
            state = (await link.states()).get(entity, {}).get("state")
        except (RuntimeError, Unreachable, Refused):
            return None
        if state == ("on" if verb == "turn_on" else "off"):
            return Reconciled("completed", evidence=f"read back {entity} = {state}", result={"state": state},
                              effect="unverified")
        return None

    @dev.liveness
    async def alive() -> bool:
        try:
            await link.states()
        except (RuntimeError, Unreachable, Refused):
            return False
        return True

    return srv, link
