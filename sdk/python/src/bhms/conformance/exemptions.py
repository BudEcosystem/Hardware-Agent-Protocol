"""Requirements that no automated check proves, each with the reason (see :mod:`bhms.conformance.coverage`).

Kinds: ``inspection`` (needs review evidence; the index itself says so for most), ``not-yet-testable`` (a wire test is possible
in principle but the target or the conformance device cannot provoke the condition), ``not-applicable`` (does not concern
the implementation under test). ``tests/test_conformance_runner.py::test_every_core_must_is_covered_or_has_a_recorded_reason`` fails when an ID listed here also has a check
(stale entry) or when a ``core`` MUST has neither a check nor an entry.
"""

INSPECTION = "inspection"
UNTESTABLE = "not-yet-testable"
NOT_APPLICABLE = "not-applicable"

_COMPACT = (UNTESTABLE, "BHMS-Compact frame and endpoint behaviour: needs a compact simulated endpoint, which the Python SDK does not "
            "provide (Task 9b); the static layout rules BHMS-DEV-070/071 are checked by compact.layout-rules")

EXEMPT: dict[str, tuple[str, str]] = {
    "BHMS-LIF-022": (INSPECTION, "client behaviour (SHOULD)"),
    "BHMS-LIF-053": (INSPECTION, "client behaviour"),
    "BHMS-LIF-071": (INSPECTION, "review of each extension against the core guarantees"),
    "BHMS-TRN-021": (INSPECTION, "refusal to start a non-loopback TCP listener without TLS is a start-up behaviour of the implementation"),
    "BHMS-TRN-050": (INSPECTION, "custom transports are documented and reviewed; the runner suite passing over one is the evidence"),
    "BHMS-DEV-031": (INSPECTION, "review of each measured action's evidence path"),
    "BHMS-DEV-050": (INSPECTION, "review of driver acquisition effects (the transaction property of the conformance device is exercised by "
                     "observations.retained-after-effect)"),
    "BHMS-DEV-051": (INSPECTION, "review of evidence declarations against driver behaviour"),
    "BHMS-OPS-036": (INSPECTION, "client behaviour (key reuse and retention)"),
    "BHMS-PRG-006": (UNTESTABLE, "the only multi-principal target (the gateway fixture) does not serve programs"),
    "BHMS-PRG-021": (UNTESTABLE, "the only multi-principal target (the gateway fixture) does not serve programs"),
    "BHMS-EVT-013": (UNTESTABLE, "the v0.1 scope grammar has no per-device read scope, so no event can be hidden from a principal"),
    "BHMS-ERR-002": (INSPECTION, "client SDKs dispatch on bhmsCode (code review and SDK unit test)"),
    "BHMS-AGT-050": (UNTESTABLE, "needs the function-tool definitions of an adapter as data; the Python adapter is compared with the MCP bridge in "
                     "tests/test_openai_tools.py"),
    "BHMS-SEC-002": (INSPECTION, "constant-time comparison and hashed storage need code review; transport.no-token-in-logs reports token leaks in "
                     "captured logs as a warning, never as a pass"),
    "BHMS-SEC-004": (INSPECTION, "deployment configuration of non-loopback listeners"),
    "BHMS-SEC-020": (UNTESTABLE, "needs a hostile device whose text contains instructions; the runner's conformance device has benign text "
                     "(the Python bridge is tested with injected text in tests/test_bridge_render.py)"),
    "BHMS-SEC-021": (INSPECTION, "applies to the validator of a client or gateway; needs review of its depth, size and fetch limits (tests/test_schema_module.py covers the Python validator); a device whose description carries a pathological schema (deep nesting, remote $ref)"),
    "BHMS-SEC-042": (INSPECTION, "documentation and tool descriptions never call software stop an emergency stop"),
    "BHMS-CNF-001": (INSPECTION, "a property of the report the runner writes (tests/test_conformance_runner.py::test_report_states_what_bhms_cnf_001_to_005_require), not of the target"),
    "BHMS-CNF-002": (INSPECTION, "a property of the report the runner writes (tests/test_conformance_runner.py::test_report_states_what_bhms_cnf_001_to_005_require), not of the target"),
    "BHMS-CNF-003": (INSPECTION, "a property of the report the runner writes (tests/test_conformance_runner.py::test_report_states_what_bhms_cnf_001_to_005_require), not of the target"),
    "BHMS-CNF-004": (INSPECTION, "a property of the report the runner writes: the exit status is non-zero while any MUST row of a claimed "
                     "profile failed"),
    "BHMS-CNF-005": (INSPECTION, "a property of the report the runner writes (tests/test_conformance_runner.py::test_report_states_what_bhms_cnf_001_to_005_require), not of the target"),
    "BHMS-CNF-006": (INSPECTION, "needs the implementation's own message validator; the Python SDK asserts it in tests/test_schema_examples.py"),
    "BHMS-SEC-050": (INSPECTION, "documentation statement about FCS-16"),
    **{f"BHMS-CMP-{n}": _COMPACT for n in ("001", "002", "003", "010", "011", "020", "021", "022", "023", "030", "031", "032", "033", "034",
                                           "035", "040", "041", "050", "051", "060")},
}
