"""``bhms bench invoke|read``: round-trip latency of a target, measured with the real client (no mocks).

``bench invoke DEVICE ACTION key=value... -n 200`` sends sequential (or ``--concurrency N``) invocations, each with a
unique operation key and ``wait_ms``, and prints min/p50/p95/p99/max and throughput. ``bench read DEVICE PROPERTY`` does the
same for ``properties/read --fresh``. Actions have effects: point it at a simulator.
"""

from __future__ import annotations

import asyncio
import json
import math
import secrets
import time
from typing import Annotated

import typer
from rich.console import Console

from bhms.cli.targets import open_client, run, split_arguments


def percentile(sorted_ms: list[float], q: float) -> float:
    """Nearest-rank percentile of an ascending list."""
    if not sorted_ms:
        raise ValueError("no samples")
    return sorted_ms[max(math.ceil(q / 100 * len(sorted_ms)) - 1, 0)]


def summarize(samples_ms: list[float], elapsed_s: float, failures: int) -> dict[str, float | int]:
    ordered = sorted(samples_ms)
    return {"n": len(ordered), "failures": failures, "min_ms": ordered[0], "p50_ms": percentile(ordered, 50),
            "p95_ms": percentile(ordered, 95), "p99_ms": percentile(ordered, 99), "max_ms": ordered[-1],
            "throughput_per_s": len(ordered) / elapsed_s if elapsed_s > 0 else 0.0}


async def measure(call, count: int, concurrency: int) -> tuple[list[float], float, int]:  # type: ignore[no-untyped-def]
    """Run ``call(i)`` ``count`` times with ``concurrency`` in flight; returns (latencies in ms, elapsed s, failures)."""
    samples: list[float] = []
    failures = 0
    queue = iter(range(count))

    async def worker() -> None:
        nonlocal failures
        for i in queue:
            started = time.perf_counter()
            try:
                await call(i)
            except Exception:  # a failed call is counted, not hidden
                failures += 1
                continue
            samples.append((time.perf_counter() - started) * 1000)

    begin = time.perf_counter()
    await asyncio.gather(*(worker() for _ in range(max(concurrency, 1))))
    return samples, time.perf_counter() - begin, failures


def register(app: typer.Typer) -> None:
    bench = typer.Typer(no_args_is_help=True, help="Measure round-trip latency of a target.")
    app.add_typer(bench, name="bench")
    out = Console(highlight=False)

    def report(name: str, stats: dict[str, float | int], as_json: bool) -> None:
        if as_json:
            typer.echo(json.dumps({"benchmark": name, **stats}, indent=2))
            return
        out.print(f"{name}: n={stats['n']} failures={stats['failures']} min {stats['min_ms']:.2f} p50 {stats['p50_ms']:.2f} "
                  f"p95 {stats['p95_ms']:.2f} p99 {stats['p99_ms']:.2f} max {stats['max_ms']:.2f} ms, "
                  f"{stats['throughput_per_s']:.0f}/s")

    @bench.command("invoke")
    def bench_invoke(device: str, action: str, pairs: Annotated[list[str] | None, typer.Argument(metavar="[KEY=VALUE]...")] = None,
                     url: Annotated[str | None, typer.Option("--url", "-u", envvar="BHMS_URL")] = None,
                     token: Annotated[str | None, typer.Option("--token", envvar="BHMS_TOKEN")] = None,
                     n: Annotated[int, typer.Option("-n", min=1, help="Invocations.")] = 100,
                     concurrency: Annotated[int, typer.Option(min=1)] = 1,
                     wait_ms: Annotated[int, typer.Option(help="0 measures admission only.")] = 1000,
                     as_json: Annotated[bool, typer.Option("--json")] = False) -> None:
        """Latency of actions/invoke (unique key per call; leases are not taken: use an action without one)."""
        async def go() -> None:
            arguments = split_arguments(pairs or [])
            run_id = secrets.token_hex(3)
            async with open_client(url, token=token, timeout=60) as client:
                async def call(i: int) -> None:
                    await client.actions_invoke(device, action, arguments, operation_key=f"bench-{run_id}-{i}", wait_ms=wait_ms)

                samples, elapsed, failures = await measure(call, n, concurrency)
            if not samples:
                from bhms.cli.targets import CliError

                raise CliError(f"all {n} invocations failed", "try `bhms call` with the same arguments to see the refusal")
            report(f"invoke {device}.{action} wait_ms={wait_ms} concurrency={concurrency}", summarize(samples, elapsed, failures),
                   as_json)
        run(go())

    @bench.command("read")
    def bench_read(device: str, prop: Annotated[str, typer.Argument(metavar="PROPERTY")],
                   url: Annotated[str | None, typer.Option("--url", "-u", envvar="BHMS_URL")] = None,
                   token: Annotated[str | None, typer.Option("--token", envvar="BHMS_TOKEN")] = None,
                   n: Annotated[int, typer.Option("-n", min=1)] = 200, concurrency: Annotated[int, typer.Option(min=1)] = 1,
                   as_json: Annotated[bool, typer.Option("--json")] = False) -> None:
        """Latency of properties/read with fresh: true."""
        async def go() -> None:
            async with open_client(url, token=token, timeout=60) as client:
                async def call(i: int) -> None:
                    await client.properties_read(device, prop, fresh=True)

                samples, elapsed, failures = await measure(call, n, concurrency)
            if not samples:
                from bhms.cli.targets import CliError

                raise CliError(f"all {n} reads failed", "try `bhms read` to see the refusal")
            report(f"read {device}.{prop} fresh concurrency={concurrency}", summarize(samples, elapsed, failures), as_json)
        run(go())
