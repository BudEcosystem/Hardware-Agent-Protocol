"""The device server every BHMS benchmark scenario drives: ``--devices N`` identical devices, three actions.

``set_point(value)`` returns at once (the cost measured is the protocol and the journal, not the device); ``emit_tick(seq)``
appends one ``bench.tick`` event; ``hang()`` waits until cancelled (used to leave ``unknown`` operations behind a SIGKILL).

``python device_server.py [--listen unix:/p | ws://127.0.0.1:P] [--durability dispatch|full|process|memory]
[--state-dir DIR] [--devices N] [--queue-limit N] [--cprofile FILE] [--no-checkpoint] [--gc-freeze] [--gc-log FILE]``. Without ``--listen`` it serves stdio. With a listener it
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


async def serve(args: argparse.Namespace) -> None:  # noqa: C901
    srv = build(args)
    if not args.listen:
        await srv.serve(None)
        return
    await srv.listen(args.listen)
    if args.gc_freeze:
        import gc

        gc.collect()
        gc.freeze()
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
    parser.add_argument("--no-checkpoint", action="store_true",
                        help="experiment only: effectively disable the background WAL checkpointer (to attribute latency stalls)")
    parser.add_argument("--gc-freeze", action="store_true",
                        help="experiment only: gc.collect() then gc.freeze() once the server is up (what Gateway.serve does)")
    parser.add_argument("--gc-log", help="experiment only: append one line per garbage collection slower than 5 ms to this file")
    args = parser.parse_args()
    if args.gc_log:
        import gc
        import time

        state = {"t": 0.0}

        def on_gc(phase: str, info: dict) -> None:
            if phase == "start":
                state["t"] = time.perf_counter()
            else:
                took = (time.perf_counter() - state["t"]) * 1000
                if took > 5:
                    with open(args.gc_log, "a") as log:
                        log.write(f"gen{info['generation']} {took:.1f} ms collected={info['collected']}\n")

        gc.callbacks.append(on_gc)
    if args.no_checkpoint:
        from bhms.runtime import store

        original = store._Checkpointer.__init__
        store._Checkpointer.__init__ = lambda self, path, *, every=10**9, interval_s=3600.0: original(self, path, every=every, interval_s=interval_s)
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
