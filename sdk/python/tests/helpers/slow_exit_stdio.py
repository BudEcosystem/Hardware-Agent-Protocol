"""Child for leak tests: a BHMS stdio server that does not exit when its stdin closes (it must be terminated)."""

import asyncio
import signal
import sys

from bhms.jsonrpc.dispatcher import Server


async def main() -> None:
    server = Server(server_info={"name": "slow-exit", "version": "0.0.1"}, epoch="e")
    await server.serve_stdio()
    await asyncio.sleep(float(sys.argv[1]) if len(sys.argv) > 1 else 30.0)  # ignores EOF for this long


signal.signal(signal.SIGTERM, signal.SIG_IGN)  # and ignores SIGTERM: only SIGKILL ends it
asyncio.run(main())
