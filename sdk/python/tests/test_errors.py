import pytest

from bhms.protocol.errors import CODES, OPERATION_ONLY_CODES, RETRY_VALUES, BhmsError, from_jsonrpc

ORDER = [
    "INVALID_ARGUMENT", "OUT_OF_RANGE", "UNIT_MISMATCH", "UNKNOWN_DEVICE", "UNKNOWN_ACTION",
    "UNSUPPORTED", "LEASE_REQUIRED", "LEASE_CONFLICT", "LEASE_EXPIRED", "FENCED", "KEY_CONFLICT",
    "STALE", "DEVICE_UNAVAILABLE", "UNAUTHORIZED", "BUSY", "DEADLINE_EXCEEDED", "INTERNAL",
    "UNSUPPORTED_VERSION", "UNVERIFIED", "DEVICE_FAULT",
]

# Literal numbers are pinned: they are wire contract (spec/bhms/10-errors.md).
NUMBERS = {
    "INVALID_ARGUMENT": -32602, "OUT_OF_RANGE": -32602, "UNIT_MISMATCH": -32602,
    "UNKNOWN_DEVICE": -32001, "UNKNOWN_ACTION": -32002, "UNSUPPORTED": -32003,
    "LEASE_REQUIRED": -32004, "LEASE_CONFLICT": -32005, "LEASE_EXPIRED": -32006, "FENCED": -32007,
    "KEY_CONFLICT": -32008, "STALE": -32009, "DEVICE_UNAVAILABLE": -32010, "UNAUTHORIZED": -32011,
    "BUSY": -32012, "DEADLINE_EXCEEDED": -32013, "INTERNAL": -32014, "UNSUPPORTED_VERSION": -32015,
    "UNVERIFIED": -32016, "DEVICE_FAULT": -32017,
}


def test_table_complete_and_ordered():
    assert list(CODES) == ORDER


def test_numeric_codes():
    for c in ("INVALID_ARGUMENT", "OUT_OF_RANGE", "UNIT_MISMATCH"):
        assert CODES[c].number == -32602
    assert {c: s.number for c, s in CODES.items()} == NUMBERS
    rest = [CODES[c].number for c in ORDER[3:]]
    assert rest == list(range(-32001, -32001 - 17, -1))
    assert len(set(rest)) == len(rest)
    assert all(-32020 <= n <= -32001 for n in rest)


def test_default_retry_values_valid_and_sensible():
    assert all(s.retry in RETRY_VALUES for s in CODES.values())
    assert BhmsError("DEVICE_UNAVAILABLE", "x").retry == "backoff"
    assert BhmsError("BUSY", "x").retry == "backoff"
    assert BhmsError("INTERNAL", "x").retry == "never"
    assert BhmsError("STALE", "x").retry == "after-reconcile"
    assert BhmsError("DEVICE_FAULT", "x").retry == "after-reconcile"
    assert BhmsError("UNVERIFIED", "x").retry == "after-reconcile"
    assert BhmsError("UNSUPPORTED_VERSION", "x").retry == "never"


WIRE_CODES = [c for c in ORDER if c not in ("DEVICE_FAULT", "UNVERIFIED")]


@pytest.mark.parametrize("code", WIRE_CODES)
def test_round_trip_every_code(code):
    e = BhmsError(code, "msg", field="params.x", bound={"max": 5}, may_have_acted=True,
                  retry="same-key", hint="do it")
    wire = e.to_jsonrpc()
    assert wire["code"] == CODES[code].number
    assert wire["message"] == "msg"
    assert wire["data"] == {"bhmsCode": code, "field": "params.x", "bound": {"max": 5},
                            "mayHaveActed": True, "retry": "same-key", "hint": "do it"}
    back = from_jsonrpc(wire)
    assert back.to_jsonrpc() == wire
    assert (back.code, back.field, back.bound, back.may_have_acted, back.retry, back.hint) == (
        code, "params.x", {"max": 5}, True, "same-key", "do it")


def test_operation_only_codes_never_become_jsonrpc_errors():
    assert OPERATION_ONLY_CODES == {"DEVICE_FAULT", "UNVERIFIED"}
    for code in OPERATION_ONLY_CODES:
        err = BhmsError(code, "stall", may_have_acted=True, hint="inspect")
        with pytest.raises(ValueError, match="operation"):
            err.to_jsonrpc()
        assert err.to_operation_error() == {"bhmsCode": code, "mayHaveActed": True, "retry": "after-reconcile",
                                            "hint": "inspect", "message": "stall"}
        with pytest.raises(ValueError, match="operation-only"):
            from_jsonrpc({"code": CODES[code].number, "message": "m",
                          "data": {"bhmsCode": code, "mayHaveActed": True, "retry": "never", "hint": ""}})


@pytest.mark.parametrize("missing", ["mayHaveActed", "retry", "hint"])
def test_from_jsonrpc_never_defaults_required_data(missing):
    data = {"bhmsCode": "BUSY", "mayHaveActed": False, "retry": "backoff", "hint": "later"}
    del data[missing]
    with pytest.raises(ValueError, match=missing):
        from_jsonrpc({"code": -32012, "message": "m", "data": data})
    with pytest.raises(ValueError, match="boolean"):
        from_jsonrpc({"code": -32012, "message": "m",
                      "data": {"bhmsCode": "BUSY", "mayHaveActed": "no", "retry": "backoff", "hint": ""}})


def test_operation_id_round_trip():
    e = BhmsError("KEY_CONFLICT", "key reused", field="operationKey", operation_id="op-1")
    wire = e.to_jsonrpc()
    assert wire["data"]["operationId"] == "op-1"
    assert from_jsonrpc(wire).operation_id == "op-1"


def test_optional_fields_omitted():
    data = BhmsError("BUSY", "m").to_jsonrpc()["data"]
    assert data == {"bhmsCode": "BUSY", "mayHaveActed": False, "retry": "backoff", "hint": ""}


def test_unknown_code_rejected():
    with pytest.raises(ValueError, match="NOPE"):
        BhmsError("NOPE", "x")
    with pytest.raises(ValueError, match="NOPE"):
        from_jsonrpc({"code": -32001, "message": "m", "data": {"bhmsCode": "NOPE", "mayHaveActed": False,
                                                              "retry": "never", "hint": ""}})


def test_invalid_retry_rejected():
    with pytest.raises(ValueError, match="retry"):
        BhmsError("BUSY", "x", retry="sometimes")


def test_from_jsonrpc_requires_bhms_data():
    with pytest.raises(ValueError, match="bhmsCode"):
        from_jsonrpc({"code": -32000, "message": "m"})


def test_from_jsonrpc_rejects_mismatched_number():
    with pytest.raises(ValueError, match="-32001"):
        from_jsonrpc({"code": -32005, "message": "m", "data": {"bhmsCode": "UNKNOWN_DEVICE"}})


def test_is_exception():
    with pytest.raises(BhmsError, match="boom"):
        raise BhmsError("INTERNAL", "boom")
