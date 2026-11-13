"""The device contract every SimLab server must meet, checked through the real client.

``bhms conformance`` (Task 7) did not exist when this was written, so these are the rows of the behavioural contract
that apply to any device server, taken from the spec requirement IDs, run against every twin and adapter:

* DEV-011/020/021: every description validates against the schema and is compact; the digest is stable.
* DEV-030/031/032: every action declares effect, idempotency, completion evidence, a bounded duration and resources;
  an action that claims ``measured`` completion names ``verifiedBy`` properties that exist and are ``measured``.
* DEV-041: every number carries a unit.
* OBS-001: every property read returns an observation whose evidence is the declared evidence (or quality invalid with a
  null value); never a substituted value.
* DEV-050/OPS-030: an invoke replayed with the same operation key yields the same operation (no second effect).
* EVIDENCE honesty (SimLab rule): ``measured`` is only claimed by properties documented as modelled sensors.

Not-applicable rows are listed by each test module with the reason (for instance: an adapter that has no stop procedure
declares ``stop: unsupported`` and is checked for that instead).
"""

from __future__ import annotations

from typing import Any

from bhms.client.client import Client
from bhms.protocol.canonical import canonical
from serving import described, read

EVIDENCE = {"measured", "reported", "commanded", "estimated", "simulated"}


async def check_description(client: Client, device_id: str, *, measured_ok: set[str] | None = None) -> dict[str, Any]:
    """DEV rows. ``measured_ok`` names the properties allowed to claim ``measured`` (documented sensors); None = any."""
    listing = await client.devices_list()
    summary = next(d for d in listing.devices if d.device_id == device_id)
    assert len(canonical(summary.model_dump(by_alias=True))) <= 1600
    desc = await described(client, device_id)
    again = await described(client, device_id)
    assert desc["digest"] == again["digest"] == summary.digest
    assert desc["actions"] or desc["properties"]
    for name, prop in desc["properties"].items():
        assert prop["evidence"] in EVIDENCE, name
        if measured_ok is not None and prop["evidence"] == "measured":
            assert name in measured_ok, f"{device_id}.{name} claims measured but is not a documented sensor"
    for name, action in desc["actions"].items():
        assert action["effect"] in {"none", "reversible", "irreversible", "hazardous"}, name
        assert action["idempotency"] in {"idempotent", "absolute", "relative", "toggle"}, name
        assert action["completionEvidence"] in {"measured", "reported", "none"}, name
        assert action["maxDurationMs"] >= 1 and action["cancel"] in {"supported", "unsupported"}, name
        if action["completionEvidence"] == "measured":
            assert action.get("verifiedBy"), f"{name}: measured completion needs verifiedBy"
            for prop in action["verifiedBy"]:
                assert desc["properties"][prop]["evidence"] == "measured", f"{name}: verifiedBy {prop} is not measured"
        if action["effect"] != "none":
            assert action["resources"], f"{name}: an effectful action must name resources"
    _assert_units(desc)
    return desc


def _assert_units(node: Any, path: str = "") -> None:
    """DEV-041: every number schema carries ``x-bhms-unit``."""
    if isinstance(node, dict):
        if node.get("type") in ("number", "integer") or (isinstance(node.get("type"), list)
                                                          and {"number", "integer"} & set(node["type"])):
            assert "x-bhms-unit" in node, f"number without a unit at {path}"
        for key, value in node.items():
            _assert_units(value, f"{path}/{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _assert_units(value, f"{path}/{index}")


async def check_observations(client: Client, device_id: str, desc: dict[str, Any], *,
                             skip: frozenset[str] = frozenset()) -> None:
    """OBS-001: each readable property returns its declared evidence, or an invalid null; never a made-up value."""
    for name, prop in desc["properties"].items():
        if name in skip or prop.get("readEffect") == "transaction":
            continue
        obs = await read(client, device_id, name)
        assert obs.evidence == prop["evidence"], f"{device_id}.{name}: evidence {obs.evidence} != {prop['evidence']}"
        assert obs.quality in {"valid", "stale", "invalid", "unknown"}
        if obs.quality in ("invalid", "unknown"):
            assert obs.value is None


async def check_replay_is_one_effect(client: Client, device_id: str, action: str, args: dict[str, Any],
                                     effects_of: Any) -> None:
    """OPS-030: the same key twice is one operation and one physical effect (``effects_of()`` counts them)."""
    from serving import run
    before = effects_of()
    first = await run(client, device_id, action, args, key="replay-1")
    second = await run(client, device_id, action, args, key="replay-1")
    assert first.operation_id == second.operation_id and first.state == second.state
    assert effects_of() == before + 1
