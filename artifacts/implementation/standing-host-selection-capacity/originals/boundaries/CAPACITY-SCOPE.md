# Capacity scope and reachable boundaries

The production checker is unchanged. Its exact row charge is512 bytes plus each
TEXT/BLOB byte,8 per numeric cell and0 per NULL. Its disjoint ceilings are:

```
16 standing owners ×896KiB =14MiB
standing base              =512KiB
16 finite owners ×64KiB    =1MiB
fixed incl metadata        =512KiB
                           -------
                            16MiB
```

The existing source proof bounds one complete legal standing history at903569B,
below its917504B allocation, and one legal finite history at46080B, below65536B.
The full16MiB arithmetic state is consequently a loose accounting ceiling; it
is not automatically reachable through a valid Journal schema and public APIs.
The isolated in-memory model tests the checker's charge interface, not valid
deployment documents, physical storage, schema integrity, admission or recovery.
Given the partition inequality, a state above16MiB must exceed a partition too;
there is no independent total-only overflow within all the partition ceilings.

The real per-edge controls use unchanged public methods and retain original keys:

* Mutation capacity is128 actual retained outbox identities. Explicit abandonment
  is the already implemented authenticated `never_handed_off` settlement, and
  all119+6 abandonment checkpoints are before any possible handoff. No table is
  prefilled by SQL. The common REVOKE receipt has its own exact outbox and is
  required before using the remaining ACK/RETIRE tail; a stopped lifecycle alone
  is not treated as resolution of that separate common outbox.
* Episode capacity is the reachable ordinary-admission edge24 at the maximum
  request32. The next RESUME must refuse before spending the reserved8. This does
  not claim that32 independent public episodes are reachable after that refusal.
* Activation capacity uses actual acquisition/output/feedback plus two complete
  loss witnesses to retain100 current and200 first/final version rows. This is
  the literal synthetic configuration and500ms budget, not arbitrary parameters.
* Owner count is16 retained standing keys plus16 finite owners in the same DB,
  using public prepare/abandon and submit/cancel. It does not populate128 mutations
  for each of the16 owners, nor simultaneously maximize their activation histories.
* Fixed capacity is reached by public namespace issuance. No additional schema,
  private ordinary event fill or artificial data blob substitutes for that writer.
  The control checks a refused additional token is rolled back and then exercises
  maximum-width clock metadata, owner reopen and existing standing continuation.

All quota constants and full original records remain unchanged. The separately
declared32MiB per-file capacity profile is new coverage, not a rerun of failed
1MiB controls under looser caps. Main DB plus a DELETE rollback journal can each
consume the file ceiling; bounded evidence/logs explain a96MiB observed state
ceiling. The current source does not prove all SQLite index/page layouts fit32MiB;
actual attempts must fail and retain evidence if that limit is insufficient.
This is not a reservation of disk/journal space or aggregate memory/CPU.

Simultaneously realizing every legal per-owner record maximum across all32
retained owners would require a dedicated reviewed persistent-peer accumulation
plan under independently enforced per-step bounds. It is not implemented here.
Per-edge passes and the synthetic16MiB model must be reported separately from
that outstanding durable coverage gate.
