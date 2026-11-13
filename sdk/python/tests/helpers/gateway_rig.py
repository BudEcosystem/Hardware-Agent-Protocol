"""A gateway in front of real in-process device servers (real sockets, real SQLite) for the gateway tests."""

from __future__ import annotations

import contextlib
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from bhms.client.client import Client
from bhms.gateway import Gateway, GatewayConfig, UpstreamConfig
from bhms.runtime.authority import token_digest
from bhms.testing.conformance_device import build as conformance_build
from helpers.devices import Axis, build

UID = os.getuid()
TOKENS = {"agent-b": "tok-b", "admin": "tok-admin", "stopper": "tok-stop"}


@dataclass
class Rig:
    gateway: Gateway
    tmp: Path
    servers: dict[str, Any] = field(default_factory=dict)
    axes: dict[str, Axis] = field(default_factory=dict)
    listeners: dict[str, Any] = field(default_factory=dict)
    clients: list[Client] = field(default_factory=list)

    @property
    def socket(self) -> str:
        return f"unix:{self.tmp}/gw.sock"

    async def client(self, *, token: str | None = None, http: bool = False, **kw: Any) -> Client:
        """Connect to the gateway: over its Unix socket (principal by uid) or, with ``token``, WebSocket (or
        Streamable HTTP with ``http=True``)."""
        if http:
            client = await Client.connect(f"http://127.0.0.1:{self.http_port}/bhms", token=token, **kw)
        elif token is not None:
            url = f"ws://127.0.0.1:{self.ws_port}"
            client = await Client.connect(url, token=token, **kw)
        else:
            client = await Client.connect(self.socket, **kw)
        self.clients.append(client)
        return client

    ws_port: int = 0
    http_port: int = 0


def principals(*, agent_scopes: list[str] | None = None, bounds: dict[str, Any] | None = None) -> dict[str, Any]:
    """``agent`` (Unix, this uid) with the given scopes; ``agent-b``, ``admin`` and ``stopper`` over WebSocket."""
    agent: dict[str, Any] = {"uids": [UID], "scopes": agent_scopes or ["read", "lease", "invoke:*/*"]}
    if bounds:
        agent["bounds"] = bounds
    return {
        "agent": agent,
        "agent-b": {"tokens": [token_digest(TOKENS["agent-b"])], "scopes": ["read", "lease", "invoke:*/*"]},
        "admin": {"tokens": [token_digest(TOKENS["admin"])], "scopes": ["admin"]},
        "stopper": {"tokens": [token_digest(TOKENS["stopper"])], "scopes": ["stop"]},
    }


@contextlib.asynccontextmanager
async def rig(tmp_path: Path, names: tuple[str, ...] = ("a", "b"), *, principals_doc: dict[str, Any] | None = None,
              upstream_kw: dict[str, Any] | None = None, gateway_kw: dict[str, Any] | None = None,
              memory: bool = False, devices_kw: dict[str, Any] | None = None,
              conformance: bool = False) -> AsyncIterator[Rig]:
    """Start one device server per name (devices ``axis-1``) and a gateway over them; everything closes on exit."""
    upstreams = []
    servers, axes, listeners = {}, {}, {}
    for name in names:
        if conformance:
            srv, axis = conformance_build(state_dir=str(tmp_path / name), **(devices_kw or {}))
        else:
            srv, axis = build(tmp_path / name, name=f"up-{name}", **(devices_kw or {}))
        path = str(tmp_path / f"{name}.sock")
        listeners[name] = await srv.listen(f"unix:{path}")
        servers[name], axes[name] = srv, axis
        upstreams.append(UpstreamConfig(name=name, url=f"unix:{path}", health_interval_ms=300, health_timeout_ms=500,
                                        **(upstream_kw or {})))
    config = GatewayConfig(id="gw-test", state_dir=tmp_path / "gw", upstreams=tuple(upstreams),
                           principals=principals_doc if principals_doc is not None else principals(),
                           connect_wait_ms=5000, **(gateway_kw or {}))
    gateway = Gateway(config, memory=memory)
    await gateway.start()
    out = Rig(gateway, tmp_path, servers, axes, listeners)
    out.listeners["gw-unix"] = await gateway.listen(out.socket)
    ws = await gateway.listen("ws://127.0.0.1:0")
    out.listeners["gw-ws"] = ws
    out.ws_port = ws.address[1]
    http = await gateway.listen("http://127.0.0.1:0/bhms")
    out.listeners["gw-http"] = http
    out.http_port = http.address[1]
    try:
        yield out
    finally:
        for client in out.clients:
            with contextlib.suppress(Exception):
                await client.close()
        await gateway.close()
        for name, listener in out.listeners.items():
            if not name.startswith("gw-"):
                with contextlib.suppress(Exception):
                    await listener.close()
        for srv in servers.values():
            with contextlib.suppress(Exception):
                await srv.close()
