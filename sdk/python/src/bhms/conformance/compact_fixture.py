"""The ``compact-gateway`` fixture: a gateway in front of native BHMS-Compact endpoints, with faults and direct endpoints.

``bhms conformance compact-gateway --profile compact`` builds the C library's host simulators (``sdk/c``, cmake and a C
compiler), starts

* two ``sim_bench`` endpoints, ``rig`` (with a persistent boot epoch) and ``vol`` (without), each behind a fault-injecting
  :class:`~bhms.testing.compact_endpoint.Wire` that the runner owns, and
* a gateway process (``python -m bhms.gateway``) with a ``type = "compact"`` upstream for each, served as ``rig/bench-rig``
  and ``vol/bench-rig``,

and lets the compact checks drive extra endpoints directly (:meth:`CompactFixture.raw`) for the rows that are about the
endpoint itself (frame rules, ring, fences, stop). The wire sees every frame, so a check can assert what the gateway sent;
it can lose, corrupt or hold chosen frames and reboot the endpoint, which is how lost replies and silent resets are provoked.

Thread-safety: one event loop.
"""

from __future__ import annotations

import asyncio
import contextlib
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from bhms.testing.compact_endpoint import SDK_C, NativeEndpoint, NativeUnavailable, Wire, build_native
from bhms.transport import compact as cp

SIDECAR = SDK_C / "tests" / "host" / "bench.sidecar.json"
DEVICE_ID = "bench-rig"
FLAVOURS = {"rig": True, "vol": False}  # upstream name -> has a persistent boot epoch


@dataclass
class RawEndpoint:
    """A native endpoint driven directly over a socket pair, speaking as the gateway."""

    endpoint: NativeEndpoint
    link: cp.CompactLink
    session: int = 0
    hello_reply: cp.Hello | None = None
    nonce: int = 0

    def send(self, message: Any, *, session: int | None = None, channel: int = cp.CHANNEL, kind: int = cp.CONTROL) -> bytes:
        return self.link.send(message, session=self.session if session is None else session, channel=channel, kind=kind)

    async def reply(self, timeout: float = 2.0) -> cp.Incoming | None:
        return await self.link.receive(timeout)

    async def exchange(self, message: Any, *, session: int | None = None, timeout: float = 2.0) -> cp.Incoming | None:
        self.send(message, session=session)
        return await self.reply(timeout)

    async def silent(self, seconds: float = 0.4) -> bool:
        """Whether nothing arrives for ``seconds`` (a discarded frame is answered by silence)."""
        return await self.link.receive(seconds) is None

    async def hello(self, *, new_session: bool = False, timeout: float = 5.0) -> cp.Hello:
        self.nonce += 1
        self.link.send(cp.HelloReq(self.nonce, cp.HELLO_NEW_SESSION if new_session else 0), session=0)
        while True:
            got = await self.link.receive(timeout)
            if got is None:
                raise TimeoutError("the endpoint did not answer HELLO_REQ")
            if isinstance(got.message, cp.Hello) and got.message.nonce == self.nonce:
                self.hello_reply, self.session = got.message, got.message.epoch
                return got.message

    async def drain(self, seconds: float = 0.2) -> list[cp.Incoming]:
        out = []
        while (got := await self.link.receive(seconds)) is not None:
            out.append(got)
        return out

    def effects(self, prefix: str) -> int:
        return self.endpoint.count(prefix)

    async def reboot(self) -> None:
        await self.link.close()
        await self._attach(self.endpoint)

    async def _attach(self, endpoint: NativeEndpoint) -> None:
        reader, writer = await asyncio.open_connection(sock=endpoint.start())
        self.link = cp.CompactLink(cp.SocketStream(reader, writer))
        self.link.start()
        self.session = 0

    async def close(self) -> None:
        await self.link.close()
        self.endpoint.stop()


@dataclass
class CompactFixture:
    work: Path
    binaries: dict[str, Path]
    wires: dict[str, Wire] = field(default_factory=dict)
    endpoints: dict[str, NativeEndpoint] = field(default_factory=dict)
    raws: list[RawEndpoint] = field(default_factory=list)
    state_dir: Path | None = None
    config_path: Path | None = None
    started: bool = False

    @classmethod
    def create(cls, work: Path) -> CompactFixture:
        if not SIDECAR.is_file():
            raise NativeUnavailable(f"{SIDECAR} is missing: the compact fixture needs the sdk/c sources of this repository")
        return cls(work, build_native(work / "build"))

    def gateway_config(self) -> str:
        assert self.state_dir is not None
        lines = ["[gateway]", 'id = "compact-conformance"', f'state_dir = "{self.state_dir}"',
                 f'listen = ["unix:{self.work / "gateway.sock"}"]', "connect_wait_ms = 10000", ""]
        for name, wire in self.wires.items():
            lines += ["[[upstream]]", f'name = "{name}"', 'type = "compact"', f'port = "{wire.url}"', f'sidecar = "{SIDECAR}"',
                      "reply_timeout_ms = 250", "retries = 3", "poll_interval_ms = 300", "probe_interval_ms = 400",
                      "probe_misses = 2", "hello_timeout_ms = 300", ""]
        return "\n".join(lines)

    async def start(self) -> None:
        """Start the endpoints and their wires (the runner starts the gateway process afterwards, from :attr:`config_path`)."""
        if self.started:
            return
        self.state_dir = self.work / "gateway-state"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        for name, persistent in FLAVOURS.items():
            folder = self.work / name
            folder.mkdir(exist_ok=True)
            self.endpoints[name] = NativeEndpoint(self.binaries["sim_bench"], folder, epoch=persistent)
            self.wires[name] = Wire(self.endpoints[name], str(self.work / f"{name}.sock"))
            await self.wires[name].start()
        assert self.config_path is not None
        self.config_path.write_text(self.gateway_config())
        self.started = True

    async def raw(self, *args: str, epoch: bool = True) -> RawEndpoint:
        """A fresh ``sim_bench`` (extra command-line ``args``) on its own serial line, outside the gateway."""
        folder = Path(tempfile.mkdtemp(prefix="raw-", dir=self.work))
        endpoint = NativeEndpoint(self.binaries["sim_bench"], folder, *args, epoch=epoch)
        raw = RawEndpoint(endpoint, None)  # type: ignore[arg-type]
        await raw._attach(endpoint)
        self.raws.append(raw)
        return raw

    def clear_faults(self) -> None:
        for wire in self.wires.values():
            wire.clear_rules()

    async def aclose(self) -> None:
        for raw in self.raws:
            with contextlib.suppress(Exception):
                await raw.close()
        for wire in self.wires.values():
            with contextlib.suppress(Exception):
                await wire.close()


__all__ = ["CompactFixture", "DEVICE_ID", "FLAVOURS", "RawEndpoint", "SIDECAR"]
