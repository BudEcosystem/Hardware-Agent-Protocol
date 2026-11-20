# Bound import results

One preparation attempt started no child or worker. Six reviewed scopes executed once: five fixture scopes pass; the real worker/import method reports success but its enclosing scope fails retention. All original bounds and failures remain.

[Exact report](../RESULTS.json), [corrected read-only audit](../audit-results-current.py), [forensic evidence](../forensic01/audit.json), [storage sizing](../deduplication-sizing.json), [review](../REVIEW.md).

| Scope | Original status | Evidence |
|---|---|---|
| [Preparation](../harness01/attempts/attempt01-real-import/result.json) | failed, not started | No test child/worker |
| [harness02](../harness02/attempts/attempt01-real-import/result.json) | failed | Real30-case worker/import/replay method reported success; file retention failed |
| [harness03](../harness03/attempts/attempt01/result.json) | passed | Explicit authority/history/storage fixture passed |
| [harness04](../harness04/attempts/attempt01/result.json) | passed | Explicit authority/history/storage fixture passed |
| [harness05](../harness05/attempts/attempt01/result.json) | passed | Explicit authority/history/storage fixture passed |
| [harness06](../harness06/attempts/attempt01/result.json) | passed | Explicit authority/history/storage fixture passed |
| [harness07](../harness07/attempts/attempt01/result.json) | passed | Explicit authority/history/storage fixture passed |
