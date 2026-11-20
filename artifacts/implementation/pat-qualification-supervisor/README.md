# Staged qualification process ledger

This is an original internal Linux/Python process and archive component. It is
not mounted in Runtime or the PAT catalog. It does not publish qualification,
run a model, use a physical endpoint, or execute downloaded controller code.
The copied HMS baseline is the successful 643-test source closure captured in
`before.json`. Live sources subsequently changed; these results are historical
tests of these exact copies, not current qualification receipts.
The external input manifests cover the five installed validation distribution
inventories, the Python executable, and the `_sqlite3` extension binary. They do
not pin the entire Python standard library, dynamically linked SQLite library,
OS or kernel; this is a selected dependency identity, not whole-host attestation.

`prepare_request(trust, limits)` binds complete detached worker setup, the
deployment/evaluator/run association, and source/resource identity.
`QualificationSupervisor.execute(request)` admits once and launches only a new
attempt. Exact retry returns committed state before current implementation
checks; changed input at the same key conflicts. `lookup`, `status`, `recover`
and `stop_owned` expose explicit control/recovery. `AttemptLedger` is a separate
private SQLite authority; it never receives a live Journal or driver object.

The lease is acquired before launch intent commits and the same held descriptor
is inherited by the child. The child retains that writer authority through exit.
Only the live parent's pidfd authorizes automatic signals. Reopening marks a
nonterminal row interrupted; held, absent or replaced armed leases block
recovery. A free matching lease establishes writer quiescence, not success.
Owner-loss recovery retains unknown exit status. There is no same-run rerun.

The fixed entry uses Python isolated mode and a private image containing exact
original HMS sources and the already installed validation distributions. These
resources are copied and hashed; no package is installed or fetched. Socket
creation/name resolution is vetoed before dependency imports to prevent
accidental schema retrieval. This is a trusted-code safeguard, not an OS network
or Python security sandbox. Root/current UID and the interpreter remain trusted.

Input, lease, stdout/stderr and the exact worker return live beside the initially
empty worker output directory. Archive commit retains exact bounded return bytes
and digest in SQLite, so later path mutation cannot rewrite historical replay.
All referenced record bytes/hashes are checked after writer quiescence. The
archive's `transportComplete` means normal owned exit and intact return/record
transport, not semantic qualification. Full reducer/import remains a separate
boundary. `semanticQualificationVerified` is false and the control record leaves
`unresolvedEffects` unknown; the exact raw worker result retains its own value.

Logical retained-byte reservations, bounded scans, bounded pipe collection,
per-file RLIMIT_FSIZE and pidfd watchdog stops do not impose an aggregate disk
quota or hard termination deadline. Every archive says
`totalDiskQuotaEnforced=false`. Kernel I/O or an inherited writer may remain
unresolved. No unresolved artifacts are deleted. The configured root must
eventually be fixed by trusted service configuration; separate caller-chosen
roots cannot establish global single-flight or retention admission.

## Executed evidence

`run_attempt.py` creates a fresh copied source tree before each run, places it
ahead of live imports, verifies the parent and child HMS roots, records hashes
before/after, and retains actual worker files/SQLite databases and logs. Original
temporary working roots are also retained; no unresolved tree is cleaned up.

- `attempts/attempt01`: 12 tests, 5 reported assertion failures, no errors; 54
  source inputs unchanged. Isolated Python selected different system package
  metadata and refused before worker execution. This exposed the need to copy
  the pinned installed dependency distributions.
- `attempts/attempt02`: 12 tests, 5 reported assertion failures, no errors; 54
  inputs unchanged. A suffix-only dependency copy omitted extensionless JSON
  Schema resources. Validation attempted remote retrieval before the worker
  budget started. Owned watchdogs stopped their children. The deliberate
  owner-crash case correctly remained lease-held/unknown; the separately
  retained `orphan-cleanup.json` records root-authorized manual cleanup through
  a pidfd after checking the unique code image, command and recorded lease inode.
  This is not a PID-based supervisor recovery path.
- `attempts/attempt03`: **15 tests passed**, 0 failures/errors/skips, 62.677 test
  seconds / 64.329 harness seconds; all 54 copied inputs unchanged. Real process
  losses cover admitted, launch-intent, spawned, producer-settled and archived
  boundaries. The original worker completed its 10-case constant-program matrix;
  a subsequent full semantic reduction accepted the retained records. Tests also
  preserve an actual worker output refusal, a parent deadline stop with unknown
  effects, exact archived replay/reopen, held/replaced/missing lease refusals,
  concurrent exact/conflicting keys, malformed raw return bytes, schema/path
  refusal, logical admission, and extensionless dependency coverage.
- `attempts/attempt04-before-review-fixes`: two new controlled regressions
  failed before correction. A successful spawn lost the retained Popen when
  pidfd acquisition failed; a terminal process/EOF observed after selector wait
  escaped a stale pre-wait deadline sample. The test retained its own original
  Popen for safe pidfd cleanup, so it did not abandon that child.
- `attempts/attempt05-before-image-reservation`: the near-limit first-image test
  failed before correction: logical admission omitted new shared code-image
  bytes. No worker was launched by this controlled regression.
- `attempts/attempt06-after-review-fixes`: all three regressions passed, 4.241
  test seconds / 5.879 harness seconds; 54 copied inputs unchanged. A live Popen
  is now retained before pidfd acquisition and `stop_owned` can safely finish
  that retained child. Terminal acceptance resamples monotonic time after wait.
  New unique image bytes and directory/file counts are charged before admission;
  an existing image must match its retained identity before a zero-extra-byte
  charge is used. This remains logical accounting, not allocated filesystem
  capacity or a quota.
- `attempts/attempt07-before-ledger-grammar`: one new test method reported 11
  failing corruption subtests before correction. It demonstrated accepted
  contradictory archive flags, invalid phase/history/type claims and an archive
  attached to a nonterminal state. The 54 copied inputs and 139 selected external
  inputs were unchanged.
- `attempts/attempt08-final`: **19 tests passed**, 0 failures/errors/skips, 71.176
  test seconds / 73.176 harness seconds. All 54 copied inputs and 139 selected
  external inputs were unchanged. This combines all original crash/worker tests
  and the fixes: closed retained control grammar, legal history/lease/pid
  associations, derived transport completeness, fixed false semantic/quota flags,
  null control unresolved effects, and bounded metadata reads. Invalid stored
  controls cannot trigger repair, release the active slot or launch a worker.

Reported assertion failures include subtests; subtracting their count from the
number of test methods is not a valid count of successful methods. No budget,
operation deadline or freshness bound was widened between attempts.

`dependency-inventory/inventory.json` and `exact-resources/` preserve the installed
resource finding: 20 JSON Schema resource files (37,354 bytes), 14 omitted by the
old compiler suffix filter. Root separately corrected the live compiler identity.
This stage did not edit live source or adopt that new identity under an old pin.

`review/design-01.json` is the earlier independent design review; the separate
final implementation review pins the corrected source and terminal result.
Passing tests do not prove every exception or kernel/filesystem failure window.
The corrupt-control checks establish internal consistency, not cryptographic
authentication against a trusted UID rewriting every ledger field. Later full
evidence verification remains required.

## Required integration work

The durable supervisor must be mounted behind one trusted service configuration
and actual aggregate storage admission/enforcement. Current Registry/config
snapshots must be reauthorized and compared after capsule construction. Archive
import must use the Journal mutex with no nested transaction, because the existing
EvidenceStore owns BEGIN and still does full reduction during import. Exact
archive reuse must survive a crash before catalog commit. A serialized one-use
callback association must bind run/evaluator/config/environment and return only
retained terminal evidence; direct or pending callback use must refuse before
the catalog consumes its run key. Negative/unknown worker results need their own
reviewed catalog mapping; unknown effects cannot be converted to zero. Memo
capacity/prewarming and final dependency rechecks must be explicit. Persistent
applications, real driver/I/O/hub operation, learning and model-on-novelty remain
outside this process slice and required by the broader goal.
