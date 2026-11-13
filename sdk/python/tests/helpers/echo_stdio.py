"""Child process for stdio tests: echoes every line it receives, prefixed, until stdin closes."""

import asyncio
import sys

from bhms.transport import FrameTooLarge, TransportClosed, stdio_server_transport


async def main() -> None:
    transport = await stdio_server_transport()
    print("stray print must not corrupt the protocol")  # goes to stderr via fd redirection
    print("child started", file=sys.stderr)
    while True:
        try:
            data = await transport.receive()
        except FrameTooLarge:
            await transport.send(b"TOO-LARGE")
            continue
        except TransportClosed:
            return
        await transport.send(b"echo:" + data)


asyncio.run(main())
