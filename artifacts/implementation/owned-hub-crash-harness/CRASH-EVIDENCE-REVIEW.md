# Independent retained owner-death evidence review

Reviewed at 2026-11-09T10:38:21.652204+00:00. The retained attempt supports the
declared twelve fixed process-death cases: **6 not_started, 3 unknown, and
3 completed**. Every owner was killed with SIGKILL and reaped. The inner guardian
reaped 20 children in total: 12 original owners and 8 adopted job leaders. The
outer guardian separately reaped the control process with exit zero. Its
retained elapsed time is 1.9602454880077858 seconds.

This review read retained files and current `/proc` observations. It did not
import or execute the candidate, rerun controls, launch provider jobs, acquire
process handles, or send signals. Only this review document was added.

## Boundary outcomes

“Adopted” counts job leaders collected by the inner guardian. “Reaped” includes
that case's killed owner. An em dash means no adopted job leader. These counts
do not include the outer control process or computation children already
collected by their original leader.

| Owner checkpoint | Durable phase at checkpoint | Final execution | Adopted | Reaped | Adopted leader exit |
| --- | --- | --- | ---: | ---: | ---: |
| admitted | admitted | not_started | 0 | 1 | — |
| launching | launching | not_started | 0 | 1 | — |
| ownership_registered | launching | not_started | 1 | 2 | 73 |
| spawned | launching | not_started | 1 | 2 | 73 |
| associated | associated | not_started | 1 | 2 | 73 |
| before_release | associated | not_started | 1 | 2 | 73 |
| release_intent | released | unknown | 1 | 2 | 73 |
| gate_released | released | unknown | 1 | 2 | 0 |
| writer_settled | released | unknown | 1 | 2 | 0 |
| before_reap | settled | completed | 1 | 2 | 0 |
| reaped | settled | completed | 0 | 1 | — |
| terminal_committed | settled | completed | 0 | 1 | — |

The distinction between `writer_settled` and `before_reap` is material. The
former has no committed terminal receipt, so recovery retains uncertainty even
though the guardian later observes exit zero. At `before_reap`, the valid
terminal receipt is already committed; the guardian can collect the remaining
zombie without changing that receipt. The three completed rows remain exactly
equal to their checkpoint rows.

At `release_intent`, the durable intent precedes the gate write. Recovery still
returns `unknown`: the later guardian observation of exit 73 is not used to
rewrite durable execution knowledge. All nine recovered rows keep result and
exit code null, output validation false, and stream/group observations unknown.
The original request key, digest, nonce, owner session, lease association, and
recorded job PID remain unchanged. Each final ledger retains exactly one key.

**Lease deferral occurred in 0 of 12 cases.** Every initial reconciliation was
already terminal and equals the final reconciliation. This run therefore does
not establish deliberate retention of a live writer lease after owner death.
It also does not qualify the excluded early-leader-exit scenario.

## Independent joins and arithmetic

All 24 checkpoint/recovery JSON records were parsed and checked against the
twelve case summaries. Their 20 per-case reaping records concatenate exactly
to `checks.json`'s reaping list. Every owner record has exit -9. Each of the eight
reported unreaped job identities matches an independently adopted record by
PID and start ticks; its parent changes from the killed owner to the guardian.
The `reaped` checkpoint reports that the provider already reaped its child;
neither it nor `terminal_committed` supplies a job PID for reopening.

All 24 retained ledger slots have canonical envelopes, matching state checksums,
the expected slot parity, and adjacent generations. Each newest snapshot is
exactly the final recovered row. For the nine nonterminal checkpoints, the
preceding snapshot equals the checkpoint row; for the three terminal checkpoints,
it is the preceding released row. No candidate parser or ledger implementation
was imported for these comparisons.

The input is first = -7, step = 3, count = 1000. An independent sum over the
arithmetic progression yields **2,974,571,500 modulo 2^64**. The same value follows
from `49 × 1000 - 42 × 499500 + 9 × 332833500`. All three completed receipts
contain count 1000 and the decimal string `2974571500`, with validated output,
exit zero, EOF observed, and no observed live group member. The other nine
receipts contain no reconstructed result.

Historical replay is recorded as spawning nothing, and all before/initial/final
views report no live provider owner. The reviewed control source asserts exact
historical rows and an empty in-memory ownership map on replay. These are fixed
control observations, not a universal proof about arbitrary provider code.

## Source identity and outer result

All 13 intent-pinned inputs match both the current source and frozen copy. All
seven provider input copies also match their recovery-source originals and
`provider-pins.json`. The retained interpreter hash still matches its path.
The public receipt hash and all 244 public input hashes were independently
rechecked; no public suite was rerun.

The outer receipt reports no adopted child after control exit, no pending
INT/TERM, no error reason, exact input checks, and exit zero. Its standard output
is exactly the expected five-field result; standard error is empty. The frozen
sources match the independently reviewed versions:

| File | SHA256 |
| --- | --- |
| guardian.py | cf682bcfae001f5e1d33cad603ec4a7e3911dc4eab8557714b6973deec7bb206 |
| owner_crash_checks.py | ee5cd4b4a7a267a286b5c623657c5ee165db5a61942ccdcae4862dea5306dea3 |
| run_owner_crashes.py | e2a80fcc3314ed1932efb7ae6e29157e744f38cdd747a12d3212f37a7d110912 |
| CRASH-PLAN.md | d0736dd683c2705bc79672dae557f15ebfa6d616a70ffb8e54ebdcae5f5159ae |
| provider-pins.json | 3ae463225c0837ee6b1f8806e5c9c893bfd424ca31bb97e427e0371019c2c8b0 |

Principal retained evidence hashes:

| Evidence | SHA256 |
| --- | --- |
| owner-crash-attempt01/RESULTS.json | 1f09a405950fad9ccb008f1d94af46f183ff4778685f1297ccb09c3ddd68074d |
| owner-crash-attempt01/state/checks.json | 8d2b4796c8c1f716da502aca6f5fae8a63056e68ba397efe49600d85b3e75a78 |
| owner-crash-attempt01/intent.json | 78dafada8bceaa8e7ff523b72cd3a8fa451d72a5112c7ca4a3d47994950fa687 |
| helper-attempt01/RESULTS.json | 73c73562c8cd8930779aedf3a411eb09fb256828eb0c87efb6ea7aacf8632abc |
| guardian-attempt01/RESULTS.json | 9d157309e9cd89a662e04e07661217ec4832f160b857dd2c20252e6f9d0f77ab |

## Current process observations

At the review timestamp, all **23 distinct retained owner-crash identities**
were absent from `/proc`, including zombies. This set contains the 20 inner
guardian reaping identities, the outer control identity, and two additional job
leaders recorded in terminal receipts and already reaped by their providers.
All **6 identities** from the earlier adoption control were also absent. The
three helper build/control PID numbers were absent; those older records lack
start ticks, so their current check is a numeric absence observation only.

The 29 identity observations, shown as `PID:startTicks`, were:

```text
67711:10737204 67712:10737206 67713:10737206
67714:10737208 67715:10737208 67716:10737208
69235:10804126 69236:10804129 69237:10804140
69238:10804152 69239:10804160 69240:10804165
69241:10804173 69242:10804179 69243:10804187
69244:10804193 69246:10804201 69247:10804209
69248:10804217 69249:10804225 69250:10804233
69252:10804241 69253:10804249 69255:10804260
69256:10804268 69258:10804278 69259:10804286
69261:10804297 69263:10804305
```

Helper PID numbers observed absent: 65909, 65916, 65921. These are read-only
snapshots of retained observations, not universal descendant enumeration or
authority to signal a process later.

## Earlier controls, kept separate

The helper attribute control passed **9 checks**, created no children within
that control, and restored the original attribute. Its two compile commands and
control command each have retained exit-zero, reaped, no-remaining-group-member
receipts. This establishes the tested binding/attribute behavior, not adoption.
The helper binary still hashes to
`a6ee94bcf3dc03df19f0dd07a81663badd4875ef1a6c429afbc55d7b2373b977`;
the four retained build sources and compiler match their pins.

The separate guardian adoption control passed two fixed trees of depths two and
three, reaping **5 tree children** plus its separately recorded outer control
process. Its retained checks include refusal before a process becomes a direct
child, adoption across separate sessions, and restoration of the subreaper
attribute. Initial registration records can precede a child's `setsid`; they
are not snapshots of its final session. The original control's fresh per-step
assertions establish its tested separate-session behavior. No provider job ran
in either earlier control, and neither earlier control was rerun for this review.

## Qualification limit

The passing slice requires a living guardian and the reviewed fixed job family.
It is process-death evidence, not power-loss durability, public control-storage
qualification, aggregate host resource enforcement, arbitrary-process
containment, deliberate live-writer deferral, real GB10/GPU integration, or
independent physical stopping. This review does not seal the packet; root will
perform the final packet seal.
