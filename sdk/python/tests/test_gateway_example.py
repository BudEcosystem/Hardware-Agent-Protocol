"""DX: the example configuration runs with one command and does what its comments say (Task 5 brief)."""

from __future__ import annotations

import asyncio
import shutil
import sys
from pathlib import Path

import pytest

from bhms.client.client import Client
from bhms.gateway import load_config
from bhms.protocol.errors import BhmsError

EXAMPLES = Path(__file__).resolve().parents[3] / "examples" / "bhms"
SDK_EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def test_example_config_loads_and_keeps_tokens_hashed():
    config = load_config(EXAMPLES / "gateway.toml")
    assert [u.name for u in config.upstreams] == ["bench", "pump", "thermo"]
    assert config.listen[1:] == ("ws://127.0.0.1:8765", "http://127.0.0.1:8766/bhms")
    assert all(t.startswith("sha256:") for p in config.principals.values() for t in p["tokens"])


async def test_example_gateway_runs_with_one_command(tmp_path):
    root = tmp_path / "repo"
    shutil.copytree(EXAMPLES, root / "examples" / "bhms", ignore=shutil.ignore_patterns("state", "__pycache__"))
    shutil.copytree(SDK_EXAMPLES, root / "sdk" / "python" / "examples", ignore=shutil.ignore_patterns("__pycache__"))
    config = root / "examples" / "bhms" / "gateway.toml"
    text = config.read_text().replace('listen = ["unix:gateway.sock", "ws://127.0.0.1:8765", "http://127.0.0.1:8766/bhms"]',
                                      'listen = ["stdio"]')
    config.write_text(text)
    async with await Client.connect(f"stdio:{sys.executable} -m bhms.gateway {config}", timeout=30) as client:
        for _ in range(200):
            devices = [d.device_id for d in (await client.devices_list()).devices]
            if len(devices) == 3:
                break
            await asyncio.sleep(0.1)
        assert devices == ["bench/stage-z", "pump/pump-1", "thermo/thermo-1"]
        assert client.server.capabilities.gateway.upstreams == 3
        op = (await client.actions_invoke("bench/stage-z", "move_to", {"target": 150}, operation_key="ex-1",
                                          wait_ms=5000)).operation
        assert op.state == "completed"  # stdio is the operator: admin, so no narrowing applies
        lease = (await client.leases_acquire(["pump/pump-1/plunger"], 5000)).lease
        dose = await client.actions_invoke("pump/pump-1", "dispense", {"volume": 250}, operation_key="ex-2",
                                           lease_id=lease.lease_id, wait_ms=5000)
        assert dose.operation.state == "completed" and dose.operation.result == {"dispensed": 250}
        reading = (await client.properties_read("thermo/thermo-1", "temperature")).observation
        assert 20 < reading.value < 22 and reading.evidence == "simulated"
        stops = (await client.stop("example", scope="all")).stops
        assert {s.device_id: s.outcome for s in stops} == {"bench/stage-z": "unsupported", "pump/pump-1": "unsupported",
                                                           "thermo/thermo-1": "unsupported"}


async def test_example_agent_policy_narrows_and_refuses_with_rules(tmp_path):
    from bhms.gateway import Gateway

    config = load_config(EXAMPLES / "gateway.toml")
    config = type(config)(**{**{f: getattr(config, f) for f in config.__dataclass_fields__},
                             "state_dir": tmp_path / "state", "listen": ()})
    gateway = Gateway(config, memory=True)
    await gateway.start()
    try:
        listener = await gateway.listen("ws://127.0.0.1:0")
        url = f"ws://127.0.0.1:{listener.address[1]}"
        async with await Client.connect(url, token="demo-agent-token") as agent, \
                await Client.connect(url, token="demo-operator-token") as operator:
            mine = (await agent.devices_describe("bench/stage-z")).description
            theirs = (await operator.devices_describe("bench/stage-z")).description
            assert mine.actions["move_to"].input["properties"]["target"]["maximum"] == 100
            assert theirs.actions["move_to"].input["properties"]["target"]["maximum"] == 200
            assert mine.digest != theirs.digest
            with pytest.raises(BhmsError) as exc:
                await agent.actions_invoke("bench/stage-z", "move_to", {"target": 150}, operation_key="big")
            assert exc.value.bhms_code == "OUT_OF_RANGE" and "[rule: bounds:target]" in exc.value.hint
            # the default agent policy: it can stop the devices it can act on (Task 11 S5), and no others
            mine = (await agent.stop("x", scope="all")).stops
            assert sorted(s.device_id for s in mine) == ["bench/stage-z", "pump/pump-1"]
            other = (await agent.stop("x", device_ids=["thermo/thermo-1"])).stops[0]
            assert other.outcome == "failed" and "[rule: scope:stop]" in other.error.hint
    finally:
        await gateway.close()
