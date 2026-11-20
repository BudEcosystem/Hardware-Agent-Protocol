# Public shared-board I/O integration

The reviewed original GPIO/PWM provider is mounted through `open_runtime` and
explicit daemon profile flags. It uses the existing 14 local API/MCP methods,
including finite procedures. This directory retains two failed focused attempts
and a final passing transport run; it is not itself a passing full-suite receipt.

| Attempt | Result | Retained input closure |
|---|---|---|
| `20261107T005504.237197Z-360d486cb278` | 37 tests: 27 passed, 1 failure, 9 errors; 162.415 test seconds | 151 inputs including its runner; unchanged |
| `20261107T010528.593414Z-866704e0e9cd` | 52 tests: 50 passed, 1 failure, 1 error; 262.365 test seconds | 152 inputs including its runner; unchanged |
| `20261107T011252.060219Z-62ab23b8d215` | All 4 transport tests passed; 97.067 test seconds | 152 inputs including its runner; unchanged |

Compiler and provider identities were stable within each attempt. All source
snapshots, logs, provider database snapshots and explicit transport failure
captures remain retained. The 52-test attempt and final transport run use the
same production code. Their only common project-input difference is the MCP
resume test expectation; their separately selected controller scripts differ.
No operation deadline, pulse limit, observation age, retry policy or public
validation rule was weakened to obtain a pass.

The first run passed all 24 provider methods but exposed an invalid example
`driverProfile` and a public response incompatibility. The blueprint now uses the
existing resource-topology schema constant while its generator fills actual
source digests. It does not relax the schema. The [response diagnosis](../io-response-contract-diagnosis/README.md)
reconstructed four retained terminal projections: each passed JSON Schema and
failed the legacy cross-field requirement for `effectCommitted`.

The correction defines `hms.synthetic-io-result/1`, with closed fields, exact
Boolean activation/cycle/idle facts, typed primitive footprints, and a receipt
digest. It preserves prior activation after cancellation. Historical terminal
receipts may remain visible while authority settlement and claims are unresolved.
The unprofiled simulator validation body is AST-identical. The [independent
resolution review](../io-response-contract-resolution-review/README.md) also
covers the blueprint correction and the existing CLI factory test-double change.
The earlier [entry review](../io-runtime-entry-review/review.json) is a limited
static inspection, not an overall integration or API approval.

The second run passed all 24 provider tests, 9 runtime/profile tests, 14 new pure
API-carrier tests, the existing CLI initialization/cleanup test, and the CLI and
crash-recovery transport cases. Both MCP cases reached explicit resume after
reopen and correctly returned `IO_SESSION_CHANGED`; the tests had incorrectly
expected success. The [session resolution](../io-transport-session-resolution/README.md)
retains both failed responses, sessions and business state. Only the test was
corrected: an immutable unstarted child is not silently rebound to a new board
session. Explicit cancellation then remains available.

The final four transport tests pass through real daemon, CLI, UDS, modern MCP
and installed legacy MCP SDK processes. Each MCP case invokes all 14 existing
tools and records 32 validated replies. GPIO/PWM aliases conflict without new
operation/replay-key allocation, two-child procedures complete, and exact replay
adds no activation. Both stale-session resume refusals leave the interrupted
parent, absent child operation, reserved keys, effects and business counts
`[4, 0, 3, 2]` unchanged before explicit cancellation.

The owned-daemon SIGKILL test first observes an actual pending provider receipt.
Reopening cancels that pulse with activation retained, modeled idle state and
claims released, and exact replay does not add another activation. Clean reopen,
missing/tampered board refusal, malformed configuration and source-pinned example
generation are separately exercised. The final transport run retained 150
read-only observer reads, all successful with zero BUSY retries. This is an
observation of that run, not an availability or timing guarantee.

The example and operating limits are documented in [the I/O walkthrough](../../../docs/io-simulation.md).
No physical port, target MCU/emulator, neural model, acquired controller or hub
service was executed. The SQLite board is a host-driven model without autonomous
pulse/watchdog/stop guarantees. Graceful close alone does not settle a pending
pulse. Physical verification remains unverified; the finite fan PAT policy does
not qualify this I/O provider, and driver/hub lifecycle effects remain separate.

Two reporting clarifications preserve the original bytes: the profile report's
`stateCreated` field is a post-call pathname-existence probe, not a creation event.
It is intentionally true in the missing/tampered-store test that began with an
existing authority. The initial `source-comparison.json` describes the source
before the first failed attempt; `source-comparison-final.json` describes the
later production correction. No historical review or attempt has been rewritten.

`proof.json` records exact attempts, current closure comparisons and review
references. `index.json` seals all files in this lane except itself. The complete
runtime result is recorded separately by the full-suite attempt/pointer mechanism.
