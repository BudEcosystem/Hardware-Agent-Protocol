"""Home Assistant adapter against the real Home Assistant demo container (WebSocket API).

Needs ``SIMLAB_HA_URL`` (for example ``http://127.0.0.1:18123``) and ``SIMLAB_HA_REFRESH`` (path of a JSON file holding a
``refresh_token``); the AMD machine has both (``~/hms-lab/cache/ha_refresh.json``). Skipped elsewhere.
"""

import json
import os
from pathlib import Path

import pytest

from contract import check_description, check_observations
from serving import read, run, serving
from simlab.adapters import home_assistant as ha_adapter
from simlab.oracle import Claim, Oracle, Verdict
from simlab.profiles import FACILITY_HA
from simlab.scene import BENCH
from simlab.world import World

URL = os.environ.get("SIMLAB_HA_URL")
REFRESH = os.environ.get("SIMLAB_HA_REFRESH")

pytestmark = [pytest.mark.ha, pytest.mark.skipif(not (URL and REFRESH), reason="no Home Assistant (SIMLAB_HA_URL)")]


@pytest.fixture
async def rig(tmp_path):
    token = await ha_adapter.access_token(URL, json.loads(Path(REFRESH).read_text())["refresh_token"])
    w = World(BENCH, seed=9, attach_arm=False)
    srv, link = ha_adapter.build_server(w, FACILITY_HA, URL, token, state_dir=tmp_path / "ha")
    try:
        async with serving(srv, tmp_path) as client:
            yield client, srv, link, w, token
    finally:
        await link.close()


async def test_contract(rig):
    client, srv, link, w, token = rig
    desc = await check_description(client, "facility-1", measured_ok=set())
    await check_observations(client, "facility-1", desc)
    assert desc["properties"]["sensor_outside_temperature"]["evidence"] == "reported"
    assert desc["actions"]["turn_on"]["input"]["properties"]["entity"]["enum"] == [
        "light.bed_light", "light.kitchen_lights", "switch.decorative_lights"]


async def test_sensor_values_carry_units_and_are_reported(rig):
    client, srv, link, w, token = rig
    temp = await read(client, "facility-1", "sensor_outside_temperature")
    assert temp.unit == "Cel" and temp.evidence == "reported" and -60 < temp.value < 60


async def test_light_on_off_round_trip_is_read_back_and_unverified(rig):
    client, srv, link, w, token = rig
    off = await run(client, "facility-1", "turn_off", {"entity": "light.bed_light"})
    assert off.state == "completed", off.error
    assert (await read(client, "facility-1", "light_bed_light")).value == "off"
    on = await run(client, "facility-1", "turn_on", {"entity": "light.bed_light"})
    assert on.state == "completed" and on.effect != "verified" and on.result["state"] == "on"
    assert (await read(client, "facility-1", "light_bed_light")).value == "on"
    assert Oracle(w).judge(Claim(on.operation_id, "completed", on.effect, lambda s: True)) is Verdict.CONSISTENT


async def test_arbitrary_entities_are_not_reachable(rig):
    client, srv, link, w, token = rig
    from bhms.protocol.errors import BhmsError
    with pytest.raises(BhmsError):
        await client.actions_invoke("facility-1", "turn_on", {"entity": "switch.ac"})  # exists in HA, not in the profile


async def test_a_phantom_entity_in_the_profile_is_refused_with_proof_not_reported_as_success(tmp_path, rig):
    client, srv, link, w, token = rig
    from simlab.adapters.home_assistant import Entity, HomeAssistantProfile
    profile = HomeAssistantProfile("facility-2", "Ghost", "profile naming an entity HA does not have",
                                   (Entity("light.does_not_exist", "phantom"),))
    srv2, link2 = ha_adapter.build_server(w, profile, URL, token, state_dir=tmp_path / "ha2")
    async with serving(srv2, tmp_path) as client2:
        op = await run(client2, "facility-2", "turn_on", {"entity": "light.does_not_exist"})
        assert op.state == "failed" and op.effect == "none" and op.error.may_have_acted is False
        assert (await read(client2, "facility-2", "light_does_not_exist")).quality == "invalid"
    await link2.close()


async def test_a_bad_token_is_unreachable_not_a_silent_success(tmp_path):
    w = World(BENCH, seed=9, attach_arm=False)
    srv, link = ha_adapter.build_server(w, FACILITY_HA, URL, "not-a-token", state_dir=tmp_path / "ha3")
    async with serving(srv, tmp_path) as client:
        op = await run(client, "facility-1", "turn_on", {"entity": "light.bed_light"})
        assert op.state == "failed" and op.effect == "none" and "refused the token" in op.error.message
        assert (await read(client, "facility-1", "light_bed_light")).quality == "invalid"
    await link.close()
