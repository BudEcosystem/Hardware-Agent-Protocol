# Verification results

| Scope | Result |
| --- | --- |
| harness01 | Unexecuted; parent target-count guards were found inconsistent during review. |
| harness03 / attempt01-pure21 | Failed at child startup on inherited one-target guards. No methods, SQLite opens or worker ran; scratch was empty. |
| harness04 / attempt01-pure21 | **21 passed**, zero failures/errors/skips, in 4.648 test seconds (6.885 enclosing seconds). Seven new definition controls plus 14 inherited normalization controls. No SQLite opens or worker. |
| harness02 / attempt01-actual | **Passed**, in 121.428 test seconds (127.664 enclosing seconds). Complete actual 30-case worker/import/catalog/application/replay integration. |

The [actual-data audit](../actual-catalog-audit.json) and [aggregate audit](../RESULTS.json) pass without modifying original or copied databases. The original worker is `c21509e368f244f99d8713c829eca5a5`; its evidence import and catalog evaluation are joined to that exact attempt, not a replacement success.

The source authority contains one completed simulated application, one activation and completion, zero cancellations, zero remaining claims and zero board owners. Original-key replay adds no effect. Configuration change inhibits fresh reuse without a novelty result; cold historical replay after session reopening preserves the original receipt and application identity.

The authority database is 16,199,680 bytes with 577,536 bytes of headroom under the original 16 MiB file ceiling. It retains 4,011 references and 2,798 exact bodies. Original worker/group, parent, evidence, retention and effect limits remain unchanged.

The current diagnostic and all preceding catalog failures remain separate failed scopes. This success is not evidence of their precise cause, arbitrary-load reliability, protected control capacity, public service integration or physical qualification. The `executed:false` field in `audit-actual-origin.json` describes that audit's preparation time; its later successful execution is recorded by `actual-catalog-audit.json` and `RESULTS.json`.
