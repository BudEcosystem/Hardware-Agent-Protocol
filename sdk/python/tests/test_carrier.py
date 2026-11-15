"""The request credential carrier ``_meta["bhms/authorization"]`` (spec/bhms/13-security.md BHMS-SEC-005..007; Ruling R56).

Task 8 deferral: the TypeScript SDK carried a TCP bearer in an SDK-private ``_meta["org.bhms.sdk/bearer"]`` and the Python SDK
had no TCP credential at all (``DeviceServer.listen("tcp://...")`` was refused). v0.2 defines one carrier for transports without
a credential header: raw TCP, a loopback WebSocket upgraded without ``Authorization``, and stdio.
"""

from __future__ import annotations

import json
import logging

import pytest
import websockets

from bhms.client.client import Client
from bhms.protocol.errors import BhmsError
from bhms.protocol.version import V0_1
from bhms.runtime.authority import Policy, token_digest
from bhms.server import DeviceServer, Range
from bhms.testing.memory import connect_in_process
from helpers.devices import build

ADMIN, READER = "carrier-admin-token", "carrier-reader-token"


def policy() -> Policy:
    return Policy({"admin": {"tokens": [token_digest(ADMIN)], "scopes": ["admin"]},
                   "reader": {"tokens": [token_digest(READER)], "scopes": ["read"]}}, trust_same_uid=False)


@pytest.fixture
async def tcp(tmp_path, unused_tcp_port):
    srv, axis = build(tmp_path / "state", policy=policy())
    listener = await srv.listen(f"tcp://127.0.0.1:{unused_tcp_port}")
    yield srv, f"tcp://127.0.0.1:{unused_tcp_port}"
    await listener.close()
    await srv.close()


async def refused(coro) -> BhmsError:
    with pytest.raises(BhmsError) as info:
        await coro
    return info.value


async def test_tcp_requests_carry_their_credential(tcp, caplog):  # BHMS-SEC-005
    caplog.set_level(logging.DEBUG)
    srv, url = tcp
    client = await Client.connect(url, token=ADMIN)
    try:
        assert (await client.discover()).principal.id == "admin"
        op = (await client.actions_invoke("axis-1", "move_to", {"target": 3}, wait_ms=2000)).operation
        assert op.state == "completed"
    finally:
        await client.close()
    reader = await Client.connect(url, token=READER)
    try:
        assert (await refused(reader.actions_invoke("axis-1", "move_to", {"target": 4}))).bhms_code == "UNAUTHORIZED"
    finally:
        await reader.close()
    anonymous = await Client.connect(url)
    try:
        assert (await anonymous.discover()).principal is None
        assert (await refused(anonymous.devices_list())).bhms_code == "UNAUTHORIZED"
    finally:
        await anonymous.close()
    wrong = await Client.connect(url, token="not-the-token")
    try:
        exc = await refused(wrong.devices_list())
        assert exc.bhms_code == "UNAUTHORIZED" and "not valid" in exc.message
    finally:
        await wrong.close()
    assert ADMIN not in caplog.text and READER not in caplog.text  # never logged (BHMS-SEC-002)


async def test_a_v0_1_request_does_not_get_the_carrier_from_the_client(tcp):  # BHMS-LIF-016 for v0.1 peers
    srv, url = tcp
    client = await Client.connect(url, token=ADMIN)
    try:
        client.version = V0_1
        assert "bhms/authorization" not in client._meta()
    finally:
        await client.close()


async def test_a_carrier_beside_a_transport_credential_is_refused(tmp_path, unused_tcp_port):  # BHMS-SEC-006
    srv, axis = build(tmp_path / "state", policy=policy(), token=ADMIN)
    listener = await srv.listen(f"ws://127.0.0.1:{unused_tcp_port}")
    unix = await srv.listen(f"unix:{tmp_path}/s.sock")
    url = f"ws://127.0.0.1:{unused_tcp_port}"

    async def ask(conn, meta_extra):
        await conn.send(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "devices/list",
                                    "params": {"_meta": {"bhms/protocolVersion": "2026-11-15", **meta_extra}}}))
        return json.loads(await conn.recv())

    try:
        async with websockets.connect(url, subprotocols=["bhms"]) as bare:  # loopback, no header: the carrier is the credential
            assert ask and (await ask(bare, {}))["error"]["data"]["bhmsCode"] == "UNAUTHORIZED"
            assert "result" in await ask(bare, {"bhms/authorization": f"Bearer {ADMIN}"})
        async with websockets.connect(url, subprotocols=["bhms"], additional_headers={"Authorization": f"Bearer {READER}"}) as headed:
            twice = await ask(headed, {"bhms/authorization": f"Bearer {ADMIN}"})
            assert twice["error"]["data"]["bhmsCode"] == "UNAUTHORIZED" and "second" in twice["error"]["message"]
        transport = await connect_in_process(srv.rpc)  # an in-process peer is a Unix peer of this uid
        client = await Client.from_transport(transport, credential=ADMIN)
        try:
            assert (await refused(client.devices_list())).bhms_code == "UNAUTHORIZED"
        finally:
            await client.close()
    finally:
        await listener.close()
        await unix.close()
        await srv.close()


async def test_tls_schemes_and_off_loopback_tcp_are_refused_without_tls(tmp_path):  # BHMS-SEC-007, BHMS-TRN-021
    srv, _ = build(tmp_path / "state", policy=policy())
    try:
        with pytest.raises(ValueError, match="tcps:// promises encryption"):
            await srv.listen("tcps://127.0.0.1:9")
        with pytest.raises(ValueError, match="BHMS-TRN-021"):
            await srv.listen("tcp://0.0.0.0:9")
    finally:
        await srv.close()


async def test_on_stdio_a_carrier_is_the_requests_principal(tmp_path):  # BHMS-SEC-005 (stdio)
    srv = DeviceServer("stdio-carrier", state_dir=tmp_path / "s", policy=policy())
    dev = srv.device("d", resources=["d"])
    dev.report_alive()

    @dev.action(effect="reversible", idempotency="absolute", max_duration_ms=1000)
    async def go(ctx, value: Range(0, 1, unit="1")) -> None:  # noqa: F821
        """Go."""

    await srv.start()
    try:
        from bhms.transport.base import Peer

        transport = await connect_in_process(srv.rpc, peer=Peer("stdio", address="parent"))
        reader = await Client.from_transport(transport, credential=READER)
        reader._credential = READER
        try:
            assert (await reader.discover()).principal.id == "reader"
            assert (await refused(reader.actions_invoke("d", "go", {"value": 1}))).bhms_code == "UNAUTHORIZED"
        finally:
            await reader.close()
    finally:
        await srv.close()
