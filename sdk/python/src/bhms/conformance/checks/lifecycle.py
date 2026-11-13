"""Chapter 3 (lifecycle, metadata, versions, discovery, cancellation, cursors, extensions) and chapter 2 framing rules."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import rfc8785

from bhms.conformance.checks._util import raw_bytes, vectors
from bhms.conformance.context import Context
from bhms.conformance.core import check
from bhms.protocol.version import PROTOCOL_VERSION

CORE_METHODS = ("server/discover", "devices/list", "devices/describe", "properties/read", "actions/invoke", "operations/get",
                "operations/wait", "operations/list", "operations/cancel", "stop", "subscriptions/listen")
CAPABILITY_METHODS = {"leases": ("leases/acquire", "leases/renew", "leases/release"), "events": ("events/read",),
                      "programs": ("programs/run",), "programs.registry": ("programs/register", "programs/get", "programs/list")}


async def _vector_group(c: Context, group: str) -> None:
    """Send every vector of ``group`` raw and require a refusal with an acceptable code."""
    problems = []
    for vec in vectors("malformed")["vectors"]:
        if vec["group"] != group:
            continue
        try:
            answers = await c.wire.exchange_raw(raw_bytes(vec["raw"], vec.get("encoding"), c.wire.meta()), timeout=5.0)
        except (UnicodeError, ValueError) as exc:
            c.skip(f"this binding cannot carry the malformed frame of vector {vec['name']!r} ({exc})")
        expect = vec["expect"]
        errors = [a for a in answers if isinstance(a, dict) and isinstance(a.get("error"), dict)]
        accepted = [a for a in answers if isinstance(a, dict) and "result" in a]
        if accepted:
            problems.append(f"{vec['name']}: the server accepted it ({json.dumps(accepted[0])[:100]})")
        elif not errors:
            problems.append(f"{vec['name']}: no error response (got {answers!r})")
        else:
            error = errors[0]["error"]
            if error.get("code") not in expect["rpcCodes"]:
                problems.append(f"{vec['name']}: error {error.get('code')} (expected one of {expect['rpcCodes']})")
            elif error.get("code") == -32602 and (error.get("data") or {}).get("bhmsCode") != "INVALID_ARGUMENT":
                problems.append(f"{vec['name']}: -32602 without bhmsCode INVALID_ARGUMENT")
            if vec["group"] in ("batch",) and len(errors) != 1:
                problems.append(f"{vec['name']}: expected exactly one error, got {len(errors)}")
            if vec["group"] in ("batch", "id") and errors[0].get("id") is not None and vec["name"] != "jsonrpc-version":
                problems.append(f"{vec['name']}: the error must carry id null, carries {errors[0].get('id')!r}")
    c.expect(not problems, "; ".join(problems))
    # the connection must still work after every malformed frame
    c.result(await c.call("devices/list", {"limit": 1}), "devices/list after malformed frames")


@check("lifecycle.nan-tokens", ["BHMS-LIF-001"], generic=True)
async def nan_tokens(c: Context) -> None:
    """NaN and Infinity tokens are refused, never accepted."""
    await _vector_group(c, "nan")


@check("lifecycle.invalid-utf8-and-truncation", ["BHMS-LIF-001"], generic=True)
async def invalid_utf8(c: Context) -> None:
    """Invalid UTF-8 and truncated JSON are refused, never accepted."""
    await _vector_group(c, "utf8")


@check("lifecycle.request-id-rules", ["BHMS-LIF-010"], generic=True)
async def request_ids(c: Context) -> None:
    """An id that is null, an object, an array or a boolean is -32600; wrong jsonrpc or no method too."""
    await _vector_group(c, "id")
    await _vector_group(c, "shape")


@check("transport.batch-rejected", ["BHMS-TRN-002"], generic=True)
async def batch_rejected(c: Context) -> None:
    """A JSON array batch gets one -32600 error with id null."""
    await _vector_group(c, "batch")


@check("lifecycle.params-and-meta-required", ["BHMS-LIF-011"], generic=True)
async def params_required(c: Context) -> None:
    """No params, no _meta or no protocolVersion: INVALID_ARGUMENT naming _meta.bhms/protocolVersion."""
    await _vector_group(c, "params")
    for meta in (None, {}, {"bhms/clientInfo": {"name": "x", "version": "1"}}):
        response = await c.call("devices/list", {}, meta=meta)
        data = c.refused(response, "INVALID_ARGUMENT", may_have_acted=False)
        field = str(data.get("field", ""))
        c.expect("protocolVersion" in field or "_meta" in field, f"the error must name _meta.bhms/protocolVersion, names {field!r}")


@check("lifecycle.unknown-and-unadvertised-methods", ["BHMS-LIF-013"], generic=True)
async def unknown_method(c: Context) -> None:
    """An unknown method is -32601; a method of an un-advertised capability is UNSUPPORTED naming the capability."""
    response = await c.call("conformance/no_such_method", {})
    c.expect(response.rpc_code == -32601, f"unknown method should be -32601, got {response.describe()}")
    for capability, methods in CAPABILITY_METHODS.items():
        node: Any = c.caps
        for part in capability.split("."):
            node = node.get(part) if isinstance(node, dict) else None
        if node:
            continue
        for method in methods:
            response = await c.call(method, {})
            if response.rpc_code == -32601:
                continue  # -32601 for an un-advertised optional method is also an honest refusal (LIF-013 first sentence)
            data = c.refused(response, "UNSUPPORTED", may_have_acted=False, what=method)
            text = json.dumps(data) + str(response.error.get("message"))
            c.expect(capability.split(".")[0] in text, f"{method}: UNSUPPORTED should name the capability {capability!r}: {text[:160]}")


@check("lifecycle.notifications-get-no-response", ["BHMS-LIF-014", "BHMS-LIF-051"], generic=True)
async def notification_no_response(c: Context) -> None:
    """A notification (no id) is never answered, even an unknown one; cancelling an unknown request is ignored."""
    await c.wire.settle(0.05)
    await c.wire.notify("conformance/unknown-notification", {})
    await c.wire.notify("notifications/cancelled", {"requestId": "no-such-request-9999"})
    await c.wire.notify("notifications/cancelled", {"requestId": 987654321})
    stray = await c.wire.settle(0.3)
    c.expect(not stray, f"the server answered a notification: {json.dumps(stray)[:200]}")
    c.result(await c.call("devices/list", {"limit": 1}), "devices/list after notifications")
    # a request that has already finished
    response = await c.call("devices/list", {"limit": 1})
    await c.wire.notify("notifications/cancelled", {"requestId": response.request["id"]})
    stray = await c.wire.settle(0.2)
    c.expect(not stray, f"cancelling a finished request produced a message: {json.dumps(stray)[:200]}")


def _method_params(c: Context, device: str, description: dict[str, Any]) -> dict[str, dict[str, Any]]:
    prop = next(iter(description.get("properties") or {"x": 0}))
    return {
        "devices/list": {}, "devices/describe": {"deviceId": device}, "properties/read": {"deviceId": device, "property": prop},
        "operations/get": {"operationId": "op-none"}, "operations/wait": {"operationId": "op-none", "timeoutMs": 1},
        "operations/list": {}, "operations/cancel": {"operationId": "op-none"},
        "stop": {"reason": "closed params check", "deviceIds": ["no-such-device"]},
        "subscriptions/listen": {"notifications": {"devicesListChanged": True}},
        "leases/acquire": {"resources": ["x/y"], "ttlMs": 1000}, "leases/renew": {"leaseId": "l-none", "ttlMs": 1000},
        "leases/release": {"leaseId": "l-none"}, "events/read": {}, "programs/list": {}, "programs/get": {"digest": "sha256:" + "0" * 64},
    }


@check("lifecycle.closed-params", ["BHMS-LIF-015"], generic=True)
async def closed_params(c: Context) -> None:
    """An undeclared member in params is INVALID_ARGUMENT naming it, for every method."""
    summaries = await c.devices()
    if not summaries:
        c.not_applicable("the server lists no devices to build valid requests from")
    device = summaries[0]["deviceId"]
    description = await c.describe(device)
    problems = []
    for method, params in _method_params(c, device, description).items():
        if method.startswith(("leases/", "events/", "programs/")):
            if (method.startswith("leases") and "leases" not in c.caps) or (method.startswith("events") and "events" not in c.caps) \
                    or (method.startswith("programs") and "programs" not in c.caps):
                continue
        if method == "subscriptions/listen":
            continue
        response = await c.call(method, {**params, "undeclaredMember": 1})
        if response.code != "INVALID_ARGUMENT" or "undeclaredMember" not in json.dumps(response.error):
            problems.append(f"{method}: {response.describe()}")
    # actions/invoke: the same, with a deliberately closed request
    response = await c.invoke(device, "no_such_action", {}, undeclaredMember=1)
    if response.code != "INVALID_ARGUMENT" or "undeclaredMember" not in json.dumps(response.error):
        problems.append(f"actions/invoke: {response.describe()}")
    c.expect(not problems, "; ".join(problems))


@check("lifecycle.meta-keys", ["BHMS-LIF-016", "BHMS-LIF-017", "BHMS-AUTH-001"], generic=True)
async def meta_keys(c: Context) -> None:
    """Unknown bhms/ keys are refused, other prefixes ignored; clientInfo never changes authorization."""
    base = c.wire.meta()
    refused = await c.call("devices/list", {}, meta={**base, "bhms/admin": True})
    c.refused(refused, "INVALID_ARGUMENT", may_have_acted=False, what="_meta bhms/admin")
    c.expect("bhms/admin" in json.dumps(refused.error), "the refusal should name bhms/admin")
    c.result(await c.call("devices/list", {}, meta={**base, "com.example/x": {"anything": 1}}), "_meta with another prefix")
    before = (await c.ok("server/discover"))["principal"] if "principal" in c.discover_result else None
    for name in ("admin", "root", "bhms-gateway"):
        response = await c.call("server/discover", {}, meta={**base, "bhms/clientInfo": {"name": name, "version": "1"}})
        result = c.result(response, "discover with an admin-sounding clientInfo")
        c.expect(result.get("principal") == before, f"clientInfo.name {name!r} changed the principal: {result.get('principal')} vs {before}")
    for claim in ({"principal": "admin"}, {"scopes": ["admin"]}, {"bhms/principal": "admin"}):
        response = await c.call("devices/list", {}, meta={**base, **claim})
        if not response.ok:  # accepted-and-ignored is allowed for a key with another prefix
            c.expect(response.code == "INVALID_ARGUMENT", f"identity claim {claim} in _meta: {response.describe()}")


@check("lifecycle.version-negotiation", ["BHMS-LIF-019", "BHMS-ERR-011"], generic=True)
async def version_negotiation(c: Context) -> None:
    """An unserved version is UNSUPPORTED_VERSION (-32015) naming the field and listing supportedVersions."""
    response = await c.call("devices/list", {}, meta={"bhms/protocolVersion": "1999-01-01"})
    data = c.refused(response, "UNSUPPORTED_VERSION", field="_meta.bhms/protocolVersion", may_have_acted=False)
    c.expect(response.rpc_code == -32015, f"UNSUPPORTED_VERSION must be -32015, is {response.rpc_code}")
    bound = data.get("bound")
    c.expect(isinstance(bound, list) and bound, f"bound must list the supported versions, is {bound!r}")
    c.expect(PROTOCOL_VERSION in c.discover_result.get("supportedVersions", []), "discover.supportedVersions lacks the tested version")
    c.expect(sorted(bound) == sorted(c.discover_result["supportedVersions"]), f"bound {bound} differs from discover.supportedVersions")
    discover = await c.call("server/discover", {}, meta={"bhms/protocolVersion": "1999-01-01"})
    c.refused(discover, "UNSUPPORTED_VERSION", field="_meta.bhms/protocolVersion", may_have_acted=False, what="server/discover")


@check("lifecycle.discover", ["BHMS-LIF-020", "BHMS-LIF-021", "BHMS-LIF-023", "BHMS-LIF-024", "BHMS-LIF-025", "BHMS-TRN-004"], generic=True)
async def discover_contents(c: Context) -> None:
    """Required capabilities, stable within an epoch, no disclosure, no client capability required, sane limits."""
    d = c.discover_result
    for member in ("supportedVersions", "serverInfo", "capabilities", "epoch", "limits"):
        c.expect(member in d, f"server/discover lacks {member}")
    for capability in ("operations", "stop", "subscriptions"):
        c.expect(capability in c.caps, f"capabilities.{capability} must be advertised (BHMS-LIF-023)")
    descriptions = await c.descriptions()
    needs_lease = any(a.get("requiresLease") for desc in descriptions.values() for a in (desc.get("actions") or {}).values())
    if needs_lease:
        c.expect("leases" in c.caps, "an action requires a lease but capabilities.leases is not advertised")
    for member in ("devices", "operations", "leases"):
        c.expect(member not in d, f"server/discover must not disclose {member} (BHMS-LIF-021)")
    again = await c.ok("server/discover")
    c.expect(again["capabilities"] == c.caps, "capabilities changed between two discover calls of one epoch")
    c.expect(again["epoch"] == d["epoch"], "the epoch changed between two discover calls")
    result = await c.ok("devices/list", {}, meta={**c.wire.meta(), "bhms/clientCapabilities": {}})
    c.expect("devices" in result, "a request with empty clientCapabilities must succeed")
    maximum = c.limits.get("maxMessageBytes")
    c.expect(isinstance(maximum, int) and maximum >= 1_048_576, f"limits.maxMessageBytes must be at least 1048576, is {maximum!r}")
    c.expect(isinstance(c.limits.get("maxWaitMs"), int), "limits.maxWaitMs must be advertised")


@check("lifecycle.core-methods-implemented", ["BHMS-LIF-020"], generic=True)
async def core_methods(c: Context) -> None:
    """Every core method and every method of an advertised capability answers something other than -32601."""
    summaries = await c.devices()
    device = summaries[0]["deviceId"] if summaries else "no-device"
    description = await c.describe(device) if summaries else {}
    params = _method_params(c, device, description)
    methods = [m for m in CORE_METHODS if m not in ("server/discover", "actions/invoke", "subscriptions/listen")]
    for capability, extra in CAPABILITY_METHODS.items():
        node: Any = c.caps
        for part in capability.split("."):
            node = node.get(part) if isinstance(node, dict) else None
        if node:
            methods.extend(m for m in extra if m != "programs/run")
    missing = []
    for method in methods:
        response = await c.call(method, params.get(method, {}))
        if response.rpc_code == -32601:
            missing.append(method)
    response = await c.invoke(device, "no_such_action", {})
    if response.rpc_code == -32601:
        missing.append("actions/invoke")
    if "programs" in c.caps:
        response = await c.call("programs/run", {"arguments": {}})
        if response.rpc_code == -32601:
            missing.append("programs/run")
    stream, _ = await c.wire.listen({"devicesListChanged": True})
    await stream.cancel()
    c.expect(not missing, f"methods answered -32601: {missing}")


@check("lifecycle.stateless-connection", ["BHMS-LIF-030"], generic=True)
async def stateless(c: Context) -> None:
    """A fresh connection with no discover and no prior traffic: a request with its own _meta succeeds."""
    async with c.fresh_wire() as wire:
        result = c.result(await wire.request("devices/list", {"limit": 1}), "first request on a fresh connection")
        c.expect("devices" in result, "devices/list on a fresh connection returned no devices member")


@check("lifecycle.minted-identifiers", ["BHMS-LIF-031"], generic=True)
async def minted_ids(c: Context) -> None:
    """Identifiers the client invents (operation id, cursor) are refused, never adopted."""
    summaries = await c.devices()
    device = summaries[0]["deviceId"] if summaries else "x"
    response = await c.call("operations/get", {"operationId": "op-" + "0" * 24})
    c.refused(response, "INVALID_ARGUMENT", field="operationId", what="operations/get of an invented id")
    response = await c.call("devices/list", {"cursor": "fabricated-cursor"})
    c.refused(response, "INVALID_ARGUMENT", field="cursor", what="devices/list with an invented cursor")
    desc = await c.describe(device) if summaries else {}
    action = next(iter(desc.get("actions") or {"x": 0}))
    response = await c.invoke(device, action, {}, operationId="op-invented")
    c.refused(response, "INVALID_ARGUMENT", what="actions/invoke with an operationId member")


@check("lifecycle.cursors-and-ordering", ["BHMS-LIF-060", "BHMS-LIF-061", "BHMS-LIF-062"], generic=True)
async def cursors(c: Context) -> None:
    """Fabricated cursors are refused; paging loses and repeats nothing, honours limit and ends without nextCursor."""
    listing = [m for m, ok in (("devices/list", True), ("operations/list", True), ("events/read", "events" in c.caps),
                               ("programs/list", "programs" in c.caps and "registry" in c.caps["programs"])) if ok]
    for method in listing:
        member = "after" if method == "events/read" else "cursor"
        response = await c.call(method, {member: "fabricated.cursor.value"})
        c.refused(response, "INVALID_ARGUMENT", what=f"{method} with a fabricated cursor")
        c.expect(member in str(response.data.get("field", "")), f"{method}: the error should name {member}, names {response.data.get('field')!r}")
    everything = await c.devices(refresh=True)
    ids = [d["deviceId"] for d in everything]
    c.expect(ids == sorted(ids), f"devices must be ordered by deviceId (code point): {ids[:6]}")
    paged: list[str] = []
    cursor, pages = None, 0
    while True:
        page = await c.ok("devices/list", {"limit": 1, **({"cursor": cursor} if cursor else {})})
        c.expect(len(page["devices"]) <= 1, "a page exceeded limit 1")
        paged.extend(d["deviceId"] for d in page["devices"])
        cursor = page.get("nextCursor")
        pages += 1
        if cursor is None or pages > len(ids) + 3:
            break
    c.expect(cursor is None, "nextCursor never ended")
    c.expect(paged == ids, f"paging with limit 1 returned {paged}, a full listing returned {ids}")
    last = await c.ok("devices/list", {"limit": max(len(ids), 1)})
    c.expect("nextCursor" not in last or last["nextCursor"] is None, "nextCursor must be absent when nothing further exists")
    ops = await c.ok("operations/list", {"limit": 100})
    keys = [(-_epoch(o["createdAt"]), o["operationId"]) for o in ops["operations"]]
    c.expect(keys == sorted(keys), "operations must be listed by createdAt descending then operationId ascending")


def _epoch(stamp: str) -> float:
    from datetime import datetime

    return datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()


@check("lifecycle.extensions", ["BHMS-LIF-070"], generic=True)
async def extensions(c: Context) -> None:
    """Advertised extension ids follow the ExtensionKey pattern, never use the bhms/ prefix."""
    pattern = re.compile(r"^(?!bhms/)[a-z][a-z0-9-]*(\.[a-z][a-z0-9-]*)*/[A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?$")
    for key in (c.caps.get("extensions") or {}):
        c.expect(pattern.match(key), f"extension id {key!r} is not <reverse-dns>/<name> outside the bhms/ prefix")
    c.expect(not any(k.startswith("bhms/") for k in c.caps), "capabilities must not use the reserved bhms/ prefix as an extension")


@check("vectors.canonical-digests", ["BHMS-LIF-002"], generic=True)
async def canonical_vectors(c: Context) -> None:
    """The runner's JCS oracle agrees with the shared vectors (so a digest check cannot pass by sharing a bug)."""
    for vec in vectors("canonical")["vectors"]:
        produced = rfc8785.dumps(vec["value"]).decode()
        c.expect(produced == vec["canonical"], f"vector {vec['name']}: JCS gives {produced}, vector says {vec['canonical']}")
        import hashlib

        c.expect("sha256:" + hashlib.sha256(produced.encode()).hexdigest() == vec["digest"], f"vector {vec['name']}: digest differs")


@check("lifecycle.cancel-request-keeps-work", ["BHMS-LIF-050", "BHMS-TRN-012", "BHMS-TRN-032", "BHMS-LIF-044"])
async def cancel_request(c: Context) -> None:
    """Cancelling an actions/invoke request or an operations/wait stops the wait, never the physical work."""
    axis = c.axis()
    ident, task = c.wire.submit("actions/invoke", {"deviceId": axis, "action": "slow_move", "arguments": {"duration_ms": 600},
                                                   "waitMs": 5000})
    await asyncio.sleep(0.15)
    await c.wire.notify("notifications/cancelled", {"requestId": ident, "reason": "conformance"})
    await asyncio.sleep(0.3)
    c.expect(not task.done(), "the server answered a request after it was cancelled (nothing may follow a cancel, BHMS-TRN-012)")
    task.cancel()
    ops = (await c.ok("operations/list", {"deviceId": axis, "limit": 5}))["operations"]
    running = [o for o in ops if o["action"] == "slow_move"]
    c.expect(running, "the operation started by the cancelled invoke does not exist")
    op = await c.settle(running[0]["operationId"])
    c.expect(op["state"] == "completed", f"cancelling the request changed the operation: it ended {op['state']}")
    # a cancelled wait does not cancel the operation either
    started = await c.invoke_op(axis, "slow_move", {"duration_ms": 400})
    wident, wtask = c.wire.submit("operations/wait", {"operationId": started["operationId"], "timeoutMs": 5000})
    await asyncio.sleep(0.1)
    await c.wire.notify("notifications/cancelled", {"requestId": wident})
    await asyncio.sleep(0.1)
    wtask.cancel()
    op = await c.settle(started["operationId"])
    c.expect(op["state"] == "completed", f"cancelling operations/wait changed the operation: {op['state']}")
    await c.wire.settle(0.05)


@check("lifecycle.subscription-stream", ["BHMS-LIF-040", "BHMS-LIF-041", "BHMS-LIF-044", "BHMS-LIF-046", "BHMS-OBS-020", "BHMS-OPS-090"])
async def subscription_stream(c: Context) -> None:
    """Acknowledgement first and tagged; only requested types; refused filters listed; cancel ends delivery."""
    axis = c.axis()
    stream, ack = await c.wire.listen({"operations": {"deviceIds": [axis]},
                                       "observations": [{"deviceId": axis, "property": "no_such_property"}]})
    c.expect(ack.get("method") == "notifications/subscriptions/acknowledged", f"the first message must be the acknowledgement, was {ack.get('method')}",
             ("BHMS-LIF-040",))
    c.expect(ack["params"]["_meta"].get("bhms/subscriptionId") == stream.id, "the acknowledgement must carry the listen request id", ("BHMS-LIF-040",))
    refused = ack["params"].get("refused") or []
    c.expect(any("no_such_property" in json.dumps(r) or "observations" in r.get("path", "") for r in refused),
             f"the unknown observation filter must be listed in refused, ack={json.dumps(ack['params'])[:240]}", ("BHMS-OBS-020", "BHMS-LIF-040"))
    op = await c.invoke_op(axis, "pulse", {"count": 1})
    seen = []
    deadline = asyncio.get_running_loop().time() + 3
    while asyncio.get_running_loop().time() < deadline:
        item = await stream.next(0.3)
        if item is not None:
            seen.append(item)
        if any(n["params"]["operation"]["state"] in ("completed", "failed") for n in seen if n["method"] == "notifications/operation"):
            break
    kinds = {n["method"] for n in seen}
    c.expect(kinds <= {"notifications/operation"}, f"notifications of types that were not requested arrived: {kinds}", ("BHMS-LIF-041",))
    states = [n["params"]["operation"]["state"] for n in seen if n["params"]["operation"]["operationId"] == op["operationId"]]
    c.expect(states and states[-1] == "completed", f"the operation's notifications should end with completed, were {states}", ("BHMS-OPS-090",))
    c.expect(all("history" not in n["params"]["operation"] for n in seen), "operation notifications must omit history", ("BHMS-OPS-090",))
    order = ["accepted", "dispatching", "running", "completed"]
    positions = [order.index(s) for s in states if s in order]
    c.expect(positions == sorted(positions), f"operation notifications arrived out of order: {states}", ("BHMS-OPS-090",))
    # BHMS-LIF-046: the durable record exists without any subscription
    await stream.cancel()
    await asyncio.sleep(0.15)
    stream.drain()
    quiet = await c.invoke_op(axis, "pulse", {"count": 1})
    c.expect(await stream.next(0.4) is None, "the server sent a notification after the client cancelled the subscription", ("BHMS-LIF-044",))
    c.expect(not stream.final.done(), "the server sent a final result after the client cancelled the subscription", ("BHMS-LIF-044",))
    settled = await c.settle(quiet["operationId"])
    c.expect(settled["state"] == "completed", "an operation's outcome must be retrievable with operations/get without a subscription", ("BHMS-LIF-046",))
