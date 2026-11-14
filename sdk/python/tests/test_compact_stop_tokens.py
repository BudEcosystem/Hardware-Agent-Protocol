"""STOP and STOP_ACK are correlated by a token (BHMS-CMP-050, compact version 2): only the acks of the stop in progress confirm it."""

from __future__ import annotations

import asyncio
import logging

from helpers.compact_rig import BENCH
from helpers.compact_script import Scripted, scripted_rig

from bhms.protocol.types import to_wire
from bhms.transport import compact as cp

PERSISTENT = cp.FLAG_PERSISTENT_EPOCH | cp.FLAG_FENCING | cp.FLAG_STOP_SUPPORTED


def confirm(token_of=lambda m: m.token, delay=0.0):
    async def behave(ep, m):
        if delay:
            await asyncio.sleep(delay)
        ep.say(cp.StopAck(cp.STOPACK_CONFIRMED, cp.EVIDENCE_MEASURED, 0, token_of(m)))

    return behave


async def stop(client):
    return to_wire(await client.stop("t", device_ids=["bench-rig"], wait_ms=4000))["stops"][0]


async def test_an_echoed_token_confirms_a_stop_with_one_frame_even_after_an_unanswered_stop(tmp_path):
    script = Scripted(cp.digest8_of(BENCH), epoch=7, flags=PERSISTENT)
    async with scripted_rig(tmp_path, sidecar=BENCH, scripted=script) as (client, bridge, ep):
        ep.on[cp.Stop] = lambda e, m: None  # the first stop is not answered at all
        assert (await stop(client))["outcome"] != "confirmed"
        ep.seen.clear()
        ep.on[cp.Stop] = confirm()
        for _ in range(4):
            before = len(ep.of(cp.Stop))
            assert (await stop(client))["outcome"] == "confirmed"
            assert len(ep.of(cp.Stop)) - before == 1  # no residue from the unanswered one
        tokens = {m.token for m in ep.of(cp.Stop)}
        assert 0 not in tokens and len(tokens) == 4  # non-zero and distinct per stop


async def test_the_late_acks_of_a_confirmed_stop_never_confirm_the_next_one(tmp_path):
    """Acks arrive 1.5 reply times late: stop A retransmits and is confirmed by the first ack; stop B starts after A's retransmit
    is long forgotten by any time horizon; the endpoint never receives B's STOPs. A's second late ack must not confirm B."""
    script = Scripted(cp.digest8_of(BENCH), epoch=7, flags=PERSISTENT)
    async with scripted_rig(tmp_path, sidecar=BENCH, scripted=script) as (client, bridge, ep):
        first_token: list[int] = []

        async def late(e, m):
            if not first_token:
                first_token.append(m.token)
            if m.token != first_token[0]:
                return  # B's STOPs never reach the endpoint
            await asyncio.sleep(bridge.timing.reply * 1.5)
            e.say(cp.StopAck(cp.STOPACK_CONFIRMED, cp.EVIDENCE_MEASURED, 0, m.token))

        ep.on[cp.Stop] = late
        a = await stop(client)
        assert a["outcome"] == "confirmed"
        b = await stop(client)
        assert b["outcome"] != "confirmed"  # the retransmitted STOP's second ack belongs to A


async def test_an_ack_with_a_foreign_token_or_the_hardware_token_confirms_nothing(tmp_path, caplog):
    script = Scripted(cp.digest8_of(BENCH), epoch=7, flags=PERSISTENT)
    async with scripted_rig(tmp_path, sidecar=BENCH, scripted=script) as (client, bridge, ep):
        ep.on[cp.Stop] = confirm(token_of=lambda m: m.token % 255 + 1)  # another stop's token
        assert (await stop(client))["outcome"] != "confirmed"
        ep.on[cp.Stop] = confirm(token_of=lambda m: 0)  # the endpoint's own stop input
        assert (await stop(client))["outcome"] != "confirmed"
        events = to_wire(await client.events_read(types=["stop"]))["events"]
        assert any(e["data"].get("reason") == "endpoint hardware stop input" for e in events)  # reported, as an event


async def test_an_endpoint_of_another_compact_version_is_refused_with_a_clear_log(tmp_path, caplog):
    caplog.set_level(logging.ERROR, logger="bhms.gateway.compact")
    old = Scripted(cp.digest8_of(BENCH), epoch=7, flags=PERSISTENT, version=1)
    async with scripted_rig(tmp_path / "hello", sidecar=BENCH, scripted=old, served=False) as (client, bridge, ep):
        await asyncio.sleep(1.0)
        assert not bridge.ready and bridge.device is None
    assert "compact version 1" in caplog.text
    caplog.clear()
    refusing = Scripted(cp.digest8_of(BENCH), epoch=7, flags=PERSISTENT)
    refusing.on[cp.HelloReq] = lambda e, m: e.say(cp.Error(cp.HELLO_REQ, 0, cp.E_UNSUPPORTED, 1))  # a version 1 endpoint's answer
    async with scripted_rig(tmp_path / "error", sidecar=BENCH, scripted=refusing, served=False) as (client, bridge, ep):
        await asyncio.sleep(1.0)
        assert not bridge.ready and bridge.device is None
    assert "speaks compact version 1" in caplog.text and "not served" in caplog.text
