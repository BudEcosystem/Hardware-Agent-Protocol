"""Hot paths of a durable invoke (Task 12b, from the Task 12a profiles): what one ``actions/invoke`` costs in journal statements,
that serialising to the wire builds no validator per call, and that a serving process moves its start-up heap out of the
garbage collector's way.
"""

from __future__ import annotations

import importlib
import sys
import textwrap

from bhms.client.client import Client
from bhms.protocol import types
from bhms.protocol.types.devices import DevicesCapability
from helpers.devices import build, connect, serve


async def test_a_durable_invoke_costs_two_commits_and_no_pragma(tmp_path):
    srv, _axis = build(tmp_path / "state")
    url, listener = await serve(srv, tmp_path)
    client = await connect(url)
    try:
        for i in range(3):  # warm caches (prepared statements, the device's validators)
            await client.actions_invoke("axis-1", "move_to", {"target": float(i)}, wait_ms=2000)
        statements: list[str] = []
        srv.store._db.set_trace_callback(statements.append)
        op = (await client.actions_invoke("axis-1", "move_to", {"target": 4.0}, wait_ms=2000)).operation
        srv.store._db.set_trace_callback(None)
    finally:
        await client.close()
        await listener.close()
        await srv.close()
    assert op.state == "completed"
    writes = [s.split()[0] for s in statements if not s.startswith("SELECT")]
    # accepted+dispatching in one barrier transaction, completed in one more: BEGIN, INSERT operation, INSERT both history
    # rows in one statement, COMMIT; BEGIN, UPDATE, INSERT history, COMMIT. No PRAGMA synchronous switching.
    assert writes == ["BEGIN", "INSERT", "INSERT", "COMMIT", "BEGIN", "UPDATE", "INSERT", "COMMIT"], statements


def test_to_wire_builds_no_validator_per_call(monkeypatch):
    def refuse(*args, **kw):
        raise AssertionError("to_wire built a TypeAdapter")

    monkeypatch.setattr(importlib.import_module("bhms.protocol.types._base"), "TypeAdapter", refuse)
    value = {"a": [DevicesCapability(list_changed=True)], "b": 1}
    assert types.to_wire(value) == {"a": [{"listChanged": True}], "b": 1}


async def test_a_serving_device_server_freezes_its_start_up_heap(tmp_path):
    """``DeviceServer.serve`` (what ``run`` does) collects once and freezes what start-up allocated, as ``Gateway.serve``
    does, so that no generation-2 collection over long-lived objects pauses the event loop later."""
    script = tmp_path / "frozen_server.py"
    script.write_text(textwrap.dedent("""
        import gc
        from bhms import DeviceServer

        srv = DeviceServer("frozen", store=None)
        dev = srv.device("probe-1", resources=["probe-1"])
        dev.report_alive()

        @dev.action(effect="none", idempotency="idempotent", max_duration_ms=1000)
        def frozen(ctx) -> {"objects": "1"}:  # noqa: F821
            return {"objects": gc.get_freeze_count()}

        srv.run()
    """))
    client = await Client.connect(f"stdio:{sys.executable} {script}", timeout=20)
    try:
        op = (await client.actions_invoke("probe-1", "frozen", {}, wait_ms=2000)).operation
    finally:
        await client.close()
    assert op.state == "completed" and op.result["objects"] > 10_000
