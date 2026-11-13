"""TypeScript SDK server versus Python SDK server, same conformance-device action, same Python client, same unix socket.

Each SDK ships a ``conformance-device`` that mirrors the other device for device and number for number; the action is
``axis-1`` ``pulse(count=1)`` (a 1 ms hold in both) with ``waitMs=1000`` and a unique ``operation_key``. Cases: ``durable``
(the default store of each: SQLite WAL with a barrier on the intent for Python; an append-only JSON-lines journal with ``fsync``
for TypeScript) and ``memory`` (``--memory``: no persistence). Sequential, one client. Skipped (and said so in the result) when
no Node 20+ is available.
"""

from __future__ import annotations

import asyncio
import os
import secrets
import subprocess
import sys
import tempfile

from common import ROOT, SDK_PY, Context, invoke_stats, timed
from bhms.client.client import Client

NAME = "ts_vs_py"
TS_DEVICE = ROOT / "sdk" / "typescript" / "dist" / "src" / "testing" / "conformanceDevice.js"


async def connect_when_up(url: str, proc: subprocess.Popen) -> Client:
    for _ in range(400):
        if proc.poll() is not None:
            raise RuntimeError(f"server exited with {proc.returncode}")
        if os.path.exists(url[len("unix:"):]):
            try:
                return await Client.connect(url, timeout=60)
            except OSError:
                pass
        await asyncio.sleep(0.05)
    raise RuntimeError("server did not start")


async def case(ctx: Context, sdk: str, memory: bool, n: int) -> dict:
    tag = secrets.token_hex(3)
    env = {**os.environ, "PYTHONPATH": f"{SDK_PY / 'src'}{os.pathsep}{os.environ.get('PYTHONPATH', '')}"}
    with tempfile.TemporaryDirectory(dir=ctx.state_root) as tmp:
        url = f"unix:{tmp}/s.sock"
        flags = ["--memory"] if memory else ["--state-dir", tmp]
        command = ([sys.executable, "-m", "bhms.testing.conformance_device"] if sdk == "python"
                   else [ctx.node, str(TS_DEVICE)]) + [url, *flags]
        proc = subprocess.Popen(command, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            client = await connect_when_up(url, proc)
            try:
                async def call(i: int) -> None:
                    res = await client.actions_invoke("axis-1", "pulse", {"count": 1}, operation_key=f"{tag}-{i}", wait_ms=1000)
                    if res.operation.state != "completed":
                        raise RuntimeError(res.operation.state)

                row: dict = {}
                with timed(row):
                    row.update(await invoke_stats(call, n, 1, warmup=ctx.n(30, 200)))
                return row
            finally:
                await client.close()
        finally:
            proc.terminate()
            try:
                proc.wait(30)
            except subprocess.TimeoutExpired:
                proc.kill()


async def run(ctx: Context) -> dict:
    if not ctx.node or not TS_DEVICE.exists():
        return {"skipped": f"node={ctx.node!r}, built TS SDK present={TS_DEVICE.exists()} (build: cd sdk/typescript && npm ci && npx tsc)"}
    n = ctx.n(100, 1000)
    out: dict = {"n": n, "action": "axis-1.pulse(count=1) waitMs=1000"}
    for memory in (False, True):
        for sdk in ("python", "typescript"):
            out[f"{sdk}/{'memory' if memory else 'durable'}"] = await case(ctx, sdk, memory, n)
    return out
