"""STOP and STOP_ACK are correlated by a token (BHMS-CMP-050, compact version 2): only the acks of the stop in progress confirm it."""

from __future__ import annotations

import asyncio
import logging

from helpers.compact_rig import BENCH, compact_rig, effects
from helpers.compact_script import Scripted, scripted_rig

from bhms.gateway import compact_bridge
from bhms.gateway.compact_bridge import CompactBridge, Timing
from bhms.protocol.types import to_wire
from bhms.testing.compact_endpoint import TO_DEVICE
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
        assert any(e["data"].get("reason") == "endpoint-originated stop" for e in events)  # reported, as an event


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


# ---------------------------------------------------------------- tokens across a HELLO and a bridge restart (R40)

def first_tokens(monkeypatch, *seeds):
    """Make the bridges created next start their token counters at ``seeds`` (in order) instead of at random values."""
    values = iter(seeds)
    monkeypatch.setattr(compact_bridge, "_initial_stop_token", lambda: next(values), raising=False)


async def stop_events(client):
    return [e["data"] for e in to_wire(await client.events_read(types=["stop"]))["events"]]


def test_a_bridge_starts_its_stop_tokens_at_a_random_value(tmp_path):
    seeds = {CompactBridge("b", "unix:/unused", BENCH)._stop_token for _ in range(12)}
    assert len(seeds) > 1 and all(0 <= s <= 254 for s in seeds)  # (the first token is seed % 255 + 1: never 0)


async def test_a_restarted_bridge_is_not_confirmed_by_the_late_ack_of_its_predecessors_stop(tmp_path, monkeypatch):
    """Bridge 1: stop A is ``initiated`` and the bridge goes away before the confirming ack. Bridge 2 (same endpoint, same
    epoch): every STOP of stop B is lost, and A's ``confirmed/measured`` arrives. With a counter that started at 0 in every
    bridge both stops had token 1 and B was reported confirmed."""
    first_tokens(monkeypatch, 40, 170)
    script = Scripted(cp.digest8_of(BENCH), epoch=7, flags=PERSISTENT)
    async with scripted_rig(tmp_path, sidecar=BENCH, scripted=script) as (client, bridge, ep):
        ep.on[cp.Stop] = lambda e, m: e.say(cp.StopAck(cp.STOPACK_INITIATED, cp.EVIDENCE_NONE, 0, m.token))
        a = to_wire(await client.stop("t", device_ids=["bench-rig"], wait_ms=300))["stops"][0]
        assert a["outcome"] == "initiated"
        token_a = ep.of(cp.Stop)[0].token
    script = Scripted(cp.digest8_of(BENCH), epoch=7, flags=PERSISTENT)
    async with scripted_rig(tmp_path, sidecar=BENCH, scripted=script) as (client, bridge, ep):
        ep.on[cp.Stop] = lambda e, m: None  # B's STOPs never arrive
        asyncio.get_running_loop().call_later(0.1, lambda: ep.say(
            cp.StopAck(cp.STOPACK_CONFIRMED, cp.EVIDENCE_MEASURED, 0, token_a), kind=cp.TELEMETRY))
        b = await stop(client)
        assert ep.of(cp.Stop) and all(m.token != token_a for m in ep.of(cp.Stop))
        assert b["outcome"] == "failed"


async def test_a_closing_bridge_ends_its_stop_in_progress_at_once_and_says_so(tmp_path):
    """No ack can reach a stop once its bridge closes, so the stop ends then (failed, the device may be stopped) instead of
    holding the gateway's shutdown for its bound or outliving the server."""
    script = Scripted(cp.digest8_of(BENCH), epoch=7, flags=PERSISTENT)
    async with scripted_rig(tmp_path, sidecar=BENCH, scripted=script) as (client, bridge, ep):
        ep.on[cp.Stop] = lambda e, m: e.say(cp.StopAck(cp.STOPACK_INITIATED, cp.EVIDENCE_NONE, 0, m.token))
        a = to_wire(await client.stop("t", device_ids=["bench-rig"], wait_ms=200))["stops"][0]
        assert a["outcome"] == "initiated"
        seen: list[dict] = []
        bridge.server.events.listen(lambda event, seq: seen.append(event))
        await client.close()
        started = asyncio.get_running_loop().time()
        await bridge.close()
        assert asyncio.get_running_loop().time() - started < 1.0  # the stop's bound is 2 s
        failed = [e for e in seen if e["type"] == "stop" and e["data"]["outcome"] == "failed"]
        assert len(failed) == 1 and "closed before the stop was confirmed" in failed[0]["message"], seen


async def test_an_ack_with_a_token_from_before_the_last_hello_confirms_nothing(tmp_path):
    """The endpoint forgets a stop's token at every HELLO it sends (BHMS-CMP-050), so an ack that still carries a token
    issued before the last adopted HELLO does not come from a conforming endpoint's stop: the bridge ignores it."""
    script = Scripted(cp.digest8_of(BENCH), epoch=7, flags=PERSISTENT)
    async with scripted_rig(tmp_path, sidecar=BENCH, scripted=script) as (client, bridge, ep):
        ep.on[cp.Stop] = lambda e, m: e.say(cp.StopAck(cp.STOPACK_INITIATED, cp.EVIDENCE_NONE, 0, m.token))
        a = to_wire(await client.stop("t", device_ids=["bench-rig"], wait_ms=200))["stops"][0]
        assert a["outcome"] == "initiated"
        token = ep.of(cp.Stop)[0].token
        hellos = len(ep.of(cp.HelloReq))
        ep.say(cp.Status(1, cp.ST_RUNNING, 0, 0), session=8)  # a frame of another epoch: the bridge asks for HELLO again
        for _ in range(100):
            if len(ep.of(cp.HelloReq)) > hellos:
                break
            await asyncio.sleep(0.02)
        else:
            raise AssertionError("the bridge never asked for a new HELLO")
        await asyncio.sleep(0.1)  # the HELLO is adopted
        ep.say(cp.StopAck(cp.STOPACK_CONFIRMED, cp.EVIDENCE_MEASURED, 0, token), kind=cp.TELEMETRY)
        outcomes: list[str] = []
        for _ in range(150):
            outcomes = [d["outcome"] for d in await stop_events(client)]
            if "failed" in outcomes or "confirmed" in outcomes:
                break
            await asyncio.sleep(0.02)
        assert "confirmed" not in outcomes and "failed" in outcomes
        # a stop sent after the HELLO is confirmed as usual
        ep.on[cp.Stop] = confirm()
        assert (await stop(client))["outcome"] == "confirmed"


async def test_the_c_endpoint_gives_its_pre_hello_stop_token_zero_so_a_restarted_bridge_is_not_confirmed(tmp_path, native,
                                                                                                    monkeypatch):
    """The reviewer's reproduction against the real endpoint, with the worst case forced: both bridges issue the same
    token. A bridge restart says a plain HELLO_REQ (no NEW_SESSION), so the endpoint keeps finishing stop A; its confirming
    ack must not carry A's token after that HELLO."""
    first_tokens(monkeypatch, 6, 6)
    slow = Timing(reply=1.0, retries=3, poll=0.3, probe=0.4, probe_misses=2, hello=0.3, stop_confirm=2.0)
    async with compact_rig(tmp_path, native, args=("--stop-ms", "1500")) as rig:
        a = to_wire(await rig.client.stop("t", device_ids=["bench-rig"], wait_ms=200))["stops"][0]
        assert a["outcome"] == "initiated"
        token = rig.wire.sent(cp.Stop)[0].message.token
        rig.timing = slow  # stop B keeps asking for 4 s: the endpoint finishes stop A in the middle of it
        await rig.restart_bridge()
        rig.wire.drop(TO_DEVICE, 1000, lambda m: isinstance(m, cp.Stop))  # B's STOPs are all lost
        b = to_wire(await rig.client.stop("t", device_ids=["bench-rig"], wait_ms=6000))["stops"][0]
        lost = [s for s in rig.wire.sent(cp.Stop) if not s.delivered]
        assert lost and all(s.message.token == token for s in lost)  # the same token as stop A, and none arrived
        assert len(effects(rig, "STOP")) == 1  # the endpoint ran its stop procedure once: for A
        acks = [s.message for s in rig.wire.sent(cp.StopAck)]
        assert [(m.outcome, m.token) for m in acks] == [(cp.STOPACK_INITIATED, token), (cp.STOPACK_CONFIRMED, 0)]
        assert b["outcome"] == "failed"
        assert "endpoint-originated stop" in b["error"]["message"]  # and it says what was seen instead
        assert any(d.get("reason") == "endpoint-originated stop" and d["outcome"] == "confirmed"
                   for d in await stop_events(rig.client))


# ---------------------------------------------------------------- the endpoint's own stop during a gateway stop

async def test_the_hardware_stop_during_a_gateway_stop_fails_it_and_says_the_device_may_be_stopped(tmp_path):
    """BHMS-CMP-050: the endpoint's stop input replaces the token of the gateway stop in progress, so the confirming ack
    carries token 0. The gateway stop is not confirmed (the safe direction); its error says what happened."""
    script = Scripted(cp.digest8_of(BENCH), epoch=7, flags=PERSISTENT)
    async with scripted_rig(tmp_path, sidecar=BENCH, scripted=script) as (client, bridge, ep):
        async def pin_fires(e, m):
            e.say(cp.StopAck(cp.STOPACK_INITIATED, cp.EVIDENCE_NONE, 0, m.token))
            await asyncio.sleep(0.05)
            e.say(cp.StopAck(cp.STOPACK_INITIATED, cp.EVIDENCE_NONE, 0, 0), kind=cp.TELEMETRY)
            await asyncio.sleep(0.05)
            e.say(cp.StopAck(cp.STOPACK_CONFIRMED, cp.EVIDENCE_MEASURED, 0, 0), kind=cp.TELEMETRY)

        ep.on[cp.Stop] = pin_fires
        s = await stop(client)
        assert s["outcome"] == "failed"
        message = s["error"]["message"]
        assert "endpoint-originated stop" in message and "may be stopped" in message and "read" in message
        assert len(ep.of(cp.Stop)) == 1  # known as soon as the endpoint's confirmation arrived: no waiting out the bound
        # a stop that simply got no answer says nothing of the kind
        ep.on[cp.Stop] = lambda e, m: None
        silent = await stop(client)
        assert silent["outcome"] == "failed" and "endpoint-originated" not in silent["error"]["message"]


async def test_a_refused_compact_version_is_logged_once_at_error_then_quietly(tmp_path, caplog):
    caplog.set_level(logging.DEBUG, logger="bhms.gateway.compact")
    old = Scripted(cp.digest8_of(BENCH), epoch=7, flags=PERSISTENT, version=1)
    async with scripted_rig(tmp_path, sidecar=BENCH, scripted=old, served=False) as (client, bridge, ep):
        for _ in range(200):
            if len(ep.of(cp.HelloReq)) >= 3:
                break
            await asyncio.sleep(0.05)
        await asyncio.sleep(0.1)
        assert len(ep.of(cp.HelloReq)) >= 3  # the bridge keeps asking (the endpoint may be reflashed)...
    about_version = [r for r in caplog.records if "compact version" in r.getMessage()]
    assert [r.levelno for r in about_version if r.levelno >= logging.WARNING] == [logging.ERROR]  # ...and says it once
    assert len(about_version) >= 3 and all(r.levelno == logging.DEBUG for r in about_version[1:])
