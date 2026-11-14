"""Bare JSON-RPC server for the transport-only scenario: ``x-test/ping`` over the transport named on the command line.

``python ping_server.py unix:/p | tcp://127.0.0.1:P | ws://127.0.0.1:P`` (prints ``ready``), or no argument for stdio. No device
runtime and no journal: this isolates framing, JSON and the session machinery of each transport. (``DeviceServer`` refuses TCP
because TCP carries no credential, so TCP can only be measured at this level.)
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# the checked-out SDK, also when started as a stdio command (which does not get the harness's PYTHONPATH)
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "sdk" / "python" / "src"))

from bhms.jsonrpc.dispatcher import Server
from bhms.transport import serve_tcp, serve_unix, serve_websocket


async def main(url: str | None) -> None:
    server = Server(server_info={"name": "bench-ping", "version": "0"})

    async def ping(params, ctx):  # noqa: ANN001
        return {"resultType": "complete", "n": params.get("n", 0)}

    server.register("x-test/ping", ping)
    if url is None:
        await server.serve_stdio()
        return
    if url.startswith("unix:"):
        await serve_unix(url[5:], server.handle_connection)
    else:
        host, _, port = url.split("://", 1)[1].rpartition(":")
        await (serve_tcp if url.startswith("tcp") else serve_websocket)(host, int(port), server.handle_connection)
    print("ready", flush=True)
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else None))
