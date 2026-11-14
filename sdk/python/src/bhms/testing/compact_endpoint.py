"""Native BHMS-Compact endpoints and a fault-injecting wire, for the bridge tests and the conformance fixture.

* :func:`build_native` builds the C library's host simulators with cmake (``sdk/c``: ``sim_device`` is the LedAnalog
  example, ``sim_bench`` a richer endpoint with asynchronous work, cancellation, stop, fences, faults and a
  disconnectable sensor), or finds binaries named by ``BHMS_SIM_DEVICE`` / ``BHMS_SIM_BENCH``.
* :class:`NativeEndpoint` runs one such binary on a socket pair ("the serial port") and can be killed and started again
  with the same persistent-epoch file, which is how a board reboots.
* :class:`Wire` sits between a gateway bridge and the endpoint on a Unix socket (``port = "unix:<path>"``), parses the
  frames in both directions and can drop, corrupt or hold chosen ones, sever the link and reboot the endpoint, so lost
  replies, silent resets and corrupt frames are provoked deterministically. Every frame it saw is in :attr:`Wire.log`.

Example::

    bins = build_native(tmp_path / "c")
    endpoint = NativeEndpoint(bins["sim_bench"], tmp_path, epoch=True)
    wire = Wire(endpoint, str(tmp_path / "wire.sock"))
    await wire.start()
    wire.drop("to_gateway", match=lambda m: isinstance(m, Result))      # the next RESULT never arrives

Thread-safety: one event loop.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
import socket
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bhms.transport import compact as cp
from bhms.transport import hm_frame

REPO = Path(__file__).resolve().parents[5]
SDK_C = REPO / "sdk" / "c"
TO_DEVICE, TO_GATEWAY = "to_device", "to_gateway"


class NativeUnavailable(RuntimeError):
    """No native toolchain (cmake and a C compiler) and no prebuilt simulator: the native tests are skipped."""


def build_native(build_dir: Path) -> dict[str, Path]:
    """The host simulators of ``sdk/c`` as ``{"sim_device": path, "sim_bench": path}``; builds them once into
    ``build_dir`` unless ``BHMS_SIM_DEVICE`` and ``BHMS_SIM_BENCH`` already name them."""
    given = {"sim_device": os.environ.get("BHMS_SIM_DEVICE"), "sim_bench": os.environ.get("BHMS_SIM_BENCH")}
    if all(given.values()):
        return {name: Path(path) for name, path in given.items() if path}
    if shutil.which("cmake") is None or not (shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")):
        raise NativeUnavailable("cmake and a C compiler are needed to build sdk/c (or set BHMS_SIM_DEVICE and BHMS_SIM_BENCH)")
    build_dir.mkdir(parents=True, exist_ok=True)
    for step in (["cmake", "-S", str(SDK_C), "-B", str(build_dir), "-DCMAKE_BUILD_TYPE=Debug", "-DBHMS_BUILD_TESTS=OFF"],
                 ["cmake", "--build", str(build_dir), "--target", "sim_device", "sim_bench", "-j", str(os.cpu_count() or 2)]):
        done = subprocess.run(step, capture_output=True, text=True)
        if done.returncode != 0:
            raise NativeUnavailable(f"building sdk/c failed:\n{done.stdout[-1500:]}\n{done.stderr[-1500:]}")
    return {name: build_dir / name for name in ("sim_device", "sim_bench")}


class NativeEndpoint:
    """A simulator process on a socket pair. ``epoch=True`` gives it a persistent boot-counter file (so it reports
    ``PERSISTENT_EPOCH`` and its epoch advances at every :meth:`start`); ``epoch=False`` has no persistent epoch."""

    def __init__(self, binary: Path, workdir: Path, *args: str, epoch: bool = True) -> None:
        self.binary, self.workdir, self.args = Path(binary), Path(workdir), list(args)
        self.epoch_file = self.workdir / "epoch.bin" if epoch else None
        self.process: subprocess.Popen[bytes] | None = None
        self.starts = 0
        self._stderr: list[Path] = []

    def start(self) -> socket.socket:
        """Boot the simulator; returns the parent end of its serial line."""
        self.stop()
        parent, child = socket.socketpair()
        self.starts += 1
        log = self.workdir / f"stderr{self.starts}.txt"
        self._stderr.append(log)
        command = [str(self.binary), *self.args]
        if self.epoch_file is not None:
            command += ["--epoch", str(self.epoch_file)]
        with log.open("wb") as err:
            self.process = subprocess.Popen(command, stdin=child.fileno(), stdout=child.fileno(), stderr=err, close_fds=True)
        child.close()
        return parent

    def stop(self) -> None:
        process, self.process = self.process, None
        if process is not None and process.poll() is None:
            process.kill()
            process.wait(5)

    def effects(self) -> list[str]:
        """What the endpoint reported doing (stderr lines of every boot, in order)."""
        lines: list[str] = []
        for path in self._stderr:
            if path.exists():
                lines += [ln for ln in path.read_text(errors="replace").splitlines() if ln.strip()]
        return lines

    def count(self, prefix: str) -> int:
        return sum(1 for line in self.effects() if line.startswith(prefix))


class ProcessStream:
    """A child process speaking compact on its stdin/stdout (a firmware simulator, or ``ssh host docker run -i ...`` to one on
    another machine): a :class:`~bhms.transport.compact.ByteStream` for ``CompactBridge(opener=...)``. Its stderr lines are
    kept in :attr:`stderr` (the simulators report effects there)."""

    def __init__(self, process: asyncio.subprocess.Process) -> None:
        self.process = process
        self.stderr: list[str] = []
        self._pump = asyncio.get_running_loop().create_task(self._collect())

    async def _collect(self) -> None:
        assert self.process.stderr is not None
        while line := await self.process.stderr.readline():
            self.stderr.append(line.decode(errors="replace").rstrip())

    async def read(self) -> bytes:
        assert self.process.stdout is not None
        return await self.process.stdout.read(4096)

    def write(self, data: bytes, *, urgent: bool = False) -> None:
        assert self.process.stdin is not None
        if not self.process.stdin.is_closing():
            self.process.stdin.write(data)

    async def close(self) -> None:
        if self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), 5)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()
        self._pump.cancel()
        await asyncio.gather(self._pump, return_exceptions=True)
        transport = getattr(self.process, "_transport", None)
        if transport is not None:
            transport.close()  # no ResourceWarning for a killed child


async def spawn_process_stream(command: str) -> ProcessStream:
    """Run ``command`` (shell syntax) and speak compact over its stdin/stdout."""
    process = await asyncio.create_subprocess_shell(command, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                                                    stderr=asyncio.subprocess.PIPE)
    return ProcessStream(process)


@dataclass
class Seen:
    """One frame the wire carried: direction, decoded message (None if it did not decode), exact bytes and the fate."""

    direction: str
    message: Any
    wire: bytes
    kind: int
    session: int
    delivered: bool = True


@dataclass
class _Rule:
    direction: str
    action: str  # "drop" | "corrupt"
    remaining: int
    match: Callable[[Any], bool] | None = None


class Wire:
    """The serial line between a bridge and a :class:`NativeEndpoint`, with faults; see the module docstring."""

    def __init__(self, endpoint: NativeEndpoint, path: str, *, log_limit: int | None = None) -> None:
        """``log_limit`` keeps only the newest frames in :attr:`log` (``None``: all, for tests that inspect them)."""
        self.endpoint, self.path = endpoint, path
        self.log: list[Seen] = []
        self.log_limit = log_limit
        self._rules: list[_Rule] = []
        self._held: dict[str, list[bytes]] = {}
        self._server: asyncio.AbstractServer | None = None
        self._gateway: asyncio.StreamWriter | None = None
        self._device: asyncio.StreamWriter | None = None
        self._tasks: list[asyncio.Task[None]] = []
        self._connected = asyncio.Event()

    @property
    def url(self) -> str:
        return f"unix:{self.path}"

    async def start(self) -> None:
        self._server = await asyncio.start_unix_server(self._accept, path=self.path)
        await self._attach_device()

    async def close(self) -> None:
        for writer in (self._gateway, self._device):
            if writer is not None:
                writer.close()
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        if self._server is not None:
            self._server.close()
            await asyncio.wait_for(self._server.wait_closed(), 5)
        self.endpoint.stop()

    # ------------------------------------------------------------------ plumbing

    async def _attach_device(self) -> None:
        sock = self.endpoint.start()
        reader, writer = await asyncio.open_connection(sock=sock)
        self._device = writer
        self._spawn(self._pump(reader, TO_GATEWAY))

    async def _accept(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        if self._gateway is not None:
            self._gateway.close()
        self._gateway = writer
        self._connected.set()
        await self._pump(reader, TO_DEVICE)

    def _spawn(self, coro: Any) -> None:
        self._tasks.append(asyncio.get_running_loop().create_task(coro))

    async def _pump(self, reader: asyncio.StreamReader, direction: str) -> None:
        decoder = hm_frame.Decoder()
        wire = bytearray()
        try:
            while True:
                chunk = await reader.read(4096)
                if not chunk:
                    return
                for byte in chunk:
                    event = decoder.feed(byte)
                    wire.append(byte)
                    if byte == hm_frame.FLAG:
                        if event is not None and event[0] == "frame":
                            self._carry(direction, event[1], bytes(wire))
                        wire = bytearray([byte])
        except (ConnectionError, asyncio.CancelledError):
            return

    def _carry(self, direction: str, frame: Any, wire: bytes) -> None:
        try:
            message = cp.decode(frame.payload)
        except cp.CompactError:
            message = None
        seen = Seen(direction, message, wire, frame.kind, frame.session)
        self.log.append(seen)
        if self.log_limit is not None and len(self.log) > self.log_limit:
            del self.log[: len(self.log) - self.log_limit]
        for rule in list(self._rules):
            if rule.direction == direction and rule.remaining > 0 and (rule.match is None or rule.match(message)):
                rule.remaining -= 1
                if rule.remaining == 0:
                    self._rules.remove(rule)
                if rule.action == "drop":
                    seen.delivered = False
                    return
                broken = bytearray(wire)
                broken[len(broken) // 2] ^= 0x04
                wire = bytes(broken)
                break
        if direction in self._held:
            self._held[direction].append(wire)
            seen.delivered = False
            return
        self._write(direction, wire)

    def _write(self, direction: str, wire: bytes) -> None:
        target = self._gateway if direction == TO_GATEWAY else self._device
        if target is not None and not target.is_closing():
            target.write(wire)

    # ------------------------------------------------------------------ faults

    def drop(self, direction: str, count: int = 1, match: Callable[[Any], bool] | None = None) -> None:
        """Lose the next ``count`` frames in ``direction`` (that satisfy ``match(message)``)."""
        self._rules.append(_Rule(direction, "drop", count, match))

    def corrupt(self, direction: str, count: int = 1, match: Callable[[Any], bool] | None = None) -> None:
        """Flip a bit in the next ``count`` frames in ``direction``: the receiver's FCS check must refuse them."""
        self._rules.append(_Rule(direction, "corrupt", count, match))

    def hold(self, direction: str) -> None:
        """Keep every frame in ``direction`` back until :meth:`release`."""
        self._held.setdefault(direction, [])

    def release(self, direction: str, *, deliver: bool = True) -> None:
        for wire in self._held.pop(direction, []):
            if deliver:
                self._write(direction, wire)

    def clear_rules(self) -> None:
        self._rules.clear()
        for direction in list(self._held):
            self.release(direction)

    @staticmethod
    def frame_for(message: Any, session: int, *, channel: int = cp.CHANNEL, kind: int = cp.CONTROL, sequence: int = 0) -> bytes:
        """The wire bytes of ``message`` in an ``HM`` frame (for :meth:`inject`: a frame nobody on the line sent)."""
        payload = message if isinstance(message, bytes) else message.encode()
        return hm_frame.encode(hm_frame.Frame(kind, channel, session, sequence, payload))

    def inject(self, direction: str, data: bytes) -> None:
        """Put raw bytes on the line toward ``direction`` (line noise, a foreign frame): neither side's parser may be
        confused by them."""
        self._write(direction, data)

    async def sever(self) -> None:
        """Pull the cable on the gateway side: the bridge sees end of stream and reconnects."""
        self._connected.clear()
        if self._gateway is not None:
            self._gateway.close()
            self._gateway = None

    async def reboot(self) -> None:
        """Power-cycle the endpoint (same epoch file) while the bridge's connection stays open."""
        if self._device is not None:
            self._device.close()
        await self._attach_device()

    async def wait_connected(self, timeout: float = 5.0) -> None:
        await asyncio.wait_for(self._connected.wait(), timeout)

    def sent(self, kind: type, direction: str | None = None) -> list[Seen]:
        """The frames carrying a ``kind`` message (``cp.Invoke``...) in ``direction`` (any), oldest first."""
        return [s for s in self.log if isinstance(s.message, kind) and (direction is None or s.direction == direction)]


async def serve(binary: str, socket_path: str, workdir: str, args: list[str]) -> None:
    """Run ``binary`` as an endpoint whose serial line is the Unix socket ``socket_path`` until cancelled."""
    work = Path(workdir)
    work.mkdir(parents=True, exist_ok=True)
    wire = Wire(NativeEndpoint(Path(binary), work, *args, epoch=True), socket_path, log_limit=1000)
    await wire.start()
    try:
        await asyncio.sleep(0.2)
        process = wire.endpoint.process
        if process is not None and process.poll() is not None:  # bad arguments, a missing library, an init failure
            raise RuntimeError(f"{binary} exited at once with status {process.returncode}; its stderr: "
                               f"{' | '.join(wire.endpoint.effects()[-5:]) or '(nothing)'}")
        await asyncio.Event().wait()
    finally:
        await wire.close()


def main(argv: list[str] | None = None) -> int:
    """``python -m bhms.testing.compact_endpoint BINARY SOCKET [--workdir DIR] [-- ARGS...]``: a host build of a
    BHMS-Compact endpoint (``sdk/c``'s ``sim_device``, the BHMS Arm's ``sim_arm``) served on a Unix socket, standing in
    for a board on a serial port: a gateway's compact upstream connects with ``port = "unix:SOCKET"``. The endpoint gets a
    persistent boot counter (``epoch.bin`` in the work directory) and its stderr lines go to ``stderr<N>.txt`` there.
    SIGINT or SIGTERM stops it."""
    import argparse
    import signal

    parser = argparse.ArgumentParser(prog="python -m bhms.testing.compact_endpoint", description=main.__doc__)
    parser.add_argument("binary", help="the endpoint executable (its stdin/stdout is the serial line)")
    parser.add_argument("socket", help="the Unix socket path to serve the line on")
    parser.add_argument("--workdir", default="endpoint-work", help="epoch file and stderr logs (default endpoint-work)")
    given = list(sys.argv[1:] if argv is None else argv)
    split = given.index("--") if "--" in given else len(given)
    options = parser.parse_args(given[:split])
    extra = given[split + 1:]  # after --: arguments for the endpoint itself (sim_arm --tool 1, ...)

    async def run() -> None:
        task = asyncio.ensure_future(serve(options.binary, options.socket, options.workdir, extra))
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, task.cancel)
        with contextlib.suppress(asyncio.CancelledError):
            await task

    try:
        asyncio.run(run())
    except (RuntimeError, OSError) as exc:
        print(f"bhms.testing.compact_endpoint: {exc}", file=sys.stderr)
        return 1
    return 0


__all__ = ["NativeEndpoint", "NativeUnavailable", "ProcessStream", "Seen", "TO_DEVICE", "TO_GATEWAY", "Wire", "build_native", "main",
           "serve", "spawn_process_stream"]

if __name__ == "__main__":
    raise SystemExit(main())
