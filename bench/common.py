"""Shared plumbing of the BHMS benchmark harness: environment capture, load recording, server processes, the fsync probe.

Latency statistics and the concurrent measuring loop are the ones of ``bhms bench`` (``bhms.cli.bench.measure`` and
``summarize``), so the harness and the CLI report identically (nearest-rank percentiles, failures counted not hidden). The
transport-level durability baseline (``commit_latency``) comes from ``sdk/python/benchmarks/invoke_roundtrip.py``, loaded by
path because ``benchmarks/`` is not a package.

Thread-safety: one event loop per scenario; nothing here is shared between processes.
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib.util
import json
import os
import platform
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

from bhms.cli.bench import measure, summarize

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "bench"
SDK_PY = ROOT / "sdk" / "python"
DEVICE_SERVER = BENCH / "servers" / "device_server.py"
PING_SERVER = BENCH / "servers" / "ping_server.py"
TOKEN = "bench-token"

__all__ = ["Context", "ServerProc", "measure", "summarize", "load_sdk_benchmark", "environment", "fsync_samples", "spawn_server",
           "load_probe", "timed", "stats_ms", "record", "SAMPLES"]


def load_sdk_benchmark(name: str) -> ModuleType:
    """Import ``sdk/python/benchmarks/<name>.py`` (Task 4/5's benchmarks) without copying their logic."""
    path = SDK_PY / "benchmarks" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"sdk_bench_{name}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@dataclass
class Context:
    """What a scenario receives: sizes (``quick`` or ``full``), where durable state lives, tool locations."""

    quick: bool
    state_root: Path
    out_dir: Path
    node: str | None = None
    simavr_cmd: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def n(self, quick: int, full: int) -> int:
        return quick if self.quick else full


SAMPLES: dict[str, list[float]] = {}


def record(label: str, samples: list[float]) -> None:
    """Keep the raw per-sample latencies (ms, in arrival order) of one cell; ``run.py`` writes them gzipped to ``samples/``."""
    key, n = label, 1
    while key in SAMPLES:
        n += 1
        key = f"{label}#{n}"
    SAMPLES[key] = [round(x, 4) for x in samples]


def stats_ms(samples: list[float], elapsed_s: float, failures: int = 0, label: str | None = None) -> dict[str, float | int]:
    """``bhms bench``'s summary, rounded for the JSON files; with ``label`` the raw samples are kept (see :func:`record`)."""
    if label:
        record(label, samples)
    return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in summarize(samples, elapsed_s, failures).items()}


def load_probe() -> dict[str, float]:
    one, five, fifteen = os.getloadavg()
    return {"load1": one, "load5": five, "load15": fifteen, "t": time.time()}


@contextlib.contextmanager
def timed(record: dict[str, Any], key: str = "load"):  # noqa: ANN201
    """Record the load average before and after a measurement into ``record[key]``."""
    before = load_probe()
    try:
        yield
    finally:
        record[key] = {"before": before, "after": load_probe()}


def _read(path: str) -> str:
    try:
        return Path(path).read_text().strip()
    except OSError:
        return ""


def environment(state_root: Path, node_binary: str | None = None) -> dict[str, Any]:
    """Hardware, OS, interpreter and filesystem facts for the report header."""
    cpu = next((ln.split(":", 1)[1].strip() for ln in _read("/proc/cpuinfo").splitlines() if ln.startswith("model name")), "")
    mem_kb = next((int(ln.split()[1]) for ln in _read("/proc/meminfo").splitlines() if ln.startswith("MemTotal")), 0)
    fs = subprocess.run(["findmnt", "-n", "-o", "SOURCE,FSTYPE,OPTIONS", "-T", str(state_root)], capture_output=True, text=True)
    sha = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    try:
        from importlib.metadata import version

        pkgs = {name: version(name) for name in ("mcp", "websockets", "aiohttp", "orjson", "pydantic", "bhms")}
    except Exception:  # noqa: BLE001 - a missing optional package is reported as absent
        pkgs = {}
    node = node_binary or shutil.which("node")
    node_version = subprocess.run([node, "--version"], capture_output=True, text=True).stdout.strip() if node else None
    return {"host": platform.node(), "cpu": cpu, "cpus_online": os.cpu_count(), "affinity": sorted(os.sched_getaffinity(0)),
            "mem_gb": round(mem_kb / 1048576, 1), "kernel": platform.release(), "os": _read("/etc/os-release").split("\n")[0],
            "python": platform.python_version(), "node": node_version, "packages": pkgs, "git": sha,
            "state_dir_fs": fs.stdout.strip(), "state_root": str(state_root), "load": load_probe(),
            "date": time.strftime("%Y-%m-%dT%H:%M:%S%z")}


def fsync_samples(directory: Path, n: int, *, size: int = 600, sync: str = "fdatasync") -> list[float]:
    """Latency (ms) of appending ``size`` bytes to a file and ``fdatasync``/``fsync``ing it, on ``directory``'s filesystem.

    This is the cost floor of one durable intent record (a WAL frame is of this order): the budget is stated relative to it.
    """
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"fsync-probe-{os.getpid()}.dat"
    flush = os.fdatasync if sync == "fdatasync" else os.fsync
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    out: list[float] = []
    try:
        payload = b"x" * size
        for _ in range(n + 20):
            started = time.perf_counter()
            os.write(fd, payload)
            flush(fd)
            out.append((time.perf_counter() - started) * 1000)
    finally:
        os.close(fd)
        path.unlink(missing_ok=True)
    return out[20:]


class ServerProc:
    """A ``device_server.py`` (or ``ping_server.py``) child: spawn, wait for ``ready``, SIGTERM/SIGKILL, collect output."""

    def __init__(self, proc: subprocess.Popen[str], url: str | None) -> None:
        self.proc, self.url = proc, url

    def kill(self) -> None:
        """SIGKILL: the crash of the crash-recovery scenario."""
        self.proc.send_signal(signal.SIGKILL)
        self.proc.wait()

    def stop(self) -> str:
        if self.proc.poll() is None:
            self.proc.terminate()
        try:
            out, _ = self.proc.communicate(timeout=60)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            out, _ = self.proc.communicate()
        return out or ""


def spawn_server(script: Path, args: list[str], *, url: str | None, wait_ready: bool = True) -> ServerProc:
    """Start ``script`` with this interpreter; blocks until it prints ``ready`` (listening servers only)."""
    env = {**os.environ, "PYTHONPATH": f"{SDK_PY / 'src'}{os.pathsep}{os.environ.get('PYTHONPATH', '')}", "PYTHONUNBUFFERED": "1"}
    proc = subprocess.Popen([sys.executable, str(script), *args], stdout=subprocess.PIPE, text=True, env=env)
    if wait_ready and url is not None:
        assert proc.stdout is not None
        line = proc.stdout.readline().strip()
        if line != "ready":
            proc.kill()
            raise RuntimeError(f"{script.name} {args} did not become ready (said {line!r})")
    return ServerProc(proc, url)


@contextlib.asynccontextmanager
async def device_server(ctx: Context, durability: str, transport: str = "unix", *, devices: int = 1, queue_limit: int = 64,
                        profile: Path | None = None) -> AsyncIterator[tuple[str, ServerProc]]:
    """A running device server on a fresh state directory under ``ctx.state_root``; yields (client target, process)."""
    with tempfile.TemporaryDirectory(dir=ctx.state_root) as tmp:
        base = ["--durability", durability, "--state-dir", tmp, "--devices", str(devices), "--queue-limit", str(queue_limit)]
        if profile is not None:
            base += ["--cprofile", str(profile)]
        if transport == "unix":
            url = f"unix:{tmp}/b.sock"
            server = spawn_server(DEVICE_SERVER, ["--listen", url, *base], url=url)
            target = url
        elif transport == "ws":
            port = free_port()
            url = f"ws://127.0.0.1:{port}"
            server = spawn_server(DEVICE_SERVER, ["--listen", url, *base], url=url)
            target = url
        elif transport == "stdio":
            server = None
            target = "stdio:" + " ".join([sys.executable, str(DEVICE_SERVER), *base])
        else:
            raise ValueError(transport)
        try:
            yield target, server  # type: ignore[misc]
        finally:
            if server is not None:
                server.stop()


def free_port() -> int:
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def token_for(target: str) -> str | None:
    return TOKEN if target.startswith("ws://") else None


async def invoke_stats(call: Callable[[int], Any], n: int, concurrency: int, warmup: int = 100,
                       label: str | None = None) -> dict[str, float | int]:
    """Warm up, then measure ``call(i)`` ``n`` times with ``concurrency`` in flight (``bhms bench``'s loop)."""
    if warmup:
        await measure(lambda i: call(-1 - i), warmup, concurrency)
    samples, elapsed, failures = await measure(call, n, concurrency)
    if not samples:
        raise RuntimeError("every call failed")
    return stats_ms(samples, elapsed, failures, label)


def dump(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, default=str))


async def run_blocking(fn: Callable[..., Any], *args: Any) -> Any:
    return await asyncio.get_running_loop().run_in_executor(None, lambda: fn(*args))
