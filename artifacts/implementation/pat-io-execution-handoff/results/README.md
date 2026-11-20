# Durable execution-handoff results

All **50 new control methods pass**: 13 supervisor-authority checks, 32 handoff checks and five additional multi-run history checks. Across all 349 selected methods, **135 have complete passing receipts, 8 have complete failing receipts, and 206 belong to incomplete selections**. Every one of the 30 frozen scopes was invoked once. Partial log checks are reported separately and are not promoted to passing-scope evidence.

The explicit version-2 supervisor ledger has a durable authority identity. The Journal mount pins that actual store and commits an association from reservation and request digests to the original attempt before launch. Only the invocation that creates and associates the attempt can launch it. Replays and recovery preserve the original attempt; missing/replaced stores, mismatched rows, revoked authority and retained corruption do not authorize a replacement. Legacy ledger behavior is preserved by the reviewed metadata hooks and AST comparison. This is an isolated library candidate.

The real new handoff worker persists its association before launch but reaches its original 60-second deadline without a complete return. Its full 30-case inspection and later configuration/session replay are unreached. Eleven states remain; ten can be inspected, showing seven activations, four completions and three cancellations with no observed claims or owners. One incomplete state prevents aggregate effect/claim/owner totals from being known. Its bytes remain untouched. The control-scope replay checks do not substitute for this missing end-to-end result.

The 206-method compatibility batch reaches its original 180-second harness deadline. Its log has 194 completed checks, but lacks the complete child, origin and final compiler/driver receipts. All 614 raw scratch files match their retained copies and inventory. Read-only checks preserve eleven intentionally corrupt records, three diagnostic lease fixtures and three malformed returns. The initial acquisition helper compared path-component ordering with serialized string ordering and failed; its original source and [failure record](../acquisition-timeout-failure01.json) are retained. Correcting only inventory ordering allowed acquisition; no test or retained state was changed.

The spawn-loss worker returns a canonical failed group after 26 cases with `PAT_IO_AUTHORITY_UNEXPECTED_FAILURE`. Its final recorded public call receives the expected `ACCESS_DENIED`; the wrapper does not retain the inner error responsible for the later generic failure. The [trace and source review](../AUTHORITY-FAILURE.md) identify a possible masking path but do not establish its cause in this run. It is not relabeled as a deadline or permission bypass.

The legacy configured-worker variant stops for `SUPERVISOR_RETENTION_UNKNOWN`, before its deadline. All three retained states are inspectable, with two activations, one completion, no cancellation and one remaining claim/board owner. Its scanner does not preserve the underlying exception detail. Terminal file counts cannot establish the transient cause, and process exit does not settle that retained modeled effect.

The inherited canonical-document auditor initially used its preceding stage's fixed result-folder name. Its failed log and original reader are retained; the corrected reader accepts the current result argument and verifies the existing 19-test result without rerunning it. The archive-loss state's first reader also encountered a missing runtime table during interrupted construction. A corrected read-only preflight records that state as uninspected, without creating tables or inferring zero effects. The original failed reader/log remain retained. Any additional retained audit-tool failures appear in the exact summary.

The five multi-run controls use a separate test-only source copy. All 252 preceding project files remain byte-identical; one test module adds coverage for two distinct attempts, reopen replay, forged receipt links, borrowed attempt IDs, regressed timestamps and reordered committed rows. Each control substitutes both launch boundaries. Independent read-only audits join two reservations and 74 input documents to the actual attempts and verify the exact retained mutation or replay.

No original worker, harness, effect, storage or timing bounds were widened. Failed logical runs were not relaunched. Source copy 1 has 252 project/255 frozen files; copy 2 has 253/256. Created worker images use the unchanged production closure of 262 files, including ten supervisor sources and 157 runtime dependencies. Current authorization and admission eligibility remain separate from historical replay. There is no cross-database atomicity or protection against coordinated rollback of both stores.

| Failed worker attempt | Recorded reason | Retained states | Uninspected states |
|---|---|---:|---:|
| [attempt08-owned-handoff](attempt08-failed-owned-handoff/README.md) | SUPERVISOR_DEADLINE | 11 | 1 |
| [attempt24-pwm](attempt24-failed-pwm/README.md) | SUPERVISOR_DEADLINE | 19 | 1 |
| [attempt25-crash-archived](attempt25-failed-crash-archived/README.md) | SUPERVISOR_DEADLINE | 17 | 1 |
| [attempt26-crash-settled](attempt26-failed-crash-settled/README.md) | SUPERVISOR_DEADLINE | 23 | 0 |
| [attempt27-crash-spawned](attempt27-failed-crash-spawned/README.md) | PAT_IO_AUTHORITY_UNEXPECTED_FAILURE | 23 | 0 |
| [attempt28-configured](attempt28-failed-configured/README.md) | SUPERVISOR_RETENTION_UNKNOWN | 3 | 0 |
| [attempt29-authority-owned](attempt29-failed-authority-owned/README.md) | SUPERVISOR_DEADLINE | 15 | 1 |
| [attempt30-reserved-owned](attempt30-failed-reserved-owned/README.md) | SUPERVISOR_DEADLINE | 13 | 1 |

| Attempt | Selected methods | Result | Test seconds |
|---|---:|---|---:|
| [attempt01-authority13](attempt01-passed-authority13/README.md) | 13 | passed | 9.109 |
| [attempt02-handoff06a](attempt02-passed-handoff06a/README.md) | 6 | passed | 72.204 |
| [attempt03-handoff06b](attempt03-passed-handoff06b/README.md) | 6 | passed | 81.373 |
| [attempt04-handoff06c](attempt04-passed-handoff06c/README.md) | 6 | passed | 94.665 |
| [attempt05-handoff06d](attempt05-passed-handoff06d/README.md) | 6 | passed | 150.998 |
| [attempt06-handoff06e](attempt06-passed-handoff06e/README.md) | 6 | passed | 105.713 |
| [attempt07-handoff02](attempt07-passed-handoff02/README.md) | 2 | passed | 84.22 |
| [attempt08-owned-handoff](attempt08-failed-owned-handoff/README.md) | 1 | failed | 106.08 |
| [attempt09-legacy-control206](attempt09-timeout-legacy206/README.md) | 206 | timed_out | unavailable |
| [attempt10-history-clock](attempt10-passed-history-clock/README.md) | 1 | passed | 55.211 |
| [attempt11-history-order](attempt11-passed-history-order/README.md) | 1 | passed | 52.467 |
| [attempt12-history-identity](attempt12-passed-history-identity/README.md) | 1 | passed | 52.316 |
| [attempt13-history-reopen](attempt13-passed-history-reopen/README.md) | 1 | passed | 38.165 |
| [attempt14-history-chain](attempt14-passed-history-chain/README.md) | 1 | passed | 47.91 |
| [attempt15-canonical19](attempt15-passed-canonical19/README.md) | 19 | passed | 1.714 |
| [attempt16-authority32](attempt16-passed-authority32/README.md) | 32 | passed | 70.358 |
| [attempt17-runs15](attempt17-passed-runs15/README.md) | 15 | passed | 102.539 |
| [attempt18-runs14](attempt18-passed-runs14/README.md) | 14 | passed | 114.148 |
| [attempt19-cutoff](attempt19-passed-cutoff/README.md) | 1 | passed | 43.626 |
| [attempt20-pidfd](attempt20-passed-pidfd/README.md) | 1 | passed | 15.758 |
| [attempt21-deadline](attempt21-passed-deadline/README.md) | 1 | passed | 20.639 |
| [attempt22-crash-admitted](attempt22-passed-crash-admitted/README.md) | 1 | passed | 17.988 |
| [attempt23-crash-launching](attempt23-passed-crash-launching/README.md) | 1 | passed | 16.238 |
| [attempt24-pwm](attempt24-failed-pwm/README.md) | 1 | failed | 77.509 |
| [attempt25-crash-archived](attempt25-failed-crash-archived/README.md) | 1 | failed | 75.452 |
| [attempt26-crash-settled](attempt26-failed-crash-settled/README.md) | 1 | failed | 74.39 |
| [attempt27-crash-spawned](attempt27-failed-crash-spawned/README.md) | 1 | failed | 76.577 |
| [attempt28-configured](attempt28-failed-configured/README.md) | 1 | failed | 37.894 |
| [attempt29-authority-owned](attempt29-failed-authority-owned/README.md) | 1 | failed | 79.081 |
| [attempt30-reserved-owned](attempt30-failed-reserved-owned/README.md) | 1 | failed | 80.751 |

See the [exact summary](../RESULTS.json), [design](../DESIGN.md) and [next work](../NEXT.md). Serialized I/O evidence import, configuration-aware promotion, public tooling, protected capacity and aggregate storage enforcement, prompt learning, persistent Arduino applications and actual device/driver/hub providers remain unfinished. The full HMS goal remains active.
