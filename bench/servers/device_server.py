"""The device server every BHMS benchmark scenario drives: ``--devices N`` identical devices, three actions.

``set_point(value)`` returns at once (the cost measured is the protocol and the journal, not the device); ``emit_tick(seq)``
appends one ``bench.tick`` event; ``hang()`` waits until cancelled (used to leave ``unknown`` operations behind a SIGKILL).

``python device_server.py [--listen unix:/p | ws://127.0.0.1:P] [--durability dispatch|full|process|memory]
[--state-dir DIR] [--devices N] [--queue-limit N] [--cprofile FILE]``. Without ``--listen`` it serves stdio. With a listener it
prints ``ready`` once it accepts connections. ``memory`` is ``store=None`` (nothing durable at all); the others are the SDK's
journal modes (see ``bhms.runtime.store``). ``--cprofile`` writes cProfile statistics (cumulative, then own time) on SIGTERM.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import signal
import sys

from bhms import DeviceServer, Range

TOKEN = "bench-token"


def build(args: argparse.Namespace) -> DeviceServer:
    memory = args.durability == "memory"
    kw: dict = {"store": None, "programs": False} if memory else {"state_dir": args.state_dir, "durability": args.durability}
    srv = DeviceServer("bench", token=TOKEN, queue_limit=args.queue_limit, **kw)
    for i in range(1, args.devices + 1):
        dev = srv.device(f"dev-{i}", resources=[f"dev-{i}"])
        dev.report_alive()
        dev.event("bench.tick", description="one benchmark event")

        @dev.action(effect="reversible", idempotency="absolute", max_duration_ms=5000)
        async def set_point(ctx, value: Range(0, 1e9, unit="1")) -> None:  # noqa: F821 - unit marker
            return None

        @dev.action(effect="reversible", idempotency="absolute", max_duration_ms=5000)
        async def emit_tick(ctx, seq: Range(0, 1e9, unit="1")) -> None:  # noqa: F821
            ctx.emit("bench.tick", message=str(int(seq)))

        @dev.action(effect="reversible", idempotency="absolute", max_duration_ms=3_600_000, cancel="supported")
        async def hang(ctx) -> None:
            await ctx.wait_cancelled(3600)
    return srv


async def serve(args: argparse.Namespace) -> None:
    srv = build(args)
    if not args.listen:
        await srv.serve(None)
        return
    await srv.listen(args.listen)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    print("ready", flush=True)
    await stop.wait()
    await srv.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--listen")
    parser.add_argument("--durability", default="dispatch", choices=["dispatch", "full", "process", "memory"])
    parser.add_argument("--state-dir")
    parser.add_argument("--devices", type=int, default=1)
    parser.add_argument("--queue-limit", type=int, default=64)
    parser.add_argument("--cprofile")
    args = parser.parse_args()
    profiler = None
    if args.cprofile:
        import cProfile

        profiler = cProfile.Profile()
        profiler.enable()
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(serve(args))
    if profiler is not None:
        import pstats

        profiler.disable()
        with open(args.cprofile, "w") as out:
            pstats.Stats(profiler, stream=out).sort_stats("cumulative").print_stats(40)
            pstats.Stats(profiler, stream=out).sort_stats("tottime").print_stats(25)


if __name__ == "__main__":
    sys.exit(main())
