# Current retained result

Both original reviewed profiles passed under root ownership. The subsequent
root-run [data auditor](audit_retained.py) also passed: [AUDIT.json](AUDIT.json)
retains 51,874 checks over all 608 actual attempt files and eleven owned process
identities. No candidate or auditor rerun was needed.

| Original profile | Completed cases | New control checks | Legacy checks | Native / outer reaps | Observed control wall time | Final elapsed time |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| [Pure attempt01](selection-reuse-pure-attempt01/RESULTS.json) | 1 | 84 | 0 | 0 / 1 | 2.356071599 s | 4.284285973 s |
| [Live attempt01](selection-reuse-live-attempt01/RESULTS.json) | 9 | 267 | 76 | 9 / 1 | 20.334696434 s | 22.301185156 s |

The 351 new checks comprise 349 case checks and two invocation checks. The 76
legacy checks are separate. Final elapsed time includes cleanup and source
rehashing; each observed control completed within its original 30-second bound.
These observations do not establish a speedup against the earlier diagnostic,
which exercised a different workload with intrusive timing instrumentation.

The pure case compared 34 vectors against the exact retained original compiler:
six successful outputs and 28 refusals. Public parsing/error precedence,
simultaneously malformed artifact and installation inputs, strict types, invalid
driver-slot bindings, qualified endpoint identity, returned-object detachment,
and changed constants/helpers between separate calls were covered. The control
observed five installation validations in the public compiler and one in the
private catalog compilation. The live complete selection observed three; the
old complete selection's seven is established by the retained source call graph,
not a new timing measurement. The public compiler's five checks remain intact.
The auditor independently reconstructed the successful compiled-record hashes
and joined the literal result to the actual live catalog selection.

The nine live cases covered management replay and original-run reassociation
refusal, final evidence withdrawal, final artifact corruption, renewal after
authority withdrawal, post-commit image expiry, shared finite/standing claims,
finite policy replacement, explicit prepared-mutation abandonment, and separate
common REVOKE uncertainty. Each fixture used the actual original native pipe
image. All 28 final selectors and every recorded request/response were retained.
Nine native children reached clean EOF exit zero; both outer controls also
exited zero. Registration, direct parent, reap, cleanup receipts and current
process absence were joined. No unexpected children or cleanup errors remained.

The retained databases contain eight standing deployments, two separately
retained canceled finite operations and three accepted retirements. Five
standing owners retain three claims each, totaling 15. The expired OPEN remains
possible and unsent. The abandoned original START remains never handed off with
its key, request and STATUS proof intact. Its explicit new-key successor is a
separate admission. The possible common REVOKE remains unsent and unresolved;
STOP and its loss witness do not release that owner's three claims or authorize
RETIRE. Physical resource proof remains exactly two atoms; actual shared claims
also include the installed driver's lifecycle slot.

Only [standing_pat.py](project/hms/standing_pat.py) changed in production. The
private detached installation snapshot exists within one uninterrupted pure
compilation call. Current policy, database, inventory, image, evidence and final
commit checks remain. The actual changed host source identity is bound into the
installed artifact, evaluation and deployment. The original native qualifier
bundle remains at its original absolute root, run `native-standing-original:4`,
attempt `native-standing-attempt:4`; its original 12-case/638-assertion receipt
was neither rerun nor reassociated. It is literal C-domain evidence, not proof
that this host change has completed every qualification gate.

The audit reverified the exact 283 reviewed inputs, 260 unchanged reuse copies,
11 provenance copies, all 4,394 indexed parent files and public 244-file baseline.
SQLite was read through immutable read-only/query-only connections; independent
canonical identities, cell-charge arithmetic, receipt joins and before/after
hashes were checked. The 16 MiB logical ceiling remains unchanged and supplies
no protected physical storage or compute capacity.

An independent child reviewer read the auditor and retained data without
executing or importing candidate/auditor code. Review found one auditor-only
constant error: `NOT_SEEN` is wire status 20, not 8. The complete draft is retained
under [audit-history/draft01](audit-history/draft01/), and the
[exact correction](audit-history/draft01-to-current.patch) changes that one
check. Root independently confirmed the enum and original reply, reviewed the
complete corrected source, and invoked the auditor once. The reviewer found no
remaining concrete blocker; that source review is distinct from root's actual
audit execution. Final auditor SHA is
`bbae120506ceb972e4a5031f04d9a66229e87641e700edb5b4eef9796847cb6d`;
AUDIT.json SHA is
`b5ffc7d98db5e752ad0b11ef0a0959763ae8feb1d8fb5de9e8802d30582fe4bf`.

[README.md](README.md), [PLAN.md](PLAN.md), [source-pins.json](source-pins.json)
and [SOURCE-REVIEW.json](SOURCE-REVIEW.json) preserve their exact historical
source-preparation wording and tested bytes. This newly authored results file
records the later executions; it was not an executed input. Full 128-record
capacity, all remaining capacity edges, actual owner-death requalification of
this changed host, physical device/driver/hub qualification, protected capacity
and public-mount eligibility remain unestablished. The old capacity timeout
remains failed. [NEXT.md](NEXT.md) identifies the next bounded gate.
