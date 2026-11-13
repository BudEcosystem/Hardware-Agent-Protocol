#!/usr/bin/env python3
"""Profile a sequential ``actions/invoke`` loop on the server (cProfile, and py-spy when it can attach) and on the client.

``python bench/scripts/profile_invoke.py --durability dispatch --wait-ms 1000 --n 3000 [--pyspy] --out DIR``

Default pass: spawns ``servers/device_server.py --cprofile`` on a unix socket, drives ``--n`` invokes with this process's client
under cProfile too, then SIGTERMs the server (which writes its statistics): ``server.cprofile.txt`` (cumulative and own-time
tables) and ``client.cprofile.txt``. cProfile inflates every number (about 2x); read the shares, not the absolute times.
With ``--pyspy`` the server is instead started *under* ``py-spy record`` (ptrace_scope=1 forbids attaching to a sibling, and a
child of py-spy is allowed) with no cProfile, sampling at 500 Hz: ``server.pyspy.collapsed`` and ``server.pyspy.top.txt`` (leaf
and inclusive sample shares), which are not distorted by instrumentation.
"""

from __future__ import annotations

import argparse
import asyncio
import cProfile
import collections
import io
import pstats
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "sdk" / "python" / "src"))

from common import DEVICE_SERVER, spawn_server  # noqa: E402
from bhms.client.client import Client  # noqa: E402


def pyspy_top(collapsed: Path, limit: int = 25) -> str:
    leaf: collections.Counter[str] = collections.Counter()
    inclusive: collections.Counter[str] = collections.Counter()
    total = 0
    for line in collapsed.read_text().splitlines():
        stack, _, count = line.rpartition(" ")
        frames, weight = stack.split(";"), int(count)
        total += weight
        leaf[frames[-1]] += weight
        for frame in set(frames):
            inclusive[frame] += weight
    out = [f"samples: {total}", "", "top leaf frames (own time):"]
    out += [f"  {100 * n / total:5.1f}%  {frame}" for frame, n in leaf.most_common(limit)]
    out += ["", "top inclusive frames:"]
    out += [f"  {100 * n / total:5.1f}%  {frame}" for frame, n in inclusive.most_common(limit)]
    return "\n".join(out)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--durability", default="dispatch")
    parser.add_argument("--wait-ms", type=int, default=1000)
    parser.add_argument("--n", type=int, default=3000)
    parser.add_argument("--pyspy", action="store_true")
    parser.add_argument("--state-root", type=Path, default=None)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    tag = secrets.token_hex(3)
    with tempfile.TemporaryDirectory(dir=args.state_root) as tmp:
        url = f"unix:{tmp}/p.sock"
        server_args = ["--listen", url, "--durability", args.durability, "--state-dir", tmp]
        spy = None
        if args.pyspy:
            py_spy = shutil.which("py-spy") or str(Path(sys.executable).parent / "py-spy")
            spy = subprocess.Popen([py_spy, "record", "--rate", "500", "--format", "raw", "--output",
                                    str(args.out / "server.pyspy.collapsed"), "--subprocesses", "--", sys.executable,
                                    str(DEVICE_SERVER), *server_args], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                   env={**__import__("os").environ, "PYTHONPATH": str(Path(__file__).resolve().parents[2] / "sdk" / "python" / "src")})
            assert spy.stdout is not None
            for _ in range(200):  # py-spy prints its own banner on stderr; the server's ready line is on stdout
                if spy.stdout.readline().strip() == "ready":
                    break
            server = None
        else:
            server = spawn_server(DEVICE_SERVER, [*server_args, "--cprofile", str(args.out / "server.cprofile.txt")], url=url)
        try:
            async with await Client.connect(url, timeout=60) as client:
                async def call(i: int) -> None:
                    await client.actions_invoke("dev-1", "set_point", {"value": abs(i)}, operation_key=f"{tag}-{i}", wait_ms=args.wait_ms)

                for i in range(300):  # warm-up
                    await call(-1 - i)
                profiler = cProfile.Profile()
                started = time.perf_counter()
                profiler.enable()
                for i in range(args.n):
                    await call(i)
                profiler.disable()
                elapsed = time.perf_counter() - started
        finally:
            if spy is not None:
                spy.send_signal(signal.SIGINT)
                _, err = spy.communicate(timeout=120)
                print("py-spy:", (err or "").strip()[-300:])
            if server is not None:
                server.stop()
    text = io.StringIO()
    stats = pstats.Stats(profiler, stream=text)
    stats.sort_stats("cumulative").print_stats(25)
    stats.sort_stats("tottime").print_stats(20)
    (args.out / "client.cprofile.txt").write_text(text.getvalue())
    collapsed = args.out / "server.pyspy.collapsed"
    if args.pyspy and collapsed.exists() and collapsed.stat().st_size:
        (args.out / "server.pyspy.top.txt").write_text(pyspy_top(collapsed))
    print(f"{args.n} invokes in {elapsed:.2f} s under client cProfile ({1000 * elapsed / args.n:.2f} ms each)")


if __name__ == "__main__":
    asyncio.run(main())
