# Partial validation; capacity profile failed

The negative and storage profiles passed 18 completed cases. The next mutation
capacity profile reached its unchanged 30-second wall limit and failed. Execution
stopped there; the episode, activation, retained-key, fixed-capacity and accounting
profiles were not run. Neither the 24-case matrix nor full reachable capacity is
established by this packet.

| Original profile | Outcome | Completed cases | Control checks | Observed successful control duration |
| --- | --- | ---: | ---: | ---: |
| negative attempt1 | Passed |8 |136 |17.284877417s |
| storage attempt1 | Passed |10 |122 |18.612281730s |
| mutation attempt1 | Wall-limit failure |0 |209 partial |Not a successful duration |

The two passing profiles total 258 checks: 252 completed-case checks and six
owner/finalization checks. The failed profile's 209 partial checks are separate,
not another passing case or completed capacity proof. Its final elapsed time was
31.743594587s including cleanup and final revalidation; the original 30-second
control bound was not enlarged or retried.

The completed controls cover qualification/driver expiry, installed context and
boot changes, premature retirement, refused original mutation identity, an
automatic-ACK revision refusal, sticky dispute with bounded original evidence,
and pre/post SQLite COMMIT exceptions at prepare, OPEN possibility, collection
and RETIRE receipt boundaries. They also cover a rollback-call exception and
configured SQLITE_FULL followed by close/reopen. These are actual synthetic
native/public-writer paths and synchronous living-owner storage controls; they
do not establish physical storage durability, power-loss behavior or arbitrary
compound failure coverage.

The failed retained DB contains 68 canonical `never_handed_off` START identities,
numbers 1..68 and keys `never-start:0..67`, each proposing endpoint sequence 1 and
retaining its unchanged-sequence STATUS settlement. The OPEN is accepted, the
stored current mutation sequence remains 0, there are no activation/episode rows,
and all three original resource claims remain held. Its file is 286720 bytes and
independently recomputed logical charge 136720 bytes. This was a wall-limit failure,
not evidence of reaching the 16MiB logical ceiling.

The retained stack shows interruption during the next public reservation's
`pending()`/mutation canonical validation scan. The control used 23.090823 CPU
seconds; its native child used 0.011718 CPU seconds. This identifies a relevant
host-side validation path for further investigation, without claiming a complete
performance profile. No complete per-case native counter snapshot or full raw
stream trace was published for the failed case. The auditor does not reconstruct
those missing artifacts or infer additional effect facts from their absence.

All 22 actual child identities were joined to retained reaps and observed absent:
19 native children exited cleanly on EOF, and three outer controls were reaped
(two exit 0, one exit 1). The failed inner cleanup receipt independently records its
one native child, empty/closed owner and no cleanup errors. The failed outer
reducer's `innerReaps:0` means it had not loaded the inner result; it does not mean
that no native child existed.

Root executed the independent data-only [auditor](audit_retained.py) and observed
terminal 0. Its [AUDIT.json](AUDIT.json) passed 42895 evidence checks over 995 retained
attempt files, 18 completed cases and 22 owned identities. It independently joined
all 28 completed native snapshot selectors, canonical DB records, raw request/reply evidence,
original image/qualification provenance, source/interpreter pins, 4530 sealed
parent files and public 244. SQLite was opened read-only/immutable/query-only,
with sidecar absence and DB hashes checked before and after. Audit success means
the retained prefix and failure are consistent; it does not turn the failed
capacity profile into a pass.

Audit SHA256:
`9256654248b0751839b52aa2573ec0eee5fe251889b7f508d60b559c08e10177`.
Auditor SHA256:
`da98d091cc59a3fb7c49a53f08635a76e1644f03e240c7f9669d6a0b67244f0d`.

The tested production/native sources were unchanged. The prior 20-case 173-check
host result, original 12-case 638-assertion qualifier and separate 13-cut owner-death
evidence were reused from their sealed original locations; none was rerun or
relabelled. The frozen README, PLAN and SOURCE-REVIEW retain their historical
unexecuted-at-freeze status. This new results document records the actual later
outcome. Physical/public eligibility and protected capacity remain false.
