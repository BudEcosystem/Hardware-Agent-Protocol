"""The one check of an action result against I-JSON and the declared output (BHMS-OPS-008), shared by the executor (a
handler's result, a device's reconciliation) and the operator resolution (``operations/resolve``). Fix round 2 of Task 7b:
the resolution path used to re-implement it."""

from __future__ import annotations

import inspect

from bhms.protocol import schema
from bhms.runtime import resolution
from bhms.runtime.results import RANGE_KEYWORDS, ResultDefect, check_result
from bhms.server.executor import Executor

OUTPUT = {"type": "object", "properties": {"speed": {"type": "number", "minimum": 0, "maximum": 300},
                                           "label": {"type": "string"}},
          "required": ["speed"], "additionalProperties": False}


def _validator():
    return schema.compile_schema(OUTPUT)


def test_a_valid_result_has_no_defect():
    assert check_result({"speed": 12.5}, _validator()) is None
    assert check_result({"anything": [1, "x"]}, None) is None  # no declared output: only I-JSON applies


def test_a_number_beyond_ijson_is_named_by_its_member():
    for validator in (None, _validator()):
        defect = check_result({"speed": float("nan")}, validator)
        assert defect is not None and defect.kind == "not-ijson" and defect.member == "result.speed"
        assert "result.speed is nan" in defect.message and "NaN" in defect.message
    big = check_result({"count": 2 ** 60}, None)
    assert big.kind == "not-ijson" and big.member == "result.count" and "2^53" in big.message


def test_a_value_that_is_not_json_at_all_is_not_ijson():
    defect = check_result({"when": object()}, None)
    assert defect.kind == "not-ijson" and defect.member == "result"
    assert defect.message.startswith("the result is not JSON-serialisable (") and defect.cause in defect.message


def test_a_value_outside_only_its_declared_range_is_out_of_range():
    defect = check_result({"speed": 300.5}, _validator())
    assert defect == ResultDefect(kind="out-of-range", member="result.speed", instance=300.5, keyword="maximum",
                                  bound={"maximum": 300},
                                  message="the result does not match the declared output schema: "
                                          "300.5 is greater than the maximum of 300",
                                  cause="300.5 is greater than the maximum of 300")
    assert defect.keyword in RANGE_KEYWORDS


def test_any_other_mismatch_is_a_schema_defect_even_beside_a_range_violation():
    missing = check_result({}, _validator())
    assert missing.kind == "schema" and missing.message.startswith("the result does not match the declared output schema: ")
    mixed = check_result({"speed": -1, "label": 3}, _validator())
    assert mixed.kind == "schema" and mixed.keyword is None and mixed.bound is None


def test_the_executor_and_the_operator_resolution_use_the_shared_check():
    for user in (Executor._result_problem, Executor._result_out_of_range, resolution._checked_result):
        source = inspect.getsource(user)
        assert "check_result(" in source
        assert "iter_errors" not in source and "canonical(" not in source  # neither re-implements it
