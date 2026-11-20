# Fixture topology profile correction and distinct retry provenance

Status: source-only correction after root attempt01 failed. All275 freeze04
inputs and its source review are preserved under `history/source-freeze04`;
attempt01 outputs remain unchanged. Root reported clean owner close/empty and
four outer reaps, successful native builds and the original12-case/638-assertion
evaluator. Host controls failed before launching a native fixture.

The fixture supplied an invented `native-standing-pipe/0.1` profile for service
and driver nodes. The unchanged resource-topology schema requires respectively
`synthetic-service/0.1` and `synthetic-io-hub/0.1` (schema lines238–243 and287–297).
The fixture now declares those existing synthetic profiles. Driver source/image
identity and the actual owned native pipe remain separately bound as before.
No schema, production guard, control count, or resource cap is relaxed.

The reviewed launcher now exclusively creates `host-attempt02`, verifies the
retained attempt01 result hash before/after commands, and uses distinct original
qualification `runId` and `attemptId` values ending in`:2`. Its intent accurately
records previous candidate execution and that this revision has not yet run.
The old reservation/receipt/manifest and failed attempt are never overwritten or
reused as the new evaluator attempt. All twenty proposed host cases remain.
`revision-05.patch` is the exact delta; actual owner-death and other completion
gates remain outstanding. No retry was executed during this source correction.
