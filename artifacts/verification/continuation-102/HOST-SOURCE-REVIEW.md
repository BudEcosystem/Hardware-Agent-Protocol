# Standing host revision review, continuation 102

This records source review before the first candidate execution. It does not
qualify physical hardware, protected storage capacity, natural-language learning
or recovery after an actually killed host owner.

The prior 269-file freeze remains exact. Root independently verified the complete
271-file second freeze under `history/source-freeze02`, whose source-review
manifest SHA-256 is
`aa101e745748ca9b2366fd128a8e5a30ab7750cc1206ba2f16a3503125fcda68`.
The first freeze's review coverage remains in the continuation-101 report.

Root read the complete revision deltas for the store, coordinator, contracts,
native bridge, fixture, control cases and runner. Root also reread the complete
outer runner, Journal commit-check implementation and dispatch transaction,
the prepared OPEN settlement body, prepared ACK continuation, and the two added
prepared-ACK/common-REVOKE controls in bounded outputs. Large truncated JSON
outputs are not manual source-reading coverage; inventory checks parse them as
data.

The revised settlement path only abandons an original durably prepared request
that never reached the possible-send boundary. It retains its original key and
bytes and requires explicit authenticated reconciliation. A new caller request
can obtain a new identity; the original is not resent. Allocated route numbers
and fences remain monotone, while confirmed historical OPENs separately explain
the endpoint's observed floors. Prepared OPEN abandonment now refuses any common
REVOKE outbox, including an unresolved possible handoff, and retains its claims.

Malformed or wrongly associated real native replies now create durable conflict
evidence after the receive watermark commit. The private bridge changes an
actual queued original-endpoint reply and recomputes its transport CRC. Its two
fault modes exercise response identity and state validity without substituting
a mocked endpoint. Later valid STATUS cannot erase the resulting dispute.

The fixture and both reducers now require joined clean native EOF exit zero.
Standing owner epochs use the Journal's safe-integer domain. Finite admission
adds final freshness checks, but root found one remaining issue in freeze02:
submission_record or the trusted dispatch reservation callback can replace
`journal.policy` after admission. Calling the old policy's `fresh` method alone
does not detect this. The author independently confirmed the reachable ordering
and is preparing a narrow identity/reassociation guard and negative controls.
No candidate execution is authorized by this report until that exact revision
and the bounded runner are reviewed.

The existing 16 MiB logical writer ceiling and reserved continuation categories
remain unchanged. Logical row accounting is not a physical SQLite page, journal,
disk or aggregate-memory capacity guarantee. The proposed living-owner exception
and reopen controls remain separate from actual owner-death qualification.

## Final source review before the first bounded attempt

Root verified freeze03's 273 indexed files, read its complete delta, and confirmed
the policy/Journal identity guard and replacement controls. The independent
revision reviewer then fully read the 917-line store and found a separate common
REVOKE issue: STATUS could clear its uncertainty, allowing a new START, and
retirement lacked the separate-outbox guard. The reviewer also read the complete
revision02/03 patches, transport, relevant coordinator/policy functions, added
controls, fixture cleanup and result reducers; no candidate execution occurred.

Freeze04 preserves that history and adds a central save/read invariant for common
REVOKE authority, plus guards at RETIRE admission and both settlement paths.
Exactly associated common replies settle only that send's transport possibility.
The new twentieth control covers accepted OPEN, possible REVOKE, reopen/STATUS,
START refusal, no resend, bounded STOP/collection, and retained claims on RETIRE
refusal. Root read the complete exact delta and its note, including the runner's
count/freeze-list changes, and independently verified all 275 indexed files.

Final source-review SHA-256:
`8f02d1dc5dc8724904e29c2fb2656e1c2836d6ae13b68c3fc25b849da3899878`.
Reviewed runner SHA-256:
`d143aa313adbcb941b1460eca057fc08580bca0c4ce7d816f38f930d7b873594`.
The fixed original `python3 -I -B run_checks.py` invocation may now execute its
four bounded commands as a partial native validation. No limit, target, domain,
physical eligibility or public mounting requirement is relaxed. Actual outcomes
belong in the retained attempt and independent audit, not this source review.

## Executed attempts and subsequent corrections

Attempt01 completed both native compilations and the original twelve-case /
638-assertion evaluator, then failed before launching a native fixture. The
fixture supplied service/driver profile labels absent from the unchanged schema.
Root read that schema and the exact revision05 delta: two fixture labels changed,
with a new exclusive attempt02 path and distinct qualification identities. All
277 revised manifest entries were independently checked before execution.

Attempt02 again completed the native prerequisite, then refused the fixture's
GPIO aliases because they included a driver lifecycle atom. Root read the exact
graph footprint, alias, dependency and binding-proof functions and the installed
host contract. The graph correctly requires physical aliases to contain precisely
their physical footprints. A separate installed endpoint slot cannot be hidden
inside that proof. Independent review agreed with the correction's scope.

Revision06 validates exactly two physical claims plus a separate driver lifecycle
slot, bound to the installed driver source digest and every participating alias's
explicit dependency path. Both finite and standing admission use the same resolver
to reserve all three actual claims. PAT identity continues binding the complete
installation; the graph/schema and Journal are unchanged. Existing shared-authority
controls now check exact sets, invalid slots, disconnected aliases, driver identity
and driver/service lifecycle exclusion. Root read the entire delta/note and checked
all 279 manifest entries before the fixed attempt03 invocation.

Attempt03 passed nine host cases / 81 checks and joined ten clean native exits.
The tenth case failed because its capacity setup tried repeated `running` to
`running` transitions. The existing state machine correctly rejects those. Root
requested a test-only ordinary-event fill through the installed writer boundary,
retaining one legal running transition and the original reserved settlement checks.
No state-machine or capacity relaxation is authorized.

The three independent data audits retain exact input/output inventories, held
binary and qualification provenance, process joins and identity absence. They
verify twelve outer reaps and ten native fixture reaps in total, all source/tool
pins and the unchanged 244 public inputs. Each native evaluator passed 12/638;
none of these three attempts passed the complete twenty-case host matrix.

## Final partial native result

Root reviewed revision07's test-only capacity correction: one legal running
transition plus five explicit ordinary control events fills the eight-event
ordinary allocation. The next event rolls back without changing stored status or
events, and four reserved settlement continuations remain available. Production
transitions, event classification and limits are unchanged.

The fourth root execution passed all twenty host cases / 173 checks and the
original twelve-case / 638-assertion native evaluator. Its twenty native fixtures
exited cleanly; four outer commands were reaped. Across the four retained attempts,
the independent audits join sixteen outer and thirty native reaps, observe all
forty-six owned identities absent, and verify 1,264 attempt files. No failed
attempt was overwritten. Public244 remains unchanged.

The host packet is sealed at index SHA-256
`72371ef7752f2e90f6e8b185c125b00b165b8b64ce50d8121680c5a24951249b`,
3,755 files / 71,212,778 bytes. This is partial native validation. It does not
qualify actual owner death, complete partition exhaustion, protected backing
capacity, physical I/O, public mounting or a production provider. The separate
thirteen-cut owner-death plan remains source-only and must join the final tested
revision before implementation.
