"""What the runner connects to, and how it starts, restarts and stops it.

``resolve(spec)`` accepts

* ``stdio:<command>``, ``unix:<path>``, ``tcp://host:port``, ``ws[s]://host:port``, ``http[s]://host:port/bhms``: a server
  that already exists (``--token`` or ``BHMS_TOKEN`` is the bearer token);
* a path to a server script ``*.py`` (spawned over stdio) or a gateway configuration ``*.toml`` (``python -m bhms.gateway``
  with ``listen = ["stdio"]`` is not assumed: the file is run as written, so list ``"stdio"`` in it);
* the built-in fixtures ``conformance-device`` (``:stdio`` default, ``:ws``, ``:unix``), ``gateway`` (``:ws`` default, ``:stdio``,
  ``:http``: a gateway fronting two conformance devices as ``u0`` and ``u1``, with the principals of :data:`ROLES` on ws/http)
  and ``agent-bridge`` (the MCP bridge over a websocket conformance device).

Spawned targets are *controllable*: :meth:`Target.restart` stops (or kills) and starts the server again on the same state
directory, which is what the durability and crash checks need. A stdio server dies with its connection, so extra
connections (``connect_extra``) are separate processes with their own in-memory state; checks that need two connections to
one server require ``persistent`` (a socket server).

Thread-safety: one event loop.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
import signal
import socket
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from bhms.testing.gateway_fixture import NAMESPACES, ROLES, TOKEN_PREFIX, Role, gateway_toml
from bhms.transport import connect_tcp, connect_unix, connect_websocket, spawn_stdio
from bhms.transport.base import Transport, TransportClosed

URL_PREFIXES = ("unix:", "tcp://", "ws://", "wss://", "http://", "https://")
BUILTINS = ("conformance-device", "conformance-device:stdio", "conformance-device:ws", "conformance-device:unix",
            "gateway", "gateway:stdio", "gateway:http", "agent-bridge", "mcp:<bridge command>")


class TargetError(Exception):
    """The target cannot be resolved or started (printed as a message, never a traceback)."""


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def connect_url(url: str, token: str | None) -> Transport:
    """Open a transport to ``url`` (retried briefly: a freshly spawned server may not accept yet)."""
    last: Exception | None = None
    for _ in range(100):
        try:
            if url.startswith("unix:"):
                path = url[5:]
                return await connect_unix(path[2:] if path.startswith("//") else path)
            if url.startswith("tcp://"):
                host, _, port = url[6:].rstrip("/").rpartition(":")
                return await connect_tcp(host.strip("[]"), int(port))
            if url.startswith(("ws://", "wss://")):
                return await connect_websocket(url, token=token)
            if url.startswith(("http://", "https://")):
                from urllib.parse import urlsplit

                from bhms.transport.http import connect_http

                parts = urlsplit(url)  # an HTTP transport only connects on its first POST: wait until the port accepts
                with contextlib.closing(socket.create_connection((parts.hostname or "127.0.0.1", parts.port or 80), timeout=1)):
                    pass
                return await connect_http(url, token=token)
            raise TargetError(f"unsupported target {url!r}")
        except (OSError, TransportClosed) as exc:
            last = exc
            await asyncio.sleep(0.1)
    raise TargetError(f"cannot connect to {url}: {last}")


@dataclass
class Target:
    """A server under test. ``kind`` is the transport kind (stdio, unix, tcp, ws, http); ``persistent`` means the server
    outlives a connection; ``controllable`` means the runner started it and can restart it."""

    spec: str
    kind: str
    token: str | None = None
    url: str | None = None
    command: list[str] | None = None
    extra_command: list[str] | None = None
    state_dir: Path | None = None
    env: dict[str, str] = field(default_factory=dict)
    log_path: Path | None = None
    work_dir: Path | None = None
    simulated: bool | None = None
    """True for fixtures the runner starts; None (unknown) for a target it did not start."""
    tokens: dict[str, str] = field(default_factory=dict)
    """role -> bearer token of the principals a built-in gateway fixture defines (see :data:`ROLES`)."""
    config_path: Path | None = None
    flavour: str = ""
    is_gateway: bool = False
    """A gateway fixture (explicit metadata; the runner never guesses from device ids)."""
    conformance_devices: tuple[str, ...] = ()
    """Device ids the fixture asserts to be conformance devices (a gateway does not forward the extension)."""
    upstreams: dict[str, Target] = field(default_factory=dict)
    """Gateway fixture: the device servers behind it, by namespace, started by the runner."""
    bridge_command: list[str] | None = None
    """kind ``mcp``: the MCP bridge process the runner talks to (stdio)."""
    device: Target | None = None
    """kind ``mcp``: the BHMS target the bridge fronts (the runner also talks to it for counters and faults)."""
    notes: list[str] = field(default_factory=list)
    _process: asyncio.subprocess.Process | None = field(default=None, repr=False)
    _base: Transport | None = field(default=None, repr=False)
    _extras: list[Transport] = field(default_factory=list, repr=False)

    @property
    def controllable(self) -> bool:
        return self.command is not None

    @property
    def persistent(self) -> bool:
        return self.kind != "stdio"

    @property
    def loopback(self) -> bool:
        if self.kind in ("stdio", "unix"):
            return True
        host = (self.url or "").split("://", 1)[-1].split("/", 1)[0].rpartition(":")[0].strip("[]")
        return host in ("127.0.0.1", "localhost", "::1")

    @property
    def command_line(self) -> str:
        return " ".join(self.command) if self.command else self.spec

    # ------------------------------------------------------------------ connecting

    def _stderr(self) -> Any:
        if self.log_path is None:
            return None
        return open(self.log_path, "ab")  # noqa: SIM115  (handed to the child; closed with the process)

    async def _spawn_stdio(self, command: list[str]) -> Transport:
        stderr = self._stderr()
        try:
            return await spawn_stdio(command, env=self._environment(), stderr=stderr, cwd=str(self.work_dir) if self.work_dir else None)
        finally:
            if stderr is not None:
                stderr.close()

    def _environment(self) -> dict[str, str]:
        return {**os.environ, "PYTHONUNBUFFERED": "1", **self.env}

    async def _start_server(self) -> None:
        assert self.command is not None and self.url is not None
        stderr = self._stderr()
        try:
            self._process = await asyncio.create_subprocess_exec(
                *self.command, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.DEVNULL, stderr=stderr,
                env=self._environment(), cwd=str(self.work_dir) if self.work_dir else None)
        finally:
            if stderr is not None:
                stderr.close()

    async def open_base(self) -> Transport:
        """The connection the runner uses for most checks (starts the server first when the runner owns it). For an agent
        bridge it is the connection to the device the bridge fronts."""
        for upstream in self.upstreams.values():
            if upstream._process is None:
                await upstream._start_server()
                await upstream._ready()
        if self.kind == "mcp":
            if self.device is None:
                raise TargetError("an agent target needs the BHMS target it fronts: pass --device")
            return await self.device.open_base()
        if self.kind == "stdio":
            if self.command is None:
                raise TargetError("a stdio target needs a command")
            self._base = await self._spawn_stdio(self.command)
            return self._base
        if self.command is not None and self._process is None:
            await self._start_server()
        assert self.url is not None
        self._base = await connect_url(self.url, self.token)
        return self._base

    async def connect_extra(self, role: str | None = None) -> Transport:
        """A further connection (``role`` picks the principal of a gateway fixture). For stdio this is a new server process
        (in-memory state of its own)."""
        if self.kind == "stdio":
            command = self.extra_command or self.command
            if command is None:
                raise TargetError("cannot open a second stdio connection without a command")
            transport = await self._spawn_stdio(command)
        else:
            assert self.url is not None
            if role is not None and role not in self.tokens:
                raise TargetError(f"this target defines no principal {role!r}")
            transport = await connect_url(self.url, self.tokens[role] if role else self.token)
        self._extras.append(transport)
        return transport

    async def restart(self, *, kill: bool = False) -> Transport:
        """Stop (SIGKILL when ``kill``) and start the server again on the same state; returns the new base connection."""
        if not self.controllable:
            raise TargetError("the runner did not start this target and cannot restart it")
        if self.kind == "stdio":
            await self._stop_stdio(kill)
            return await self.open_base()
        if self._base is not None:
            with contextlib.suppress(Exception):
                await self._base.close()
        await self._stop_process(kill)
        if self.kind == "unix" and self.url:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(self.url[5:].removeprefix("//"))
        return await self.open_base()

    async def _stop_stdio(self, kill: bool) -> None:
        base = self._base
        process = getattr(base, "process", None)
        if base is None:
            return
        if kill and process is not None and process.returncode is None:
            process.kill()
            await process.wait()
        with contextlib.suppress(Exception):
            await base.close()
        self._base = None

    async def _stop_process(self, kill: bool) -> None:
        process, self._process = self._process, None
        if process is None or process.returncode is not None:
            return
        if kill:
            process.kill()
        else:
            process.terminate()
        try:
            await asyncio.wait_for(process.wait(), 10)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()

    def server_pid(self) -> int | None:
        """The process id of the server the runner started (None when it did not start it)."""
        if self._process is not None:
            return self._process.pid
        process = getattr(self._base, "process", None)
        return process.pid if process is not None else None

    async def reload_policy(self, principals: dict[str, Role]) -> None:
        """Rewrite the principals of the gateway configuration and send SIGHUP (the gateway applies it without a restart,
        BHMS-SEC-012)."""
        if self.config_path is None or self._process is None:
            raise TargetError("only a gateway fixture started by the runner can reload its policy")
        urls = {ns: up.url or "" for ns, up in self.upstreams.items()}
        self.config_path.write_text(gateway_toml(self.flavour, self.url, self.state_dir, principals, urls))
        self._process.send_signal(signal.SIGHUP)
        await asyncio.sleep(0.5)

    async def wipe_state(self) -> None:
        """Delete the durable state (the server must be stopped)."""
        if self.state_dir is not None:
            shutil.rmtree(self.state_dir, ignore_errors=True)
            self.state_dir.mkdir(parents=True, exist_ok=True)

    async def stop_base(self, *, kill: bool = False) -> None:
        """Stop the server without starting it again (for restart checks that wipe or alter state in between)."""
        if self.kind == "stdio":
            await self._stop_stdio(kill)
            return
        if self._base is not None:
            with contextlib.suppress(Exception):
                await self._base.close()
        await self._stop_process(kill)

    async def exit_after_stdin_eof(self, timeout: float = 5.0) -> bool | None:
        """BHMS-TRN-011: close the base connection's stdin and report whether the server process exited; ``None``
        when the target is not a spawned stdio server."""
        base = self._base
        process = getattr(base, "process", None)
        if self.kind != "stdio" or process is None:
            return None
        process.stdin.close()
        try:
            await asyncio.wait_for(process.wait(), timeout)
        except asyncio.TimeoutError:
            return False
        return True

    async def _ready(self) -> None:
        """Wait until the server this target started accepts connections (a probe connection, closed at once)."""
        probe = await connect_url(self.url or "", self.token)
        await probe.close()

    async def aclose(self) -> None:
        for upstream in self.upstreams.values():
            await upstream.aclose()
        if self.device is not None:
            await self.device.aclose()
        for transport in [self._base, *self._extras]:
            if transport is not None:
                with contextlib.suppress(Exception):
                    await transport.close()
        self._extras.clear()
        await self._stop_process(False)
        if self.work_dir is not None and self.notes_owned:
            shutil.rmtree(self.work_dir, ignore_errors=True)

    notes_owned: bool = False


# ---------------------------------------------------------------------- resolution


def resolve(spec: str, *, token: str | None = None, keep_state: str | None = None) -> Target:
    """Turn a command-line target into a :class:`Target` (see the module docstring)."""
    token = token or os.environ.get("BHMS_TOKEN")
    if spec == "conformance-device" or spec.startswith("conformance-device:"):
        return _conformance_device(spec.partition(":")[2] or "stdio", keep_state)
    if spec == "agent-bridge":
        return _agent_bridge(keep_state)
    if spec.startswith("mcp:"):
        import shlex

        return Target(spec, "mcp", bridge_command=shlex.split(spec[4:]))
    if spec == "gateway" or spec.startswith("gateway:"):
        return _gateway_fleet(spec.partition(":")[2] or "ws", keep_state)
    if spec.startswith("stdio:"):
        import shlex

        return Target(spec, "stdio", token, command=shlex.split(spec[6:]))
    if spec.startswith(URL_PREFIXES):
        kind = "unix" if spec.startswith("unix:") else "tcp" if spec.startswith("tcp://") else "ws" if spec.startswith("ws") else "http"
        return Target(spec, kind, token, url=spec)
    path = Path(spec).expanduser()
    if path.is_file() and path.suffix == ".py":
        return Target(spec, "stdio", token, command=[sys.executable, str(path.resolve())], work_dir=path.resolve().parent)
    if path.is_file() and path.suffix == ".toml":
        return Target(spec, "stdio", token, command=[sys.executable, "-m", "bhms.gateway", str(path.resolve())],
                      work_dir=path.resolve().parent)
    raise TargetError(f"{spec!r} is neither a built-in fixture ({', '.join(BUILTINS)}) nor a URL, a server .py or a gateway .toml")


def _workspace(prefix: str, keep: str | None) -> Path:
    if keep:
        path = Path(keep).expanduser().resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path
    return Path(tempfile.mkdtemp(prefix=f"bhms-conf-{prefix}-"))


def _device_command(*extra: str) -> list[str]:
    return [sys.executable, "-m", "bhms.testing.conformance_device", *extra]


def _conformance_device(flavour: str, keep: str | None) -> Target:
    work = _workspace("device", keep)
    state = work / "state"
    state.mkdir(exist_ok=True)
    log = work / "server.log"
    if flavour == "stdio":
        target = Target("conformance-device", "stdio", command=_device_command("--state-dir", str(state)),
                        extra_command=_device_command("--memory"), state_dir=state)
    elif flavour == "ws":
        url = f"ws://127.0.0.1:{free_port()}"
        target = Target("conformance-device:ws", "ws", url=url, command=_device_command(url, "--state-dir", str(state)), state_dir=state,
                        token=TOKEN_PREFIX + "admin", env={"BHMS_TOKEN": TOKEN_PREFIX + "admin"})
    elif flavour == "unix":
        url = f"unix:{work / 'device.sock'}"
        target = Target("conformance-device:unix", "unix", url=url, command=_device_command(url, "--state-dir", str(state)),
                        state_dir=state)
    else:
        raise TargetError(f"unknown conformance-device flavour {flavour!r} (stdio, ws, unix)")
    target.work_dir, target.log_path, target.notes_owned, target.simulated = work, log, keep is None, True
    return target


def _gateway_fleet(flavour: str, keep: str | None) -> Target:
    """A gateway over two conformance devices that the runner also starts (on Unix sockets) and can reach directly."""
    if flavour not in ("ws", "stdio", "http"):
        raise TargetError(f"unknown gateway flavour {flavour!r} (ws, stdio, http)")
    work = _workspace("gateway", keep)
    state = work / "gateway-state"
    state.mkdir(exist_ok=True)
    upstreams: dict[str, Target] = {}
    urls: dict[str, str] = {}
    for namespace in NAMESPACES:
        url = f"unix:{work / (namespace + '.sock')}"
        urls[namespace] = url
        upstreams[namespace] = Target(f"upstream:{namespace}", "unix", url=url, work_dir=work, log_path=work / f"{namespace}.log",
                                      command=_device_command(url, "--memory", "--gateway"))
    port = free_port()
    url = None if flavour == "stdio" else (f"ws://127.0.0.1:{port}" if flavour == "ws" else f"http://127.0.0.1:{port}/bhms")
    config = work / "gateway.toml"
    config.write_text(gateway_toml(flavour, url, state, ROLES, urls))
    command = [sys.executable, "-m", "bhms.gateway", str(config)]
    tokens = {role: TOKEN_PREFIX + role for role in ROLES}
    asserted = tuple(f"{ns}/{name}" for ns in NAMESPACES for name in ("axis-1", "pump-1"))
    common = dict(state_dir=state, work_dir=work, log_path=work / "gateway.log", notes_owned=keep is None, config_path=config,
                  flavour=flavour, is_gateway=True, simulated=True, conformance_devices=asserted, upstreams=upstreams)
    if flavour == "stdio":
        spare = work / "gateway-spare.toml"
        (work / "spare-state").mkdir(exist_ok=True)
        spare.write_text(gateway_toml("stdio", None, work / "spare-state", ROLES, urls))
        return Target(f"gateway:{flavour}", "stdio", command=command, extra_command=[sys.executable, "-m", "bhms.gateway", str(spare)],
                      **common)
    return Target(f"gateway:{flavour}", "ws" if flavour == "ws" else "http", token=tokens["admin"], url=url, command=command,
                  tokens=tokens, **common)


def _agent_bridge(keep: str | None) -> Target:
    """The Python MCP bridge (``bhms mcp``) in front of a WebSocket conformance device."""
    device = _conformance_device("ws", keep)
    command = [sys.executable, "-m", "bhms", "mcp", device.url or "", "--token", device.token or ""]
    return Target("agent-bridge", "mcp", bridge_command=command, device=device, work_dir=device.work_dir)
