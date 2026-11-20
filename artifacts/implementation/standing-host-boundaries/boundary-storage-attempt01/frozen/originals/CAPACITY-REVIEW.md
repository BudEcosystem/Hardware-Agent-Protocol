# Closed-profile logical capacity proof for review

Status: source arithmetic and enforcement review only; no candidate execution.
The unchanged planned ceiling is16MiB. This is a bound on charged retained user
values in this installed SQLite profile, not a reservation of SQLite pages,
rollback journal space, filesystem metadata, physical disk, memory or CPU.
`protectedCapacity`, physical eligibility and public eligibility remain false.

Every Journal business transaction calls `standing_capacity.check` before its
pure final commit checks. It inspects every installed user table under that same
transaction and refuses unknown table schemas. Fixed tables, finite owner
records, standing owner records and standing route/meta records have disjoint
ceilings. Other public finite APIs cannot commit writes outside this gate.
Clock-floor-only commits change only a bounded metadata value; they do not grant
new work or spend a business partition. This requires the existing exclusive
local owner and trusted single-connection service contract; arbitrary SQL from
another same-user process is outside it.

Each row is charged512 bytes plus the UTF-8 byte length of each TEXT value, the
byte length of each BLOB, eight bytes per INTEGER/REAL and zero per NULL. SQL
computes lengths before fetching values. There are fixed row-count and column
limits. SQL keys count again even when duplicated in a document. Index/page
allocation does not use this formula and is deliberately not a physical bound.

The partition inequality is:

```
16 standing owners × 896KiB = 14MiB
standing route/meta          = 512KiB
16 finite owners × 64KiB     = 1MiB
all fixed/registry/PAT tables = 512KiB
                              -------
                              16MiB
```

Unused standing bytes never become capacity another writer family can spend.
Standing admission reserves the full per-owner charge, not merely its initial
row. Sixteen original keys remain retained without LRU eviction. Both finite and
standing common-owner rows remain in the fixed partition after claim release.
Their creation fits before any handoff; loss/recovery does not insert new owners,
instance aliases, resource floors, namespaces, catalog entries or registry rows.
Existing floors are INTEGERs of fixed charged width. Claims can be removed only
through their existing evidence paths.

The512KiB fixed partition separately limits non-`meta` tables to496KiB and reserves
16KiB for Journal metadata. Authority/version are fixed. `last_clock` and
`owner_epoch` have at most16 decimal digits in the original safe-integer domain,
so recovery retains room for their growth even when ordinary fixed writers stop.
Standing route/meta have their own512KiB: route document<=4096 bytes and a single
installation metadata document<=65536 bytes, plus fixed keys/row charge. Updating
rx/tx/fences or owner recovery cannot consume catalog capacity.

For one finite owner the whole-row limits are8192 bytes for its operation,1024
for its sole replay key, and1536 for each of at most24 events. The checker refuses
replay aliases beyond one key per operation, and operation growth beyond8192.
Thus8192+1024+24×1536 =46080 bytes, below65536. The sixteen reserved event slots
are purpose-specific: two each for recovery_unknown, outcome_unknown,
cancel_requested, cancel_ack, reconciled and terminal execution evidence; one
each for resource release, dispute, pre-dispatch rejection and pre-dispatch
cancellation. Eight ordinary events include acceptance and dispatch. Repeated
running/cancel traffic cannot consume another category's settlement slot. A
reconciliation back to running is ordinary traffic, not terminal reconciliation;
running restoration refuses once either future owner-recovery/unknown category
has spent its two records. Existing unknown state can still settle terminally. On
exhaustion, further extension is refused; existing records are not evicted.

For one standing owner, use conservative duplicated-key bounds: ownerID<=50
bytes (generated IDs actually41), all actor/key identifiers<=128, episode key<=64
(actual decimal loss tick/reason is shorter). Integer columns charge8 bytes.
The maximum charged rows are:

| Retained collection | Ceiling | Conservative bytes |
| --- | ---: | ---: |
| Deployment with complete mutable fields |1 × (32768+512+50+4×128+71) |33913 |
| Current activations |100 × (1024+512+50+8) |159400 |
| Immutable first/final activation versions |200 × (1024+512+50+8+8) |320400 |
| Mutation intents including replies |128 × (1536+512+50+8+128+8) |286976 |
| Loss episodes |32 × (1536+512+50+64) |69184 |
| Retained contradictory packets |16 × (1536+512+50+8) |33696 |
| Total | |903569 |

903569 <=917504 bytes (896KiB). Admission caps the initial deployment row at24576
bytes, reserving8192 inside its32768-byte lifetime ceiling for OPEN/last-state
replies, common REVOKE outbox/reply and counter growth. The source bounds two
state/OPEN envelopes to1476 bytes, common REVOKE to565 and scalar growth below256.
Prepared mutation records are capped576 bytes (closed fields bound521); ordinary
reply growth is<=598 and the lost-RETIRE two-page proof<=798, keeping the lifetime
record below1536. Canonical limits are enforced on both inserts and updates.

Ordinary control leaves eight mutation intents and eight episode slots. New
active intervals refuse before consuming the episode reserve. Bounded STOP/
SUSPEND cannot consume the final owed ACK/RETIRE slots; repeated already-stopping
commands and identical refused bodies do not allocate new identities. Unknown
sequence uses a separate single common REVOKE outbox inside the deployment row.
An unknown/disputed effect cannot become retireable merely because capacity is
low. Complete negative controls for reserve edges remain outstanding; arithmetic
and source checks are not execution evidence.


Source revision02 adds no tables, quotas or raised ceilings. A never-handed-off
mutation adds a closed settlement string and longer state label (under64 bytes),
so its prepared576+ordinary-reply598+settlement64 <=1238-byte bound remains below
1536. The original lost-RETIRE bound is unchanged. Prepared OPEN settlement uses
the existing OPEN/state envelope fields, releases only claims, and retains the
owner/original key and allocated floors. Owner epochs now accept exactly the
same safe-integer domain as Journal (up to16 decimal digits), covered by the
existing scalar-growth headroom. Native malformed response evidence uses the
existing16-conflict partition and cannot consume a new unbounded history.
