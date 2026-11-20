# Standing host source review, continuation 101

This is source review, not build, execution, qualification, or approval to publish.
The full host implementation remains in progress. The root read these complete
files in bounded, nontruncated tool outputs:

| Candidate-relative file | LF lines | SHA-256 |
|---|---:|---|
| `project/hms/standing_wire.py` | 544 | `663742aaa933097edd165bdab8b3ab7ef753d7d378d262b01178fc2241c38e9c` |
| `project/tests/standing_host_pipe.c` | 232 | `bbe0fa458aec16a0369b435f47322257a5c4bbe4ece0854f1633dd7565b527e0` |
| `WIRE-BRIDGE-NOTES.md` | 120 | `6682ba5255827d026283ce5ea1d636fc1d95cb60cc8e0e84b9fc2d3cd4a21514` |
| `project/hms/standing_pat.py` | 644 | `b1734acbe443501124b2a6965aa9768abd1eb3c3966e57f4945ebc10f801d726` |
| `PAT-QUALIFICATION-NOTES.md` | 211 | `1f5a8e7a4be099af9d218843caf916e0959e8a41462d443249b766dd06a371fc` |

Candidate directory: `artifacts/implementation/standing-host-deployment`.
Earlier combined tool output was truncated and is not counted as read coverage.
The complete reads above supersede that attempted read. The root also read
lines 1–185 and 335–480 of the copied original `standing.c` to compare the
request syntax, response prefix, descriptor and retirement behavior; this is
not a new full-file read of that C source.

The codec preserves exact canonical bytes and distinguishes unapproved witness
candidates from valid aggregate settlement. It checks request correlation,
record identity on successful replies, duplicated counters and typed body
layouts. Frame continuity, independently sampled page association, durable ACK
eligibility and authority remain host responsibilities.

The synthetic bridge uses the original serial link, endpoint, standing core and
fixture. It accepts a single inherited private control descriptor and performs
only explicitly requested service polls. The reviewed future runner must own
the descriptor types and lifetime, wait for each complete wire reply before a
control command, and wait for its acknowledgment before another wire request.
Polling before a blocking write is not by itself an absolute I/O deadline;
the runner's bounded process ownership and cleanup remain required. No physical
I/O, executable selection, new process launch or automatic service is present
in the bridge source.

The PAT source binds one exact literal synthetic configuration to the original
twelve-case, 638-assertion controller sources. It does not qualify arbitrary
parameters, another controller image, physical execution or protected capacity.
The future runner must create the original reservation before launch, enforce
the stated limits, wait and close owned child handles before publishing its
receipt, and honor immutable publication and shared evidence locks. Matching
receipt JSON alone is not independent proof of execution. Selection rechecks
the complete catalog inventory and held evidence inside the admission
transaction; historical replay must precede fresh selection in the store.

The shared finite/standing writer capacity bound, mutation-response association,
recovery coordinator, actual native producer and host test runner are still
required. No import, compilation or test of this host candidate has occurred
in this review. Full HMS implementation remains active and incomplete.

## Findings during review of the changing draft

These are review findings against work in progress, not complete frozen-source
coverage or execution results. The author is preparing a final review packet.

- The shared Journal claims schema must have one typed finite/standing owner
  authority, including both installed instance aliases. DDL substitutions must
  require exactly one matching baseline fragment before replacement.
- A limit on standing rows alone leaves finite and catalog writers outside the
  continuation guarantee. The draft must account for all installed writer
  tables and refuse unknown schemas at the shared transaction boundary.
- The sealed plan's 16 MiB logical ceiling remains. A proposed 32 MiB total was
  rejected during review. The replacement draft partitions the original total
  among finite, standing, fixed and route records; its worst-case charge proof
  and actual controls remain review gates.
- Ordinary finite events and replay aliases must not consume terminal/recovery
  slots or bytes. Per-row caps alone do not reserve the remaining obligation.
- Driver evidence reads must be bounded before allocation and held through
  admission. The original launcher must bind the inherited peer to the exact
  installed executable; a current pathname hash alone is not peer attestation.
- Test controls must cover receive-watermark commit before business-record
  commit, boot change between descriptor pages, post-commit evidence expiry,
  and a lost ACK followed by explicit read-only reconciliation.
- A final passing receipt must not survive an interrupt delivered on signal
  unmasking. Cleanup and publication failures need retained terminal failure
  records in both the outer runner and inner controls. The exact corrected
  runner still requires root review before execution.
- Injected exceptions in a living owner do not replace actual owner-death
  checkpoints. Those crash controls remain outstanding.

## Independent frozen-source findings

The first complete host source freeze is retained under
`artifacts/implementation/standing-host-deployment/history/source-freeze01/`.
Its `SOURCE-REVIEW.json` SHA-256 is
`f7f605c415cb348fff31ebae2335f39ed7b7a5dc479c11cdc73ed1f8347c412b`;
it inventories 269 files and excludes itself. No candidate execution preceded
this review. The author preserved the complete freeze before remediation.

The independent lifecycle reviewer fully read the frozen coordinator (354 LF),
fixture (159 LF), controls (278 LF), store (823 LF) and existing transport (96 LF),
plus README/PLAN. The capacity/authority reviewer fully read the capacity checker
(77 LF), contracts (273 LF), store, review documents and complete Journal,
Registry and ResourceCatalog diffs, with selected original Journal transition
bodies. These delegated reads do not imply that root reread every file in full.
Root separately read the complete frozen 274-line outer runner and the capacity
proof, README and PLAN. The inner and outer final-unmask corrections were present
in that freeze; the following additional findings still require correction:

1. A mutation committed as `prepared`, followed by failure before its
   possible-send commit, could remain permanently pending. Reconciliation only
   resolved possible sends, while the pending row blocked subsequent mutation
   and retirement. Prepared OPEN also lacked explicit abandonment settlement.
2. Coordinator decoding could raise after the receive watermark committed but
   before the store retained the offending response. A later valid STATUS could
   then clear uncertainty without the required durable conflict association.
3. Finite admission registered only an image check at final commit, leaving
   policy withdrawal or installation change after its earlier freshness check
   insufficiently guarded. Standing selection already had a fuller final check.
4. The fixture/control reducer did not require each reaped native process to
   exit successfully. A late native failure could leave the control report
   marked passed despite complete process cleanup.
5. Standing row validation limited owner epochs to unsigned 32 bits while the
   shared Journal permits the larger safe-integer domain, creating an eventual
   recovery-domain mismatch.

Root requested source remediation and controls for these findings, preserving
the rule that a possibly sent effect is never automatically retried. Remediation
is in progress and is not verified by this first-freeze review. Actual owner
death, broader negative/capacity controls and the entire host execution remain
outstanding. Neither source arithmetic nor a future partial control run can
complete the full standing host qualification by itself.
