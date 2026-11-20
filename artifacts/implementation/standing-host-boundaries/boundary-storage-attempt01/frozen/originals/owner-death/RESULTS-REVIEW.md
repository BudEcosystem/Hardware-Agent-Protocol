# Verified fixed standing-host owner-death results

All13 owner-death cases passed, followed by a separate stdlib-only retained-data
audit that passed12,739 checks. [AUDIT.json](AUDIT.json) verifies all476 retained
attempt files, the exact287 reviewed inputs,261 copied source/helper files,
19 original provenance copies,3,755 sealed host-parent files and public244 inputs.
The audit imported no candidate code and reran neither controls nor qualification.

The original control completed within the unchanged30-second observed bound:
22.150156088 seconds to terminal observation,22.943975796 seconds including final
cleanup and source verification, with16.270212 recorded CPU seconds. It reaped13
intentionally killed owners,13 successful recovery hosts and13 native peers with
cleanEOF exit0; the outer control also exited0 and was reaped. Both owners were
empty/closed, without cleanup errors, pending interrupts or unexpected children.
The independent audit observed all40 historical owned identities absent, including
checking that none remained as a zombie.

| Cut | Verified recovery and ownership |
|---|---|
|OPEN prepared|Original marked never_handed_off; retired and claims released|
|OPEN possible|Possible send unresolved; all three claims retained|
|OPEN reply|Exact original OPEN accepted through observation; claims retained|
|START prepared|Old original settled never_handed_off; separate new START accepted|
|START possible|Possible send unresolved; no resend; claims retained|
|START reply|Exact original START accepted through observation|
|Collection before ACK|Committed prefix retained; separately requested ACK accepted|
|ACK prepared|Old ACK settled never_handed_off; separate new ACK accepted|
|ACK possible|Possible ACK unresolved; acknowledged prefix stays0; claims retained|
|ACK reply|Exact ACK accepted within the already committed prefix|
|RETIRE prepared|Old RETIRE settled; separate new RETIRE accepted; claims released|
|RETIRE possible|Possible RETIRE unresolved; terminal endpoint remains owned|
|RETIRE reply|Retained terminal proof joins same-boot empty descriptor; claims released|

These outcomes total three retired/released deployments, four unresolved possible
sends retaining claims, and six accepted or explicitly settled deployments retaining
ownership. The same native peer survived each original owner's SIGKILL. Before any
separately requested new action, a parent-observed recovery barrier checked original
snapshots, outgoing read-only frame bodies/correlation and unchanged native counters.
No historical possible effect was resent. A new START's acceptance did not fabricate
an output dispatch. RETIRE's reset native counters were joined to retained original
prefix/witness/fence evidence, rather than treated as independent proof of release.

The audit independently checked canonical original request/deployment digests,
keyed mutation/activation/version/episode records, immutable original body/key/tx
identity, exact allowed reopen changes, raw response and witness joins, authority/
replay/claim SQL columns, foreign keys, and final read-only database state. Its
40 process identities and observed command deadline join the original start/reap
records. All successful fixed child logs were empty. The original qualifier bundle
was consumed at its original absolute host-attempt04 root with original run/attempt
IDs:4 and actual12-case/638-assertion evidence; it was not relocated or rerun.

Important retained pins:

- Original run RESULTS SHA256: c7dc7de7f0bf5f8b70ab1037f7894c9e5b8518c289e0d24b3be1e33ae26a4f77.
- Executed source manifest SHA256: 4dca9bff924a726520952e9beae2a4b7d18bd73f46a4735e2fd1c227f2aba9fe.
- Audit source SHA256: 0280e7dd3f291c42d342aa19b1f6d707826052078a7fd44b30179a682f376377.
- Audit output SHA256: 030ee016eed19a7ecc699d8ab6071245d3344840bfe63bd0ea1b3f3c3b661fbf.

This final note is a post-run document. The reviewed README/PLAN/SOURCE-REVIEW,
drafts, audit history, frozen inputs and original attempt remain unchanged;
their source-only or pending-audit status records their historical review stage.
This note and the packet index describe the current verified result.

The evidence qualifies these13 fixed complete-transaction/complete-reply cuts with
a living guardian and synthetic native peer. Whole-host qualification, physical
and public-mount eligibility, protected capacity and universal containment remain
false. It does not qualify partial frames, death inside COMMIT, host power loss,
full storage pressure, guardian loss, physical devices/GPU services or the complete
natural-language application/PAT system. [NEXT.md](NEXT.md) retains those gates.
