# Deterministic writer-deferral results

Root executed the reviewed runner once. `writer-deferral-attempt01/RESULTS.json` reports success with exit zero in 0.734000753 observed wall seconds. This is the current execution report; the unchanged frozen README, design and plan describe the preparation state.

| Case | Normal worker leader exit | Held writer settlement | Final execution |
| --- | ---: | --- | --- |
| release | 0 | R released the writer; exit 0 | recovered `unknown` |
| eof | 0 | Closing the guardian writer produced EOF; exit 79 | recovered `unknown` |
| guardian_stop | 0 | Held pidfd delivered SIGKILL; exit -9 | recovered `unknown` |

All three cases positively observed inherited-writer deferral. Each computation child retained the matching lease after its worker leader exited normally. The separate provider owner observed that normal exit through its retained unreaped child, and the guardian later adopted and reaped the same leader with exit zero. The guardian selected each live writer from kernel child enumeration and acquired a pidfd before checking the ready notice's reported identity. The notice supplied association evidence, never signal authority.

The installed pipe-role/access/device/inode identity matched the artifact manifest. Each bounded ready notice matched the job request digest, launch nonce, artifact digest, child identity and exact writer-lease inode, and reported the independently checked fixed sum: 1,000 terms produced `2974571500` modulo 2^64. Arithmetic and its ordinary output occurred only after the original G admission gate. The second pipe held writer lifetime afterward; no sleep established that hold.

Each case recorded three independently opened matching-inode probes that found the lease held: before provider-owner death, after that death and the normal leader's reaping, and after deferred reconciliation. Thus the run contains nine positive held-lease observations. Reconciliation while held returned the unchanged released row with no receipt and unchanged committed slot bytes. The unresolved row also retained admission against a fresh key.

Only after the guardian settled and individually reaped the writer did the fourth matching-inode probe find the lease free. All three final receipts were recovered `unknown`, with `mayHaveActed=true`, no result, no process exit code and no validated output. Locally observed computation bytes did not become an invented durable success. Historical replay launched no work before or after settlement.

The controls killed and reaped three owned provider owners, reaped three normally exited worker leaders, and settled/reaped three writers: nine family members in total. The outer guardian additionally reaped the control process. Its final record has no children left to adopt after normal control completion and no pending cleanup interrupt. Registration-state snapshots in identity records are historical; the `exitCode` and `reaped` fields come from the later wait operation.

The attempt reports exact source inputs, stable sealed parents and all 244 public baseline hashes unchanged. `guardian.py` and its native binding remain exact copies of the sealed guardian authority. The prior 866 tests were not rerun. The earlier [owner-death packet](../owned-hub-crash-harness/README.md), whose twelve initial lease probes were all free, remains unchanged; this separate run supplies deliberate held-writer coverage.

Root's separate [retained-data audit](AUDIT.json) completed successfully without importing candidate code or rerunning provider jobs. It verified six adjacent canonical ledger slots, three independently calculated results, nine historical held-lease and three historical free-lease observations, and three new independently opened matching-inode probes that found the leases free. It joined nine family reaps and the outer reap, found all ten observed identities absent, and confirmed 29 frozen source pins, all 653 sealed parent files and the 244 public baseline hashes. The historical held observations remain evidence from the single original run. No source, frozen input or attempt bytes were changed when writing this review.

The guardian must remain alive and the kernel must service its observations/signals. This finite fixed-family result does not establish universal descendant containment, aggregate capacity, hard physical stop deadlines or power-loss durability. The descriptor hook remains a private installed fixture, with no caller-selected descriptors or executable. No public provider mount, GPU/GB10 readiness, physical I/O/driver control or learned PAT deployment is qualified here. [NEXT.md](NEXT.md) records the remaining integration work.
