"""Chapter 4: descriptions, digests and static rules every device description must satisfy."""

from __future__ import annotations

import json
from typing import Any

from bhms.conformance.checks._util import walk_schema
from bhms.conformance.context import Context
from bhms.conformance.core import check
from bhms.protocol import units
from bhms.protocol.canonical import canonical


@check("descriptions.digest-and-immutability", ["BHMS-DEV-020", "BHMS-DEV-021", "BHMS-LIF-002"], generic=True)
async def digest_immutability(c: Context) -> None:
    """The digest is the JCS digest of the description; two describes with one digest are byte-identical."""
    summaries = await c.devices(refresh=True)
    c.expect(summaries, "the server lists no devices, so no description can be checked")
    for summary in summaries:
        first = (await c.ok("devices/describe", {"deviceId": summary["deviceId"]}))["description"]
        second = (await c.ok("devices/describe", {"deviceId": summary["deviceId"]}))["description"]
        c.expect(c.digest_of(first) == first.get("digest"),
                 f"{summary['deviceId']}: digest {first.get('digest')} is not sha256(JCS(description without digest)) = {c.digest_of(first)}")
        c.expect(canonical(first) == canonical(second) or first["digest"] != second["digest"],
                 f"{summary['deviceId']}: two descriptions with digest {first['digest']} differ")
        c.expect(first["digest"] == summary.get("digest"), f"{summary['deviceId']}: summary digest {summary.get('digest')} differs from description digest")
        c.expect(first["digest"] == second["digest"], f"{summary['deviceId']}: the digest changed between two describes")
        c.expect(set(first.get("actions", {})) == set(summary.get("actions", [])), f"{summary['deviceId']}: summary actions differ from the description")
        c.expect(set(first.get("properties", {})) == set(summary.get("properties", [])), f"{summary['deviceId']}: summary properties differ from the description")


@check("descriptions.stale-digest", ["BHMS-DEV-022"], generic=True)
async def stale_digest(c: Context) -> None:
    """devices/describe with a digest that is not current is STALE naming digest, bound = the current digest."""
    device = (await c.devices())[0]["deviceId"]
    current = (await c.describe(device))["digest"]
    result = await c.ok("devices/describe", {"deviceId": device, "digest": current})
    c.expect("description" in result, "describe with the current digest must still succeed")
    wrong = "sha256:" + ("0" * 64 if not current.endswith("0" * 64) else "1" * 64)
    response = await c.call("devices/describe", {"deviceId": device, "digest": wrong})
    data = c.refused(response, "STALE", field="digest", may_have_acted=False)
    c.expect(data.get("bound") == current or isinstance(data.get("bound"), dict), f"STALE bound must be the current digest {current}, is {data.get('bound')!r}")
    if isinstance(data.get("bound"), str):
        c.expect(data["bound"] == current, f"STALE bound {data['bound']} is not the current digest {current}")


def _problems_static(description: dict[str, Any]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {k: [] for k in ("DEV-032", "DEV-034", "DEV-040", "DEV-041", "DEV-042", "EVT-003")}
    device = description.get("deviceId")
    resources = set(description.get("resources") or [])
    properties = description.get("properties") or {}
    for name, action in (description.get("actions") or {}).items():
        where = f"{device}.{name}"
        for resource in action.get("resources") or []:
            if resource not in resources:
                out["DEV-032"].append(f"{where}: resource {resource!r} is not a resource of the device")
        if action.get("requiresLease") and not action.get("resources"):
            out["DEV-032"].append(f"{where}: requires a lease but declares no resources")
        seen = set()
        for entry in action.get("requiresFresh") or []:
            prop = entry.get("property")
            if prop not in properties:
                out["DEV-034"].append(f"{where}: requiresFresh names unknown property {prop!r}")
            if prop in seen:
                out["DEV-034"].append(f"{where}: requiresFresh names {prop!r} twice")
            seen.add(prop)
        schema = action.get("input") or {}
        if schema.get("type") != "object" or schema.get("additionalProperties") is not False:
            out["DEV-040"].append(f"{where}: input must be an object schema with additionalProperties false")
    schemas = [(f"{device}.{n}.input", a.get("input")) for n, a in (description.get("actions") or {}).items()]
    schemas += [(f"{device}.{n}.output", a.get("output")) for n, a in (description.get("actions") or {}).items() if a.get("output")]
    schemas += [(f"{device}.{n}.schema", p.get("schema")) for n, p in properties.items()]
    schemas += [(f"{device}.event.{n}", e.get("data") or e.get("schema")) for n, e in (description.get("events") or {}).items()
                if isinstance(e, dict) and (e.get("data") or e.get("schema"))]
    for label, schema in schemas:
        for path, sub in walk_schema(schema):
            if "$ref" in sub and not str(sub["$ref"]).startswith("#"):
                out["DEV-040"].append(f"{label}{path}: remote $ref {sub['$ref']!r}")
            if sub.get("type") in ("number", "integer") or (isinstance(sub.get("type"), list) and {"number", "integer"} & set(sub["type"])):
                unit = sub.get("x-bhms-unit")
                if not isinstance(unit, str) or not unit:
                    out["DEV-041"].append(f"{label}{path}: numeric schema without x-bhms-unit")
                else:
                    try:
                        units.convert(1.0, unit, unit)
                    except Exception:
                        out["DEV-042"].append(f"{label}{path}: unit {unit!r} is not in the BHMS unit registry")
    return out


@check("descriptions.static-rules", ["BHMS-DEV-032", "BHMS-DEV-034", "BHMS-DEV-040", "BHMS-DEV-041", "BHMS-DEV-042"], generic=True)
async def static_rules(c: Context) -> None:
    """Resources, requiresFresh, closed inputs, no remote refs, units on every numeric schema, units from the registry."""
    problems: list[str] = []
    for description in (await c.descriptions()).values():
        for rid, found in _problems_static(description).items():
            problems.extend(f"BHMS-{rid}: {p}" for p in found if rid != "EVT-003")
    c.expect(not problems, "; ".join(problems[:6]))


@check("descriptions.hazardous-actions-require-lease", ["BHMS-DEV-033"], generic=True)
async def hazardous_lease(c: Context) -> None:
    """SHOULD: actions with effect hazardous declare requiresLease."""
    problems = [f"{device}.{name} is hazardous without requiresLease"
                for device, description in (await c.descriptions()).items()
                for name, action in (description.get("actions") or {}).items()
                if action.get("effect") == "hazardous" and not action.get("requiresLease")]
    c.expect(not problems, "; ".join(problems))


@check("descriptions.stop-and-disconnect-claims", ["BHMS-DEV-060"], generic=True)
async def stop_claims(c: Context) -> None:
    """MUST: onDisconnect other than unknown only when implemented device-side (not provable here: such a claim is
    skipped for inspection). SHOULD (reported as a warning): irreversible or hazardous devices declare stop supported."""
    claims = []
    for device, description in (await c.descriptions()).items():
        safety = description.get("safety") or {}
        risky = any(a.get("effect") in ("irreversible", "hazardous") for a in (description.get("actions") or {}).values())
        if risky and safety.get("stop") != "supported":
            c.warn(f"{device} has irreversible or hazardous actions but declares stop {safety.get('stop')!r}")
        if safety.get("onDisconnect") not in (None, "unknown"):
            claims.append(f"{device} declares onDisconnect {safety.get('onDisconnect')!r}")
    if claims:
        c.skip("device-side implementation of onDisconnect cannot be proven by a wire test (inspection): " + "; ".join(claims))


@check("descriptions.size-and-summary", ["BHMS-DEV-011"], generic=True)
async def summary_size(c: Context) -> None:
    """A DeviceSummary is at most 4096 bytes of canonical JSON (the observer repeats this on all traffic); report > 1600."""
    over = [(s["deviceId"], len(canonical(s))) for s in await c.devices(refresh=True) if len(canonical(s)) > 4096]
    c.expect(not over, f"DeviceSummary over 4096 bytes: {over}")


@check("descriptions.events-declared", ["BHMS-EVT-003"], profile="events", generic=True)
async def events_declared(c: Context) -> None:
    """Device-specific event types seen in the log are declared in a description (and their data validates)."""
    declared: set[str] = set()
    schemas: dict[str, Any] = {}
    for description in (await c.descriptions()).values():
        for name, spec in (description.get("events") or {}).items():
            declared.add(name)
            schemas[name] = (spec or {}).get("data") if isinstance(spec, dict) else None
    from bhms.protocol import schema as bhms_schema

    result = await c.ok("events/read", {"limit": 500})
    for event in result["events"]:
        kind = event["type"]
        if kind in schemas and schemas[kind]:
            errors = list(bhms_schema.compile_schema(schemas[kind]).iter_errors(event.get("data", {})))
            c.expect(not errors, f"event {kind} data violates its declared schema: {errors[0].message[:120]}")
        else:
            c.expect(kind in declared or kind.startswith(("device.", "stop", "operation.", "lease.", "policy.", "program.", "upstream.")),
                     f"event type {kind!r} is neither a core type nor declared in a description")
    json.dumps(result)
