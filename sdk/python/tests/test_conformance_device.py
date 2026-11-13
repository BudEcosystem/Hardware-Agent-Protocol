"""The conformance device keeps its documented contract, and the 15-line example works over stdio and WebSocket."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

from bhms.client.client import Client
from bhms.protocol import schema
from bhms.protocol.canonical import canonical
from bhms.protocol.errors import BhmsError
from bhms.testing.conformance_device import build

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "bench_stage.py"


@pytest.fixture
async def device(tmp_path):
    srv, sim = build(state_dir=str(tmp_path), strict=True)  # strict: every request and result is schema-checked
    listener = await srv.listen(f"unix:{tmp_path}/c.sock")
    client = await Client.connect(f"unix:{tmp_path}/c.sock", strict=True)
    yield srv, sim, client
    await client.close()
    await listener.close()
    await srv.close()


async def counters(client: Client) -> dict:
    return await client.request("x-conformance/counters")


async def test_descriptions_are_valid_and_compact(device):  # BHMS-DEV-011, DEV-020, DEV-021
    srv, sim, client = device
    listing = await client.devices_list()
    assert [d.device_id for d in listing.devices] == ["axis-1", "pump-1"]
    for summary in listing.devices:
        assert summary.status == "online" and len(canonical(summary.model_dump(by_alias=True))) <= 1600
        desc = (await client.devices_describe(summary.device_id)).description
        schema.validate("DeviceDescription", desc.model_dump(by_alias=True, exclude_unset=True))
        assert desc.digest == summary.digest
    caps = client.server.capabilities
    assert caps.extensions["org.bhms/conformance"]["version"] == "2"
    filtered = await client.devices_list(filter={"capability": "bhms.axis.*"})
    assert [d.device_id for d in filtered.devices] == ["axis-1"]
    page = await client.devices_list(limit=1)
    rest = await client.devices_list(limit=1, cursor=page.next_cursor)
    assert [d.device_id for d in page.devices + rest.devices] == ["axis-1", "pump-1"] and rest.next_cursor is None


async def test_counters_prove_exactly_one_effect(device):  # BHMS-OPS-030
    srv, sim, client = device
    for _ in range(3):
        op = (await client.actions_invoke("axis-1", "move_to", {"position": 50.1}, operation_key="m",
                                          wait_ms=2000)).operation
    assert op.state == "completed" and op.effect == "verified" and op.result == {"position": 50.1}
    assert (await counters(client))["counter"] == 1
    pulse = (await client.actions_invoke("axis-1", "pulse", {"count": 3}, wait_ms=2000)).operation
    assert pulse.result == {"pulses": 3} and pulse.effect == "unverified"
    obs = (await client.properties_read("axis-1", "counter", fresh=True)).observation
    assert obs.value == 2 and obs.unit == "1"


async def test_fault_injection(device):  # BHMS-OBS-001, OBS-030, OPS-007, ERR-012
    srv, sim, client = device
    await client.request("x-conformance/inject", {"fault": "fail_next"})
    op = (await client.actions_invoke("axis-1", "pulse", {"count": 1}, wait_ms=2000)).operation
    assert op.state == "failed" and op.error.bhms_code == "DEVICE_FAULT" and op.error.may_have_acted
    await client.request("x-conformance/inject", {"fault": "encoder_disagrees"})
    op = (await client.actions_invoke("axis-1", "move_to", {"position": 10}, require={"effect": "verified"},
                                      wait_ms=2000)).operation
    assert op.state == "failed" and op.error.bhms_code == "UNVERIFIED"
    await client.request("x-conformance/inject", {"fault": "sensor_invalid"})
    obs = (await client.properties_read("axis-1", "position", fresh=True)).observation
    assert obs.quality == "invalid" and obs.value is None
    await client.request("x-conformance/inject", {"fault": "sensor_stale"})
    obs = (await client.properties_read("axis-1", "temperature", fresh=True)).observation
    assert obs.quality == "stale" and obs.age_ms >= 10_000
    lease = (await client.leases_acquire(["pump-1/plunger"], 5000)).lease
    with pytest.raises(BhmsError) as info:
        await client.actions_invoke("pump-1", "dispense", {"volume": 5}, lease_id=lease.lease_id)
    assert (info.value.code, info.value.field) == ("STALE", "requiresFresh[0]")
    await client.request("x-conformance/inject", {"fault": "none"})
    ok = (await client.actions_invoke("pump-1", "dispense", {"volume": 5}, lease_id=lease.lease_id,
                                      require={"effect": "verified"}, wait_ms=2000)).operation
    assert ok.state == "completed" and ok.effect == "verified"
    with pytest.raises(BhmsError) as info:
        await client.request("x-conformance/inject", {"fault": "meteor"})
    assert info.value.code == "INVALID_ARGUMENT"


async def test_hang_is_released_by_stop_and_crash_is_unknown_then_reconciled(device):  # BHMS-OPS-004/005
    srv, sim, client = device
    await client.request("x-conformance/inject", {"fault": "hang_next"})
    op = (await client.actions_invoke("axis-1", "pulse", {"count": 1}, wait_ms=50)).operation
    assert op.state == "dispatching"
    stop = (await client.stop("release", device_ids=["axis-1"], wait_ms=1000)).stops[0]
    assert stop.outcome == "confirmed" and op.operation_id in stop.cancel_requested_operations
    done = (await client.operations_wait(op.operation_id, 2000)).operation
    assert done.state == "canceled"
    await client.request("x-conformance/inject", {"fault": "crash_next"})
    crashed = (await client.actions_invoke("axis-1", "pulse", {"count": 1}, wait_ms=2000)).operation
    assert crashed.state == "unknown"
    await srv.reconcile("axis-1")
    after = (await client.operations_get(crashed.operation_id)).operation
    assert after.state == "failed" and after.error.may_have_acted is True


async def test_journal_readonly_injection(device):  # BHMS-OPS-003, AUTH-025
    srv, sim, client = device
    await client.request("x-conformance/inject", {"fault": "journal_readonly"})
    with pytest.raises(BhmsError) as info:
        await client.actions_invoke("axis-1", "pulse", {"count": 1})
    assert info.value.code == "BUSY"
    stop = (await client.stop("audit", device_ids=["axis-1"])).stops[0]
    assert stop.detail == "degraded-audit"
    await client.request("x-conformance/inject", {"fault": "journal_writable"})
    assert (await client.actions_invoke("axis-1", "pulse", {"count": 1}, wait_ms=2000)).operation.state == "completed"
    assert (await counters(client))["counter"] == 1


async def test_conformance_device_runs_as_a_module_over_stdio(tmp_path):  # BHMS-TRN-011
    command = f"{sys.executable} -m bhms.testing.conformance_device --memory"
    async with await Client.connect(f"stdio:{command}") as client:
        assert client.server.server_info.name == "conformance-device"
        assert client.server.capabilities.operations.durable is False
        op = (await client.actions_invoke("axis-1", "pulse", {"count": 2}, wait_ms=2000)).operation
        assert op.state == "completed"


# --------------------------------------------------------------------------- the 15-line example


async def test_example_server_over_stdio(tmp_path):
    env_prefix = f"env BHMS_STATE_DIR={tmp_path} "
    async with await Client.connect(f"stdio:{env_prefix}{sys.executable} {EXAMPLE}") as client:
        desc = (await client.devices_describe("stage-z")).description
        assert desc.actions["move_to"].input["properties"]["target"]["maximum"] == 200
        res = await client.actions_invoke("stage-z", "move_to", {"target": 120}, operation_key="go", wait_ms=2000)
        assert res.operation.state == "completed" and res.operation.result == {"position": 120}
        with pytest.raises(BhmsError) as info:
            await client.actions_invoke("stage-z", "move_to", {"target": 250})
        assert info.value.code == "OUT_OF_RANGE" and info.value.field == "arguments.target"
        obs = (await client.properties_read("stage-z", "position")).observation
        assert obs.value == 120 and obs.evidence == "simulated" and obs.unit == "um"
    assert (tmp_path / "bench-stage.sqlite3").exists()


async def test_example_server_over_websocket(tmp_path, monkeypatch):
    monkeypatch.setenv("BHMS_STATE_DIR", str(tmp_path))
    monkeypatch.delenv("BHMS_TOKEN", raising=False)
    spec = importlib.util.spec_from_file_location("bench_stage_example", EXAMPLE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    srv = module.srv
    listener = await srv.listen("ws://127.0.0.1:0")
    token_file = tmp_path / "bench-stage.token"
    assert oct(os.stat(token_file).st_mode & 0o777) == "0o600"
    url = f"ws://127.0.0.1:{listener.address[1]}"
    try:
        with pytest.raises(Exception):  # noqa: B017 - no bearer token: HTTP 401 at the handshake
            await Client.connect(url)
        async with await Client.connect(url, token=token_file.read_text().strip()) as client:
            res = await client.actions_invoke("stage-z", "move_to", {"target": 33}, wait_ms=2000)
            assert res.operation.state == "completed" and res.operation.result == {"position": 33}
            sub = await client.subscribe(operations={"all": True})
            await client.actions_invoke("stage-z", "move_to", {"target": 34}, wait_ms=2000)
            item = await sub.__anext__()
            assert item.params.operation.state == "accepted"
            await sub.cancel()
    finally:
        await listener.close()
        await srv.close()
