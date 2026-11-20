# Current result: workload failed, retained-data audit passed

The root-owned [original attempt](selection-capacity-mutation-attempt01/RESULTS.json)
failed with `CONTROL_WALL_LIMIT` under the unchanged 30-second bound. No complete
case passed. Final elapsed time was 31.613240683 seconds, including cleanup and
rehashing; there is no observed within-limit completion timestamp. The control
used 21.5343 CPU seconds. This result does not establish the full 128-record
capacity gate or a general speedup from the earlier failed prefix.

The later retained inner receipt records 333 partial original assertions and one
wrapper invocation assertion, zero completed cases, and orderly interruption by
TERM. The outer receipt honestly reports null inner counts because it did not
reduce that receipt before its deadline failure. The inner record separately
proves one native clean EOF exit zero, using 0.012672 CPU seconds; the outer
control exited one. Both exact registered identities were reaped, then observed
absent. Owners closed empty with no cleanup errors or unexpected children.

The closed 344,064-byte database retains 111 original mutation records:
110 explicitly settled `never_handed_off` STARTs and one `prepared` record,
key `never-start:110`, with no reply or settlement. The original OPEN remains
accepted and unretired. All three resource claims remain held; mutation sequence,
activation/collection/ACK prefixes are zero. No activation, episode, common
REVOKE, ACK or RETIRE evidence was created in this failed prefix.

The retained partial trace has 454 packets: 227 paired requests/replies consisting
of four DESCRIBE, one BIND, one OPEN and 221 STATUS requests. The last observed
request is tx337/response rx227. The final prepared START is tx338, while durable
route.tx339 includes a separately reserved read-only STATUS. Neither 338 nor 339
appears as sent. The interruption traceback is inside that STATUS reservation's
COMMIT; that observation does not attribute the workload's total elapsed cost.
There is no full final 28-selector native snapshot, and the partial evidence does
not claim one. Identical observed STATUS bodies are earlier observations only.

Root reviewed and invoked [audit_retained.py](audit_retained.py) once. The
independent [AUDIT.json](AUDIT.json) passed 63,046 retained-evidence checks over
all 299 attempt files, the 289 reviewed inputs, 262 exact reuse files, 18 provenance
copies, 5,969 indexed parent files and public 244. Canonical identities, every keyed
mutation, original qualification association, partial wire receipts, shared
claims and process roles were joined. SQLite reads were immutable/read-only and
query-only, with unchanged before/after hashes and no recovery sidecars. The
logical charge is 202,173 bytes under the unchanged 16 MiB ceiling; this is neither
full reachable capacity nor protected physical storage.

Audit SHA is
`2b32b2736d366a9e90262ef4c5662379183de062516c4207498fdf7677221034`;
failed database SHA is
`26cd3b6046e64f960d2b5c91e3a012ed82d105897b46204ddb3784c1ca3cd19e`.
Audit success establishes consistency of the retained failure, not workload
success. The original project closure and original full scenario remain exact;
no code correction, bound increase, candidate rerun, compiler or qualifier run
followed the failure. Both capacity failures remain preserved.

[README.md](README.md), [PLAN.md](PLAN.md), [REVIEW-NOTES.md](REVIEW-NOTES.md)
and [SOURCE-REVIEW.json](SOURCE-REVIEW.json) retain their historical reviewed
source-preparation wording and tested bytes. This new results file records the
later outcome. Full capacity, other capacity edges, owner-death requalification,
physical I/O/driver/hub qualification, protected capacity and public eligibility
remain unfinished. [NEXT.md](NEXT.md) records source-grounded remaining work.
