"""The control socket: a JSON-lines side channel for the *test harness* (never for agents) to drive a running lab.

One JSON object per line in, one JSON object per line out, over a Unix socket in the lab's run directory (agents are given
BHMS endpoints only, so this channel is the harness's, like the oracle). Requests::

    {"op": "step", "seconds": 1.5}                       advance world time (instantly, whatever the mode)
    {"op": "snapshot"}                                   the canonical world snapshot
    {"op": "digest"}                                     the world digest (causes anonymised: BHMS operation ids vary)
    {"op": "effects", "cause": "op-..."}                 the effects an operation caused (omit cause: all)
    {"op": "inject", "fault": {"target": "plate", "kind": "drop_object",
                               "when": {"at": 3.0} | {"on": "move_started", "device": null},
                               "params": {...}}}         inject a fault; replies its id
    {"op": "clear", "id": "fault-1"}                     clear a fault

Replies are ``{"ok": true, ...}`` or ``{"ok": false, "error": "..."}``.

Thread-safety: runs on the world's event loop.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from simlab.faults import At, Fault, OnEvent
from simlab.world import World


class ControlServer:
    """Serves the control protocol for one world."""

    def __init__(self, world: World, path: Path) -> None:
        self.world, self.path = world, path
        self._server: asyncio.AbstractServer | None = None

    async def start(self) -> None:
        self._server = await asyncio.start_unix_server(self._serve, path=str(self.path))

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            while line := await reader.readline():
                try:
                    reply = {"ok": True, **self.handle(json.loads(line))}
                except (KeyError, ValueError, TypeError) as exc:
                    reply = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
                writer.write(json.dumps(reply, default=str).encode() + b"\n")
                await writer.drain()
        except ConnectionError:
            pass
        finally:
            writer.close()

    def handle(self, request: dict[str, Any]) -> dict[str, Any]:
        world, op = self.world, request["op"]
        if op == "step":
            world.step(float(request["seconds"]))
            return {"time_s": world.time_s}
        if op == "snapshot":
            return {"snapshot": world.snapshot()}
        if op == "digest":
            return {"digest": world.digest(anonymize_causes=True)}
        if op == "effects":
            cause = request.get("cause")
            return {"effects": [[e.seq, e.time_s, e.device, e.kind, e.detail, e.cause] for e in world.effect_log()
                                if cause is None or e.cause == cause]}
        if op == "inject":
            spec = request["fault"]
            when = spec["when"]
            trigger = At(float(when["at"])) if "at" in when else OnEvent(when["on"], when.get("device"))
            return {"id": world.faults.inject(Fault(spec["target"], spec["kind"], trigger, spec.get("params", {})))}
        if op == "clear":
            world.faults.clear(request["id"])
            return {}
        raise ValueError(f"unknown op {op!r}")
