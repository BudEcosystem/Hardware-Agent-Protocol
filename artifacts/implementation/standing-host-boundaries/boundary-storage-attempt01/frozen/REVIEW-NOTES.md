# Source review joins

This is new original control/launcher code over unchanged production. There are
260 byte-identical reused project/helper files. The sole changed reused source is
the207-line Guardian; `guardian.patch` records its closed FSIZE profile parameter.
Its original206-line bytes remain in `originals/guardian.py`. No public or sealed
parent file is modified. `BASELINE.json` records independent revalidation of all
3755 host files and775 owner-death files; `source-pins.json` binds those parents,
the244-file public receipt, every exact reuse pair, and20 original provenance
copies. Copied qualification artifacts are audit-only.

The installed native image stays at the original absolute path:

```
/home/bud/Desktop/bud/hms/artifacts/implementation/standing-host-deployment/host-attempt04/standing-host-pipe
```

Its SHA256 is`5ab180cb56526a352691583bbcec4033b85af0c38c6d46057b1f4ae0cd607399`.
The original qualification root remains the adjacent`qualification` directory,
runId`native-standing-original:4`, attemptId`native-standing-attempt:4`. Its
manifest retains the original absolute argv; no copied manifest changes its
run identity. The original executable hash is
`b89d0a1030768932ace1c9c2da5a4a888d0ae7da46a8a77473b2b145293ff842`.

Source-grounded control joins (paths under the unchanged`project/`):

| Existing source | Relevant contract |
| --- | --- |
|`hms/standing_store.py:208`|one shared owner, original key, initial/future standing allocation and monotone route floors |
|`hms/standing_store.py:318`|bounded16 original conflicts; sticky dispute remains even when retention is full |
|`hms/standing_store.py:464`|ordinary120 of128, episode ordinary24 of32, same-body refusal key reuse, loss ACK/RETIRE tail |
|`hms/standing_store.py:633`|actual current/first/final activation records and exact terminal prefix before ACK |
|`hms/standing_store.py:751`|possible RETIRE requires original terminal proof and same-boot empty descriptor before release |
|`hms/standing_store.py:820`|common REVOKE resolves its own outbox only; unrelated possible sends remain unresolved |
|`hms/standing_store.py:872`|explicit never-possible mutation settlement retains original bytes, key and number |
|`hms/standing_store.py:902`|explicit never-possible OPEN settlement; common REVOKE must be absent |
|`hms/standing_endpoint.py:246`|commit possible OPEN before one handoff; post-commit held-evidence veto cannot authorize retry |
|`hms/standing_endpoint.py:316`|collection commit precedes ACK reservation; automatic key includes committed prefix and revision |
|`hms/standing_capacity.py:30`|all-user-table scan,512B row charge,16MiB partition inequality, individual row/owner ceilings |
|`hms/journal.py:294`|business gate before COMMIT, rollback and observed-clock preservation after synchronous exceptions |
|`hms/journal.py:560`|public namespace issuance used to fill fixed capacity, original ordering/token retention |
|`protocol/endpoint/standing.c:240`|ACK is terminal/non-disputed-prefix only |
|`protocol/endpoint/standing.c:267`|refused revision consumes no sequence, exact accepted-body comparison |
|`protocol/endpoint/standing.c:549`|strict commanded-ON budget and actual dispatch cutoff |
|`protocol/endpoint/standing.c:611`|activation identity bound before installed dispatch |
|`tests/standing_host_pipe.c:140`|finite private native controls, no new opcodes or modified image |
|`tests/standing_host_fixture.py:57`|held native image descriptor and directly owned child; source installation/physical2+actual3 claims |

The immutable first draft of six new/changed files is preserved under
`history/draft01`; it is not execution evidence. Later source revisions retain
an explicit diff before the final input inventory. Review of controls does not
mean they passed: state assertions, timing, SQLite fit and all result/evidence
joins remain subject to the first reviewed bounded attempt and independent audit.

Known coverage limits remain explicit: per-edge public records are not a
simultaneous32-owner maximum database; in-memory direct SQL is only charge-model
testing; pre/post COMMIT exceptions and SQLITE_FULL do not qualify real media,
power loss, every compound recovery failure or arbitrary partial-frame death.
ProtectedCapacity, public eligibility and physical eligibility remain false.
