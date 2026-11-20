# Independent I/O operation-history component

This isolated candidate preserves all 2,802 files of the board-history candidate
and adds a pure operation-ledger fold and 38 tests. The combined selection is
112 methods: 38 operation-history, 35 board-history and 39 transcript-reader tests.
Preparation is static only; actual attempts and failures are retained separately.

The checker derives state, cancellation, possible effect, owner epoch and claims
from complete immutable event streams. Admission allocates a fence for each typed
resource even when cancellation prevents dispatch. Dispatch joins its exact
attempt, clock, session, footprint and durable link. Evidence must reference an
exact retained authority receipt and identical board-history version. Completion
and resource release are separate events. Reopening an active operation requires
an unknown-outcome event; historical completion can reconcile under a later owner.
The missing-current-receipt trial retains its unresolved authority claim and does
not become a successful outcome just because its authority history is coherent.

Namespace issuance, expiry, series floor, immutable parent request, child request
inventory, linked prefix, reserved keys and replay mappings are checked against
the captured plan. Event sequence is bounded before allocating a range. Immutable
rows, events, dispatch links and retained receipts cannot disappear or change.
Rehashed semantic mutations must first pass the independent structural reader.
The tests expect all nineteen actual authority histories to retain 32 admissions,
156 events and exactly one unresolved operation with one held claim. A purity
check vetoes file, SQLite and clock access after setup and verifies nonmutation.

This profile is deliberately finite and single-actor. The implementation imports
shared canonical/invocation contracts and independent reader/typed-footprint
helpers; it imports no Journal, ProcedureStore, runtime, adapter or provider
validator. The plan is captured input, not an independently recomputed PAT
lowering. Parent control-flow/event semantics, live authorization/configuration
attestation, arbitrary dispatcher refusal causes, no-start evidence, auxiliary
actors, final qualification and the fault matrix remain unfinished. Registry
revision text is shape-checked, not attested against uncaptured policy state.
All corresponding outcome/qualification flags remain false. Board history must
be checked separately; coherent authority history does not imply valid effects.

No live HMS implementation, prior frozen artifact, adjacent Harness checkout,
physical device, MCU, emulator, live inference or external service is changed.
Review is by the primary agent; helper account limits prevent independent review.
