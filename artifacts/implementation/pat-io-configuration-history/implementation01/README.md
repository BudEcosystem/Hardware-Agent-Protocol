# Independent finite I/O configuration and permission history

This candidate adds a pure configuration checker and 48 tests, with all 39
existing transcript tests selected for regression. Its inputs are exact copies
of the twelve newly captured configuration trials: 1,721 execution records,
504 configuration records and twelve manifests, plus separately trusted grant
plans derived from the reviewed test setup. No provider or runtime is executed.

The checker requires trusted installation/PAT/descriptor setup and a separate
initial principal, deployment, grant set and registry revision, with an ordered
plan of effective grant changes. Captured grants cannot authorize themselves.
The current change profile requires the same principal's prior administrator
authority and increments revision by effective row additions/deletions. It does
not reconstruct arbitrary provisioning calls or idempotent grant mutations.

Both streams share the original 4,096-record and 16 MiB ceilings. The reader
checks canonical bytes, exact ordered references, closed fifteen-table inventory,
SQLite cell types, primary-key uniqueness, complete eight-row pages, no unused
records, snapshot/checkpoint joins and runtime session/owner identity. Static
semantics cover all installed execution contracts, instance identities, bindings
and history, capabilities, routes, requirements, topology, generations, proofs
and actual resolver registration. The actor's entire type bundle and binding
must match the trusted descriptor. Non-actor TD presentation metadata is hashed
but not independently regenerated; operational contracts are checked for every
installed instance. Static configuration changes refuse this immutable profile.

Dynamic checks preserve exact session/stream history, observation provenance,
sequence order and presence/sample clock association. They do not reconstruct
intermediate sample instants within an adapter phase. Activation observations
may lag the board counter; this is explicit and no sampling claim is returned.
New namespace, parent-step, admission and dispatch permissions are checked using
the trusted grant plan. Admission records must name the captured revision and
current session, and possible execution must retain a dispatch link. The two
actual permission failures retain their distinct no-parent/no-dispatch evidence.
Active permission withdrawal is explicitly unsupported and refuses; it needs
additional real trials and guard-cause semantics before composition.

Two capture tests repeat an identical final checkpoint. The only inherited code
change permits consecutive identical final execution checkpoints, with no changed
table, phase, time or intervening record. The new configuration reader additionally
requires identical configuration snapshots there. Changed execution/configuration
recaptures are negative tests. The existing 39 transcript tests are rerun.

The 48 new methods include all twelve actual histories and rehashed adversaries
for permissions, grant plans, revisions, bindings, type contracts, routes, proofs,
sessions, observations, replay identity, refusal causes and shared limits. Pure
operation is checked with file, SQL and clock access forbidden. The remaining
2,809 inherited project/data files stay unchanged. Source preparation uses only
static parsing/hashing, not project imports or tests.

Configuration consistency and authorization-decision checks remain distinct
from current-source attestation, complete board/operation/parent outcomes, timing
policy composition, the full fault/auxiliary-actor matrix, enforced aggregate
storage, public qualification and promotion. All full attestation/outcome and
qualification flags remain false. No live runtime, physical device, MCU/emulator,
inference, external service or adjacent Harness changes. Primary-agent review
only; helper account limits prevent independent review. Actual results separate.
