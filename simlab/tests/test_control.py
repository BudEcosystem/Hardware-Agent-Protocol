"""The control socket drives a running lab from the harness side."""

import json

from simlab.control import ControlServer
from simlab.lab import Lab


async def talk(path, *requests):
    import asyncio
    reader, writer = await asyncio.open_unix_connection(str(path))
    replies = []
    for request in requests:
        writer.write(json.dumps(request).encode() + b"\n")
        await writer.drain()
        replies.append(json.loads(await reader.readline()))
    writer.close()
    return replies


async def test_step_inject_snapshot_and_errors(tmp_path):
    async with await Lab.start(tmp_path / "run", seed=3, devices=("arm",)) as lab:
        control = ControlServer(lab.world, lab.socket_dir / "control.sock")
        await control.start()
        try:
            step, injected, bad, digest = await talk(
                control.path, {"op": "step", "seconds": 2.0},
                {"op": "inject", "fault": {"target": "plate", "kind": "drop_object", "when": {"at": 3.0}}},
                {"op": "nonsense"}, {"op": "digest"})
            assert step["ok"] and step["time_s"] == 2.0
            assert injected["ok"] and injected["id"].startswith("fault-")
            assert bad["ok"] is False and "nonsense" in bad["error"]
            assert digest["digest"].startswith("sha256:")
            fired, snapshot, effects = await talk(control.path, {"op": "step", "seconds": 2.0}, {"op": "snapshot"},
                                                  {"op": "effects"})
            assert snapshot["snapshot"]["ledger"]["plate"] == "lost"
            assert [e[3] for e in effects["effects"] if e[2] == "fault"] == ["fault_injected", "fault_fired"]
        finally:
            await control.stop()
