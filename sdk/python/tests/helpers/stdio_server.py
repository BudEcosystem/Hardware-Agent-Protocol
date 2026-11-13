"""Child process for client tests and benchmarks: a BHMS Server on stdio with a ping method."""

import asyncio

from bhms.jsonrpc.dispatcher import Server


async def main() -> None:
    server = Server(server_info={"name": "stdio-test-server", "version": "0.0.1"}, epoch="stdio-epoch")

    async def ping(params, ctx):
        return {"resultType": "complete", "n": params.get("n", 0)}

    server.register("x-test/ping", ping)

    async def devices_list(params, ctx):
        return {"resultType": "complete", "devices": []}

    server.register("devices/list", devices_list)
    await server.serve_stdio()


asyncio.run(main())
