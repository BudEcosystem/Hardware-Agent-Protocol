"""Ruling R16: every SimLab device is marked as a simulation, at device level and in serverInfo, so no agent or log can mistake
a twin's `measured` reading for physical evidence."""

import pytest

from serving import described
from simlab.lab import NATIVE, Lab


@pytest.mark.parametrize("bridged", [(), ("balance", "thermal", "centrifuge")])
async def test_every_device_and_server_carries_the_marker(tmp_path, bridged):
    async with await Lab.start(tmp_path / "lab", devices=NATIVE, bridged=bridged) as lab:
        seen = 0
        for key, client in lab.clients.items():
            info = client.server.server_info
            assert info.name.startswith("simlab-"), (key, info.name)
            assert "SIMULATED" in client.server.instructions
            for summary in (await client.devices_list()).devices:
                description = await described(client, summary.device_id)
                assert "simulated" in description["tags"] and "simlab" in description["tags"], summary.device_id
                seen += 1
        assert seen == len(NATIVE)


async def test_a_server_that_is_not_named_simlab_is_refused(tmp_path):
    from simlab.scene import BENCH
    from simlab.simdevice import make_server
    from simlab.world import World
    with pytest.raises(ValueError):
        make_server(World(BENCH, seed=1, attach_arm=False), "plain-server", state_dir=tmp_path)
