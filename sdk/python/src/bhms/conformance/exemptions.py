"""Requirements that no automated check proves, each with the reason (see :mod:`bhms.conformance.coverage`).

Kinds: ``inspection`` (needs review evidence; the index itself says so for most), ``not-yet-testable`` (a wire test is possible
in principle but the target or the conformance device cannot provoke the condition), ``not-applicable`` (does not concern
the implementation under test). ``tests/test_conformance_coverage.py`` fails when an ID listed here also has a check
(stale entry) or when a ``core`` MUST has neither a check nor an entry.
"""

INSPECTION = "inspection"
UNTESTABLE = "not-yet-testable"
NOT_APPLICABLE = "not-applicable"

_COMPACT = (UNTESTABLE, "BHMS-Compact frame and endpoint behaviour: needs a compact simulated endpoint, which the Python SDK does not "
            "provide (Task 9b); the static layout rules BHMS-DEV-070/071 are checked by compact.layout-rules")

EXEMPT: dict[str, tuple[str, str]] = {
    "BHMS-LIF-018": (UNTESTABLE, "traceparent/tracestate propagation is observable only at the upstream; the conformance device does not echo "
                     "request metadata"),
    "BHMS-LIF-022": (INSPECTION, "client behaviour (SHOULD)"),
    "BHMS-LIF-042": (UNTESTABLE, "needs a principal whose read scope is revoked mid-subscription; scopes are policy-file state the runner can "
                     "reload only on the built-in gateway, and read scope is not per-device"),
    "BHMS-LIF-053": (INSPECTION, "client behaviour"),
    "BHMS-LIF-071": (INSPECTION, "review of each extension against the core guarantees"),
    "BHMS-TRN-021": (INSPECTION, "refusal to start a non-loopback TCP listener without TLS is a start-up behaviour of the implementation"),
    "BHMS-TRN-022": (UNTESTABLE, "needs connections from two different uids to compare peer-credential principals and the socket file mode"),
    "BHMS-TRN-050": (INSPECTION, "custom transports are documented and reviewed; the runner suite passing over one is the evidence"),
    "BHMS-DEV-010": (UNTESTABLE, "the v0.1 scope grammar has no per-device read scope (read is global), so no principal can be made unable "
                     "to read one device"),
    "BHMS-DEV-023": (UNTESTABLE, "needs the device to change its description (a bound, firmware); the conformance device has no command for it"),
    "BHMS-DEV-031": (INSPECTION, "review of each measured action's evidence path"),
    "BHMS-DEV-050": (INSPECTION, "review of driver acquisition effects (the transaction property of the conformance device is exercised by "
                     "observations.retained-after-effect)"),
    "BHMS-DEV-051": (INSPECTION, "review of evidence declarations against driver behaviour"),
    "BHMS-OBS-002": (UNTESTABLE, "needs a property that echoes a commanded setpoint when its sensor is unplugged; the conformance device has "
                     "none"),
    "BHMS-OPS-036": (INSPECTION, "client behaviour (key reuse and retention)"),
    "BHMS-OPS-041": (UNTESTABLE, "needs a lease-requiring action that queues behind a busy resource (to expire a lease between acceptance and "
                     "dispatch); conformance-device lease actions use their own resource"),
    "BHMS-OPS-052": (UNTESTABLE, "needs a device that acknowledges a cancel and then loses the termination evidence; the conformance device has "
                     "no such fault"),
    "BHMS-LSE-011": (UNTESTABLE, "needs a partitioned gateway and a second path to the device to replay a superseded holder's command"),
    "BHMS-LSE-012": (UNTESTABLE, "needs a lease-requiring action that runs longer than the minimum lease TTL; clamp holds for 50 ms"),
    "BHMS-AUTH-003": (UNTESTABLE, "the conformance devices declare no hazardous action to attach a glob scope to"),
    "BHMS-PRG-006": (UNTESTABLE, "the only multi-principal target (the gateway fixture) does not serve programs"),
    "BHMS-PRG-012": (UNTESTABLE, "needs a program whose steps take longer than its declared maxDurationMs; step durations of the conformance "
                     "device are bounded by their declared maxima"),
    "BHMS-PRG-021": (UNTESTABLE, "the only multi-principal target (the gateway fixture) does not serve programs"),
    "BHMS-EVT-013": (UNTESTABLE, "the v0.1 scope grammar has no per-device read scope, so no event can be hidden from a principal"),
    "BHMS-ERR-002": (INSPECTION, "client SDKs dispatch on bhmsCode (code review and SDK unit test)"),
    "BHMS-AGT-050": (UNTESTABLE, "needs the function-tool definitions of an adapter as data; the Python adapter is compared with the MCP bridge in "
                     "tests/test_openai_tools.py"),
    "BHMS-SEC-002": (INSPECTION, "constant-time comparison, hashed storage and log scanning need code and log review"),
    "BHMS-SEC-004": (INSPECTION, "deployment configuration of non-loopback listeners"),
    "BHMS-SEC-020": (UNTESTABLE, "needs a hostile device whose text contains instructions; the runner's conformance device has benign text "
                     "(the Python bridge is tested with injected text in tests/test_bridge_render.py)"),
    "BHMS-SEC-021": (UNTESTABLE, "needs a device whose description carries a pathological schema (deep nesting, remote $ref)"),
    "BHMS-SEC-022": (UNTESTABLE, "needs a gateway with a malicious upstream; verified for the Python gateway in tests/test_conformance_gateway.py"),
    "BHMS-SEC-042": (INSPECTION, "documentation and tool descriptions never call software stop an emergency stop"),
    "BHMS-CNF-001": (INSPECTION, "a property of the report the runner writes (tests/test_conformance_report.py), not of the target"),
    "BHMS-CNF-002": (INSPECTION, "a property of the report the runner writes (tests/test_conformance_report.py), not of the target"),
    "BHMS-CNF-003": (INSPECTION, "a property of the report the runner writes (tests/test_conformance_report.py), not of the target"),
    "BHMS-CNF-004": (INSPECTION, "a property of the report the runner writes: the exit status is non-zero while any MUST row of a claimed "
                     "profile failed"),
    "BHMS-CNF-005": (INSPECTION, "a property of the report the runner writes (tests/test_conformance_report.py), not of the target"),
    "BHMS-CNF-006": (UNTESTABLE, "needs the implementation's own message validator; the Python SDK asserts it in tests/test_schema_examples.py"),
    "BHMS-SEC-050": (INSPECTION, "documentation statement about FCS-16"),
    **{f"BHMS-CMP-{n}": _COMPACT for n in ("001", "002", "003", "010", "011", "020", "021", "022", "023", "030", "031", "032", "033", "034",
                                           "035", "040", "041", "050", "051", "060")},
}
