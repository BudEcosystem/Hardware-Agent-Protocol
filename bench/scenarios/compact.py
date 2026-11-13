"""BHMS-Compact over a pseudo-terminal: invoke and read round trip against the C endpoint, and the wire size of its frames.

Standalone and stdlib-only on purpose (it also runs inside the AVR container, which has no ``bhms`` package), driving the C
library through the host harness ``sdk/c/tests/host/bhms_host.py`` (an independent struct-based implementation of the payload
layouts and the ``protocol/serial/frame.py`` framing).

Targets: ``native`` is ``sdk/c`` ``sim_device`` (the host HAL build of the same LedAnalog device, built here with the
sanitizers OFF so the numbers are those of optimised code); ``simavr`` is the Arduino LedAnalog firmware on a simulated
ATmega328P at 16 MHz, 115200 baud, with simavr emulating the UART timing and the runner pacing to wall-clock time, so the
latency is dominated by wire time. ``wire_floor_ms`` is the arithmetic minimum for the frames actually exchanged
(10 bits per byte at the baud rate, request plus reply, nothing else); the measured p50 minus the floor is the device and
host overhead.

``python compact.py --cmd 'CMD with {tmp}' --label native|simavr [--n N] [--baud 115200] [--json OUT]``.
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import platform
import shlex
import statistics
import subprocess
import sys
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "sdk" / "c" / "tests" / "host"))

import bhms_host as h  # noqa: E402

NAME = "compact"
FLAGS = 0x02  # PERSISTENT_EPOCH only, as in test_e2e.py
INVOKE_FRAME_BUDGET_BYTES = 64


def pct(ordered: list[float], q: float) -> float:
    return ordered[max(math.ceil(q / 100 * len(ordered)) - 1, 0)]


def summary(samples: list[float]) -> dict:
    ordered = sorted(samples)
    return {"n": len(ordered), "min_ms": round(ordered[0], 4), "p50_ms": round(pct(ordered, 50), 4), "p95_ms": round(pct(ordered, 95), 4),
            "p99_ms": round(pct(ordered, 99), 4), "max_ms": round(ordered[-1], 4), "mean_ms": round(statistics.fmean(ordered), 4)}


def measure(cmd: list[str], n: int, baud: int | None, timeout: float) -> dict:
    with tempfile.TemporaryDirectory() as directory:
        tmp = pathlib.Path(directory)
        target = h.spawn(cmd, tmp / "stderr.txt")
        link = h.Link(target)
        try:
            _, hello, _ = link.exchange(h.hello_req(0xB0B, False), 0, timeout)
            if hello is None:
                raise RuntimeError("no HELLO from the firmware")
            invoke_sizes: set[int] = set()
            reply_sizes: set[int] = set()
            invoke_ms: list[float] = []
            for i in range(n + 20):
                payload = h.invoke(i + 1, 0, bytes([i & 1]))
                started = time.perf_counter()
                sent = link.send(payload, 1)
                wire, fr = link.recv(timeout)
                elapsed = (time.perf_counter() - started) * 1000
                if wire is None or fr.payload[0] != h.RESULT:
                    raise RuntimeError(f"invoke {i}: no RESULT (got {None if wire is None else fr.payload[:4].hex()})")
                if i >= 20:
                    invoke_ms.append(elapsed)
                invoke_sizes.add(len(sent))
                reply_sizes.add(len(wire))
            read_ms: list[float] = []
            read_sizes: set[int] = set()
            for i in range(n // 2 + 20):
                started = time.perf_counter()
                sent = link.send(h.read(i + 1, 0), 1)
                wire, fr = link.recv(timeout)
                elapsed = (time.perf_counter() - started) * 1000
                if wire is None or fr.payload[0] != h.VALUE:
                    raise RuntimeError(f"read {i}: no VALUE")
                if i >= 20:
                    read_ms.append(elapsed)
                read_sizes.update((len(sent), len(wire)))
        finally:
            target.close()
    out = {"samples_ms": {"invoke": [round(x, 4) for x in invoke_ms], "read": [round(x, 4) for x in read_ms]},
           "invoke": summary(invoke_ms), "read": summary(read_ms), "invoke_request_bytes": sorted(invoke_sizes),
           "invoke_reply_bytes": sorted(reply_sizes), "read_frame_bytes": sorted(read_sizes),
           "hello_bytes": len(hello), "typical_invoke_frame_bytes": max(invoke_sizes | reply_sizes),
           "frame_budget_bytes": INVOKE_FRAME_BUDGET_BYTES}
    if baud:
        floor = (max(invoke_sizes) + max(reply_sizes)) * 10 / baud * 1000
        out["baud"] = baud
        out["wire_floor_ms"] = round(floor, 3)
        out["invoke_over_floor_ms"] = round(out["invoke"]["p50_ms"] - floor, 3)
    return out


def build_native(out_dir: pathlib.Path) -> pathlib.Path:
    """Build ``sim_device`` with the host toolchain, sanitizers off (a benchmark of instrumented code is not a benchmark)."""
    src = HERE.parents[1] / "sdk" / "c"
    out_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["cmake", "-S", str(src), "-B", str(out_dir), "-DCMAKE_BUILD_TYPE=Release", "-DBHMS_SANITIZE=OFF"],
                   check=True, capture_output=True)
    subprocess.run(["cmake", "--build", str(out_dir), "--target", "sim_device", "-j4"], check=True, capture_output=True)
    return out_dir / "sim_device"


async def run(ctx) -> dict:  # noqa: ANN001 - bench.common.Context
    """Orchestrator entry: the native build over a pty here, simavr when ``ctx.simavr_cmd`` is set (a JSON file from the AVR container)."""
    exe = build_native(ctx.state_root / "compact-build")
    n = ctx.n(500, 3000)
    out: dict = {"native": measure([str(exe), "--epoch", str(ctx.state_root / "compact-build" / "epoch.bin"), "--analog", "341"], n, None, 10.0)}
    from common import record

    for op, values in out["native"].pop("samples_ms").items():
        record(f"compact__native_{op}", values)
    if ctx.simavr_cmd:  # path to a compact.py JSON produced inside the AVR container (see bench/README.md)
        out["simavr"] = json.loads(pathlib.Path(ctx.simavr_cmd).read_text())
        for op, values in out["simavr"].pop("samples_ms", {}).items():
            record(f"compact__simavr_{op}", values)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--cmd", required=True, help="firmware command line; {tmp} is replaced by a scratch directory")
    parser.add_argument("--label", required=True)
    parser.add_argument("--n", type=int, default=2000)
    parser.add_argument("--baud", type=int, default=0)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--json")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as scratch:
        cmd = shlex.split(args.cmd.replace("{tmp}", scratch))
        before = open("/proc/loadavg").read().split()[:3]
        result = measure(cmd, args.n, args.baud or None, args.timeout)
        after = open("/proc/loadavg").read().split()[:3]
    result.update({"label": args.label, "cmd": args.cmd, "load": {"before": before, "after": after}, "python": platform.python_version()})
    text = json.dumps(result, indent=1)
    if args.json:
        pathlib.Path(args.json).write_text(text)
    print(text)


if __name__ == "__main__":
    main()
