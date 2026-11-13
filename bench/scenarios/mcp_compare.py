"""The same action two ways: native BHMS client versus an MCP client through the MCP bridge.

Both drive the same durable device server (unix socket, ``dispatch`` durability, ``set_point``, ``waitMs=1000``, a unique
``operation_key`` per call):

* ``native``: ``bhms.client.Client`` straight to the server;
* ``mcp_bridge``: the official ``mcp`` Python client over stdio to ``python -m bhms mcp unix:<socket>`` (the bridge process
  holds its own BHMS client to the server), calling the ``bhms_invoke`` tool. The tool path adds the bridge's description fetch
  (cached after the first call), argument validation against the action schema, an extra process hop, MCP JSON-RPC framing
  in both directions and result rendering (text summary plus structured content).

Also reports the size of the tool result text the agent's context receives (``result_text_bytes``), since for an agent the
cost of a call is tokens as much as time.
"""

from __future__ import annotations

import os
import secrets
import sys
import time

from common import SDK_PY, Context, device_server, invoke_stats, timed
from bhms.client.client import Client

NAME = "mcp_compare"


async def run(ctx: Context) -> dict:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    n = ctx.n(100, 1000)
    tag = secrets.token_hex(3)
    out: dict = {"n": n}
    async with device_server(ctx, "dispatch", "unix") as (target, _):
        async with await Client.connect(target, timeout=60) as client:
            async def native(i: int) -> None:
                res = await client.actions_invoke("dev-1", "set_point", {"value": abs(i)}, operation_key=f"n{tag}-{i}", wait_ms=1000)
                if res.operation.state != "completed":
                    raise RuntimeError(res.operation.state)

            row: dict = {}
            with timed(row):
                row.update(await invoke_stats(native, n, 1, warmup=ctx.n(30, 100), label="mcp__native"))
            out["native"] = row
        env = {**os.environ, "PYTHONPATH": f"{SDK_PY / 'src'}{os.pathsep}{os.environ.get('PYTHONPATH', '')}"}
        params = StdioServerParameters(command=sys.executable, args=["-m", "bhms", "mcp", target], env=env)
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            sizes: list[int] = []

            async def bridged(i: int) -> None:
                res = await session.call_tool("bhms_invoke", {"device_id": "dev-1", "action": "set_point",
                                                              "arguments": {"value": abs(i)}, "operation_key": f"m{tag}-{i}",
                                                              "wait_ms": 1000})
                if getattr(res, "isError", getattr(res, "is_error", False)):  # mcp 1.x / 2.x spelling
                    raise RuntimeError(res.content[0].text if res.content else "tool error")
                sizes.append(sum(len(c.text.encode()) for c in res.content if hasattr(c, "text")))

            await bridged(-10**6)  # first call fetches and caches the description
            row = {}
            with timed(row):
                row.update(await invoke_stats(bridged, n, 1, warmup=ctx.n(30, 100), label="mcp__bridge"))
            row["result_text_bytes"] = sizes[-1]
            out["mcp_bridge"] = row
            started = time.perf_counter()
            await session.list_tools()
            out["mcp_list_tools_ms"] = round((time.perf_counter() - started) * 1000, 3)
    out["bridge_overhead_p50_ms"] = round(out["mcp_bridge"]["p50_ms"] - out["native"]["p50_ms"], 3)
    return out
