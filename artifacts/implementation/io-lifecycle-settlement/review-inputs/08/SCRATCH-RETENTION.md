# Snapshot07 private scratch handling — source-only preparation

The failed immutable06 admission smoke never reached Journal construction. Its child TMPDIR was below repository ancestors with mode0775, which the unchanged stock state-path policy correctly refused. No production permission or policy change is proposed.

The only executable change in07 is the original runner's scratch allocation/retention. It creates a real current-UID mode0700 `tempfile.mkdtemp` directory directly below a verified trusted `/tmp` directory. It records the actual path, device/inode, UID/GID/mode and parent metadata before launching the child. That actual path becomes TMPDIR. No symbolic-link alias, shared-directory chmod, caller-provided ownership exemption or Runtime path-policy override is introduced.

After attempting to reap the retained child, an independent finalizer verifies the scratch root still has its exact original identity and writes an actual file/symlink inventory relative to that recorded raw root. It marks whether the inventory was sampled after terminal child state. The pass gate requires the raw root to remain present, unchanged and terminally inventoried. A changed/deleted root, hashing failure or unavailable identity fails bookkeeping rather than manufacturing stable evidence.

This runner never deletes the raw scratch root, on either success or failure. Existing test cleanup behavior is unchanged: successful logical captures may permit an individual test workspace to be removed, while capture/Runtime-close failures retain that workspace under the raw root. Logical captures continue to be written directly into the attempt's evidence directory. The producer must explicitly acquire and hash any remaining raw outputs after a run; automatic `/tmp` cleanup or host failure can otherwise remove them. Retention is not a durable filesystem guarantee or hard quota.

The raw root itself remains visible even if capture or finalization fails. If the attempt filesystem cannot accept the path record, finalization still attempts to report the in-memory retained path; disk/host failures cannot guarantee any receipt. No raw scratch has been allocated or tested by this source preparation.

All156 project inputs and the child script remain exact06. Seven selected package inventories, source-origin refusal, bytecode-cache veto, test counts, timeouts and operation deadlines are unchanged. A corrected one-method admission smoke requires independent source review and explicit parent release.

## Deferred matching regression composition

Only after a successful current-source admission smoke, and after a separate explicit execution release, prepare a new isolated composition containing the exact07 runner/child and immutable06 project/tests. Copy the exact snapshot01 manifest and source files into that composition's `review-inputs/01` directory; preserve their hashes and original paths. The existing `--source-snapshot 01` option then overlays only the old `hms/` rows, leaving the current test methods unchanged. The top-level07 snapshot does not silently acquire a new overlay search path.

The two planned targets are:

- `test_io_lifecycle.LifecycleTests.test_rehashed_publication_cannot_substitute_valid_old_proof_or_bool_revision`
- `test_io_lifecycle.LifecycleTests.test_final_guard_operation_lookup_delay_cannot_escape_start_deadline`

Run each old-source composition and the matching current07 composition in distinct immutable attempts. A setup error or unrelated failure is not evidence of the intended regression. Preserve every actual result and database capture. This plan authorizes no run and adds no lifecycle acceptance cases; driver-target, consumer-free service, capacity and revision-exhaustion tests still await current-source evidence.
