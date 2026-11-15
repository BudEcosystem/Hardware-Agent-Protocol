"""Per-principal budgets at the gateway, across its upstreams (spec/bhms/07-leases-and-authority.md 7.4.1; Ruling R50).

The gateway enforces its own policy's budgets with the same module as a device server (:mod:`bhms.runtime.budgets`): the
reservation is written with the pending-forward record, released when the upstream refused before creating anything, and
kept for anything that was forwarded and may have acted.
"""

from __future__ import annotations

import pytest

from bhms.client.client import Client
from bhms.protocol.errors import BhmsError
from bhms.runtime.authority import token_digest
from helpers.gateway_rig import TOKENS, principals, rig

BUDGET = {"id": "pulses", "action": "*/axis-1/pulse", "quantity": "/count", "unit": "1", "total": 5}


def budgeted() -> dict:
    doc = principals()
    doc["agent-b"] = {"tokens": [token_digest(TOKENS["agent-b"])], "scopes": ["read", "lease", "invoke:*/*"],
                      "budgets": [BUDGET]}
    return doc


async def refused(coro) -> BhmsError:
    with pytest.raises(BhmsError) as info:
        await coro
    return info.value


async def test_one_budget_spans_the_upstreams_and_is_enforced_at_the_gateway(tmp_path):
    async with rig(tmp_path, conformance=True, principals_doc=budgeted()) as r:
        agent = await r.client(token=TOKENS["agent-b"])
        before = {name: axis.counter for name, axis in r.axes.items()}
        await agent.actions_invoke("a/axis-1", "pulse", {"count": 3}, wait_ms=2000)
        exc = await refused(agent.actions_invoke("b/axis-1", "pulse", {"count": 3}, operation_key="over"))
        assert exc.bhms_code == "OUT_OF_RANGE" and exc.field == "arguments.count" and exc.bound["maximum"] == 2
        assert r.axes["b"].counter == before["b"]  # refused at the gateway: nothing forwarded
        assert r.gateway.journal.lookup_key("agent-b", "over") is None and r.gateway.journal.pending_get("agent-b", "over") is None
        found = await agent.discover()
        assert found.capabilities.authority.budgets is True and found.principal.budgets[0].remaining == 2
        await agent.actions_invoke("b/axis-1", "pulse", {"count": 2}, wait_ms=2000)
        assert r.axes["a"].counter + r.axes["b"].counter == sum(before.values()) + 2  # two commands, five pulses


async def test_an_upstream_refusal_gives_the_reservation_back(tmp_path):
    async with rig(tmp_path, conformance=True, principals_doc=budgeted()) as r:
        agent = await r.client(token=TOKENS["agent-b"])
        direct = await Client.connect(f"unix:{tmp_path}/b.sock")  # the upstream's own principal holds its motion lease
        try:
            await direct.leases_acquire(["axis-1/motion"], 30_000)
            exc = await refused(agent.actions_invoke("b/axis-1", "pulse", {"count": 4}))
            assert exc.bhms_code == "LEASE_CONFLICT" and exc.may_have_acted is False
            assert (await agent.discover()).principal.budgets[0].remaining == 5
        finally:
            await direct.close()


async def test_the_gateways_budget_survives_its_restart(tmp_path):
    async with rig(tmp_path, conformance=True, principals_doc=budgeted()) as r:
        agent = await r.client(token=TOKENS["agent-b"])
        await agent.actions_invoke("a/axis-1", "pulse", {"count": 4}, wait_ms=2000)
    async with rig(tmp_path, conformance=True, principals_doc=budgeted()) as r:
        agent = await r.client(token=TOKENS["agent-b"])
        assert (await agent.discover()).principal.budgets[0].remaining == 1
        assert (await refused(agent.actions_invoke("a/axis-1", "pulse", {"count": 2}))).bound["maximum"] == 1
