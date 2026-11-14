"""Stall attribution for the tail experiment (Task 12b, item 5): where does a rare 100 ms invoke spend its time?

Two probes, each appending JSON lines ``{"kind", "start", "ms", ...}`` (``start`` is ``time.time()``, so lines from the client
and the server process can be compared on one host):

* :func:`watch_loop` — an asyncio task that sleeps 2 ms at a time and records every wake-up that came more than
  ``threshold_ms`` late (``kind: "loop"``): the event loop was blocked, or the process was not scheduled.
* :func:`time_fdatasync` — wraps ``os.fdatasync`` and records every call slower than ``threshold_ms`` (``kind: "fsync"``,
  with the calling thread): the disk (or the filesystem journal) held the durability barrier.

:func:`attribute` classifies slow client samples by what overlapped them.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from pathlib import Path
from typing import Any

_PERIOD_S = 0.002


def _append(path: Path, entry: dict[str, Any], lock: threading.Lock) -> None:
    with lock, open(path, "a") as handle:
        handle.write(json.dumps(entry) + "\n")


async def watch_loop(path: Path, *, threshold_ms: float = 5.0, who: str = "server") -> None:
    """Record event-loop wake-ups more than ``threshold_ms`` late until cancelled."""
    lock = threading.Lock()
    loop = asyncio.get_running_loop()
    while True:
        before_wall, before = time.time(), loop.time()
        await asyncio.sleep(_PERIOD_S)
        late_ms = (loop.time() - before - _PERIOD_S) * 1000
        if late_ms > threshold_ms:
            _append(path, {"kind": "loop", "who": who, "start": before_wall, "ms": round(late_ms, 2)}, lock)


def time_fdatasync(path: Path, *, threshold_ms: float = 5.0) -> None:
    """Replace ``os.fdatasync`` in this process by a wrapper that records slow calls."""
    lock = threading.Lock()
    real = os.fdatasync

    def timed(fd: int) -> None:
        start_wall, start = time.time(), time.perf_counter()
        try:
            real(fd)
        finally:
            took_ms = (time.perf_counter() - start) * 1000
            if took_ms > threshold_ms:
                _append(path, {"kind": "fsync", "start": start_wall, "ms": round(took_ms, 2),
                               "thread": threading.current_thread().name}, lock)

    os.fdatasync = timed  # type: ignore[assignment]


def load(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def attribute(slow: list[tuple[float, float]], events: list[dict[str, Any]]) -> dict[str, int]:
    """Classify each slow sample ``(wall start, wall end)`` by the first kind of stall overlapping it: a slow ``fsync``,
    a blocked server loop, a blocked client loop, or nothing seen (``unattributed``)."""
    out = {"fsync": 0, "server loop": 0, "client loop": 0, "unattributed": 0}
    for start, end in slow:
        hit = None
        for kind in ("fsync", "server", "client"):
            for e in events:
                label = e["kind"] if e["kind"] == "fsync" else e.get("who")
                if label != kind:
                    continue
                e_end = e["start"] + e["ms"] / 1000 + (_PERIOD_S if e["kind"] == "loop" else 0)
                if e["start"] < end and e_end > start:
                    hit = kind
                    break
            if hit:
                break
        out[{"fsync": "fsync", "server": "server loop", "client": "client loop", None: "unattributed"}[hit]] += 1
    return out
