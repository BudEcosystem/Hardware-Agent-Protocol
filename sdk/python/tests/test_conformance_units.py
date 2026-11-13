"""The runner's own logic: observers over hand-written traffic, the compact-layout rules, status folding."""

from __future__ import annotations

from bhms.conformance import observers
from bhms.conformance.checks.descriptions import compact_problems
from bhms.conformance.core import CheckResult, Status
from bhms.conformance.coverage import rows
from bhms.conformance.wire import Recorder, Seen

NOW = "2026-11-13T10:00:00.000Z"


def _recording(*items: tuple[str, object, dict | None]) -> Recorder:
    recorder = Recorder()
    for direction, message, request in items:
        recorder.add(Seen("t", direction, message, 0.0, request))
    return recorder


def _response(method: str, result: dict | None = None, error: dict | None = None, params: dict | None = None, ident: int = 1):
    request = {"jsonrpc": "2.0", "id": ident, "method": method, "params": params or {}}
    body = {"jsonrpc": "2.0", "id": ident, **({"result": result} if result is not None else {"error": error})}
    return ("in", body, request)


def _op(**kw):
    base = {"operationId": "op-1", "kind": "action", "deviceId": "d", "action": "a", "state": "completed", "effect": "unverified", "result": {},
            "createdAt": NOW, "updatedAt": NOW, "cancel": {"state": "none"}}
    return {**base, **kw}


def _bad(recorder: Recorder, rid: str, descriptions: dict | None = None) -> list[str]:
    return observers.observe(recorder, descriptions or {}).findings.get(rid, [])


def test_a_result_without_result_type_is_reported():
    rec = _recording(_response("properties/read", {"observation": {"value": 1}}))
    assert _bad(rec, "BHMS-LIF-012")
    ok = _recording(_response("properties/read", {"resultType": "complete", "observation": {"value": None, "quality": "invalid"}}))
    assert _bad(ok, "BHMS-LIF-012") == []


def test_error_numbers_shapes_and_hints_are_checked():
    good = {"code": -32602, "message": "x is above 5", "data": {"bhmsCode": "OUT_OF_RANGE", "mayHaveActed": False, "retry": "never", "hint": "send 5"}}
    assert _bad(_recording(_response("actions/invoke", error=good)), "BHMS-ERR-010") == []
    wrong_number = {**good, "code": -32013}
    assert _bad(_recording(_response("actions/invoke", error=wrong_number)), "BHMS-ERR-010")
    no_flag = {**good, "data": {k: v for k, v in good["data"].items() if k != "mayHaveActed"}}
    assert _bad(_recording(_response("actions/invoke", error=no_flag)), "BHMS-ERR-001")
    blank = {**good, "data": {**good["data"], "hint": " "}}
    assert _bad(_recording(_response("actions/invoke", error=blank)), "BHMS-ERR-003")
    bhms_in_parse_error = {"code": -32700, "message": "bad", "data": {"bhmsCode": "INVALID_ARGUMENT"}}
    assert _bad(_recording(_response("x", error=bhms_in_parse_error)), "BHMS-ERR-006")
    as_error = {"code": -32017, "message": "m", "data": {"bhmsCode": "DEVICE_FAULT", "mayHaveActed": True, "retry": "after-reconcile", "hint": "h"}}
    assert _bad(_recording(_response("actions/invoke", error=as_error)), "BHMS-ERR-012")
    less_careful = {"code": -32009, "message": "m", "data": {"bhmsCode": "STALE", "mayHaveActed": False, "retry": "backoff", "hint": "h"}}
    assert _bad(_recording(_response("x", error=less_careful)), "BHMS-ERR-005")


def test_operation_invariants():
    def completed_without_result():
        op = _op()
        del op["result"]
        return _recording(_response("actions/invoke", {"resultType": "complete", "operation": op, "replayed": False}))

    assert _bad(completed_without_result(), "BHMS-OPS-008")
    failed_without_error = _recording(_response("actions/invoke", {"resultType": "complete", "operation": _op(state="failed", result=None),
                                                                     "replayed": False}))
    assert _bad(failed_without_error, "BHMS-OPS-009")
    verified_unmeasured = _recording(_response("actions/invoke", {"resultType": "complete", "replayed": False,
                                                                    "operation": _op(effect="verified", evidence={"kind": "reported"})}))
    assert _bad(verified_unmeasured, "BHMS-OPS-006")
    wrong_unknown = {"bhmsCode": "INTERNAL", "mayHaveActed": True, "retry": "never", "hint": "h", "message": "m"}
    unknown = _recording(_response("operations/get", {"resultType": "complete", "operation": _op(state="unknown", error=wrong_unknown, result=None)}))
    assert _bad(unknown, "BHMS-OPS-004")
    reopened = _recording(
        _response("operations/get", {"resultType": "complete", "operation": _op(updatedAt="2026-11-13T10:00:01.000Z")}, ident=1),
        _response("operations/get", {"resultType": "complete", "operation": _op(state="running", result=None, updatedAt="2026-11-13T10:00:02.000Z")}, ident=2))
    assert _bad(reopened, "BHMS-OPS-002")
    invalid_history = _op(history=[{"seq": 1, "at": NOW, "kind": "state", "state": "accepted"}, {"seq": 2, "at": NOW, "kind": "state", "state": "completed"}])
    assert _bad(_recording(_response("operations/get", {"resultType": "complete", "operation": invalid_history})), "BHMS-OPS-001")
    blank_reconciliation = _op(history=[{"seq": 1, "at": NOW, "kind": "state", "state": "accepted"}, {"seq": 2, "at": NOW, "kind": "state", "state": "dispatching"},
                                        {"seq": 3, "at": NOW, "kind": "state", "state": "unknown"},
                                        {"seq": 4, "at": NOW, "kind": "reconciliation", "state": "completed"}])
    assert _bad(_recording(_response("operations/get", {"resultType": "complete", "operation": blank_reconciliation})), "BHMS-OPS-005")


def test_observations_times_framing_and_stops():
    description = {"d": {"properties": {"p": {"schema": {"type": "number", "x-bhms-unit": "mm"}}}}}
    params = {"deviceId": "d", "property": "p"}
    no_unit = _recording(_response("properties/read", {"resultType": "complete", "observation": {"value": 1.0, "quality": "valid"}}, params=params))
    assert _bad(no_unit, "BHMS-OBS-005", description)
    other_unit = _recording(_response("properties/read", {"resultType": "complete", "observation": {"value": 1.0, "unit": "um", "quality": "valid"}}, params=params))
    assert _bad(other_unit, "BHMS-OBS-005", description)
    invalid_with_value = _recording(_response("properties/read", {"resultType": "complete", "observation": {"value": 0, "unit": "mm", "quality": "invalid"}}, params=params))
    assert _bad(invalid_with_value, "BHMS-OBS-001", description)
    local_time = _recording(_response("operations/get", {"resultType": "complete", "operation": _op(createdAt="2026-11-13T10:00:00+01:00")}))
    assert _bad(local_time, "BHMS-LIF-003")
    server_request = _recording(("in", {"jsonrpc": "2.0", "id": 5, "method": "x/y", "params": {}}, None))
    assert _bad(server_request, "BHMS-TRN-001")
    server_cancel = _recording(("in", {"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": 1}}, None))
    assert _bad(server_cancel, "BHMS-LIF-052")
    untagged = _recording(("in", {"jsonrpc": "2.0", "method": "notifications/event", "params": {"event": {}}}, None))
    assert _bad(untagged, "BHMS-LIF-041")
    confirmed = _recording(_response("stop", {"resultType": "complete", "stops": [{"deviceId": "d", "outcome": "confirmed", "evidence": "none",
                                                                                   "canceledOperations": [], "revokedLeases": []}]}))
    assert _bad(confirmed, "BHMS-AUTH-022")
    oversize = _recording(_response("devices/list", {"resultType": "complete", "devices": [{"deviceId": "d", "summary": "x" * 5000}]}))
    assert _bad(oversize, "BHMS-DEV-011")


def test_stdio_framing_errors_and_strict_schema_validation():
    broken_frame = Recorder()
    broken_frame.add(Seen("t", "in", b"garbage", 0.0, frame_error="not JSON"))
    assert observers.observe(broken_frame, {}, stdio=True).findings["BHMS-TRN-010"]
    not_schema = _recording(_response("devices/list", {"resultType": "complete", "devices": "nope"}))
    assert observers.observe(not_schema, {}, strict=True).findings["BHMS-LIF-012"]


GOOD_DESCRIPTION = {
    "deviceId": "mcu",
    "actions": {"set": {"input": {"type": "object", "required": ["v"], "properties": {"v": {"type": "number", "multipleOf": 0.1, "minimum": 0, "maximum": 100}}},
                        "output": {"type": "object", "properties": {"r": {"type": "number"}}},
                        "compact": {"index": 0, "args": [{"name": "v", "type": "u16", "scale": 0.1}], "result": [{"name": "r", "type": "f32"}]}}},
    "properties": {"t": {"schema": {"type": "number"}, "compact": {"index": 0, "type": "i16"}}},
}


def test_compact_layout_rules():
    assert compact_problems(GOOD_DESCRIPTION) == []
    import copy

    missing = copy.deepcopy(GOOD_DESCRIPTION)
    missing["actions"]["set"]["compact"]["args"] = []
    assert [r for r, _ in compact_problems(missing)] == ["BHMS-DEV-070"]
    unmirrored = copy.deepcopy(GOOD_DESCRIPTION)
    del unmirrored["actions"]["set"]["input"]["properties"]["v"]["multipleOf"]
    assert ("BHMS-DEV-071" in [r for r, _ in compact_problems(unmirrored)])
    too_wide = copy.deepcopy(GOOD_DESCRIPTION)
    too_wide["actions"]["set"]["input"]["properties"]["v"]["maximum"] = 99999
    assert any("range" in m for _, m in compact_problems(too_wide))
    duplicate = copy.deepcopy(GOOD_DESCRIPTION)
    duplicate["actions"]["two"] = copy.deepcopy(duplicate["actions"]["set"])
    assert any("unique" in m for _, m in compact_problems(duplicate))
    unknown_result = copy.deepcopy(GOOD_DESCRIPTION)
    unknown_result["actions"]["set"]["compact"]["result"] = [{"name": "nope", "type": "u8"}]
    assert any("output member" in m for _, m in compact_problems(unknown_result))
    no_default = copy.deepcopy(GOOD_DESCRIPTION)
    no_default["actions"]["set"]["input"]["required"] = []
    assert any("required or declare a default" in m for _, m in compact_problems(no_default))


def test_requirement_status_folding():
    ok = CheckResult("a", Status.PASSED, ("BHMS-LIF-001", "BHMS-LIF-010"), "core", True)
    failed = CheckResult("b", Status.FAILED, ("BHMS-LIF-001", "BHMS-LIF-010"), "core", True, message="boom", failed_ids=("BHMS-LIF-010",))
    skipped = CheckResult("c", Status.SKIPPED, ("BHMS-LIF-011",), "core", True, message="needs restart")
    inapplicable = CheckResult("d", Status.NOT_APPLICABLE, ("BHMS-LIF-013",), "core", True, message="no capability")
    folded = {r.id: r for r in rows([ok, failed, skipped, inapplicable], ["core"], {})}
    assert folded["BHMS-LIF-010"].status is Status.FAILED and folded["BHMS-LIF-010"].reason == "boom"
    assert folded["BHMS-LIF-001"].status is Status.PASSED  # the failed check blamed another requirement; another check proved this one
    assert folded["BHMS-LIF-011"].status is Status.SKIPPED and folded["BHMS-LIF-011"].reason == "needs restart"
    assert folded["BHMS-LIF-013"].status is Status.NOT_APPLICABLE
    assert folded["BHMS-LIF-002"].status is Status.SKIPPED and "no automated check" in folded["BHMS-LIF-002"].reason
    assert folded["BHMS-TRN-021"].status is Status.SKIPPED and folded["BHMS-TRN-021"].reason.startswith("inspection")


def test_exit_status_and_claims_distinguish_failed_unproven_and_outside_automation():
    from bhms.conformance.core import RequirementRow
    from bhms.conformance.runner import Report

    def row(rid, status, level="MUST", unproven=False, profile="core"):
        return RequirementRow(id=rid, level=level, profile=profile, method="wire", status=status, unproven=unproven)

    meta = {"profiles": ["core"]}
    passed = Report(meta, [], [row("BHMS-LIF-001", Status.PASSED), row("BHMS-TRN-021", Status.SKIPPED)])  # inspection: outside automation
    assert passed.exit_code == 0 and passed.claims["core"]["claimable"] and passed.claims["core"]["needsReview"] == ["BHMS-TRN-021"]
    unproven = Report(meta, [], [row("BHMS-LIF-001", Status.PASSED), row("BHMS-OPS-030", Status.SKIPPED, unproven=True)])
    assert unproven.exit_code == 3 and not unproven.claims["core"]["claimable"] and unproven.claims["core"]["unproven"] == ["BHMS-OPS-030"]
    assert Report({**meta, "allowUnproven": True}, [], unproven.rows).exit_code == 0
    failed = Report(meta, [], [row("BHMS-LIF-001", Status.FAILED), row("BHMS-OPS-030", Status.SKIPPED, unproven=True)])
    assert failed.exit_code == 1 and failed.claims["core"]["failed"] == ["BHMS-LIF-001"]
    should = Report(meta, [], [row("BHMS-DEV-033", Status.FAILED, level="SHOULD")])
    assert should.exit_code == 0  # a SHOULD finding does not fail the run
    assert Report(meta, [], [], fatal="x").exit_code == 2


def test_a_row_no_check_can_prove_yet_blocks_the_claim_and_a_generic_report_never_claims():
    from bhms.conformance.core import RequirementRow
    from bhms.conformance.runner import Report

    untestable = RequirementRow(id="BHMS-EVT-013", level="MUST", profile="events", method="wire", status=Status.SKIPPED, unproven=True,
                                reason="not-yet-testable: x")
    inspected = RequirementRow(id="BHMS-SEC-004", level="MUST", profile="events", method="inspection", status=Status.SKIPPED,
                               reason="inspection: x")
    passed = RequirementRow(id="BHMS-EVT-001", level="MUST", profile="events", method="wire", status=Status.PASSED)
    blocked = Report({"profiles": ["events"]}, [], [passed, untestable, inspected])
    assert not blocked.claims["events"]["claimable"] and blocked.claims["events"]["unproven"] == ["BHMS-EVT-013"] and blocked.exit_code == 3
    review = Report({"profiles": ["events"]}, [], [passed, inspected])
    assert review.claims["events"]["claimable"] and review.claims["events"]["needsReview"] == ["BHMS-SEC-004"]
    generic = Report({"profiles": ["events"], "reportKind": "generic"}, [], [passed])
    assert not generic.claims["events"]["claimable"] and "generic report" in generic.claims["events"]["reason"]


def test_a_stop_result_without_stops_and_other_non_conforming_shapes_are_findings_not_crashes():
    broken = _recording(_response("stop", {"resultType": "complete"}))
    assert _bad(broken, "BHMS-AUTH-022")
    weird = _recording(_response("devices/list", {"resultType": "complete", "devices": [5, "x", None]}),
                       _response("operations/get", {"resultType": "complete", "operation": {"state": "completed", "history": [1, 2]}}))
    findings = observers.observe(weird, {}).findings  # must return, whatever the shapes
    assert isinstance(findings, dict)


def test_embedded_schemas_are_bounded_and_never_fetched():  # BHMS-SEC-021
    from bhms.protocol.schema import schema_bounds_problem

    assert schema_bounds_problem({"type": "object", "properties": {"a": {"type": "number"}}, "$ref": "#/$defs/x"}) is None
    node: dict = {"type": "number"}
    for _ in range(31):
        node = {"type": "object", "properties": {"x": node}}
    assert schema_bounds_problem(node) is None
    assert "deeper than 32" in schema_bounds_problem({"type": "object", "properties": {"x": node}})
    assert "leaves the document" in schema_bounds_problem({"items": {"$ref": "http://example.invalid/x.json"}})
    wide = {"anyOf": [{"type": "integer"} for _ in range(10_001)]}
    assert "more than 10000" in schema_bounds_problem(wide)
    assert schema_bounds_problem(True) is None and schema_bounds_problem({"properties": {"x": 5}}) is None


def test_the_authority_capability_carries_no_member():
    from bhms.runtime.authority import Policy

    assert Policy().authority_capability() is None
    assert Policy({"a": {"scopes": ["admin"]}}).authority_capability() is None  # one administrator: single-principal
    assert Policy({"a": {"scopes": ["admin"]}, "b": {"scopes": ["read"]}}).authority_capability() == {}


def test_a_gateway_refuses_an_upstream_description_with_a_hostile_schema():
    from bhms.gateway.upstreams import _description_problem
    from bhms.protocol.canonical import digest

    node: dict = {"$ref": "http://example.invalid/x"}
    for _ in range(40):
        node = {"type": "object", "properties": {"x": node}}
    description = {"deviceId": "d", "actions": {"a": {"input": node}}, "properties": {}, "resources": [], "capabilities": [], "safety": {}}
    description["digest"] = digest(description)
    assert "not acceptable" in (_description_problem(description, "d") or "")
