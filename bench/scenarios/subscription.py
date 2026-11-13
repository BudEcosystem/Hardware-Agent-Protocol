"""Subscription fan-out: one event stream from a device server delivered to 1, 10, 50 and 100 listeners.

Each listener holds its own connection and a ``subscriptions/listen`` for ``events``; an invoker connection calls ``emit_tick``
(``waitMs=0``) which appends one ``bench.tick`` event. Latency is measured per delivery, from just before the invoke was sent
to the moment that listener parsed the event (so it includes the invoke itself, one event append, and the fan-out to every
listener). Events are emitted one at a time so latency is not queueing behind a burst. Also reports the all-listeners-have-it
time (the slowest listener) per event.
"""

from __future__ import annotations

import asyncio
import secrets
import time

from common import Context, device_server, stats_ms, timed
from bhms.client.client import Client

NAME = "subscription"


async def cell(ctx: Context, listeners: int, events: int) -> dict:
    tag = secrets.token_hex(3)
    async with device_server(ctx, "dispatch", "unix") as (target, _):
        invoker = await Client.connect(target, timeout=60)
        conns = [await Client.connect(target, timeout=60) for _ in range(listeners)]
        subs = [await c.subscribe(events={}) for c in conns]
        sent: dict[int, float] = {}
        arrived: dict[int, list[float]] = {}
        latencies: list[float] = []

        async def consume(sub) -> None:  # noqa: ANN001
            async for note in sub:
                event = getattr(note.params, "event", None)
                if event is None or event.type != "bench.tick":
                    continue
                seq = int(event.message)
                now = time.perf_counter()
                latencies.append((now - sent[seq]) * 1000)
                arrived.setdefault(seq, []).append(now)

        tasks = [asyncio.create_task(consume(s)) for s in subs]
        row: dict = {"listeners": listeners, "events": events}
        try:
            with timed(row):
                begin = time.perf_counter()
                for seq in range(events):
                    sent[seq] = time.perf_counter()
                    await invoker.actions_invoke("dev-1", "emit_tick", {"seq": seq}, operation_key=f"{tag}-{seq}", wait_ms=0)
                    deadline = time.monotonic() + 30
                    while len(arrived.get(seq, ())) < listeners and time.monotonic() < deadline:
                        await asyncio.sleep(0)
                elapsed = time.perf_counter() - begin
            lost = sum(listeners - len(arrived.get(s, ())) for s in range(events))
            row["delivery"] = stats_ms(latencies, elapsed)
            row["slowest_listener_ms"] = stats_ms([(max(arrived[s]) - sent[s]) * 1000 for s in arrived], elapsed)
            row["deliveries_lost"] = lost
        finally:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            for s in subs:
                await s.cancel()
            for c in (*conns, invoker):
                await c.close()
        return row


async def run(ctx: Context) -> dict:
    return {f"listeners={n}": await cell(ctx, n, ctx.n(30, 200)) for n in ((1, 10, 100) if ctx.quick else (1, 10, 50, 100))}
